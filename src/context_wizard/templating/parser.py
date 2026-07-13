"""Разбор шаблона на узлы: текст, ссылки на переменные, ссылки на файлы.

Синтаксис (внутри ``{{ ... }}``):
- ``{{ name }}``          — подстановка текстовой переменной ``name``;
- ``{{ file: path }}``    — файл: inline содержимого для текстовых, иначе относительный
                            путь; поддерживает ``$NAME`` / ``$(NAME)`` в пути;
- ``{{ @path }}``         — файл/папка как ссылка (относительный путь), без inline и без
                            разворачивания ``$``.

Идентификатор переменной — как в Python, плюс дополнительные символы ``# . , / \\ ;``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from context_wizard.templating.errors import TemplateError

_SPAN_RE = re.compile(r"\{\{(.*?)\}\}", re.DOTALL)
_NAMESPACE_RE = re.compile(r"^([A-Za-z_]\w*)\s*:\s*(.*)$", re.DOTALL)


@dataclass(frozen=True)
class TextNode:
    """Литеральный фрагмент текста вне шаблонных скобок."""

    text: str


@dataclass(frozen=True)
class VarNode:
    """Ссылка на текстовую переменную ``{{ name }}``."""

    name: str


@dataclass(frozen=True)
class FileNode:
    """Ссылка на файл/папку.

    ``allow_inline`` — можно ли встроить содержимое (True для ``file:``, False для ``@``).
    ``expand`` — разворачивать ли ``$NAME`` в пути (True для ``file:``, False для ``@``).
    """

    path: str
    allow_inline: bool
    expand: bool


Node = TextNode | VarNode | FileNode


def parse_template(template: str) -> list[Node]:
    """Разобрать строку шаблона в список узлов."""
    nodes: list[Node] = []
    last = 0
    for match in _SPAN_RE.finditer(template):
        if match.start() > last:
            nodes.append(TextNode(template[last : match.start()]))
        nodes.append(_classify(match.group(1)))
        last = match.end()
    if last < len(template):
        nodes.append(TextNode(template[last:]))
    return nodes


def _classify(inner: str) -> VarNode | FileNode:
    stripped = inner.strip()

    if stripped.startswith("@"):
        return FileNode(path=stripped[1:].strip(), allow_inline=False, expand=False)

    namespace_match = _NAMESPACE_RE.match(stripped)
    if namespace_match is not None:
        namespace = namespace_match.group(1)
        value = namespace_match.group(2).strip()
        if namespace == "file":
            return FileNode(path=value, allow_inline=True, expand=True)
        raise TemplateError(f"Неизвестный namespace шаблона: {namespace!r}")

    return VarNode(name=stripped)
