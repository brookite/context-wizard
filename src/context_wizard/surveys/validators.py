"""Валидация и приведение типов ответов опросника."""

from __future__ import annotations

import re

from context_wizard.surveys.errors import AnswerValidationError
from context_wizard.surveys.model import DataType, SurveyElement

_URL_RE = re.compile(r"^[a-z][a-z0-9+.-]*://[^\s]+$", re.IGNORECASE)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^\+?[0-9][0-9\s()-]{5,}$")

_TRUE = {"true", "1", "yes", "y", "on", "да"}
_FALSE = {"false", "0", "no", "n", "off", "нет"}


def coerce(value: str, datatype: DataType) -> object:
    """Привести строковый ответ к целевому типу данных. Кидает AnswerValidationError."""
    text = value.strip()
    if datatype == "int":
        return _to_int(text)
    if datatype == "float":
        return _to_float(text)
    if datatype == "bool":
        return _to_bool(text)
    if datatype == "url":
        return _match(text, _URL_RE, "URL")
    if datatype == "email":
        return _match(text, _EMAIL_RE, "email")
    if datatype == "phone":
        return _match(text, _PHONE_RE, "телефон")
    # string, path — как есть.
    return value


def validate_input(value: str, element: SurveyElement) -> object:
    """Проверить свободный ввод (длина, регэксп) и привести к типу данных."""
    answer = element.answer
    if answer.max_input_length is not None and len(value) > answer.max_input_length:
        raise AnswerValidationError(
            f"Превышена максимальная длина ({answer.max_input_length}) для {element.var_name!r}"
        )
    if answer.validation_regex is not None and re.fullmatch(answer.validation_regex, value) is None:
        raise AnswerValidationError(
            f"Значение не соответствует шаблону {answer.validation_regex!r}"
        )
    return coerce(value, answer.datatype)


def _to_int(text: str) -> int:
    try:
        return int(text)
    except ValueError as exc:
        raise AnswerValidationError(f"Ожидалось целое число, получено {text!r}") from exc


def _to_float(text: str) -> float:
    try:
        return float(text)
    except ValueError as exc:
        raise AnswerValidationError(f"Ожидалось число, получено {text!r}") from exc


def _to_bool(text: str) -> bool:
    lowered = text.lower()
    if lowered in _TRUE:
        return True
    if lowered in _FALSE:
        return False
    raise AnswerValidationError(f"Ожидалось булево значение, получено {text!r}")


def _match(text: str, pattern: re.Pattern[str], label: str) -> str:
    if pattern.fullmatch(text) is None and pattern.match(text) is None:
        raise AnswerValidationError(f"Некорректный {label}: {text!r}")
    return text
