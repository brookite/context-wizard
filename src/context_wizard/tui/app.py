"""Textual-приложение и мост к синхронному конвейеру.

Конвейер (:class:`Collector`) синхронный и дёргает UI пошагово, а Textual — асинхронный.
Мост: конвейер выполняется в отдельном потоке-воркере, а методы UI переносят вызовы
модальных экранов на поток приложения через ``call_from_thread`` и блокируются на
результате.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import cast

from textual.app import App, ComposeResult
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from context_wizard.output import RichPromptDTO
from context_wizard.surveys import SurveyElement
from context_wizard.tui.screens import (
    MissingVarsScreen,
    MultiSelectScreen,
    OptionSelectScreen,
    PromptSelectScreen,
    SecretInputScreen,
    SurveyInputScreen,
)
from context_wizard.ui import WizardAborted

Pipeline = Callable[[], RichPromptDTO]


class WizardApp(App[None]):
    """Корневое TUI-приложение сборщика."""

    CSS = """
    #dialog {
        width: 80%;
        max-width: 100;
        height: auto;
        padding: 1 2;
        border: round $primary;
        background: $surface;
    }
    .title { text-style: bold; margin-bottom: 1; }
    .hint { color: $text-muted; }
    .error { color: $error; }
    #status { padding: 1 2; }
    """

    def __init__(self) -> None:
        super().__init__()
        self._pipeline: Pipeline | None = None
        self.result: RichPromptDTO | None = None
        self.error: BaseException | None = None
        self.aborted: bool = False

    def set_pipeline(self, pipeline: Pipeline) -> None:
        """Задать функцию запуска конвейера (выполнится в потоке-воркере)."""
        self._pipeline = pipeline

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("Сборка контекста…", id="status")
        yield Footer()

    def on_mount(self) -> None:
        self.run_worker(self._run_pipeline, thread=True, name="pipeline")

    def _run_pipeline(self) -> None:
        if self._pipeline is None:
            self.call_from_thread(self.exit)
            return
        try:
            self.result = self._pipeline()
        except WizardAborted:
            self.aborted = True
        except BaseException as exc:  # noqa: BLE001 — пробрасываем наружу после выхода
            self.error = exc
        finally:
            self.call_from_thread(self.exit)


class TextualUI:
    """Реализация :class:`WizardUI` поверх :class:`WizardApp`."""

    def __init__(self, app: WizardApp) -> None:
        self._app = app

    def select_prompt(self, prompts: list[Path]) -> Path:
        return cast(
            Path,
            self._app.call_from_thread(self._app.push_screen_wait, PromptSelectScreen(prompts)),
        )

    def ask_input(self, element: SurveyElement) -> str:
        return cast(
            str,
            self._app.call_from_thread(self._app.push_screen_wait, SurveyInputScreen(element)),
        )

    def ask_secret(self, question: str, *, hint: str | None = None) -> str:
        result = cast(
            "str | None",
            self._app.call_from_thread(
                self._app.push_screen_wait, SecretInputScreen(question, hint)
            ),
        )
        if result is None:
            raise WizardAborted("Ввод секрета отменён пользователем")
        return result

    def ask_option(self, element: SurveyElement) -> str:
        result = cast(
            "str | None",
            self._app.call_from_thread(self._app.push_screen_wait, OptionSelectScreen(element)),
        )
        if result is None:
            raise WizardAborted("Выбор отменён пользователем")
        return result

    def ask_multi(self, element: SurveyElement) -> list[str]:
        return cast(
            "list[str]",
            self._app.call_from_thread(self._app.push_screen_wait, MultiSelectScreen(element)),
        )

    def resolve_missing(self, missing: list[str]) -> set[str]:
        result = cast(
            "set[str] | None",
            self._app.call_from_thread(self._app.push_screen_wait, MissingVarsScreen(missing)),
        )
        if result is None:
            raise WizardAborted("Сборка отменена пользователем")
        return result

    def notify(self, message: str) -> None:
        self._app.call_from_thread(self._app.notify, message)

    def push_screen(self, screen: object) -> object:
        return self._app.call_from_thread(
            self._app.push_screen_wait, cast(Screen[object], screen)
        )

    @property
    def app(self) -> object | None:
        return self._app
