"""HTTP-сборщик контекста из Moodle mod_assign и mod_poasassignment."""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal
from urllib.parse import parse_qs, unquote, urlencode, urljoin, urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup, Tag

from context_wizard.plugins import PluginContext, Stage, StagedTool

_MAX_REDIRECTS: Final = 10
_DEFAULT_MAX_FILE_BYTES: Final = 100 * 1024 * 1024
_DEFAULT_MAX_TOTAL_BYTES: Final = 500 * 1024 * 1024
_USER_AGENT: Final = "ContextWizard-Moodle/0.1"
_SITES_FILENAME: Final = "moodle.sites.json"
_SITES_EXAMPLE_FILENAME: Final = "moodle.sites.example.json"

type ActivityKind = Literal["assign", "poasassignment"]


class MoodleError(RuntimeError):
    """Безопасная для показа пользователю ошибка Moodle-инструмента."""


@dataclass(frozen=True)
class SiteConfig:
    id: str
    name: str
    base_url: str
    username_env: str = "MOODLE_USERNAME"
    password_env: str = "MOODLE_PASSWORD"
    allow_http: bool = False

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> SiteConfig:
        site_id = _required_string(raw, "id")
        name = _required_string(raw, "name")
        allow_http = raw.get("allow_http", False)
        if not isinstance(allow_http, bool):
            raise MoodleError(f"sites[{site_id!r}].allow_http должен быть boolean")
        base_url = normalize_base_url(_required_string(raw, "url"), allow_http=allow_http)
        return cls(
            id=site_id,
            name=name,
            base_url=base_url,
            username_env=_optional_string(raw, "username_env", "MOODLE_USERNAME"),
            password_env=_optional_string(raw, "password_env", "MOODLE_PASSWORD"),
            allow_http=allow_http,
        )

    @property
    def origin(self) -> str:
        split = urlsplit(self.base_url)
        return urlunsplit((split.scheme, split.netloc, "", "", ""))


@dataclass(frozen=True)
class MoodleLink:
    id: str
    name: str
    url: str


@dataclass(frozen=True)
class MoodleActivity:
    id: str
    name: str
    url: str
    kind: ActivityKind


@dataclass(frozen=True)
class Submission:
    user_id: str
    student_name: str
    file_urls: tuple[str, ...]
    online_text: str = ""
    task_url: str = ""


@dataclass(frozen=True)
class LoginForm:
    action: str
    fields: dict[str, str]


def normalize_base_url(raw_url: str, *, allow_http: bool = False) -> str:
    """Нормализовать URL Moodle и запретить небезопасные/неоднозначные формы."""
    split = urlsplit(raw_url.strip())
    allowed_schemes = {"https"} | ({"http"} if allow_http else set())
    if split.scheme.lower() not in allowed_schemes:
        raise MoodleError("URL Moodle должен использовать HTTPS")
    if not split.hostname or split.username or split.password:
        raise MoodleError("URL Moodle должен содержать host и не должен содержать credentials")
    if split.query or split.fragment:
        raise MoodleError("Базовый URL Moodle не должен содержать query или fragment")
    path = split.path.rstrip("/")
    return urlunsplit((split.scheme.lower(), split.netloc.lower(), path, "", ""))


def parse_login_form(html: str, page_url: str) -> LoginForm:
    """Извлечь стандартную форму входа Moodle со всеми hidden-полями."""
    soup = BeautifulSoup(html, "html.parser")
    form = soup.select_one("form#login") or soup.select_one("form[action*='/login/index.php']")
    if not isinstance(form, Tag):
        raise MoodleError("На странице Moodle не найдена стандартная форма входа")
    action = urljoin(page_url, str(form.get("action") or page_url))
    fields: dict[str, str] = {}
    for node in form.select("input[name]"):
        if isinstance(node, Tag) and str(node.get("type", "")).lower() == "hidden":
            fields[str(node["name"])] = str(node.get("value", ""))
    return LoginForm(action=action, fields=fields)


def is_login_page(html: str, url: str) -> bool:
    split = urlsplit(url)
    if split.path.rstrip("/").endswith("/login/index.php"):
        return True
    soup = BeautifulSoup(html, "html.parser")
    return bool(soup.select_one("form#login input[name='username']"))


def parse_courses(html: str, page_url: str) -> list[MoodleLink]:
    return _parse_links(html, page_url, expected_path="/course/view.php")


def parse_assignments(html: str, page_url: str) -> list[MoodleActivity]:
    """Извлечь поддерживаемые задания в порядке страницы курса."""
    soup = BeautifulSoup(html, "html.parser")
    result: dict[tuple[ActivityKind, str], MoodleActivity] = {}
    paths: dict[str, ActivityKind] = {
        "/mod/assign/view.php": "assign",
        "/mod/poasassignment/view.php": "poasassignment",
    }
    for link in soup.select("a[href]"):
        if not isinstance(link, Tag):
            continue
        target = urljoin(page_url, str(link.get("href", "")))
        split = urlsplit(target)
        kind: ActivityKind | None = None
        for path, candidate_kind in paths.items():
            if split.path.endswith(path):
                kind = candidate_kind
                break
        item_id = _query_value(target, "id")
        name = link.get_text(" ", strip=True)
        if kind and item_id and name:
            result.setdefault(
                (kind, item_id),
                MoodleActivity(id=item_id, name=name, url=target, kind=kind),
            )
    return list(result.values())


def parse_submissions(html: str, page_url: str) -> tuple[list[Submission], list[str]]:
    """Извлечь видимые отправленные работы и страницы пагинации grading table."""
    soup = BeautifulSoup(html, "html.parser")
    submissions: dict[str, Submission] = {}
    for row in soup.select("table tbody tr"):
        if not isinstance(row, Tag):
            continue
        identity = _submission_identity(row, page_url)
        if identity is None:
            continue
        user_id, student_name = identity
        file_urls = tuple(
            dict.fromkeys(
                urljoin(page_url, str(link.get("href", "")))
                for link in row.select("a[href*='pluginfile.php']")
                if isinstance(link, Tag)
                and "assignsubmission_file" in str(link.get("href", ""))
            )
        )
        online_node = row.select_one(
            ".assignsubmission_onlinetext, [data-region='onlinetext'], "
            "[class*='assignsubmission_onlinetext']"
        )
        online_text = (
            online_node.get_text("\n", strip=True) if isinstance(online_node, Tag) else ""
        )
        if file_urls or online_text:
            submissions[user_id] = Submission(
                user_id=user_id,
                student_name=student_name,
                file_urls=file_urls,
                online_text=online_text,
            )

    assignment_id = _query_value(page_url, "id")
    pages: list[str] = []
    for link in soup.select(".paging a[href], [data-region='paging-control-container'] a[href]"):
        if not isinstance(link, Tag):
            continue
        target = urljoin(page_url, str(link.get("href", "")))
        split = urlsplit(target)
        query = parse_qs(split.query)
        if (
            split.path.endswith("/mod/assign/view.php")
            and query.get("id") == [assignment_id]
            and query.get("action") == ["grading"]
            and len(query.get("page", [])) == 1
            and query["page"][0].isdigit()
        ):
            pages.append(target)
    return list(submissions.values()), list(dict.fromkeys(pages))


def parse_poas_submissions(html: str, page_url: str) -> list[Submission]:
    """Извлечь последнюю видимую попытку каждого студента из POAS."""
    soup = BeautifulSoup(html, "html.parser")
    submissions: dict[str, Submission] = {}
    for row in soup.select("table.poasassignment-table tbody tr"):
        if not isinstance(row, Tag):
            continue
        identity = _submission_identity(row, page_url)
        if identity is None:
            continue
        user_id, student_name = identity
        file_urls = tuple(
            dict.fromkeys(
                urljoin(page_url, str(link.get("href", "")))
                for link in row.select("a[href*='pluginfile.php']")
                if isinstance(link, Tag)
                and "/mod_poasassignment/submissionfiles/"
                in urlsplit(urljoin(page_url, str(link.get("href", "")))).path
            )
        )
        response_cell = row.select_one("td.c3")
        online_text = ""
        if isinstance(response_cell, Tag) and not file_urls:
            online_text = response_cell.get_text("\n", strip=True)
        task_url = ""
        for link in row.select("td.c2 a[href]"):
            if not isinstance(link, Tag):
                continue
            candidate = urljoin(page_url, str(link.get("href", "")))
            if _query_value(candidate, "page") == "taskview":
                task_url = candidate
                break
        if file_urls or online_text:
            # POAS submissions обычно уже содержит одну актуальную строку на студента.
            # Если версия модуля вернула несколько попыток, последняя строка побеждает.
            submissions[user_id] = Submission(
                user_id=user_id,
                student_name=student_name,
                file_urls=file_urls,
                online_text=online_text,
                task_url=task_url,
            )
    return list(submissions.values())


def parse_task_text(html: str, kind: ActivityKind) -> str:
    """Извлечь общее assign-описание или индивидуальный вариант POAS."""
    soup = BeautifulSoup(html, "html.parser")
    if kind == "poasassignment":
        table = soup.select_one("#region-main table") or soup.select_one("table")
        if not isinstance(table, Tag):
            return ""
        parts: list[str] = []
        for row in table.select("tr"):
            cells = row.find_all(["th", "td"], recursive=False)
            if len(cells) >= 2:
                label = cells[0].get_text(" ", strip=True).rstrip(":")
                value = cells[1].get_text("\n", strip=True)
                if label and value:
                    parts.append(f"{label}: {value}")
        return "\n\n".join(parts)
    node = soup.select_one(
        ".activity-description, .assignintro, #intro, [data-region='activity-information']"
    )
    return node.get_text("\n", strip=True) if isinstance(node, Tag) else ""


class MoodleClient:
    """Синхронный HTTP-клиент Moodle с проверкой origin и ручными redirect-ами."""

    def __init__(
        self,
        site: SiteConfig,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 20.0,
    ) -> None:
        self.site = site
        self._client = httpx.Client(
            headers={"User-Agent": _USER_AGENT},
            timeout=timeout,
            follow_redirects=False,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def site_url(self, relative: str) -> str:
        return urljoin(f"{self.site.base_url}/", relative.lstrip("/"))

    def validate_url(self, url: str) -> str:
        absolute = urljoin(f"{self.site.base_url}/", url)
        split = urlsplit(absolute)
        origin = urlunsplit((split.scheme.lower(), split.netloc.lower(), "", "", ""))
        if origin != self.site.origin:
            raise MoodleError("Moodle попытался перейти на URL другого origin")
        return absolute

    def restore_cookies(self, raw: object) -> None:
        if not isinstance(raw, list):
            return
        host = urlsplit(self.site.base_url).hostname or ""
        for item in raw:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            value = item.get("value")
            domain = item.get("domain")
            path = item.get("path", "/")
            if not all(isinstance(value_, str) for value_ in (name, value, domain, path)):
                continue
            assert isinstance(name, str)
            assert isinstance(value, str)
            assert isinstance(domain, str)
            assert isinstance(path, str)
            if not _cookie_domain_matches(host, domain):
                continue
            self._client.cookies.set(
                name,
                value,
                domain=domain,
                path=path,
            )

    def export_cookies(self) -> list[dict[str, object]]:
        host = urlsplit(self.site.base_url).hostname or ""
        return [
            {
                "name": cookie.name,
                "value": cookie.value,
                "domain": cookie.domain,
                "path": cookie.path,
                "expires": cookie.expires,
                "secure": cookie.secure,
            }
            for cookie in self._client.cookies.jar
            if _cookie_domain_matches(host, cookie.domain)
        ]

    def is_authenticated(self) -> bool:
        response = self.request("GET", self.site_url("my/"))
        return response.status_code < 400 and not is_login_page(response.text, str(response.url))

    def login(self, username: str, password: str) -> None:
        login_url = self.site_url("login/index.php")
        page = self.request("GET", login_url)
        form = parse_login_form(page.text, str(page.url))
        data = dict(form.fields)
        data.update({"username": username, "password": password})
        response = self.request("POST", form.action, data=data)
        if response.status_code >= 400 or is_login_page(response.text, str(response.url)):
            raise MoodleError("Moodle отклонил логин или пароль")

    def list_courses(self) -> list[MoodleLink]:
        dashboard = self.request("GET", self.site_url("my/"))
        self._require_authenticated(dashboard)
        courses = parse_courses(dashboard.text, str(dashboard.url))
        if courses:
            return courses
        fallback = self.request("GET", self.site_url("course/index.php?mycourses=1"))
        self._require_authenticated(fallback)
        return parse_courses(fallback.text, str(fallback.url))

    def list_assignments(self, course: MoodleLink) -> list[MoodleActivity]:
        response = self.request("GET", course.url)
        self._require_authenticated(response)
        return parse_assignments(response.text, str(response.url))

    def list_submissions(self, assignment: MoodleActivity) -> list[Submission]:
        if assignment.kind == "poasassignment":
            page_url = _with_query(assignment.url, page="submissions")
            response = self.request("GET", page_url)
            self._require_authenticated(response)
            return parse_poas_submissions(response.text, str(response.url))
        return self._list_assign_submissions(assignment)

    def task_text(self, assignment: MoodleActivity, submission: Submission) -> str:
        url = submission.task_url if assignment.kind == "poasassignment" else assignment.url
        if not url:
            return ""
        response = self.request("GET", url)
        self._require_authenticated(response)
        return parse_task_text(response.text, assignment.kind)

    def _list_assign_submissions(self, assignment: MoodleActivity) -> list[Submission]:
        first_url = _with_query(assignment.url, action="grading", perpage="20")
        pending = [first_url]
        seen: set[str] = set()
        submissions: dict[str, Submission] = {}
        while pending:
            page_url = pending.pop(0)
            if page_url in seen:
                continue
            if len(seen) >= 100:
                raise MoodleError("Слишком много страниц списка работ Moodle")
            seen.add(page_url)
            response = self.request("GET", page_url)
            self._require_authenticated(response)
            page_submissions, pages = parse_submissions(response.text, str(response.url))
            for submission in page_submissions:
                submissions[submission.user_id] = submission
            pending.extend(self.validate_url(page) for page in pages if page not in seen)
        return list(submissions.values())

    def download_submission(
        self,
        submission: Submission,
        target_dir: Path,
        *,
        max_file_bytes: int = _DEFAULT_MAX_FILE_BYTES,
        max_total_bytes: int = _DEFAULT_MAX_TOTAL_BYTES,
    ) -> list[Path]:
        target_dir.mkdir(parents=True, exist_ok=True)
        downloaded: list[Path] = []
        total = 0
        for index, file_url in enumerate(submission.file_urls, start=1):
            destination, size = self._download_file(
                file_url,
                target_dir,
                fallback=f"submission-{index}",
                max_file_bytes=max_file_bytes,
                max_total_bytes=max_total_bytes - total,
            )
            total += size
            downloaded.append(destination)
        return downloaded

    def request(
        self,
        method: str,
        url: str,
        *,
        data: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        current_url = self.validate_url(url)
        current_method = method.upper()
        for _ in range(_MAX_REDIRECTS + 1):
            response = self._client.request(current_method, current_url, data=data)
            if not response.is_redirect:
                return response
            location = response.headers.get("location")
            if not location:
                return response
            current_url = self.validate_url(urljoin(str(response.url), location))
            if response.status_code in {301, 302, 303} and current_method != "GET":
                current_method = "GET"
                data = None
        raise MoodleError("Moodle вернул слишком много redirect-ов")

    def _download_file(
        self,
        url: str,
        target_dir: Path,
        *,
        fallback: str,
        max_file_bytes: int,
        max_total_bytes: int,
    ) -> tuple[Path, int]:
        current = self.validate_url(url)
        for _ in range(_MAX_REDIRECTS + 1):
            with self._client.stream("GET", current) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        response.raise_for_status()
                    current = self.validate_url(urljoin(str(response.url), location or ""))
                    continue
                response.raise_for_status()
                filename = _response_filename(response, fallback=fallback)
                destination = _unique_destination(target_dir, filename)
                size = 0
                try:
                    with destination.open("wb") as output:
                        for chunk in response.iter_bytes():
                            size += len(chunk)
                            if size > max_file_bytes or size > max_total_bytes:
                                raise MoodleError(
                                    "Файлы работы превышают настроенный лимит размера"
                                )
                            output.write(chunk)
                except Exception:
                    destination.unlink(missing_ok=True)
                    raise
                return destination, size
        raise MoodleError("Moodle вернул слишком много redirect-ов при скачивании")

    @staticmethod
    def _require_authenticated(response: httpx.Response) -> None:
        if response.status_code >= 400:
            raise MoodleError(f"Moodle вернул HTTP {response.status_code}")
        if is_login_page(response.text, str(response.url)):
            raise MoodleError("Сессия Moodle истекла; запустите инструмент повторно")


class MoodleTool(StagedTool):
    """Проектный ContextWizard-плагин выбора и скачивания одной работы Moodle."""

    id = "moodle"
    initial = "site"

    def stages(self) -> list[Stage]:
        return [
            Stage("site", self._select_site),
            Stage("auth", self._authenticate),
            Stage("course", self._select_course),
            Stage("assignment", self._select_assignment),
            Stage("submission", self._select_submission),
            Stage("download", self._download),
            Stage("session", self._persist_session),
        ]

    def _select_site(self, context: PluginContext) -> Mapping[str, object]:
        sites = _load_sites(context.root / _SITES_FILENAME)
        labels = _unique_labels([(site.name, site.id) for site in sites])
        selected = str(context.ask_option("Выберите Moodle", labels))
        site_id = labels[selected]
        site = next(site for site in sites if site.id == site_id)
        context.scratch["moodle.site"] = site
        return {"MOODLE_SITE": site.name}

    def _authenticate(self, context: PluginContext) -> None:
        site = _scratch(context, "moodle.site", SiteConfig)
        client = MoodleClient(site)
        sessions = context.cache.setdefault("sessions", {})
        if not isinstance(sessions, dict):
            sessions = {}
            context.cache["sessions"] = sessions
        cached = sessions.get(site.id)
        if isinstance(cached, dict) and cached.get("origin") == site.origin:
            client.restore_cookies(cached.get("cookies"))
        authenticated = client.is_authenticated()
        if authenticated:
            context.notify(f"Moodle: используется сохранённая сессия {site.name}")
        else:
            username = _credential(context, site.username_env)
            if not username:
                username = str(context.ask_input(f"Логин для {site.name}"))
            password = _credential(context, site.password_env)
            if not password:
                password = context.ask_secret(f"Пароль для {site.name}")
            client.login(username, password)
        self._remember_session(context, site, client)
        context.scratch["moodle.client"] = client

    def _select_course(self, context: PluginContext) -> Mapping[str, object]:
        client = _scratch(context, "moodle.client", MoodleClient)
        course = _choose_link(context, "Выберите курс", client.list_courses(), "курсов")
        context.scratch["moodle.course"] = course
        return {"MOODLE_COURSE": course.name}

    def _select_assignment(self, context: PluginContext) -> Mapping[str, object]:
        client = _scratch(context, "moodle.client", MoodleClient)
        course = _scratch(context, "moodle.course", MoodleLink)
        assignment = _choose_link(
            context,
            "Выберите задание",
            client.list_assignments(course),
            "заданий assign или poasassignment",
        )
        context.scratch["moodle.assignment"] = assignment
        return {"MOODLE_ASSIGNMENT": assignment.name}

    def _select_submission(self, context: PluginContext) -> Mapping[str, object]:
        client = _scratch(context, "moodle.client", MoodleClient)
        assignment = _scratch(context, "moodle.assignment", MoodleActivity)
        context.notify("Moodle: получаю список отправленных работ…")
        submissions = client.list_submissions(assignment)
        if not submissions:
            raise MoodleError("В задании не найдено отправленных работ")
        labels = _unique_labels(
            [(submission.student_name, submission.user_id) for submission in submissions]
        )
        selected = str(context.ask_option("Выберите студента", labels))
        user_id = labels[selected]
        submission = next(item for item in submissions if item.user_id == user_id)
        context.scratch["moodle.submission"] = submission
        task_text = client.task_text(assignment, submission)
        return {
            "MOODLE_STUDENT": submission.student_name,
            "MOODLE_TASK_TEXT": task_text,
            "MOODLE_SUBMISSION_TEXT": submission.online_text,
        }

    def _download(self, context: PluginContext) -> Mapping[str, object]:
        client = _scratch(context, "moodle.client", MoodleClient)
        site = _scratch(context, "moodle.site", SiteConfig)
        assignment = _scratch(context, "moodle.assignment", MoodleActivity)
        submission = _scratch(context, "moodle.submission", Submission)
        if not submission.file_urls:
            raise MoodleError("У выбранной работы нет файловых вложений")
        target_base = (
            context.root
            / ".tmp"
            / "moodle"
            / "downloads"
            / _safe_component(site.id)
            / _safe_component(assignment.id)
            / _safe_component(submission.user_id)
        )
        target_base.mkdir(parents=True, exist_ok=True)
        target = Path(tempfile.mkdtemp(prefix="attempt-", dir=target_base))
        context.notify("Moodle: скачиваю файлы выбранной попытки…")
        files = client.download_submission(submission, target)
        path = files[0] if len(files) == 1 else target
        return {"MOODLE_SUBMISSION_PATH": path}

    def _persist_session(self, context: PluginContext) -> None:
        client = _scratch(context, "moodle.client", MoodleClient)
        site = _scratch(context, "moodle.site", SiteConfig)
        self._remember_session(context, site, client)
        client.close()

    @staticmethod
    def _remember_session(
        context: PluginContext,
        site: SiteConfig,
        client: MoodleClient,
    ) -> None:
        sessions = context.cache.setdefault("sessions", {})
        if not isinstance(sessions, dict):
            sessions = {}
            context.cache["sessions"] = sessions
        sessions[site.id] = {"origin": site.origin, "cookies": client.export_cookies()}


def _parse_links(html: str, page_url: str, *, expected_path: str) -> list[MoodleLink]:
    soup = BeautifulSoup(html, "html.parser")
    result: dict[str, MoodleLink] = {}
    for link in soup.select("a[href]"):
        if not isinstance(link, Tag):
            continue
        target = urljoin(page_url, str(link.get("href", "")))
        split = urlsplit(target)
        if not split.path.endswith(expected_path):
            continue
        item_id = _query_value(target, "id")
        name = link.get_text(" ", strip=True)
        if item_id and name:
            result.setdefault(item_id, MoodleLink(id=item_id, name=name, url=target))
    return list(result.values())


def _submission_identity(row: Tag, page_url: str) -> tuple[str, str] | None:
    profiles = row.select("a[href*='/user/view.php'], a[href*='/user/profile.php']")
    profile = next(
        (
            item
            for item in profiles
            if isinstance(item, Tag) and item.get_text(" ", strip=True)
        ),
        None,
    )
    if not isinstance(profile, Tag):
        return None
    profile_url = urljoin(page_url, str(profile.get("href", "")))
    user_id = _query_value(profile_url, "id") or str(row.get("data-userid", ""))
    student_name = profile.get_text(" ", strip=True)
    return (user_id, student_name) if user_id and student_name else None


def _query_value(url: str, name: str) -> str:
    values = parse_qs(urlsplit(url).query).get(name, [])
    return values[0] if values else ""


def _with_query(url: str, **values: str) -> str:
    split = urlsplit(url)
    query = parse_qs(split.query)
    query.update({key: [value] for key, value in values.items()})
    encoded = urlencode([(key, item) for key, items in query.items() for item in items])
    return urlunsplit((split.scheme, split.netloc, split.path, encoded, split.fragment))


def _response_filename(response: httpx.Response, *, fallback: str) -> str:
    disposition = response.headers.get("content-disposition", "")
    encoded = re.search(r"filename\*=UTF-8''([^;]+)", disposition, re.IGNORECASE)
    plain = re.search(r'filename="?([^";]+)', disposition, re.IGNORECASE)
    candidate = unquote(encoded.group(1)) if encoded else plain.group(1) if plain else ""
    if not candidate:
        candidate = unquote(Path(urlsplit(str(response.url)).path).name) or fallback
    return _safe_component(candidate)


def _safe_component(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")
    return cleaned[:180] or "unnamed"


def _unique_destination(directory: Path, filename: str) -> Path:
    candidate = directory / filename
    stem, suffix = candidate.stem, candidate.suffix
    index = 2
    while candidate.exists():
        candidate = directory / f"{stem}-{index}{suffix}"
        index += 1
    return candidate


def _cookie_domain_matches(host: str, domain: str) -> bool:
    normalized = domain.lstrip(".").lower()
    return host.lower() == normalized or host.lower().endswith(f".{normalized}")


def _required_string(raw: Mapping[str, object], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise MoodleError(f"Настройка Moodle {key!r} должна быть непустой строкой")
    return value.strip()


def _optional_string(raw: Mapping[str, object], key: str, default: str) -> str:
    value = raw.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise MoodleError(f"Настройка Moodle {key!r} должна быть непустой строкой")
    return value.strip()


def _load_sites(path: Path) -> list[SiteConfig]:
    try:
        raw_sites: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise MoodleError(
            f"Файл сайтов Moodle не найден: {path}. "
            f"Скопируйте {_SITES_EXAMPLE_FILENAME} как {_SITES_FILENAME}"
        ) from error
    except json.JSONDecodeError as error:
        raise MoodleError(
            f"Некорректный JSON в {path} "
            f"(строка {error.lineno}, столбец {error.colno}): {error.msg}"
        ) from error
    except (OSError, UnicodeError) as error:
        raise MoodleError(f"Не удалось прочитать файл сайтов Moodle {path}: {error}") from error

    if not isinstance(raw_sites, list) or not raw_sites:
        raise MoodleError(f"{_SITES_FILENAME} должен содержать непустой JSON-массив")
    sites: list[SiteConfig] = []
    ids: set[str] = set()
    for raw in raw_sites:
        if not isinstance(raw, dict):
            raise MoodleError(f"Каждый элемент {_SITES_FILENAME} должен быть объектом")
        site = SiteConfig.from_mapping(raw)
        if site.id in ids:
            raise MoodleError(f"Повторяющийся id Moodle-сайта: {site.id!r}")
        ids.add(site.id)
        sites.append(site)
    return sites


def _unique_labels(items: Sequence[tuple[str, str]]) -> dict[str, str]:
    counts: dict[str, int] = {}
    labels: dict[str, str] = {}
    for name, item_id in items:
        counts[name] = counts.get(name, 0) + 1
        label = name if counts[name] == 1 else f"{name} · {item_id}"
        while label in labels:
            label = f"{label} · {item_id}"
        labels[label] = item_id
    return labels


def _choose_link[T: MoodleLink | MoodleActivity](
    context: PluginContext,
    question: str,
    items: Sequence[T],
    empty_name: str,
) -> T:
    if not items:
        raise MoodleError(f"Moodle не вернул доступных {empty_name}")
    labels = _unique_labels([(item.name, item.id) for item in items])
    selected = str(context.ask_option(question, labels))
    item_id = labels[selected]
    return next(item for item in items if item.id == item_id)


def _credential(context: PluginContext, name: str) -> str:
    return context.env.get(name, "") or os.environ.get(name, "")


def _scratch[T](context: PluginContext, key: str, expected: type[T]) -> T:
    value = context.scratch.get(key)
    if not isinstance(value, expected):
        raise MoodleError(f"Внутреннее состояние Moodle потеряно: {key}")
    return value


__all__ = [
    "LoginForm",
    "MoodleClient",
    "MoodleError",
    "MoodleActivity",
    "MoodleLink",
    "MoodleTool",
    "SiteConfig",
    "Submission",
    "is_login_page",
    "normalize_base_url",
    "parse_assignments",
    "parse_courses",
    "parse_login_form",
    "parse_poas_submissions",
    "parse_submissions",
    "parse_task_text",
]
