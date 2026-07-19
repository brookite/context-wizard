"""Вывод готового промпта и копирование вложений согласно CLI-флагам."""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from context_wizard.output.dto import RichPromptDTO

PROMPT_FILENAME = "rich_prompt.txt"


@dataclass
class OutputOptions:
    """Куда писать промпт и вложения. ``None`` — не писать (для промпта — stdout)."""

    prompt_dir: Path | None = None
    file_dir: Path | None = None


@dataclass(frozen=True)
class DeliveryDirectory:
    """Результат определения общей базы для плагинов доставки."""

    path: Path | None
    ambiguous: bool = False


def resolve_output_options(
    *,
    prompt_output: str | None,
    file_output: str | None,
    output: str | None,
) -> OutputOptions:
    """Свести CLI-флаги вывода к :class:`OutputOptions` с проверкой взаимоисключения.

    ``--output`` задаёт каталог сразу для промпта и файлов и несовместим с
    ``--prompt-output`` / ``--file-output``.
    """
    if output is not None and (prompt_output is not None or file_output is not None):
        raise ValueError(
            "--output нельзя сочетать с --prompt-output или --file-output"
        )
    if output is not None:
        directory = Path(output)
        return OutputOptions(prompt_dir=directory, file_dir=directory)
    return OutputOptions(
        prompt_dir=Path(prompt_output) if prompt_output is not None else None,
        file_dir=Path(file_output) if file_output is not None else None,
    )


def resolve_delivery_directory(options: OutputOptions, root: Path) -> DeliveryDirectory:
    """Определить общую базу доставки из CLI-каталогов.

    Два раздельных каталога совместимы, если их ближайший общий предок находится
    не более чем в двух переходах вверх от каждого из них.
    """
    prompt_dir = _absolute(options.prompt_dir)
    file_dir = _absolute(options.file_dir)
    if prompt_dir is None and file_dir is None:
        return DeliveryDirectory((root / "output").resolve())
    if prompt_dir is None:
        return DeliveryDirectory(file_dir)
    if file_dir is None or prompt_dir == file_dir:
        return DeliveryDirectory(prompt_dir)

    try:
        common = Path(os.path.commonpath((prompt_dir, file_dir)))
        prompt_depth = len(prompt_dir.relative_to(common).parts)
        file_depth = len(file_dir.relative_to(common).parts)
    except ValueError:
        return DeliveryDirectory(None, ambiguous=True)
    if prompt_depth <= 2 and file_depth <= 2:
        return DeliveryDirectory(common)
    return DeliveryDirectory(None, ambiguous=True)


def write_output(dto: RichPromptDTO, options: OutputOptions) -> Path | None:
    """Записать промпт (в файл или stdout) и скопировать вложения.

    Возвращает путь к файлу промпта, либо ``None``, если промпт ушёл в stdout.
    """
    copied: dict[Path, Path] = {}
    if options.file_dir is not None:
        copied = _copy_attachments(dto.attachments, options.file_dir)
    prompt = _rewrite_attachment_paths(
        dto.prompt,
        root=dto.root,
        copied=copied,
        prompt_dir=options.prompt_dir,
    )
    prompt_path = _write_prompt(prompt, options.prompt_dir)
    return prompt_path


def _write_prompt(prompt: str, prompt_dir: Path | None) -> Path | None:
    if prompt_dir is None:
        sys.stdout.write(prompt)
        if not prompt.endswith("\n"):
            sys.stdout.write("\n")
        return None
    prompt_dir.mkdir(parents=True, exist_ok=True)
    target = prompt_dir / PROMPT_FILENAME
    target.write_text(prompt, encoding="utf-8")
    return target


def _copy_attachments(attachments: list[Path], file_dir: Path) -> dict[Path, Path]:
    copied: dict[Path, Path] = {}
    if not attachments:
        return copied
    file_dir.mkdir(parents=True, exist_ok=True)
    for source in attachments:
        if not source.exists():
            continue
        destination = file_dir / source.name
        if source.is_dir():
            shutil.copytree(source, destination, dirs_exist_ok=True)
        else:
            shutil.copy2(source, destination)
        copied[source] = destination
    return copied


def _rewrite_attachment_paths(
    prompt: str,
    *,
    root: Path,
    copied: dict[Path, Path],
    prompt_dir: Path | None,
) -> str:
    if not copied:
        return prompt
    display_base = prompt_dir if prompt_dir is not None else Path.cwd()
    replacements = [
        (
            _relative_path(source, root),
            _relative_path(destination, display_base),
        )
        for source, destination in copied.items()
    ]
    for source_display, destination_display in sorted(
        replacements, key=lambda item: len(item[0]), reverse=True
    ):
        prompt = prompt.replace(source_display, destination_display)
    return prompt


def _relative_path(path: Path, base: Path) -> str:
    return Path(os.path.relpath(path.absolute(), base.absolute())).as_posix()


def _absolute(path: Path | None) -> Path | None:
    return None if path is None else path.expanduser().resolve()
