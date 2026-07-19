"""Встроенный AnswerTarget, открывающий подготовленную папку с промптом."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from context_wizard.builtins._workspace import prepare_workspace, resolve_path
from context_wizard.output import RichPromptDTO
from context_wizard.plugins import AnswerTarget, PluginContext


class FolderAnswerTarget(AnswerTarget):
    """Подготовить промпт и открыть его папку в системном файловом менеджере."""

    id = "folder"

    def deliver(self, dto: RichPromptDTO, context: PluginContext) -> None:
        workspace = self.prepare_workspace(dto, context)
        subprocess.Popen(self.build_open_command(workspace))  # noqa: S603
        context.notify(f"Папка с промптом открыта: {workspace}")

    def prepare_workspace(self, dto: RichPromptDTO, context: PluginContext) -> Path:
        return prepare_workspace(dto, context, self._base_dir(context))

    def _base_dir(self, context: PluginContext) -> Path:
        literal = context.settings.get("workspace_dir")
        if literal:
            return resolve_path(literal, context.root)
        if context.output_dir_ambiguous:
            raise RuntimeError(
                "Не удалось определить общую папку вывода. "
                "Задайте settings.workspace_dir для плагина folder"
            )
        return context.output_dir or context.root / "output"

    @staticmethod
    def build_open_command(workspace: Path) -> list[str]:
        if sys.platform == "win32":
            executable = shutil.which("explorer")
        elif sys.platform == "darwin":
            executable = shutil.which("open")
        else:
            executable = shutil.which("xdg-open")
        if executable is None:
            raise RuntimeError("Не найден системный файловый менеджер для открытия папки")
        return [executable, str(workspace)]


__all__ = ["FolderAnswerTarget"]
