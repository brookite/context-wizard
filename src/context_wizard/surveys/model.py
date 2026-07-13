"""Модель кастомного опросника."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

AnswerType = Literal["input", "option", "multi selection"]
DataType = Literal["int", "string", "path", "bool", "float", "url", "email", "phone"]

ANSWER_TYPES: tuple[AnswerType, ...] = ("input", "option", "multi selection")
DATA_TYPES: tuple[DataType, ...] = (
    "int",
    "string",
    "path",
    "bool",
    "float",
    "url",
    "email",
    "phone",
)


@dataclass
class Answer:
    """Описание ожидаемого ответа на элемент опросника."""

    type: AnswerType
    datatype: DataType = "string"
    hint: str | None = None
    options: list[str] = field(default_factory=list)
    options_path: str | None = None
    max_input_length: int | None = None
    validation_regex: str | None = None
    uses_validator: str | None = None


@dataclass
class SurveyElement:
    """Один вопрос опросника."""

    question: str
    answer: Answer
    var_name: str
    cached: bool = False


Survey = list[SurveyElement]
