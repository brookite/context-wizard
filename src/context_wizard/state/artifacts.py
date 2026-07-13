"""Реестр файловых артефактов (вложений), задействованных при сборке промпта."""

from __future__ import annotations

from pathlib import Path


class ArtifactRegistry:
    """Собирает не-inline файлы/папки, на которые ссылается промпт.

    Дедупликация по абсолютному нормализованному пути; порядок добавления сохраняется.
    """

    def __init__(self) -> None:
        self._paths: list[Path] = []
        self._seen: set[Path] = set()

    def add(self, path: Path) -> Path:
        """Зарегистрировать артефакт. Возвращает нормализованный абсолютный путь."""
        resolved = self._normalize(path)
        if resolved not in self._seen:
            self._seen.add(resolved)
            self._paths.append(resolved)
        return resolved

    @staticmethod
    def _normalize(path: Path) -> Path:
        try:
            return path.resolve()
        except OSError:
            return Path(path).absolute()

    @property
    def attachments(self) -> list[Path]:
        """Список зарегистрированных артефактов в порядке добавления."""
        return list(self._paths)

    def __len__(self) -> int:
        return len(self._paths)

    def __contains__(self, path: Path) -> bool:
        return self._normalize(path) in self._seen
