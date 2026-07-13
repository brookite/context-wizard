from pathlib import Path

from textual.app import App
from textual.widgets import Input, OptionList, SelectionList

from context_wizard.surveys import Answer, SurveyElement
from context_wizard.tui.screens import (
    MissingVarsScreen,
    MultiSelectScreen,
    OptionSelectScreen,
    PromptSelectScreen,
    SecretInputScreen,
    SurveyInputScreen,
)


class Host(App[None]):
    """Хост-приложение, которое пушит один экран и сохраняет его результат."""

    def __init__(self, screen) -> None:
        super().__init__()
        self.target_screen = screen
        self.captured = "UNSET"

    def on_mount(self) -> None:
        self.push_screen(self.target_screen, self._store)

    def _store(self, result) -> None:
        self.captured = result


async def _select_from_list(pilot, screen, list_id: str, index: int) -> None:
    option_list = screen.query_one(list_id, OptionList)
    option_list.focus()
    option_list.highlighted = index
    await pilot.pause()
    await pilot.press("enter")
    await pilot.pause()


async def test_prompt_select_filters_and_selects(tmp_path):
    prompts = [tmp_path / "alpha.txt", tmp_path / "beta.md", tmp_path / "gamma.txt"]
    app = Host(PromptSelectScreen(prompts))
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.target_screen
        screen.query_one("#filter", Input).value = "bet"
        await pilot.pause()
        await _select_from_list(pilot, screen, "#list", 0)
    assert app.captured == tmp_path / "beta.md"


async def test_prompt_select_uses_fuzzy_subsequence():
    alpha = Path("alpha.txt")
    beta = Path("beta.md")
    app = Host(PromptSelectScreen([alpha, beta]))
    async with app.run_test() as pilot:
        await pilot.pause()
        app.target_screen.query_one("#filter", Input).value = "btm"
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
    assert app.captured == beta


async def test_fuzzy_select_keyboard_navigation():
    element = SurveyElement(
        question="Курс?",
        answer=Answer(type="option", options=["Алгебра", "Архитектура", "Физика"]),
        var_name="course",
    )
    app = Host(OptionSelectScreen(element))
    async with app.run_test() as pilot:
        await pilot.pause()
        app.target_screen.query_one("#filter", Input).value = "а"
        await pilot.pause()
        await pilot.press("down", "enter")
        await pilot.pause()
    assert app.captured in {"Алгебра", "Архитектура"}


async def test_survey_input_validates_and_dismisses():
    element = SurveyElement(
        question="Число?",
        answer=Answer(type="input", datatype="int"),
        var_name="n",
    )
    app = Host(SurveyInputScreen(element))
    async with app.run_test() as pilot:
        await pilot.pause()
        app.target_screen.query_one("#value", Input).value = "42"
        await pilot.press("enter")
        await pilot.pause()
    assert app.captured == "42"


async def test_survey_input_rejects_invalid_then_accepts():
    element = SurveyElement(
        question="Число?",
        answer=Answer(type="input", datatype="int"),
        var_name="n",
    )
    app = Host(SurveyInputScreen(element))
    async with app.run_test() as pilot:
        await pilot.pause()
        value_input = app.target_screen.query_one("#value", Input)
        value_input.value = "notint"
        await pilot.press("enter")
        await pilot.pause()
        assert app.captured == "UNSET"  # экран не закрылся
        value_input.value = "7"
        await pilot.press("enter")
        await pilot.pause()
    assert app.captured == "7"


async def test_secret_input_is_masked_and_returns_value():
    app = Host(SecretInputScreen("Пароль"))
    async with app.run_test() as pilot:
        await pilot.pause()
        value_input = app.target_screen.query_one("#value", Input)
        assert value_input.password is True
        value_input.value = "secret-value"
        await pilot.press("enter")
        await pilot.pause()
    assert app.captured == "secret-value"


async def test_option_select():
    element = SurveyElement(
        question="Цвет?",
        answer=Answer(type="option", options=["red", "green", "blue"]),
        var_name="c",
    )
    app = Host(OptionSelectScreen(element))
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.target_screen
        screen.query_one("#filter", Input).value = "gr"
        await pilot.pause()
        await _select_from_list(pilot, screen, "#list", 0)
    assert app.captured == "green"


async def test_multi_select():
    element = SurveyElement(
        question="Теги?",
        answer=Answer(type="multi selection", options=["a", "b", "c"]),
        var_name="t",
    )
    app = Host(MultiSelectScreen(element))
    async with app.run_test() as pilot:
        await pilot.pause()
        app.target_screen.query_one("#list", SelectionList).select_all()
        await pilot.pause()
        await pilot.click("#confirm")
        await pilot.pause()
    assert set(app.captured) == {"a", "b", "c"}


async def test_missing_vars_skip_selected():
    app = Host(MissingVarsScreen(["x", "y"]))
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.click("#skip")
        await pilot.pause()
    assert app.captured == {"x", "y"}


async def test_missing_vars_abort_returns_none():
    app = Host(MissingVarsScreen(["x"]))
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.click("#abort")
        await pilot.pause()
    assert app.captured is None
