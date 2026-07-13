import json

import pytest
from textual.widgets import Input, OptionList

from context_wizard.app import Collector, CollectorOptions
from context_wizard.cli import build_parser, main
from context_wizard.config import load_setup
from context_wizard.output import PROMPT_FILENAME, resolve_output_options
from context_wizard.tui import TextualUI, WizardApp
from context_wizard.tui.screens import PromptSelectScreen, SurveyInputScreen


async def _wait_for(pilot, screen_type, child_selector: str, timeout: float = 5.0):
    """Дождаться активного экрана нужного типа с уже смонтированным дочерним виджетом."""
    from textual.css.query import NoMatches

    steps = int(timeout / 0.05)
    for _ in range(steps):
        screen = pilot.app.screen
        if isinstance(screen, screen_type):
            try:
                screen.query_one(child_selector)
                return screen
            except NoMatches:
                pass
        await pilot.pause(0.05)
    raise AssertionError(f"Экран {screen_type.__name__} не появился")


async def _wait_until_done(pilot, timeout: float = 5.0):
    steps = int(timeout / 0.05)
    for _ in range(steps):
        if not pilot.app.is_running:
            return
        await pilot.pause(0.05)


def _build_project(root):
    (root / "prompts").mkdir()
    (root / "surveys").mkdir()
    (root / "surveys" / "task.json").write_text(
        json.dumps([{"question": "Имя?", "varName": "name", "answer": {"type": "input"}}]),
        encoding="utf-8",
    )
    (root / "prompts" / "task.md").write_text("Привет, {{ name }}!", encoding="utf-8")


async def test_full_app_through_tui(tmp_path):
    _build_project(tmp_path)
    out_dir = tmp_path / "out"
    config = load_setup(tmp_path)
    options = CollectorOptions(
        output=resolve_output_options(prompt_output=None, file_output=None, output=str(out_dir)),
    )

    app = WizardApp()
    collector = Collector(tmp_path, config, TextualUI(app))
    app.set_pipeline(lambda: collector.run(options))

    async with app.run_test() as pilot:
        prompt_screen = await _wait_for(pilot, PromptSelectScreen, "#list")
        option_list = prompt_screen.query_one("#list", OptionList)
        option_list.focus()
        option_list.highlighted = 0
        await pilot.pause()
        await pilot.press("enter")

        survey_screen = await _wait_for(pilot, SurveyInputScreen, "#value")
        survey_screen.query_one("#value", Input).value = "Мир"
        await pilot.press("enter")

        await _wait_until_done(pilot)

    assert app.error is None
    assert app.result is not None
    assert app.result.prompt == "Привет, Мир!"
    assert (out_dir / PROMPT_FILENAME).read_text(encoding="utf-8") == "Привет, Мир!"


def test_parser_reads_flags():
    args = build_parser().parse_args(
        ["proj", "--prompt", "task", "--invalidate", "--output", "o", "--answer-target", "codex"]
    )
    assert args.project == "proj"
    assert args.prompt == "task"
    assert args.invalidate is True
    assert args.output == "o"
    assert args.answer_target == "codex"


def test_conflicting_output_flags_error(tmp_path):
    _build_project(tmp_path)
    with pytest.raises(SystemExit):
        main([str(tmp_path), "--output", "a", "--file-output", "b"])
