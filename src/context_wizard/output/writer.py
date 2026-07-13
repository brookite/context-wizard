"""Вывод готового промпта и копирование вложений согласно CLI-флагам."""

from __future__ import annotations

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


def write_output(dto: RichPromptDTO, options: OutputOptions) -> Path | None:
    """Записать промпт (в файл или stdout) и скопировать вложения.

    Возвращает путь к файлу промпта, либо ``None``, если промпт ушёл в stdout.
    """
    prompt_path = _write_prompt(dto, options.prompt_dir)
    if options.file_dir is not None:
        _copy_attachments(dto.attachments, options.file_dir)
    return prompt_path


def _write_prompt(dto: RichPromptDTO, prompt_dir: Path | None) -> Path | None:
    if prompt_dir is None:
        sys.stdout.write(dto.prompt)
        if not dto.prompt.endswith("\n"):
            sys.stdout.write("\n")
        return None
    prompt_dir.mkdir(parents=True, exist_ok=True)
    target = prompt_dir / PROMPT_FILENAME
    target.write_text(dto.prompt, encoding="utf-8")
    return target


def _copy_attachments(attachments: list[Path], file_dir: Path) -> None:
    if not attachments:
        return
    file_dir.mkdir(parents=True, exist_ok=True)
    for source in attachments:
        if not source.exists():
            continue
        destination = file_dir / source.name
        if source.is_dir():
            shutil.copytree(source, destination, dirs_exist_ok=True)
        else:
            shutil.copy2(source, destination)
