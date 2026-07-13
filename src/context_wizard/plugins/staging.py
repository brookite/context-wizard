"""Многоэтапные плагины: конечный автомат этапов с ветвлением и кэшем."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from context_wizard.plugins.base import ExternalTool, PluginContext
from context_wizard.state import Source

_MAX_STEPS = 1000


@dataclass
class StageResult:
    """Результат этапа: собранные значения и id следующего этапа (ветвление)."""

    values: dict[str, object] = field(default_factory=dict)
    next: str | None = None
    """id следующего этапа; ``None`` — перейти к следующему по порядку (или завершить)."""


# Этап может вернуть StageResult, отображение значений (переход по порядку) или None.
StageReturn = StageResult | Mapping[str, object] | None


@dataclass
class Stage:
    """Именованный этап работы плагина."""

    id: str
    run: Callable[[PluginContext], StageReturn]
    cached: bool = False
    """Если True — результат этапа кэшируется в ``.tmp`` и переиспользуется при повторе."""


class StagedTool(ExternalTool):
    """Внешний инструмент как автомат этапов.

    Наследник задаёт :meth:`stages` и, при необходимости, ``initial`` (id первого этапа;
    по умолчанию — первый в списке).
    """

    initial: str = ""

    def stages(self) -> list[Stage]:
        raise NotImplementedError

    def run(self, context: PluginContext) -> dict[str, object]:
        return drive_stages(self.stages(), self.initial, context)


def drive_stages(
    stages: list[Stage],
    initial: str,
    context: PluginContext,
) -> dict[str, object]:
    """Прогнать этапы от ``initial``, следуя ветвлениям ``next`` или порядку списка.

    Значения каждого этапа сразу попадают в ``store`` (слой EXTERNAL_TOOL), чтобы
    последующие этапы их видели. Кэшируемые этапы читаются/пишутся через ``context.cache``.
    """
    if not stages:
        return {}

    by_id = {stage.id: stage for stage in stages}
    order = [stage.id for stage in stages]
    current: str | None = initial or order[0]
    accumulated: dict[str, object] = {}

    for _ in range(_MAX_STEPS):
        if current is None:
            return accumulated
        stage = by_id.get(current)
        if stage is None:
            raise KeyError(f"Этап не найден: {current!r}")

        if stage.cached and stage.id in context.cache:
            cached = context.cache[stage.id]
            assert isinstance(cached, dict)
            values: dict[str, object] = cached
            next_id = _sequential_next(order, current)
        else:
            result = _normalize(stage.run(context))
            values = result.values
            if stage.cached:
                context.cache[stage.id] = values
            next_id = result.next if result.next is not None else _sequential_next(order, current)

        accumulated.update(values)
        context.store.update(values, Source.EXTERNAL_TOOL)
        current = next_id

    raise RuntimeError("Превышено число шагов автомата этапов — вероятно, зацикливание")


def _sequential_next(order: list[str], current: str) -> str | None:
    index = order.index(current)
    return order[index + 1] if index + 1 < len(order) else None


def _normalize(raw: StageReturn) -> StageResult:
    if raw is None:
        return StageResult()
    if isinstance(raw, StageResult):
        return raw
    return StageResult(values=dict(raw))


__all__ = ["Stage", "StageResult", "StagedTool", "drive_stages"]
