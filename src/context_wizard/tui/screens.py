"""Модальные экраны TUI: выбор промпта, опросник, разрешение переменных."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from textual import events
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.fuzzy import Matcher
from textual.screen import ModalScreen
from textual.style import Style
from textual.widgets import Button, Input, Label, OptionList, SelectionList, Static
from textual.widgets.option_list import Option
from textual.widgets.selection_list import Selection

from context_wizard.surveys import AnswerValidationError, SurveyElement, validate_input


@dataclass(frozen=True)
class _Choice[T]:
    label: str
    value: T


class FuzzySelectScreen[T](ModalScreen[T | None]):
    """Универсальный выбор одного варианта с fuzzy-поиском в стиле fzf."""

    def __init__(self, title: str, choices: Sequence[tuple[str, T]]) -> None:
        super().__init__()
        self._title = title
        self._choices = [_Choice(label, value) for label, value in choices]
        self._filtered = list(self._choices)

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(self._title, classes="title")
            yield Input(placeholder="fuzzy-поиск…", id="filter")
            yield OptionList(*(Option(choice.label) for choice in self._choices), id="list")

    def on_mount(self) -> None:
        option_list = self.query_one("#list", OptionList)
        option_list.highlighted = 0 if self._choices else None
        self.call_after_refresh(lambda: self.query_one("#filter", Input).focus())

    def _populate(self, query: str) -> None:
        option_list = self.query_one("#list", OptionList)
        option_list.clear_options()

        if query:
            matcher = Matcher(query, match_style=Style(bold=True, underline=True))
            ranked = [
                (matcher.match(choice.label), index, choice)
                for index, choice in enumerate(self._choices)
            ]
            ranked.sort(key=lambda item: (-item[0], item[1]))
            self._filtered = [choice for score, _, choice in ranked if score > 0]
            for choice in self._filtered:
                option_list.add_option(Option(matcher.highlight(choice.label)))
        else:
            self._filtered = list(self._choices)
            for choice in self._filtered:
                option_list.add_option(Option(choice.label))

        option_list.highlighted = 0 if self._filtered else None

    def on_input_changed(self, event: Input.Changed) -> None:
        self._populate(event.value)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(self._filtered[event.option_index].value)

    def on_key(self, event: events.Key) -> None:
        option_list = self.query_one("#list", OptionList)
        if event.key == "escape":
            event.stop()
            self.dismiss(None)
        elif event.key == "up":
            event.stop()
            option_list.action_cursor_up()
        elif event.key == "down":
            event.stop()
            option_list.action_cursor_down()
        elif event.key == "enter" and option_list.highlighted is not None:
            event.stop()
            self.dismiss(self._filtered[option_list.highlighted].value)


class PromptSelectScreen(FuzzySelectScreen[Path]):
    """Выбор промпта из списка с fuzzy-поиском."""

    def __init__(self, prompts: list[Path]) -> None:
        super().__init__("Выберите промпт", [(prompt.name, prompt) for prompt in prompts])


class SurveyInputScreen(ModalScreen[str]):
    """Свободный ввод значения для элемента опросника с валидацией."""

    def __init__(self, element: SurveyElement) -> None:
        super().__init__()
        self._element = element

    def compose(self) -> ComposeResult:
        answer = self._element.answer
        with Vertical(id="dialog"):
            yield Label(self._element.question, classes="title")
            if answer.hint:
                yield Static(answer.hint, classes="hint")
            yield Input(placeholder=answer.hint or "", id="value")
            yield Static("", id="error", classes="error")

    def on_mount(self) -> None:
        self.call_after_refresh(lambda: self.query_one("#value", Input).focus())

    def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value
        try:
            validate_input(value, self._element)
        except AnswerValidationError as exc:
            self.query_one("#error", Static).update(str(exc))
            return
        self.dismiss(value)


class SecretInputScreen(ModalScreen[str | None]):
    """Скрытый ввод секрета, который не попадает в модель опросника или кэш."""

    def __init__(self, question: str, hint: str | None = None) -> None:
        super().__init__()
        self._question = question
        self._hint = hint

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(self._question, classes="title")
            if self._hint:
                yield Static(self._hint, classes="hint")
            yield Input(placeholder=self._hint or "", password=True, id="value")

    def on_mount(self) -> None:
        self.call_after_refresh(lambda: self.query_one("#value", Input).focus())

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            event.stop()
            self.dismiss(None)


class OptionSelectScreen(FuzzySelectScreen[str]):
    """Выбор одного варианта из опросника с fuzzy-поиском."""

    def __init__(self, element: SurveyElement) -> None:
        options = list(element.answer.options)
        super().__init__(element.question, [(option, option) for option in options])


class MultiSelectScreen(ModalScreen[list[str]]):
    """Выбор нескольких вариантов из списка (чекбоксы)."""

    def __init__(self, element: SurveyElement) -> None:
        super().__init__()
        self._element = element
        self._options = list(element.answer.options)

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(self._element.question, classes="title")
            yield SelectionList[str](
                *(Selection(option, option) for option in self._options),
                id="list",
            )
            yield Button("Подтвердить", variant="primary", id="confirm")

    def on_mount(self) -> None:
        self.call_after_refresh(lambda: self.query_one("#list", SelectionList).focus())

    def on_button_pressed(self, event: Button.Pressed) -> None:
        selected = list(self.query_one("#list", SelectionList).selected)
        self.dismiss(selected)


class MissingVarsScreen(ModalScreen["set[str] | None"]):
    """Разрешение недостающих переменных: какие пропустить (развернуть в пустоту)."""

    def __init__(self, missing: list[str]) -> None:
        super().__init__()
        self._missing = missing

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Недостаёт переменных. Отметьте те, что можно пропустить:", classes="title")
            yield SelectionList[str](
                *(Selection(name, name, True) for name in self._missing),
                id="list",
            )
            yield Button("Пропустить выбранные", variant="primary", id="skip")
            yield Button("Отменить сборку", variant="error", id="abort")

    def on_mount(self) -> None:
        self.call_after_refresh(lambda: self.query_one("#list", SelectionList).focus())

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "abort":
            self.dismiss(None)
            return
        selected = set(self.query_one("#list", SelectionList).selected)
        self.dismiss(selected)
