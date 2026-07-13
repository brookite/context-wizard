"""Абстракция пользовательского интерфейса сборщика.

Конвейер (:mod:`context_wizard.app`) взаимодействует с пользователем только через
протокол :class:`WizardUI`. Это отделяет логику от Textual: реальный TUI реализует
протокол, а тесты подставляют headless-реализацию.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from context_wizard.surveys import SurveyElement


class WizardAborted(Exception):
    """Пользователь прервал сборку."""


class WizardUI(Protocol):
    """Взаимодействие сборщика с пользователем."""

    def select_prompt(self, prompts: list[Path]) -> Path:
        """Выбрать промпт из списка. Кидает :class:`WizardAborted` при отмене."""
        ...

    def ask_input(self, element: SurveyElement) -> str:
        """Свободный ввод строки для элемента опросника."""
        ...

    def ask_secret(self, question: str, *, hint: str | None = None) -> str:
        """Скрытый ввод секрета без сохранения в опрос или кэш."""
        ...

    def ask_option(self, element: SurveyElement) -> str:
        """Выбор одного варианта."""
        ...

    def ask_multi(self, element: SurveyElement) -> list[str]:
        """Выбор нескольких вариантов."""
        ...

    def resolve_missing(self, missing: list[str]) -> set[str]:
        """Разрешить недостающие переменные.

        Возвращает имена, которые пользователь согласился пропустить (развернуть в
        пустую строку). Кидает :class:`WizardAborted`, если пользователь отменяет сборку.
        """
        ...

    def notify(self, message: str) -> None:
        """Показать информационное сообщение/предупреждение."""
        ...

    def push_screen(self, screen: object) -> object:
        """Низкоуровневый доступ: показать произвольный экран/виджет и вернуть результат.

        Используется плагинами для собственного TUI. В неинтерактивных реализациях
        может кидать ``NotImplementedError``.
        """
        ...

    @property
    def app(self) -> object | None:
        """Ссылка на приложение (Textual App) или ``None`` вне TUI-режима."""
        ...
