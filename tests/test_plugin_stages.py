from pathlib import Path

from context_wizard.plugins import (
    PluginContext,
    Stage,
    StagedTool,
    StageResult,
    drive_stages,
)
from context_wizard.state import VariableStore
from context_wizard.surveys import Answer, SurveyElement


class FakeUI:
    """Минимальный UI для прямых тестов плагинов (последовательные очереди ответов)."""

    def __init__(self, inputs=(), options=(), multi=(), secrets=()):
        self.inputs = list(inputs)
        self.options = list(options)
        self.multi = list(multi)
        self.secrets = list(secrets)
        self.notes: list[str] = []

    def ask_input(self, element):
        return self.inputs.pop(0)

    def ask_option(self, element):
        return self.options.pop(0)

    def ask_secret(self, question, *, hint=None):
        return self.secrets.pop(0)

    def ask_multi(self, element):
        return self.multi.pop(0)

    def notify(self, message):
        self.notes.append(message)

    def push_screen(self, screen):
        raise NotImplementedError

    @property
    def app(self):
        return None


def _ctx(ui=None, cache=None, root=None):
    return PluginContext(
        root=root or Path("."),
        store=VariableStore(),
        ui=ui,
        cache=cache if cache is not None else {},
    )


def test_ask_helpers_coerce_types():
    ui = FakeUI(
        inputs=["42"], options=["blue"], multi=[["a", "c"]], secrets=["password"]
    )
    ctx = _ctx(ui)
    assert ctx.ask_input("n?", datatype="int") == 42
    assert ctx.ask_secret("password?") == "password"
    assert ctx.ask_option("color?", ["red", "blue"]) == "blue"
    assert ctx.ask_multi("tags?", ["a", "b", "c"]) == ["a", "c"]


def test_ctx_run_survey_with_resolve_options():
    ui = FakeUI(options=["Physics"])
    ctx = _ctx(ui)
    survey = [SurveyElement("Курс?", Answer(type="option", options=[]), var_name="course")]
    answers = ctx.run_survey(survey, resolve_options=lambda el, ans: ["Physics", "Math"])
    assert answers["course"] == "Physics"
    assert survey[0].answer.options == ["Physics", "Math"]


class BranchingTool(StagedTool):
    id = "branch"
    initial = "start"

    def stages(self):
        return [
            Stage("start", self._start),
            Stage("blue_branch", self._blue),
            Stage("finish", self._finish),
        ]

    def _start(self, ctx):
        color = ctx.ask_option("Цвет?", ["red", "blue"])
        # red -> сразу finish (пропуск blue_branch); blue -> по порядку в blue_branch
        return StageResult(values={"color": color}, next="finish" if color == "red" else None)

    def _blue(self, ctx):
        return {"blue_seen": True}

    def _finish(self, ctx):
        # видит значение предыдущего этапа через store
        assert ctx.store.get("color") is not None
        return {"done": True}


def test_staged_tool_red_branch_skips_middle():
    ui = FakeUI(options=["red"])
    ctx = _ctx(ui)
    result = BranchingTool().run(ctx)
    assert result == {"color": "red", "done": True}
    assert "blue_seen" not in result
    assert ctx.store.get("color") == "red"


def test_staged_tool_blue_branch_sequential():
    ui = FakeUI(options=["blue"])
    ctx = _ctx(ui)
    result = BranchingTool().run(ctx)
    assert result == {"color": "blue", "blue_seen": True, "done": True}


def test_per_stage_cache_skips_rerun():
    calls = {"n": 0}

    def stage_run(ctx):
        calls["n"] += 1
        return {"v": ctx.ask_input("x?")}

    stages = [Stage("s", stage_run, cached=True)]
    shared_cache: dict[str, object] = {}

    ui1 = FakeUI(inputs=["first"])
    ctx1 = _ctx(ui1, cache=shared_cache)
    assert drive_stages(stages, "s", ctx1) == {"v": "first"}
    assert calls["n"] == 1

    # второй прогон с тем же кэшем: этап не выполняется повторно
    ui2 = FakeUI(inputs=["second"])
    ctx2 = _ctx(ui2, cache=shared_cache)
    assert drive_stages(stages, "s", ctx2) == {"v": "first"}
    assert calls["n"] == 1
    assert ctx2.store.get("v") == "first"


def test_simple_external_tool_still_works():
    from context_wizard.plugins import ExternalTool

    class Simple(ExternalTool):
        id = "simple"

        def run(self, context):
            return {"k": "v"}

    assert Simple().run(_ctx()) == {"k": "v"}
