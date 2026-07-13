"""Модель дескриптора проекта ``setup.toml``."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AnswerTargetConfig(BaseModel):
    """Настройки инструмента передачи ответа (плагина-приёмника)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    """Идентификатор плагина-приёмника."""
    use_fs: bool = True
    """Может ли приёмник читать файловую систему (влияет на inline и пути)."""
    settings: dict[str, Any] = Field(default_factory=dict)
    """Произвольные настройки, передаваемые плагину."""


class SetupConfig(BaseModel):
    """Дескриптор проекта ``setup.toml``. Все поля опциональны."""

    model_config = ConfigDict(extra="forbid")

    external_tool: str | None = None
    """Идентификатор рекомендованного внешнего инструмента сбора контекста."""
    answer_target: AnswerTargetConfig | None = None
    """Инструмент передачи ответа. Если не задан — вывод в stdout/файл."""
    vars_storage: str | None = None
    """Путь (внутри проекта) к файлу глобальных переменных (.json или .env)."""
    plugins_dir: str | list[str] = "plugins"
    """Каталог или упорядоченный список каталогов локальных плагинов."""
    tool_settings: dict[str, Any] = Field(default_factory=dict)
    """Произвольные настройки для внешнего инструмента."""

    @field_validator("plugins_dir")
    @classmethod
    def _validate_plugins_dir(cls, value: str | list[str]) -> str | list[str]:
        paths = [value] if isinstance(value, str) else value
        if not paths:
            raise ValueError("plugins_dir не может быть пустым списком")
        if any(not path.strip() for path in paths):
            raise ValueError("пути в plugins_dir должны быть непустыми строками")
        return value

    @property
    def plugin_dirs(self) -> list[str]:
        """Каталоги плагинов в едином списковом представлении и заданном порядке."""
        if isinstance(self.plugins_dir, str):
            return [self.plugins_dir]
        return list(self.plugins_dir)
