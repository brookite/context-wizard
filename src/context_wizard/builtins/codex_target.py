"""Встроенный AnswerTarget: доставка готового промпта в OpenAI Codex CLI (``id = "codex"``).

Что делает при доставке:
1. берёт базовую папку из ``settings.workspace_dir``, переменной окружения (по умолчанию
   ``CODEX_WORKSPACE``), output-флагов или ``<project>/output``;
2. создаёт в ней уникальную подпапку для этого ответа;
3. копирует все вложения (``dto.attachments``) с сохранением относительной структуры,
   чтобы относительные пути из промпта разрешались внутри рабочей папки;
4. кладёт сам промпт в файл (``PROMPT.md``);
5. открывает Codex в новом окне терминала с рабочим корнем = этой папке, передав короткое
   указание прочитать ``PROMPT.md`` и выполнить задачу.

Плагин глобальный (встроенный) — доступен любому проекту без копирования. Включается в
``setup.toml``:

    [answer_target]
    id = "codex"
    use_fs = true
    [answer_target.settings]
    workspace_env = "CODEX_WORKSPACE"   # имя переменной в tools.env
    # workspace_dir = "_codex_out"      # либо явный путь (относительный — от корня проекта)
    # launch = false                    # только подготовить папку, не открывать Codex
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from context_wizard.builtins._workspace import prepare_workspace, resolve_path
from context_wizard.output import RichPromptDTO
from context_wizard.plugins import AnswerTarget, PluginContext

_DEFAULT_BOOTSTRAP = (
    "Твоя задача описана в файле {prompt} в корне рабочей папки. "
    "Прочитай его и выполни. Вложения лежат по указанным в нём относительным путям."
)


class CodexAnswerTarget(AnswerTarget):
    """Передаёт промпт и вложения в Codex CLI, открывая его в отдельном окне."""

    id = "codex"

    def deliver(self, dto: RichPromptDTO, context: PluginContext) -> None:
        workspace = self.prepare_workspace(dto, context)
        if _as_bool(context.settings.get("launch", True)):
            self.launch(workspace, context)
            context.notify(f"Codex открыт в {workspace}")
        else:
            context.notify(f"Рабочая папка Codex готова: {workspace}")

    # -- Подготовка рабочей папки (без побочных эффектов запуска) --------

    def prepare_workspace(self, dto: RichPromptDTO, context: PluginContext) -> Path:
        return prepare_workspace(dto, context, self._base_dir(context))

    def _base_dir(self, context: PluginContext) -> Path:
        literal = context.settings.get("workspace_dir")
        if literal:
            return resolve_path(literal, context.root)

        var = str(context.settings.get("workspace_env", "CODEX_WORKSPACE"))
        value = context.env.get(var) or os.environ.get(var)
        if value:
            return resolve_path(value, context.root)
        if context.output_dir_ambiguous:
            raise RuntimeError(
                "Не удалось определить общую папку вывода для Codex. "
                f"Установите {var} в tools.env или задайте settings.workspace_dir"
            )
        return context.output_dir or context.root / "output"

    # -- Запуск Codex (побочный эффект) ---------------------------------

    def launch(self, workspace: Path, context: PluginContext) -> None:
        command, creationflags = self.build_launch(workspace, context)
        subprocess.Popen(command, creationflags=creationflags)  # noqa: S603

    def build_launch(
        self, workspace: Path, context: PluginContext
    ) -> tuple[list[str], int]:
        """Собрать команду запуска и флаги создания процесса (``creationflags``).

        На Windows возвращает запуск pwsh-лаунчера в новом окне (``CREATE_NEW_CONSOLE``);
        на других ОС — прямой вызов codex без спецфлагов.
        """
        prompt_name = str(context.settings.get("prompt_filename", "PROMPT.md"))
        bootstrap = str(context.settings.get("bootstrap", _DEFAULT_BOOTSTRAP)).format(
            prompt=prompt_name
        )
        codex = str(context.settings.get("codex_command", "codex"))

        if sys.platform == "win32":
            launcher = workspace / "_run_codex.ps1"
            launcher.write_text(_ps_launcher(codex, workspace, bootstrap), encoding="utf-8")
            shell = shutil.which("pwsh") or shutil.which("powershell") or "powershell"
            return [shell, "-NoExit", "-File", str(launcher)], subprocess.CREATE_NEW_CONSOLE

        # Прочие ОС — best effort в текущем терминале.
        return [codex, "--cd", str(workspace), bootstrap], 0


def _ps_launcher(codex: str, workspace: Path, bootstrap: str) -> str:
    wdir = str(workspace).replace("'", "''")
    boot = bootstrap.replace("'", "''")
    return f"Set-Location -LiteralPath '{wdir}'\n& {codex} --cd '{wdir}' '{boot}'\n"


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"false", "0", "no", "off", ""}
