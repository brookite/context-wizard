import sys
from pathlib import Path
from typing import Any, cast

import pytest

from context_wizard.output import RichPromptDTO
from context_wizard.plugins import PluginContext, builtin_plugins_dir, discover_plugins
from context_wizard.state import VariableStore


def _load_target() -> Any:
    # codex — встроенный (глобальный) плагин, обнаруживается без проектной папки
    registry = discover_plugins(builtin_plugins_dir())
    assert registry.has_answer("codex")
    return registry.create_answer("codex")


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / "assets").mkdir(parents=True)
    (root / "assets" / "diagram.png").write_bytes(b"\x89PNG")
    return root


def _ctx(root: Path, **settings) -> PluginContext:
    env = {}
    if "workspace_env_value" in settings:
        env["CODEX_WORKSPACE"] = settings.pop("workspace_env_value")
    return PluginContext(root=root, store=VariableStore(), env=env, settings=settings)


def test_prepare_workspace_copies_prompt_and_attachments(tmp_path):
    root = _project(tmp_path)
    attachment = (root / "assets" / "diagram.png").resolve()
    dto = RichPromptDTO(prompt="see assets/diagram.png", attachments=[attachment], root=root)

    base = tmp_path / "ws"
    ctx = _ctx(root, launch=False, workspace_env_value=str(base))
    target = _load_target()

    workspace = target.prepare_workspace(dto, ctx)

    assert workspace.parent == base
    assert (workspace / "PROMPT.md").read_text(encoding="utf-8") == "see assets/diagram.png"
    # относительная структура сохранена -> путь из промпта разрешится при --cd
    assert (workspace / "assets" / "diagram.png").read_bytes() == b"\x89PNG"


def test_workspace_dir_relative_to_root(tmp_path):
    root = _project(tmp_path)
    dto = RichPromptDTO(prompt="body", attachments=[], root=root)
    ctx = _ctx(root, launch=False, workspace_dir="_codex_out")
    target = _load_target()

    workspace = target.prepare_workspace(dto, ctx)
    assert workspace.parent == root / "_codex_out"


def test_missing_workspace_env_defaults_to_project_output(tmp_path):
    root = _project(tmp_path)
    dto = RichPromptDTO(prompt="body", attachments=[], root=root)
    ctx = _ctx(root, launch=False)  # ни env, ни workspace_dir
    target = _load_target()

    workspace = target.prepare_workspace(dto, ctx)
    assert workspace.parent == root / "output"


def test_ambiguous_output_without_workspace_env_raises(tmp_path):
    root = _project(tmp_path)
    dto = RichPromptDTO(prompt="body", attachments=[], root=root)
    ctx = _ctx(root, launch=False)
    ctx.output_dir_ambiguous = True
    target = _load_target()

    with pytest.raises(RuntimeError, match="CODEX_WORKSPACE"):
        target.prepare_workspace(dto, ctx)


def test_output_dir_is_fallback_after_workspace_env(tmp_path):
    root = _project(tmp_path)
    dto = RichPromptDTO(prompt="body", attachments=[], root=root)
    output_dir = tmp_path / "cli-output"
    ctx = _ctx(root, launch=False)
    ctx.output_dir = output_dir

    workspace = _load_target().prepare_workspace(dto, ctx)

    assert workspace.parent == output_dir


def test_external_attachment_goes_to_external_dir(tmp_path):
    root = _project(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("x", encoding="utf-8")
    dto = RichPromptDTO(prompt="body", attachments=[outside.resolve()], root=root)
    ctx = _ctx(root, launch=False, workspace_env_value=str(tmp_path / "ws"))
    target = _load_target()

    workspace = target.prepare_workspace(dto, ctx)
    assert (workspace / "_external" / "outside.txt").is_file()


def test_deliver_without_launch_notifies(tmp_path):
    root = _project(tmp_path)
    dto = RichPromptDTO(prompt="body", attachments=[], root=root)

    notes: list[str] = []

    class UI:
        def notify(self, message):
            notes.append(message)

        # заглушки WizardUI (не используются)
        def select_prompt(self, prompts): ...
        def ask_input(self, element): ...
        def ask_option(self, element): ...
        def ask_multi(self, element): ...
        def resolve_missing(self, missing): ...
        def push_screen(self, screen): ...
        @property
        def app(self): return None

    ctx = PluginContext(
        root=root,
        store=VariableStore(),
        ui=cast(Any, UI()),
        env={"CODEX_WORKSPACE": str(tmp_path / "ws")},
        settings={"launch": False},
    )
    target = _load_target()
    target.deliver(dto, ctx)
    assert any("готова" in n for n in notes)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-специфичный запуск")
def test_build_launch_windows(tmp_path):
    root = _project(tmp_path)
    dto = RichPromptDTO(prompt="body", attachments=[], root=root)
    ctx = _ctx(root, launch=False, workspace_env_value=str(tmp_path / "ws"))
    target = _load_target()

    workspace = target.prepare_workspace(dto, ctx)
    command, creationflags = target.build_launch(workspace, ctx)

    assert Path(command[0]).stem.lower() in {"pwsh", "powershell"}
    assert "-File" in command
    launcher = Path(command[-1])
    assert launcher.is_file()
    content = launcher.read_text(encoding="utf-8")
    assert "codex --cd" in content
    assert creationflags != 0
