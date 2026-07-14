from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import httpx
import pytest

from context_wizard.config import load_setup
from context_wizard.plugins import PluginContext, builtin_plugins_dir, discover_plugins
from context_wizard.state import VariableStore

PLUGIN_PATH = (
    Path(__file__).parent.parent / "examples" / "moodle" / "plugins" / "moodle.py"
)


def _load_plugin() -> ModuleType:
    spec = importlib.util.spec_from_file_location("test_moodle_plugin_module", PLUGIN_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


moodle = _load_plugin()


def test_moodle_example_config_discovers_project_plugin():
    root = PLUGIN_PATH.parent.parent
    config = load_setup(root)
    registry = discover_plugins(
        builtin_plugins_dir(), *(root / path for path in config.plugin_dirs)
    )
    assert config.external_tool == "moodle"
    assert config.tool_settings == {}
    assert registry.has_external("moodle")


def test_load_sites_from_local_json(tmp_path):
    path = tmp_path / "moodle.sites.json"
    path.write_text(
        """[
          {
            "id": "main",
            "name": "Main Moodle",
            "url": "https://moodle.example",
            "username_env": "LOCAL_USER",
            "password_env": "LOCAL_PASSWORD"
          }
        ]""",
        encoding="utf-8",
    )

    sites = moodle._load_sites(path)

    assert len(sites) == 1
    assert sites[0].id == "main"
    assert sites[0].base_url == "https://moodle.example"
    assert sites[0].username_env == "LOCAL_USER"
    assert sites[0].password_env == "LOCAL_PASSWORD"


def test_load_sites_missing_file_has_copy_instruction(tmp_path):
    with pytest.raises(moodle.MoodleError, match="moodle.sites.example.json"):
        moodle._load_sites(tmp_path / "moodle.sites.json")


def test_load_sites_reports_malformed_json_position(tmp_path):
    path = tmp_path / "moodle.sites.json"
    path.write_text('[{"id": ]', encoding="utf-8")

    with pytest.raises(moodle.MoodleError, match=r"строка 1, столбец \d+"):
        moodle._load_sites(path)


@pytest.mark.parametrize("content", ["{}", "[]", "[1]"])
def test_load_sites_rejects_invalid_root_or_items(tmp_path, content):
    path = tmp_path / "moodle.sites.json"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(moodle.MoodleError):
        moodle._load_sites(path)


def test_load_sites_rejects_duplicate_ids(tmp_path):
    path = tmp_path / "moodle.sites.json"
    path.write_text(
        """[
          {"id": "same", "name": "First", "url": "https://first.example"},
          {"id": "same", "name": "Second", "url": "https://second.example"}
        ]""",
        encoding="utf-8",
    )

    with pytest.raises(moodle.MoodleError, match="Повторяющийся id"):
        moodle._load_sites(path)


def test_normalize_base_url_rejects_unsafe_forms():
    assert moodle.normalize_base_url("https://Moodle.Example/learn/") == (
        "https://moodle.example/learn"
    )
    with pytest.raises(moodle.MoodleError):
        moodle.normalize_base_url("http://moodle.example")
    with pytest.raises(moodle.MoodleError):
        moodle.normalize_base_url("https://user:pass@moodle.example")


def test_parse_login_form_preserves_hidden_fields():
    html = """
    <form id="login" action="/moodle/login/index.php" method="post">
      <input type="hidden" name="logintoken" value="token-123">
      <input type="hidden" name="anchor" value="">
      <input name="username"><input type="password" name="password">
    </form>
    """
    form = moodle.parse_login_form(html, "https://example.edu/moodle/login/index.php")
    assert form.action == "https://example.edu/moodle/login/index.php"
    assert form.fields == {"logintoken": "token-123", "anchor": ""}


def test_parse_courses_and_assignments_deduplicates_links():
    dashboard = """
    <a href="/course/view.php?id=10">Алгоритмы</a>
    <a href="/course/view.php?id=10#section-1">Алгоритмы повторно</a>
    <a href="/course/view.php?id=20">Архитектура ЭВМ</a>
    """
    courses = moodle.parse_courses(dashboard, "https://moodle.example/my/")
    assert [(item.id, item.name) for item in courses] == [
        ("10", "Алгоритмы"),
        ("20", "Архитектура ЭВМ"),
    ]

    course = """
    <a href="/mod/assign/view.php?id=30">Лабораторная №1</a>
    <a href="/mod/poasassignment/view.php?id=31">Индивидуальная лабораторная</a>
    <a href="/mod/quiz/view.php?id=40">Тест</a>
    """
    assignments = moodle.parse_assignments(course, "https://moodle.example/course/view.php?id=10")
    assert [(item.id, item.name, item.kind) for item in assignments] == [
        ("30", "Лабораторная №1", "assign"),
        ("31", "Индивидуальная лабораторная", "poasassignment"),
    ]


def test_parse_submissions_extracts_files_text_and_pagination():
    html = """
    <table><tbody><tr data-userid="7">
      <td><a href="/user/view.php?id=7&amp;course=10">Иван Петров</a></td>
      <td class="assignsubmission_file">
        <a href="/pluginfile.php/1/assignsubmission_file/submission_files/2/main.py">main.py</a>
      </td>
      <td class="assignsubmission_onlinetext"><p>Комментарий студента</p></td>
    </tr></tbody></table>
    <nav class="paging">
      <a href="/mod/assign/view.php?id=30&amp;action=grading&amp;page=1">2</a>
    </nav>
    <a href="/mod/assign/view.php?id=30&amp;action=lock&amp;page=0&amp;sesskey=secret">
      Запретить изменять ответ
    </a>
    """
    submissions, pages = moodle.parse_submissions(
        html, "https://moodle.example/mod/assign/view.php?id=30&action=grading"
    )
    assert len(submissions) == 1
    assert submissions[0].user_id == "7"
    assert submissions[0].student_name == "Иван Петров"
    assert submissions[0].online_text == "Комментарий студента"
    assert submissions[0].file_urls == (
        "https://moodle.example/pluginfile.php/1/assignsubmission_file/"
        "submission_files/2/main.py",
    )
    assert pages == [
        "https://moodle.example/mod/assign/view.php?id=30&action=grading&page=1"
    ]


def test_parse_assign_pagination_rejects_mutating_and_unrelated_links():
    html = """
    <div class="paging">
      <a href="/mod/assign/view.php?id=30&amp;action=grading&amp;page=1">2</a>
      <a href="/mod/assign/view.php?id=30&amp;action=lock&amp;page=1&amp;sesskey=x">Lock</a>
      <a href="/mod/assign/view.php?id=99&amp;action=grading&amp;page=1">Other</a>
    </div>
    """
    _, pages = moodle.parse_submissions(
        html, "https://moodle.example/mod/assign/view.php?id=30&action=grading"
    )
    assert pages == [
        "https://moodle.example/mod/assign/view.php?id=30&action=grading&page=1"
    ]


def test_parse_poas_submissions_keeps_latest_attempt_and_task():
    html = (
        '<table class="poasassignment-table"><tbody><tr>'
        '<td class="c1"><a href="/user/profile.php?id=7&amp;course=10">'
        "Иван Петров</a></td>"
        '<td class="c2"><a href="/mod/poasassignment/view.php?'
        'id=31&amp;page=taskview&amp;taskid=1">Вариант</a></td>'
        '<td class="c3"><a href="/pluginfile.php/1/mod_poasassignment/'
        'submissionfiles/10/old.zip">old.zip</a></td></tr><tr>'
        '<td class="c1"><a href="/user/profile.php?id=7&amp;course=10">'
        "Иван Петров</a></td>"
        '<td class="c2"><a href="/mod/poasassignment/view.php?'
        'id=31&amp;page=taskview&amp;taskid=2">Вариант</a></td>'
        '<td class="c3"><a href="/pluginfile.php/1/mod_poasassignment/'
        'submissionfiles/11/new.zip">new.zip</a></td>'
        "</tr></tbody></table>"
    )
    submissions = moodle.parse_poas_submissions(
        html, "https://moodle.example/mod/poasassignment/view.php?id=31&page=submissions"
    )
    assert len(submissions) == 1
    assert submissions[0].file_urls == (
        "https://moodle.example/pluginfile.php/1/mod_poasassignment/"
        "submissionfiles/11/new.zip",
    )
    assert "taskid=2" in submissions[0].task_url


def test_parse_poas_task_text_extracts_individual_variant():
    html = """
    <main id="region-main"><table>
      <tr><td>Название задания:</td><td>Вариант №4</td></tr>
      <tr><td>Описание задания:</td><td>Решить задачу.</td></tr>
    </table></main>
    """
    assert moodle.parse_task_text(html, "poasassignment") == (
        "Название задания: Вариант №4\n\nОписание задания: Решить задачу."
    )


def test_client_login_posts_token_and_reuses_session_cookie():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/login/index.php" and request.method == "GET":
            return httpx.Response(
                200,
                request=request,
                text=(
                    '<form id="login" action="/login/index.php">'
                    '<input type="hidden" name="logintoken" value="abc">'
                    '<input name="username"><input name="password" type="password">'
                    "</form>"
                ),
            )
        if request.url.path == "/login/index.php" and request.method == "POST":
            return httpx.Response(
                303,
                request=request,
                headers={"location": "/my/", "set-cookie": "MoodleSession=session; Path=/"},
            )
        return httpx.Response(200, request=request, text="<main>Dashboard</main>")

    site = moodle.SiteConfig("test", "Test", "https://moodle.example")
    client = moodle.MoodleClient(site, transport=httpx.MockTransport(handler))
    client.login("teacher", "password")

    posted = requests[1].content.decode()
    assert "logintoken=abc" in posted
    assert "username=teacher" in posted
    assert "password=password" in posted
    assert client.export_cookies()[0]["name"] == "MoodleSession"


def test_tool_reuses_cached_session_without_requesting_credentials(monkeypatch, tmp_path):
    class NoCredentialsUI:
        def __init__(self):
            self.notes: list[str] = []

        def select_prompt(self, prompts):
            return prompts[0]

        def ask_input(self, element):
            raise AssertionError("cached session must not request a login")

        def ask_secret(self, question, *, hint=None):
            raise AssertionError("cached session must not request a password")

        def ask_option(self, element):
            raise AssertionError("option prompt is not expected")

        def ask_multi(self, element):
            raise AssertionError("multi prompt is not expected")

        def resolve_missing(self, missing):
            return set(missing)

        def notify(self, message):
            self.notes.append(message)

        def push_screen(self, screen):
            raise NotImplementedError

        @property
        def app(self):
            return None

    class CachedClient:
        def __init__(self):
            self.restored = False

        def restore_cookies(self, raw):
            self.restored = bool(raw)

        def is_authenticated(self):
            return self.restored

        def export_cookies(self):
            return [{"name": "MoodleSession", "value": "refreshed"}]

    client = CachedClient()
    monkeypatch.setattr(moodle, "MoodleClient", lambda site: client)
    ui = NoCredentialsUI()
    site = moodle.SiteConfig("test", "Test", "https://moodle.example")
    context = PluginContext(
        root=tmp_path,
        store=VariableStore(),
        ui=ui,
        cache={
            "sessions": {
                "test": {
                    "origin": "https://moodle.example",
                    "cookies": [{"name": "MoodleSession", "value": "cached"}],
                }
            }
        },
    )
    context.scratch["moodle.site"] = site

    moodle.MoodleTool()._authenticate(context)

    assert client.restored is True
    assert any("сохранённая сессия" in note for note in ui.notes)


def test_client_rejects_cross_origin_redirect():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            302,
            request=request,
            headers={"location": "https://attacker.example/steal"},
        )

    site = moodle.SiteConfig("test", "Test", "https://moodle.example")
    client = moodle.MoodleClient(site, transport=httpx.MockTransport(handler))
    with pytest.raises(moodle.MoodleError, match="origin"):
        client.request("GET", "https://moodle.example/my/")


def test_assign_client_uses_small_pages_and_never_follows_action_links():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.params.get("page") == "1":
            return httpx.Response(200, request=request, text="<table></table>")
        return httpx.Response(
            200,
            request=request,
            text=(
                '<div class="paging">'
                '<a href="/mod/assign/view.php?id=30&amp;action=grading&amp;page=1">2</a>'
                "</div>"
                '<a href="/mod/assign/view.php?'
                'id=30&amp;action=lock&amp;page=0&amp;sesskey=secret">Lock</a>'
            ),
        )

    site = moodle.SiteConfig("test", "Test", "https://moodle.example")
    client = moodle.MoodleClient(site, transport=httpx.MockTransport(handler))
    activity = moodle.MoodleActivity(
        "30", "Lab", "https://moodle.example/mod/assign/view.php?id=30", "assign"
    )
    assert client.list_submissions(activity) == []
    assert len(requests) == 2
    assert requests[0].url.params.get("perpage") == "20"
    assert all(request.url.params.get("action") == "grading" for request in requests)


def test_download_sanitizes_filename_and_enforces_limit(tmp_path):
    body = b"print('hello')"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            content=body,
            headers={"content-disposition": 'attachment; filename="../main.py"'},
        )

    site = moodle.SiteConfig("test", "Test", "https://moodle.example")
    client = moodle.MoodleClient(site, transport=httpx.MockTransport(handler))
    submission = moodle.Submission(
        "7",
        "Student",
        (
            "https://moodle.example/pluginfile.php/1/"
            "mod_poasassignment/submissionfiles/11/main.py",
        ),
    )
    files = client.download_submission(submission, tmp_path)
    assert files == [tmp_path / "_main.py"]
    assert files[0].read_bytes() == body

    with pytest.raises(moodle.MoodleError, match="лимит"):
        client.download_submission(submission, tmp_path / "small", max_file_bytes=2)
    assert not list((tmp_path / "small").iterdir())
