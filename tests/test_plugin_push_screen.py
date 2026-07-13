"""Интеграция: плагин пушит собственный Textual-экран через ctx.push_screen."""

from context_wizard.app import Collector, CollectorOptions
from context_wizard.config import load_setup
from context_wizard.output import PROMPT_FILENAME, resolve_output_options
from context_wizard.tui import TextualUI, WizardApp

PLUGIN_SOURCE = '''
from textual.screen import ModalScreen
from textual.widgets import Button, Label

from context_wizard.plugins import Stage, StagedTool


class PickScreen(ModalScreen):
    def compose(self):
        yield Label("Выберите", id="q")
        yield Button("Взять значение", id="go")

    def on_button_pressed(self, event):
        self.dismiss("picked-value")


class PickerTool(StagedTool):
    id = "picker"
    initial = "pick"

    def stages(self):
        return [Stage("pick", self._pick)]

    def _pick(self, ctx):
        value = ctx.push_screen(PickScreen())
        return {"picked": value}
'''


async def _wait_for(pilot, screen_name: str, child: str, timeout: float = 5.0):
    steps = int(timeout / 0.05)
    for _ in range(steps):
        screen = pilot.app.screen
        if type(screen).__name__ == screen_name:
            from textual.css.query import NoMatches

            try:
                screen.query_one(child)
                return screen
            except NoMatches:
                pass
        await pilot.pause(0.05)
    raise AssertionError(f"Экран {screen_name} не появился")


async def _wait_until_done(pilot, timeout: float = 5.0):
    for _ in range(int(timeout / 0.05)):
        if not pilot.app.is_running:
            return
        await pilot.pause(0.05)


def _build_project(root):
    (root / "prompts").mkdir()
    (root / "plugins").mkdir()
    (root / "plugins" / "picker.py").write_text(PLUGIN_SOURCE, encoding="utf-8")
    (root / "prompts" / "p.md").write_text("Значение: {{ picked }}", encoding="utf-8")
    (root / "setup.toml").write_text(
        'external_tool = "picker"\nplugins_dir = "plugins"\n', encoding="utf-8"
    )


async def test_plugin_pushes_custom_screen(tmp_path):
    _build_project(tmp_path)
    out_dir = tmp_path / "out"
    config = load_setup(tmp_path)
    options = CollectorOptions(
        output=resolve_output_options(prompt_output=None, file_output=None, output=str(out_dir)),
        prompt_id="p",
    )

    app = WizardApp()
    collector = Collector(tmp_path, config, TextualUI(app))
    app.set_pipeline(lambda: collector.run(options))

    async with app.run_test() as pilot:
        await _wait_for(pilot, "PickScreen", "#go")
        await pilot.click("#go")
        await _wait_until_done(pilot)

    assert app.error is None
    assert app.result is not None
    assert app.result.prompt == "Значение: picked-value"
    assert (out_dir / PROMPT_FILENAME).read_text(encoding="utf-8") == "Значение: picked-value"
