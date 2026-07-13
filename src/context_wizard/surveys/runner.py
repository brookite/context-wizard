"""Прохождение опросника через абстрактный «опрашивающий» (TUI или тест).

Логика опросника отделена от Textual: раннер работает с любым объектом, реализующим
протокол :class:`SurveyPrompter`. TUI предоставляет реальную реализацию, тесты — фейковую.
"""

from __future__ import annotations

from collections.abc import Callable, MutableMapping
from typing import Protocol

from context_wizard.surveys.model import Survey, SurveyElement
from context_wizard.surveys.validators import coerce, validate_input

ResolveOptions = Callable[[SurveyElement, dict[str, object]], list[str]]
OnAnswer = Callable[[SurveyElement, object, dict[str, object]], None]
ShouldAsk = Callable[[SurveyElement, dict[str, object]], bool]


class SurveyPrompter(Protocol):
    """Источник ответов на элементы опросника."""

    def ask_input(self, element: SurveyElement) -> str:
        """Свободный ввод строки."""
        ...

    def ask_option(self, element: SurveyElement) -> str:
        """Выбор одного варианта из ``element.answer.options``."""
        ...

    def ask_multi(self, element: SurveyElement) -> list[str]:
        """Выбор нескольких вариантов из ``element.answer.options``."""
        ...


def run_survey(
    survey: Survey,
    prompter: SurveyPrompter,
    *,
    cache: MutableMapping[str, object] | None = None,
    resolve_options: ResolveOptions | None = None,
    on_answer: OnAnswer | None = None,
    should_ask: ShouldAsk | None = None,
) -> dict[str, object]:
    """Пройти опросник и вернуть словарь ``varName -> значение``.

    Для элементов с ``cached=True`` значение берётся из ``cache`` (если есть) и
    сохраняется туда после ответа.

    Хуки (для плагинов, обрабатывающих статический опросник поэтапно):

    :param resolve_options: перед вопросом типа ``option``/``multi selection`` вычисляет
        динамический список вариантов из уже собранных ответов (например, курсы из Moodle).
    :param on_answer: вызывается после каждого ответа — для фетча/ветвления/побочных эффектов.
    :param should_ask: если возвращает ``False`` — элемент пропускается (условные вопросы).
    """
    answers: dict[str, object] = {}
    for element in survey:
        if should_ask is not None and not should_ask(element, answers):
            continue

        key = element.var_name
        if element.cached and cache is not None and key in cache:
            answers[key] = cache[key]
            continue

        if resolve_options is not None and element.answer.type in ("option", "multi selection"):
            element.answer.options = list(resolve_options(element, answers))

        value = _ask(element, prompter)
        answers[key] = value

        if element.cached and cache is not None:
            cache[key] = value
        if on_answer is not None:
            on_answer(element, value, answers)
    return answers


def _ask(element: SurveyElement, prompter: SurveyPrompter) -> object:
    answer_type = element.answer.type
    if answer_type == "input":
        return validate_input(prompter.ask_input(element), element)
    if answer_type == "option":
        return coerce(prompter.ask_option(element), element.answer.datatype)
    selected = prompter.ask_multi(element)
    return [coerce(item, element.answer.datatype) for item in selected]
