"""Общая подготовка рабочей папки для встроенных AnswerTarget-плагинов."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from context_wizard.output import RichPromptDTO
from context_wizard.plugins import PluginContext


def prepare_workspace(
    dto: RichPromptDTO,
    context: PluginContext,
    base: Path,
) -> Path:
    """Создать уникальную рабочую папку с промптом и вложениями."""
    base.mkdir(parents=True, exist_ok=True)
    prefix = str(context.settings.get("folder_prefix", "answer"))
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    workspace = _create_unique_dir(base / f"{prefix}_{stamp}")

    for source in dto.attachments:
        destination = _attachment_destination(source, dto.root, workspace)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, destination, dirs_exist_ok=True)
        elif source.exists():
            shutil.copy2(source, destination)

    prompt_name = str(context.settings.get("prompt_filename", "PROMPT.md"))
    (workspace / prompt_name).write_text(dto.prompt, encoding="utf-8")
    return workspace


def resolve_path(value: object, root: Path) -> Path:
    """Разрешить абсолютный или проектно-относительный путь настройки."""
    path = Path(str(value)).expanduser()
    return path if path.is_absolute() else root / path


def _create_unique_dir(path: Path) -> Path:
    for index in range(1000):
        candidate = path if index == 0 else path.with_name(f"{path.name}-{index}")
        try:
            candidate.mkdir()
        except FileExistsError:
            continue
        return candidate
    raise RuntimeError(f"Не удалось подобрать уникальную папку рядом с {path}")


def _attachment_destination(source: Path, root: Path, workspace: Path) -> Path:
    try:
        relative = source.resolve().relative_to(root.resolve())
    except ValueError:
        return workspace / "_external" / source.name
    return workspace / relative


__all__ = ["prepare_workspace", "resolve_path"]
