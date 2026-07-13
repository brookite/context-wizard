"""Кэш проекта в каталоге ``.tmp/`` (кэш внешних инструментов и ответов опросника)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

CACHE_DIRNAME = ".tmp"
_SURVEYS_SUBDIR = "surveys"
_TOOLS_SUBDIR = "tools"


class Cache:
    """Управляет каталогом ``.tmp/`` внутри проекта."""

    def __init__(self, root: Path) -> None:
        self.dir = root / CACHE_DIRNAME

    def invalidate(self) -> None:
        """Очистить весь кэш проекта."""
        if self.dir.exists():
            shutil.rmtree(self.dir)

    @property
    def tools_dir(self) -> Path:
        """Каталог для кэша внешних инструментов (создаётся при обращении)."""
        path = self.dir / _TOOLS_SUBDIR
        path.mkdir(parents=True, exist_ok=True)
        return path

    def load_survey_answers(self, prompt_id: str) -> dict[str, object]:
        """Загрузить закэшированные ответы опросника для промпта."""
        return self._load_json(self._survey_path(prompt_id))

    def save_survey_answers(self, prompt_id: str, answers: dict[str, object]) -> None:
        """Сохранить закэшированные ответы опросника для промпта."""
        self._save_json(self._survey_path(prompt_id), answers)

    def load_tool_cache(self, tool_id: str) -> dict[str, object]:
        """Загрузить кэш внешнего инструмента (значения этапов и т.п.)."""
        return self._load_json(self._tool_path(tool_id))

    def save_tool_cache(self, tool_id: str, data: dict[str, object]) -> None:
        """Сохранить кэш внешнего инструмента."""
        self._save_json(self._tool_path(tool_id), data)

    def _survey_path(self, prompt_id: str) -> Path:
        return self.dir / _SURVEYS_SUBDIR / f"{prompt_id}.json"

    def _tool_path(self, tool_id: str) -> Path:
        return self.dir / _TOOLS_SUBDIR / f"{tool_id}.json"

    @staticmethod
    def _load_json(path: Path) -> dict[str, object]:
        if not path.is_file():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _save_json(path: Path, data: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
