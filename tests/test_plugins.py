from pathlib import Path

from context_wizard.app import Collector
from context_wizard.config import SetupConfig
from context_wizard.plugins import (
    PluginContext,
    builtin_plugins_dir,
    discover_plugins,
)
from context_wizard.state import VariableStore
from context_wizard.surveys import SurveyElement


class _UnusedUI:
    """Полная UI-заглушка: Collector.registry() не вызывает ни один из этих методов."""

    def select_prompt(self, prompts: list[Path]) -> Path:
        raise AssertionError("UI не должен вызываться")

    def ask_input(self, element: SurveyElement) -> str:
        raise AssertionError("UI не должен вызываться")

    def ask_secret(self, question: str, *, hint: str | None = None) -> str:
        raise AssertionError("UI не должен вызываться")

    def ask_option(self, element: SurveyElement) -> str:
        raise AssertionError("UI не должен вызываться")

    def ask_multi(self, element: SurveyElement) -> list[str]:
        raise AssertionError("UI не должен вызываться")

    def resolve_missing(self, missing: list[str]) -> set[str]:
        raise AssertionError("UI не должен вызываться")

    def notify(self, message: str) -> None:
        raise AssertionError("UI не должен вызываться")

    def push_screen(self, screen: object) -> object:
        raise AssertionError("UI не должен вызываться")

    @property
    def app(self) -> object | None:
        return None

PLUGIN_SOURCE = '''
from context_wizard.plugins import AnswerTarget, ExternalTool


class DemoTool(ExternalTool):
    id = "demo"

    def run(self, context):
        return {"collected": "yes"}


class DemoTarget(AnswerTarget):
    id = "demo_target"

    def deliver(self, dto, context):
        pass


class NoIdTool(ExternalTool):
    def run(self, context):
        return {}
'''


def test_discovery_registers_plugins(tmp_path):
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()
    (plugins_dir / "demo.py").write_text(PLUGIN_SOURCE, encoding="utf-8")
    (plugins_dir / "_ignored.py").write_text("x = 1", encoding="utf-8")

    registry = discover_plugins(plugins_dir)
    assert registry.external_ids() == ["demo"]
    assert registry.answer_ids() == ["demo_target"]
    assert registry.has_external("demo")
    assert not registry.has_external("missing")


def test_discovery_creates_working_instance(tmp_path):
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()
    (plugins_dir / "demo.py").write_text(PLUGIN_SOURCE, encoding="utf-8")

    registry = discover_plugins(plugins_dir)
    tool = registry.create_external("demo")
    context = PluginContext(root=tmp_path, store=VariableStore())
    assert tool.run(context) == {"collected": "yes"}


def test_discovery_empty_when_no_dir(tmp_path):
    registry = discover_plugins(tmp_path / "nope")
    assert registry.external_ids() == []


def test_builtin_codex_is_global(tmp_path):
    registry = discover_plugins(builtin_plugins_dir())
    assert "codex" in registry.answer_ids()


_OVERRIDE_SRC = '''
from context_wizard.plugins import AnswerTarget


class Dup(AnswerTarget):
    id = "dup"
    marker = "{marker}"

    def deliver(self, dto, context):
        pass
'''


def test_project_plugin_overrides_global_by_id(tmp_path):
    global_dir = tmp_path / "global"
    global_dir.mkdir()
    (global_dir / "g.py").write_text(_OVERRIDE_SRC.format(marker="global"), encoding="utf-8")
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "p.py").write_text(_OVERRIDE_SRC.format(marker="project"), encoding="utf-8")

    # порядок: глобальные -> проектные, проект переопределяет по id
    registry = discover_plugins(global_dir, project_dir)
    target: object = registry.create_answer("dup")
    assert getattr(target, "marker", None) == "project"


def test_collector_loads_multiple_plugin_dirs_in_order(tmp_path):
    first_dir = tmp_path / "first"
    first_dir.mkdir()
    (first_dir / "first.py").write_text(
        _OVERRIDE_SRC.format(marker="first"), encoding="utf-8"
    )
    second_dir = tmp_path / "second"
    second_dir.mkdir()
    (second_dir / "second.py").write_text(
        _OVERRIDE_SRC.format(marker="second"), encoding="utf-8"
    )

    config = SetupConfig(plugins_dir=["first", "second"])
    registry = Collector(tmp_path, config, _UnusedUI()).registry()

    target: object = registry.create_answer("dup")
    assert getattr(target, "marker", None) == "second"
