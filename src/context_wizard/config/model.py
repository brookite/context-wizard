"""Модель дескриптора проекта ``setup.toml``."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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
    answer_targets: list[AnswerTargetConfig] | None = None
    """Упорядоченный список инструментов передачи ответа."""
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

    @model_validator(mode="after")
    def _validate_answer_targets(self) -> SetupConfig:
        if self.answer_target is not None and self.answer_targets is not None:
            raise ValueError("answer_target и answer_targets нельзя задавать одновременно")
        targets = self.answer_target_configs
        if self.answer_targets is not None and not targets:
            raise ValueError("answer_targets не может быть пустым списком")
        ids = [target.id for target in targets]
        if len(ids) != len(set(ids)):
            raise ValueError("id в answer_targets не должны повторяться")
        return self

    @property
    def plugin_dirs(self) -> list[str]:
        """Каталоги плагинов в едином списковом представлении и заданном порядке."""
        if isinstance(self.plugins_dir, str):
            return [self.plugins_dir]
        return list(self.plugins_dir)

    @property
    def answer_target_configs(self) -> list[AnswerTargetConfig]:
        """Приёмники ответа в едином списковом представлении и заданном порядке."""
        if self.answer_targets is not None:
            return list(self.answer_targets)
        if self.answer_target is not None:
            return [self.answer_target]
        return []
