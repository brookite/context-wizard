import json

import pytest

from context_wizard.surveys import (
    AnswerValidationError,
    SurveyElement,
    SurveyError,
    coerce,
    find_survey,
    load_survey,
    run_survey,
    validate_input,
)
from context_wizard.surveys.model import Answer, AnswerType
from context_wizard.surveys.schema import build_survey, validate_schema


class FakePrompter:
    def __init__(self, inputs=None, options=None, multi=None):
        self.inputs = inputs or {}
        self.options = options or {}
        self.multi = multi or {}

    def ask_input(self, element):
        return self.inputs[element.var_name]

    def ask_option(self, element):
        return self.options[element.var_name]

    def ask_multi(self, element):
        return self.multi[element.var_name]


def _element(var_name="v", type: AnswerType = "input", **answer_kwargs):
    return SurveyElement(
        question="Q?",
        answer=Answer(type=type, **answer_kwargs),
        var_name=var_name,
    )


def test_coerce_types():
    assert coerce("42", "int") == 42
    assert coerce("3.14", "float") == 3.14
    assert coerce("yes", "bool") is True
    assert coerce("нет", "bool") is False
    assert coerce("https://x.io/a", "url") == "https://x.io/a"
    assert coerce("a@b.co", "email") == "a@b.co"


def test_coerce_invalid_int():
    with pytest.raises(AnswerValidationError):
        coerce("abc", "int")


def test_validate_input_length_and_regex():
    el = _element(max_input_length=3)
    with pytest.raises(AnswerValidationError):
        validate_input("toolong", el)

    el2 = _element(validation_regex=r"[A-Z]{2}")
    with pytest.raises(AnswerValidationError):
        validate_input("ab", el2)
    assert validate_input("AB", el2) == "AB"


def test_run_survey_collects_answers():
    survey = [
        _element("name", "input"),
        _element("color", "option", options=["red", "blue"]),
        _element("tags", "multi selection", options=["a", "b", "c"]),
    ]
    prompter = FakePrompter(
        inputs={"name": "Alice"},
        options={"color": "blue"},
        multi={"tags": ["a", "c"]},
    )
    answers = run_survey(survey, prompter)
    assert answers == {"name": "Alice", "color": "blue", "tags": ["a", "c"]}


def test_run_survey_uses_cache():
    survey = [SurveyElement(question="Q", answer=Answer(type="input"), var_name="v", cached=True)]
    cache: dict[str, object] = {"v": "cached"}
    prompter = FakePrompter(inputs={"v": "fresh"})
    answers = run_survey(survey, prompter, cache=cache)
    assert answers["v"] == "cached"


def test_run_survey_populates_cache():
    survey = [SurveyElement(question="Q", answer=Answer(type="input"), var_name="v", cached=True)]
    cache: dict[str, object] = {}
    prompter = FakePrompter(inputs={"v": "fresh"})
    run_survey(survey, prompter, cache=cache)
    assert cache["v"] == "fresh"


def test_run_survey_resolve_options_hook():
    survey = [_element("course", "option", options=[])]
    prompter = FakePrompter(options={"course": "Physics"})

    def resolve(element, answers):
        assert element.var_name == "course"
        return ["Physics", "Math"]

    answers = run_survey(survey, prompter, resolve_options=resolve)
    assert answers["course"] == "Physics"
    assert survey[0].answer.options == ["Physics", "Math"]


def test_run_survey_on_answer_and_should_ask_hooks():
    survey = [_element("a", "input"), _element("b", "input")]
    prompter = FakePrompter(inputs={"a": "1", "b": "2"})
    seen: list[tuple[str, object]] = []

    def on_answer(element, value, answers):
        seen.append((element.var_name, value))

    def should_ask(element, answers):
        return element.var_name != "b"  # пропускаем b

    answers = run_survey(survey, prompter, on_answer=on_answer, should_ask=should_ask)
    assert answers == {"a": "1"}
    assert seen == [("a", "1")]


def test_schema_validation_rejects_bad_type():
    with pytest.raises(SurveyError):
        validate_schema([{"question": "Q", "varName": "v", "answer": {"type": "bogus"}}])


def test_schema_requires_var_name():
    with pytest.raises(SurveyError):
        validate_schema([{"question": "Q", "answer": {"type": "input"}}])


def test_build_survey_prunes_irrelevant_fields():
    data = [
        {
            "question": "Q",
            "varName": "v",
            "answer": {"type": "input", "options": ["x"], "maxInputLength": 5},
        }
    ]
    validate_schema(data)
    survey, warnings = build_survey(data)
    # options неприменимо для input -> отсечено с предупреждением
    assert survey[0].answer.options == []
    assert survey[0].answer.max_input_length == 5
    assert any("options" in w for w in warnings)


def test_load_survey_with_options_path(tmp_path):
    (tmp_path / "surveys").mkdir()
    (tmp_path / "opts.txt").write_text("one\ntwo\n\nthree\n", encoding="utf-8")
    survey_data = [
        {
            "question": "Pick",
            "varName": "choice",
            "answer": {"type": "option", "options": ["zero"], "optionsPath": "opts.txt"},
        }
    ]
    survey_file = tmp_path / "surveys" / "task.json"
    survey_file.write_text(json.dumps(survey_data), encoding="utf-8")

    found = find_survey(tmp_path, "task")
    assert found is not None
    assert found == survey_file
    survey, _warnings = load_survey(found, tmp_path)
    assert survey[0].answer.options == ["zero", "one", "two", "three"]
