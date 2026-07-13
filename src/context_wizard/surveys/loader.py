"""Загрузка опросника проекта: ``surveys/<prompt>.json``."""

from __future__ import annotations

import json
from pathlib import Path

from context_wizard.surveys.errors import SurveyError
from context_wizard.surveys.model import Survey
from context_wizard.surveys.schema import build_survey, validate_schema

SURVEYS_DIR = "surveys"


def find_survey(root: Path, prompt_id: str) -> Path | None:
    """Найти файл опросника для промпта, либо None."""
    path = root / SURVEYS_DIR / f"{prompt_id}.json"
    return path if path.is_file() else None


def load_survey(path: Path, root: Path) -> tuple[Survey, list[str]]:
    """Загрузить и провалидировать опросник; развернуть optionsPath.

    Возвращает опросник и список предупреждений (об отсечённых полях и т.п.).
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SurveyError(f"Некорректный JSON опросника {path.name!r}: {exc}") from exc

    validate_schema(data)
    survey, warnings = build_survey(data)
    _resolve_option_paths(survey, root, warnings)
    return survey, warnings


def _resolve_option_paths(survey: Survey, root: Path, warnings: list[str]) -> None:
    for element in survey:
        options_path = element.answer.options_path
        if not options_path:
            continue
        path = (root / options_path).resolve()
        if not path.is_file():
            warnings.append(
                f"[{element.var_name}] optionsPath не найден: {options_path!r} — пропущен"
            )
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        element.answer.options.extend(line.strip() for line in lines if line.strip())
