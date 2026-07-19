"""Ошибки выполнения плагинов."""

from __future__ import annotations

from collections.abc import Sequence


class AnswerDeliveryError(RuntimeError):
    """Совокупность ошибок параллельной доставки ответа."""

    def __init__(self, failures: Sequence[tuple[str, BaseException]]) -> None:
        self.failures = tuple(failures)
        details = "; ".join(
            f"{plugin_id}: {type(error).__name__}: {error}"
            for plugin_id, error in self.failures
        )
        super().__init__(f"Ошибки доставки ответа ({len(self.failures)}): {details}")


__all__ = ["AnswerDeliveryError"]
