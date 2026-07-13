"""Рендеринг шаблона в текст промпта с регистрацией вложений."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from context_wizard.state import VariableStore
from context_wizard.templating.expander import expand_vars
from context_wizard.templating.mime import is_text_file
from context_wizard.templating.parser import (
    FileNode,
    TextNode,
    VarNode,
    parse_template,
)


@dataclass
class RenderResult:
    """Результат рендеринга шаблона.

    ``missing`` — имена переменных/пути, для которых не нашлось значения и которые не были
    занесены в ``skip``. Такие места развёрнуты в пустую строку, но требуют внимания
    пользователя перед финализацией.
    """

    text: str
    attachments: list[Path] = field(default_factory=list)
    missing: set[str] = field(default_factory=set)


def render(
    template: str,
    *,
    store: VariableStore,
    root: Path,
    use_fs: bool = True,
    skip: frozenset[str] = frozenset(),
) -> RenderResult:
    """Отрендерить шаблон.

    :param store: хранилище переменных.
    :param root: корень проекта — относительно него резолвятся и отображаются пути.
    :param use_fs: может ли приёмник читать файлы. Если False — inline не выполняется,
        а файлы вставляются просто по базовому имени.
    :param skip: имена, которые пользователь согласился пропустить (развернуть в пустоту).
    """
    parts: list[str] = []
    attachments: list[Path] = []
    seen_attachments: set[Path] = set()
    missing: set[str] = set()

    def register(path: Path) -> None:
        norm = _normalize(path)
        if norm not in seen_attachments:
            seen_attachments.add(norm)
            attachments.append(norm)

    for node in parse_template(template):
        if isinstance(node, TextNode):
            parts.append(node.text)
        elif isinstance(node, VarNode):
            value = store.get_text(node.name)
            if value is None:
                if node.name not in skip:
                    missing.add(node.name)
                parts.append("")
            else:
                parts.append(value)
        elif isinstance(node, FileNode):
            parts.append(
                _render_file(
                    node,
                    store=store,
                    root=root,
                    use_fs=use_fs,
                    skip=skip,
                    missing=missing,
                    register=register,
                )
            )

    return RenderResult(text="".join(parts), attachments=attachments, missing=missing)


def _render_file(
    node: FileNode,
    *,
    store: VariableStore,
    root: Path,
    use_fs: bool,
    skip: frozenset[str],
    missing: set[str],
    register: Callable[[Path], None],
) -> str:
    path_str = node.path
    if node.expand:
        path_str, path_missing = expand_vars(path_str, store, skip)
        missing |= path_missing

    if not path_str:
        return ""

    abs_path = _resolve(path_str, root)
    display = _display_path(abs_path, root, use_fs)

    if not use_fs:
        # Приёмник не читает ФС: любой файл — просто по имени, существование не проверяем.
        return display

    if node.allow_inline and is_text_file(abs_path):
        try:
            return abs_path.read_text(encoding="utf-8")
        except OSError:
            if display not in skip:
                missing.add(display)
            return ""

    # Ссылка на файл/папку (не-inline или бинарный файл).
    if abs_path.exists():
        register(abs_path)
    elif display not in skip:
        missing.add(display)
    return display


def _resolve(path_str: str, root: Path) -> Path:
    raw = Path(path_str)
    combined = raw if raw.is_absolute() else root / raw
    return _normalize(combined)


def _normalize(path: Path) -> Path:
    return Path(os.path.normpath(path.absolute()))


def _display_path(abs_path: Path, root: Path, use_fs: bool) -> str:
    if not use_fs:
        return abs_path.name
    try:
        rel = abs_path.relative_to(_normalize(root))
    except ValueError:
        rel = Path(os.path.relpath(abs_path, _normalize(root)))
    return rel.as_posix()
