import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from context_wizard.output import RichPromptDTO
from context_wizard.plugins import PluginContext, builtin_plugins_dir, discover_plugins
from context_wizard.state import VariableStore


def _target() -> Any:
    registry = discover_plugins(builtin_plugins_dir())
    assert registry.has_answer("folder")
    return registry.create_answer("folder")


def test_folder_prepares_workspace_in_output_dir(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    attachment = root / "asset.bin"
    attachment.write_bytes(b"data")
    dto = RichPromptDTO(prompt="asset.bin", attachments=[attachment], root=root)
    output_dir = tmp_path / "chosen-output"
    context = PluginContext(
        root=root,
        store=VariableStore(),
        output_dir=output_dir,
    )

    workspace = _target().prepare_workspace(dto, context)

    assert workspace.parent == output_dir
    assert (workspace / "PROMPT.md").read_text(encoding="utf-8") == "asset.bin"
    assert (workspace / "asset.bin").read_bytes() == b"data"


def test_folder_ambiguous_output_requires_workspace_setting(tmp_path):
    dto = RichPromptDTO(prompt="body", root=tmp_path)
    context = PluginContext(
        root=tmp_path,
        store=VariableStore(),
        output_dir_ambiguous=True,
    )

    with pytest.raises(RuntimeError, match="workspace_dir"):
        _target().prepare_workspace(dto, context)


def test_folder_workspace_setting_resolves_ambiguous_output(tmp_path):
    dto = RichPromptDTO(prompt="body", root=tmp_path)
    context = PluginContext(
        root=tmp_path,
        store=VariableStore(),
        settings={"workspace_dir": "explicit"},
        output_dir_ambiguous=True,
    )

    workspace = _target().prepare_workspace(dto, context)

    assert workspace.parent == tmp_path / "explicit"


def test_folder_deliver_opens_prepared_workspace(monkeypatch, tmp_path):
    dto = RichPromptDTO(prompt="body", root=tmp_path)
    context = PluginContext(root=tmp_path, store=VariableStore())
    commands: list[list[str]] = []

    def record_command(command: list[str]) -> None:
        commands.append(command)

    monkeypatch.setattr(subprocess, "Popen", record_command)
    monkeypatch.setattr(shutil, "which", lambda name: str(Path("bin") / name))

    _target().deliver(dto, context)

    command_name = (
        "explorer"
        if sys.platform == "win32"
        else "open"
        if sys.platform == "darwin"
        else "xdg-open"
    )
    assert Path(commands[0][0]).name == command_name
    assert Path(commands[0][1]).is_dir()
