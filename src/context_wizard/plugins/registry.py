"""Реестр плагинов по идентификатору."""

from __future__ import annotations

from context_wizard.plugins.base import AnswerTarget, ExternalTool


class PluginRegistry:
    """Хранит классы плагинов, найденные при обнаружении, и выдаёт их по id."""

    def __init__(self) -> None:
        self._external: dict[str, type[ExternalTool]] = {}
        self._answer: dict[str, type[AnswerTarget]] = {}

    def register_external(self, plugin: type[ExternalTool]) -> None:
        self._external[plugin.id] = plugin

    def register_answer(self, plugin: type[AnswerTarget]) -> None:
        self._answer[plugin.id] = plugin

    def external_ids(self) -> list[str]:
        return sorted(self._external)

    def answer_ids(self) -> list[str]:
        return sorted(self._answer)

    def create_external(self, plugin_id: str) -> ExternalTool:
        """Создать экземпляр внешнего инструмента по id."""
        if plugin_id not in self._external:
            raise KeyError(f"Внешний инструмент не найден: {plugin_id!r}")
        return self._external[plugin_id]()

    def create_answer(self, plugin_id: str) -> AnswerTarget:
        """Создать экземпляр приёмника ответа по id."""
        if plugin_id not in self._answer:
            raise KeyError(f"Инструмент передачи ответа не найден: {plugin_id!r}")
        return self._answer[plugin_id]()

    def has_external(self, plugin_id: str) -> bool:
        return plugin_id in self._external

    def has_answer(self, plugin_id: str) -> bool:
        return plugin_id in self._answer
