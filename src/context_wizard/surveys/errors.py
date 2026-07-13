"""Ошибки работы с опросниками."""

from __future__ import annotations


class SurveyError(Exception):
    """Ошибка загрузки, валидации или прохождения опросника."""


class AnswerValidationError(Exception):
    """Ответ пользователя не прошёл валидацию."""
