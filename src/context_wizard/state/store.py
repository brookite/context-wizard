"""Хранилище переменных со слоями-источниками и приоритетом.

Приоритет «интерактив побеждает»: значение из более позднего/интерактивного источника
перекрывает значение из более раннего. Порядок (по возрастанию приоритета):
глобальные vars → env/ промпта → опросник → внешний инструмент → runtime (CLI-оверрайды).
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import IntEnum


class Source(IntEnum):
    """Источник значения переменной. Большее значение — выше приоритет."""

    GLOBAL = 10
    """Глобальные vars.json / vars.env проекта."""
    PROMPT_ENV = 20
    """Файл env/<prompt>.{env,json} для конкретного промпта."""
    SURVEY = 30
    """Ответы кастомного опросника."""
    EXTERNAL_TOOL = 40
    """Результат работы внешнего инструмента (плагина)."""
    RUNTIME = 50
    """Оверрайды времени выполнения (CLI, user-prompt и т.п.)."""


def _to_text(value: object) -> str:
    """Привести значение переменной к тексту для подстановки в шаблон."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return ", ".join(_to_text(item) for item in value)
    return str(value)


class VariableStore:
    """Переменные, разложенные по слоям-источникам.

    Значение переменной берётся из слоя с наибольшим приоритетом, где она задана.
    """

    def __init__(self) -> None:
        self._layers: dict[Source, dict[str, object]] = {source: {} for source in Source}

    def set(self, name: str, value: object, source: Source) -> None:
        """Задать значение переменной в указанном слое-источнике."""
        self._layers[source][name] = value

    def update(self, values: Mapping[str, object], source: Source) -> None:
        """Задать несколько переменных в одном слое."""
        self._layers[source].update(values)

    def _resolve(self, name: str) -> tuple[Source, object] | None:
        """Найти источник с наибольшим приоритетом, где задана переменная."""
        for source in sorted(Source, reverse=True):
            layer = self._layers[source]
            if name in layer:
                return source, layer[name]
        return None

    def has(self, name: str) -> bool:
        """Задана ли переменная хотя бы в одном слое."""
        return self._resolve(name) is not None

    def get(self, name: str, default: object = None) -> object:
        """Вернуть эффективное значение переменной (по приоритету слоёв)."""
        resolved = self._resolve(name)
        return default if resolved is None else resolved[1]

    def get_text(self, name: str) -> str | None:
        """Вернуть эффективное значение как текст, либо None, если переменной нет."""
        resolved = self._resolve(name)
        return None if resolved is None else _to_text(resolved[1])

    def source_of(self, name: str) -> Source | None:
        """Вернуть источник эффективного значения переменной."""
        resolved = self._resolve(name)
        return None if resolved is None else resolved[0]

    def as_dict(self) -> dict[str, object]:
        """Собрать плоский снимок всех переменных с учётом приоритета."""
        result: dict[str, object] = {}
        for source in sorted(Source):
            result.update(self._layers[source])
        return result

    def names(self) -> set[str]:
        """Все известные имена переменных из всех слоёв."""
        names: set[str] = set()
        for layer in self._layers.values():
            names.update(layer)
        return names
