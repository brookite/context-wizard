"""Разворачивание ``$NAME`` / ``$(NAME)`` в путях по значениям из хранилища."""

from __future__ import annotations

import re

from context_wizard.state import VariableStore

_VAR_RE = re.compile(r"\$\((\w+)\)|\$(\w+)")


def expand_vars(
    text: str,
    store: VariableStore,
    skip: frozenset[str] = frozenset(),
) -> tuple[str, set[str]]:
    """Развернуть ``$NAME`` / ``$(NAME)`` в тексте.

    Возвращает развёрнутый текст и множество имён, значения которых отсутствуют
    (и которые не занесены в ``skip``). Отсутствующие/пропущенные разворачиваются
    в пустую строку.
    """
    missing: set[str] = set()

    def replace(match: re.Match[str]) -> str:
        name = match.group(1) or match.group(2)
        value = store.get_text(name)
        if value is None:
            if name not in skip:
                missing.add(name)
            return ""
        return value

    return _VAR_RE.sub(replace, text), missing
