import json
from pathlib import Path

import pytest

from context_wizard.app import Collector, CollectorOptions
from context_wizard.config import load_setup
from context_wizard.output import PROMPT_FILENAME, OutputOptions, resolve_output_options
from context_wizard.plugins import AnswerDeliveryError
from context_wizard.surveys import SurveyElement
from context_wizard.ui import WizardAborted


class HeadlessUI:
    """Неинтерактивная реализация WizardUI для e2e-тестов."""

    def __init__(
        self,
        *,
        prompt_id: str | None = None,
        inputs: dict[str, str] | None = None,
        options: dict[str, str] | None = None,
        multi: dict[str, list[str]] | None = None,
        skip_missing: bool = True,
        abort_on_missing: bool = False,
    ) -> None:
        self.prompt_id = prompt_id
        self.inputs = inputs or {}
        self.options = options or {}
        self.multi = multi or {}
        self.skip_missing = skip_missing
        self.abort_on_missing = abort_on_missing
        self.notifications: list[str] = []

    def select_prompt(self, prompts: list[Path]) -> Path:
        if self.prompt_id is not None:
            for path in prompts:
                if path.stem == self.prompt_id:
                    return path
        return prompts[0]

    def ask_input(self, element: SurveyElement) -> str:
        return self.inputs[element.var_name]

    def ask_secret(self, question: str, *, hint: str | None = None) -> str:
        return self.inputs[question]

    def ask_option(self, element: SurveyElement) -> str:
        return self.options[element.var_name]

    def ask_multi(self, element: SurveyElement) -> list[str]:
        return self.multi[element.var_name]

    def resolve_missing(self, missing: list[str]) -> set[str]:
        if self.abort_on_missing:
            raise WizardAborted("недостающие переменные")
        return set(missing) if self.skip_missing else set()

    def notify(self, message: str) -> None:
        self.notifications.append(message)

    def push_screen(self, screen):
        raise NotImplementedError("headless UI не поддерживает push_screen")

    @property
    def app(self):
        return None


def _build_project(root: Path) -> None:
    (root / "prompts").mkdir()
    (root / "env").mkdir()
    (root / "surveys").mkdir()
    (root / "assets").mkdir()

    (root / "vars.json").write_text(
        json.dumps({"course": {"name": "Physics"}, "teacher": "Dr. Global"}),
        encoding="utf-8",
    )
    (root / "env" / "task.json").write_text(
        json.dumps({"teacher": "Dr. Prompt"}), encoding="utf-8"
    )
    (root / "assets" / "rubric.txt").write_text("Grading rubric body", encoding="utf-8")
    (root / "assets" / "diagram.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00")

    (root / "surveys" / "task.json").write_text(
        json.dumps(
            [
                {
                    "question": "Student name?",
                    "varName": "student",
                    "answer": {"type": "input", "datatype": "string"},
                },
                {
                    "question": "Grade?",
                    "varName": "grade",
                    "answer": {"type": "option", "options": ["A", "B", "C"]},
                },
            ]
        ),
        encoding="utf-8",
    )

    (root / "prompts" / "task.md").write_text(
        "Course: {{ course.name }}\n"
        "Teacher: {{ teacher }}\n"
        "Student: {{ student }} got {{ grade }}\n"
        "Rubric: {{ file: assets/rubric.txt }}\n"
        "Diagram: {{ file: assets/diagram.png }}\n"
        "Ref: {{ @assets/diagram.png }}\n",
        encoding="utf-8",
    )


def test_full_pipeline(tmp_path):
    _build_project(tmp_path)
    config = load_setup(tmp_path)
    ui = HeadlessUI(prompt_id="task", inputs={"student": "Alice"}, options={"grade": "A"})
    collector = Collector(tmp_path, config, ui)

    out_dir = tmp_path / "out"
    options = CollectorOptions(
        output=resolve_output_options(prompt_output=None, file_output=None, output=str(out_dir)),
        prompt_id="task",
    )
    dto = collector.run(options)

    assert "Course: Physics" in dto.prompt
    # env/ промпта перекрывает глобальные vars
    assert "Teacher: Dr. Prompt" in dto.prompt
    assert "Student: Alice got A" in dto.prompt
    # текстовый файл встроен inline
    assert "Rubric: Grading rubric body" in dto.prompt
    # бинарный файл -> относительный путь + вложение
    assert "Diagram: assets/diagram.png" in dto.prompt
    assert "Ref: assets/diagram.png" in dto.prompt
    assert any(p.name == "diagram.png" for p in dto.attachments)
    assert len(dto.attachments) == 1

    assert (out_dir / PROMPT_FILENAME).is_file()
    assert (out_dir / "diagram.png").is_file()


def test_survey_answers_override_prompt_env(tmp_path):
    (tmp_path / "prompts").mkdir()
    (tmp_path / "env").mkdir()
    (tmp_path / "surveys").mkdir()
    (tmp_path / "env" / "p.json").write_text(json.dumps({"x": "env"}), encoding="utf-8")
    (tmp_path / "surveys" / "p.json").write_text(
        json.dumps([{"question": "x?", "varName": "x", "answer": {"type": "input"}}]),
        encoding="utf-8",
    )
    (tmp_path / "prompts" / "p.txt").write_text("val={{ x }}", encoding="utf-8")

    config = load_setup(tmp_path)
    ui = HeadlessUI(inputs={"x": "survey"})
    collector = Collector(tmp_path, config, ui)
    options = CollectorOptions(output=OutputOptions(), prompt_id="p")
    dto = collector.run(options)
    assert dto.prompt == "val=survey"


def test_missing_variable_abort(tmp_path):
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "p.txt").write_text("{{ absent }}", encoding="utf-8")
    config = load_setup(tmp_path)
    ui = HeadlessUI(abort_on_missing=True)
    collector = Collector(tmp_path, config, ui)
    options = CollectorOptions(output=OutputOptions(), prompt_id="p")
    with pytest.raises(WizardAborted):
        collector.run(options)


def test_missing_variable_skip(tmp_path):
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "p.txt").write_text("[{{ absent }}]", encoding="utf-8")
    config = load_setup(tmp_path)
    ui = HeadlessUI(skip_missing=True)
    collector = Collector(tmp_path, config, ui)
    options = CollectorOptions(output=OutputOptions(), prompt_id="p")
    dto = collector.run(options)
    assert dto.prompt == "[]"


_RECORDER_PLUGIN = '''
from context_wizard.plugins import AnswerTarget


class Recorder(AnswerTarget):
    id = "recorder"

    def deliver(self, dto, context):
        (context.root / "delivered.txt").write_text(dto.prompt, encoding="utf-8")
'''


def test_answer_target_override_selects_plugin(tmp_path):
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "p.txt").write_text("hello target", encoding="utf-8")
    (tmp_path / "plugins").mkdir()
    (tmp_path / "plugins" / "rec.py").write_text(_RECORDER_PLUGIN, encoding="utf-8")

    config = load_setup(tmp_path)  # в setup.toml приёмник не задан
    assert config.answer_target is None

    collector = Collector(tmp_path, config, HeadlessUI())
    options = CollectorOptions(
        output=OutputOptions(), prompt_id="p", answer_target_ids=["recorder"]
    )
    collector.run(options)
    assert (tmp_path / "delivered.txt").read_text(encoding="utf-8") == "hello target"


_CONCURRENT_TARGETS = '''
from threading import Barrier

from context_wizard.plugins import AnswerTarget


barrier = Barrier(2)


class First(AnswerTarget):
    id = "first"

    def deliver(self, dto, context):
        barrier.wait(timeout=2)
        (context.root / "first.txt").write_text(dto.prompt, encoding="utf-8")


class Second(AnswerTarget):
    id = "second"

    def deliver(self, dto, context):
        barrier.wait(timeout=2)
        (context.root / "second.txt").write_text(dto.prompt, encoding="utf-8")
'''


def test_answer_targets_run_concurrently(tmp_path):
    (tmp_path / "prompts").mkdir()
    (tmp_path / "plugins").mkdir()
    (tmp_path / "prompts" / "p.txt").write_text("parallel", encoding="utf-8")
    (tmp_path / "plugins" / "parallel.py").write_text(
        _CONCURRENT_TARGETS, encoding="utf-8"
    )

    Collector(tmp_path, load_setup(tmp_path), HeadlessUI()).run(
        CollectorOptions(
            output=OutputOptions(),
            prompt_id="p",
            answer_target_ids=["first", "second"],
        )
    )

    assert (tmp_path / "first.txt").read_text(encoding="utf-8") == "parallel"
    assert (tmp_path / "second.txt").read_text(encoding="utf-8") == "parallel"


_PARTIAL_FAILURE_TARGETS = '''
from context_wizard.plugins import AnswerTarget


class Failing(AnswerTarget):
    id = "failing"

    def deliver(self, dto, context):
        raise RuntimeError("failed on purpose")


class Successful(AnswerTarget):
    id = "successful"

    def deliver(self, dto, context):
        (context.root / "successful.txt").write_text(dto.prompt, encoding="utf-8")
'''


def test_answer_delivery_waits_for_successful_target_and_aggregates_errors(tmp_path):
    (tmp_path / "prompts").mkdir()
    (tmp_path / "plugins").mkdir()
    (tmp_path / "prompts" / "p.txt").write_text("body", encoding="utf-8")
    (tmp_path / "plugins" / "targets.py").write_text(
        _PARTIAL_FAILURE_TARGETS, encoding="utf-8"
    )

    with pytest.raises(AnswerDeliveryError) as captured:
        Collector(tmp_path, load_setup(tmp_path), HeadlessUI()).run(
            CollectorOptions(
                output=OutputOptions(),
                prompt_id="p",
                answer_target_ids=["failing", "successful"],
            )
        )

    assert (tmp_path / "successful.txt").read_text(encoding="utf-8") == "body"
    assert [plugin_id for plugin_id, _ in captured.value.failures] == ["failing"]
    assert "failed on purpose" in str(captured.value)


def test_cli_target_settings_are_preserved_and_use_fs_is_conservative(tmp_path):
    (tmp_path / "prompts").mkdir()
    (tmp_path / "plugins").mkdir()
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "notes.txt").write_text("inline body", encoding="utf-8")
    (tmp_path / "prompts" / "p.txt").write_text(
        "{{ file: assets/notes.txt }}", encoding="utf-8"
    )
    (tmp_path / "plugins" / "targets.py").write_text(
        '''
from context_wizard.plugins import AnswerTarget


class First(AnswerTarget):
    id = "first"

    def deliver(self, dto, context):
        (context.root / "settings.txt").write_text(
            f"{context.settings['marker']}|{dto.prompt}", encoding="utf-8"
        )


class Second(AnswerTarget):
    id = "second"

    def deliver(self, dto, context):
        pass
''',
        encoding="utf-8",
    )
    (tmp_path / "setup.toml").write_text(
        '[[answer_targets]]\nid = "first"\nuse_fs = true\n'
        '[answer_targets.settings]\nmarker = "kept"\n\n'
        '[[answer_targets]]\nid = "second"\nuse_fs = false\n',
        encoding="utf-8",
    )

    Collector(tmp_path, load_setup(tmp_path), HeadlessUI()).run(
        CollectorOptions(
            output=OutputOptions(),
            prompt_id="p",
            answer_target_ids=["first", "second"],
        )
    )

    assert (tmp_path / "settings.txt").read_text(encoding="utf-8") == "kept|notes.txt"


def test_cached_survey_answer_persists(tmp_path):
    (tmp_path / "prompts").mkdir()
    (tmp_path / "surveys").mkdir()
    (tmp_path / "surveys" / "p.json").write_text(
        json.dumps(
            [{"question": "x?", "varName": "x", "answer": {"type": "input"}, "cached": True}]
        ),
        encoding="utf-8",
    )
    (tmp_path / "prompts" / "p.txt").write_text("val={{ x }}", encoding="utf-8")

    config = load_setup(tmp_path)
    options = CollectorOptions(output=OutputOptions(), prompt_id="p")

    Collector(tmp_path, config, HeadlessUI(inputs={"x": "first"})).run(options)
    # второй запуск: кэш возвращает первый ответ, даже если ввод другой
    dto = Collector(tmp_path, config, HeadlessUI(inputs={"x": "second"})).run(options)
    assert dto.prompt == "val=first"


_FAILING_CACHE_PLUGIN = '''
from context_wizard.plugins import ExternalTool


class FailingCacheTool(ExternalTool):
    id = "failing-cache"

    def run(self, context):
        context.cache["sessions"] = {"site": {"cookie": "saved"}}
        raise RuntimeError("later stage failed")
'''


def test_external_tool_cache_is_saved_when_tool_fails(tmp_path):
    (tmp_path / "prompts").mkdir()
    (tmp_path / "plugins").mkdir()
    (tmp_path / "prompts" / "p.txt").write_text("{{ result }}", encoding="utf-8")
    (tmp_path / "plugins" / "failing.py").write_text(
        _FAILING_CACHE_PLUGIN, encoding="utf-8"
    )
    (tmp_path / "setup.toml").write_text(
        'external_tool = "failing-cache"\nplugins_dir = "plugins"\n',
        encoding="utf-8",
    )

    collector = Collector(tmp_path, load_setup(tmp_path), HeadlessUI())
    with pytest.raises(RuntimeError, match="later stage failed"):
        collector.run(CollectorOptions(output=OutputOptions(), prompt_id="p"))

    assert collector.cache.load_tool_cache("failing-cache") == {
        "sessions": {"site": {"cookie": "saved"}}
    }
