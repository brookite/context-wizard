"""JSON Schema опросника и разбор сырых данных в модель.

Поля, неподходящие для заданного типа ответа, отсекаются с предупреждением
(а не считаются ошибкой), как требует спецификация.
"""

from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator

from context_wizard.surveys.errors import SurveyError
from context_wizard.surveys.model import (
    ANSWER_TYPES,
    DATA_TYPES,
    Answer,
    Survey,
    SurveyElement,
)

SURVEY_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "array",
    "items": {
        "type": "object",
        "required": ["question", "answer", "varName"],
        "additionalProperties": False,
        "properties": {
            "question": {"type": "string"},
            "varName": {"type": "string", "minLength": 1},
            "cached": {"type": "boolean"},
            "answer": {
                "type": "object",
                "required": ["type"],
                "additionalProperties": False,
                "properties": {
                    "type": {"enum": list(ANSWER_TYPES)},
                    "datatype": {"enum": list(DATA_TYPES)},
                    "hint": {"type": "string"},
                    "options": {"type": "array", "items": {"type": "string"}},
                    "optionsPath": {"type": "string"},
                    "maxInputLength": {"type": "integer", "minimum": 1},
                    "validationRegex": {"type": "string"},
                    "usesValidator": {"type": "string"},
                },
            },
        },
    },
}

_validator = Draft202012Validator(SURVEY_SCHEMA)

# Поля ответа, релевантные только для конкретных типов.
_INPUT_ONLY = ("maxInputLength", "validationRegex")
_OPTION_ONLY = ("options", "optionsPath")


def validate_schema(data: Any) -> None:
    """Проверить сырые данные опросника по JSON Schema. Кидает SurveyError при ошибке."""
    errors = sorted(_validator.iter_errors(data), key=lambda e: list(e.path))
    if errors:
        messages = "; ".join(f"{list(e.path)}: {e.message}" for e in errors)
        raise SurveyError(f"Опросник не прошёл валидацию: {messages}")


def build_survey(data: list[dict[str, Any]]) -> tuple[Survey, list[str]]:
    """Построить модель опросника из провалидированных данных.

    Возвращает опросник и список предупреждений об отсечённых полях.
    """
    survey: Survey = []
    warnings: list[str] = []
    for item in data:
        element, elem_warnings = _build_element(item)
        survey.append(element)
        warnings.extend(elem_warnings)
    return survey, warnings


def _build_element(item: dict[str, Any]) -> tuple[SurveyElement, list[str]]:
    warnings: list[str] = []
    raw_answer = dict(item["answer"])
    answer_type = raw_answer["type"]
    var_name = item["varName"]

    irrelevant = _INPUT_ONLY if answer_type != "input" else _OPTION_ONLY
    for key in irrelevant:
        if key in raw_answer:
            warnings.append(
                f"[{var_name}] поле {key!r} неприменимо для типа {answer_type!r} — игнорируется"
            )
            raw_answer.pop(key)

    answer = Answer(
        type=answer_type,
        datatype=raw_answer.get("datatype", "string"),
        hint=raw_answer.get("hint"),
        options=list(raw_answer.get("options", [])),
        options_path=raw_answer.get("optionsPath"),
        max_input_length=raw_answer.get("maxInputLength"),
        validation_regex=raw_answer.get("validationRegex"),
        uses_validator=raw_answer.get("usesValidator"),
    )

    needs_options = answer_type in ("option", "multi selection")
    if needs_options and not answer.options and not answer.options_path:
        warnings.append(
            f"[{var_name}] для типа {answer_type!r} не задано ни options, ни optionsPath"
        )

    return (
        SurveyElement(
            question=item["question"],
            answer=answer,
            var_name=var_name,
            cached=bool(item.get("cached", False)),
        ),
        warnings,
    )
