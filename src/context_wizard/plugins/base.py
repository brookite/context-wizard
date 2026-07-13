"""Интерфейсы плагинов и богатый контекст выполнения.

Плагины могут взаимодействовать с пользователем на трёх уровнях (см. :class:`PluginContext`):

1. высокоуровневые абстракции над опросом (``ask_input``/``ask_option``/``ask_multi``/
   ``run_survey``/``load_survey``);
2. загрузка статического опросника + хуки (``load_survey`` + ``run_survey(resolve_options=…)``);
3. низкоуровневый прямой TUI (``push_screen`` / ``app``).

Многоэтапные плагины наследуют :class:`StagedTool` (см. :mod:`context_wizard.plugins.staging`),
тривиальные — реализуют один метод :meth:`ExternalTool.run`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping, MutableMapping
from dataclasses import dataclass, field
from pathlib import Path

from context_wizard.output.dto import RichPromptDTO
from context_wizard.state import VariableStore
from context_wizard.surveys import (
    Answer,
    AnswerType,
    DataType,
    Survey,
    SurveyElement,
    coerce,
    load_survey,
    run_survey,
    validate_input,
)
from context_wizard.surveys.runner import OnAnswer, ResolveOptions, ShouldAsk
from context_wizard.ui import WizardUI

_SURVEY_CACHE_KEY = "_survey"


@dataclass
class PluginContext:
    """Контекст выполнения плагина: данные, состояние и каналы взаимодействия."""

    root: Path
    store: VariableStore
    ui: WizardUI | None = None
    use_fs: bool = True
    settings: dict[str, object] = field(default_factory=dict)
    env: dict[str, str] = field(default_factory=dict)
    scratch: dict[str, object] = field(default_factory=dict)
    cache: MutableMapping[str, object] = field(default_factory=dict)

    # -- Высокий уровень: абстракции над опросом ------------------------

    def ask_input(
        self,
        question: str,
        *,
        datatype: DataType = "string",
        hint: str | None = None,
        regex: str | None = None,
        max_length: int | None = None,
    ) -> object:
        """Спросить свободный ввод и вернуть значение нужного типа."""
        element = SurveyElement(
            question=question,
            var_name="_",
            answer=Answer(
                type="input",
                datatype=datatype,
                hint=hint,
                validation_regex=regex,
                max_input_length=max_length,
            ),
        )
        return validate_input(self._ui().ask_input(element), element)

    def ask_secret(self, question: str, *, hint: str | None = None) -> str:
        """Спросить секрет с маскированным вводом, не добавляя его в кэш или store."""
        return self._ui().ask_secret(question, hint=hint)

    def ask_option(
        self,
        question: str,
        options: Iterable[str],
        *,
        datatype: DataType = "string",
    ) -> object:
        """Спросить выбор одного варианта."""
        element = self._choice_element(question, options, "option", datatype)
        return coerce(self._ui().ask_option(element), datatype)

    def ask_multi(
        self,
        question: str,
        options: Iterable[str],
        *,
        datatype: DataType = "string",
    ) -> list[object]:
        """Спросить выбор нескольких вариантов."""
        element = self._choice_element(question, options, "multi selection", datatype)
        return [coerce(item, datatype) for item in self._ui().ask_multi(element)]

    def run_survey(
        self,
        survey: Survey,
        *,
        resolve_options: ResolveOptions | None = None,
        on_answer: OnAnswer | None = None,
        should_ask: ShouldAsk | None = None,
    ) -> dict[str, object]:
        """Прогнать опросник (динамический или загруженный) через тот же TUI, с хуками."""
        survey_cache = self.cache.setdefault(_SURVEY_CACHE_KEY, {})
        assert isinstance(survey_cache, dict)
        return run_survey(
            survey,
            self._ui(),
            cache=survey_cache,
            resolve_options=resolve_options,
            on_answer=on_answer,
            should_ask=should_ask,
        )

    def load_survey(self, path: Path) -> Survey:
        """Загрузить статический опросник (JSON) и вернуть модель; предупреждения — в notify."""
        survey, warnings = load_survey(path, self.root)
        for warning in warnings:
            self.notify(warning)
        return survey

    def notify(self, message: str) -> None:
        """Показать сообщение пользователю (если UI доступен)."""
        if self.ui is not None:
            self.ui.notify(message)

    # -- Низкий уровень: прямой TUI ------------------------------------

    def push_screen(self, screen: object) -> object:
        """Показать собственный экран/виджет плагина и вернуть его результат."""
        return self._ui().push_screen(screen)

    @property
    def app(self) -> object | None:
        """Ссылка на Textual App (или ``None`` вне TUI-режима)."""
        return None if self.ui is None else self.ui.app

    # -- Внутреннее -----------------------------------------------------

    def _ui(self) -> WizardUI:
        if self.ui is None:
            raise RuntimeError("Взаимодействие недоступно: UI не подключён к контексту плагина")
        return self.ui

    def _choice_element(
        self,
        question: str,
        options: Iterable[str],
        answer_type: AnswerType,
        datatype: DataType,
    ) -> SurveyElement:
        return SurveyElement(
            question=question,
            var_name="_",
            answer=Answer(type=answer_type, datatype=datatype, options=list(options)),
        )


class ExternalTool(ABC):
    """Внешний инструмент сбора контекста (плагин).

    Наследники задают атрибут класса ``id`` и реализуют :meth:`run`. Для многоэтапных
    сценариев удобнее наследовать :class:`context_wizard.plugins.staging.StagedTool`.
    """

    id: str = ""

    @abstractmethod
    def run(self, context: PluginContext) -> Mapping[str, object]:
        """Собрать данные и вернуть переменные для добавления в хранилище."""
        raise NotImplementedError


class AnswerTarget(ABC):
    """Инструмент передачи готового промпта (плагин-приёмник)."""

    id: str = ""

    @abstractmethod
    def deliver(self, dto: RichPromptDTO, context: PluginContext) -> None:
        """Доставить готовый промпт (в агента, файл, API и т.п.)."""
        raise NotImplementedError


__all__ = ["AnswerTarget", "ExternalTool", "PluginContext"]
