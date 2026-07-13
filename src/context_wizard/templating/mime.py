"""Определение «текстовости» файла для решения об inlining."""

from __future__ import annotations

import mimetypes
from pathlib import Path

# MIME-типы вне text/*, которые всё же считаем текстом и допускаем inline.
_TEXT_LIKE_MIME = {
    "application/json",
    "application/xml",
    "application/javascript",
    "application/x-yaml",
    "application/x-sh",
    "application/x-toml",
    "application/toml",
    "image/svg+xml",
}

# Расширения, которые mimetypes не всегда распознаёт как текст.
_TEXT_LIKE_EXT = {
    ".md",
    ".markdown",
    ".txt",
    ".rst",
    ".toml",
    ".yaml",
    ".yml",
    ".ini",
    ".cfg",
    ".env",
    ".csv",
    ".tsv",
    ".log",
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".json",
    ".xml",
    ".html",
    ".css",
    ".sql",
}

_SNIFF_BYTES = 4096


def is_text_file(path: Path) -> bool:
    """Эвристически определить, является ли файл текстовым (пригодным для inline)."""
    if not path.is_file():
        return False

    suffix = path.suffix.lower()
    if suffix in _TEXT_LIKE_EXT:
        return True

    guessed, _ = mimetypes.guess_type(path.name)
    if guessed is not None:
        if guessed.startswith("text/"):
            return True
        return guessed in _TEXT_LIKE_MIME

    # Тип не распознан — принюхиваемся к содержимому.
    return _looks_textual(path)


def _looks_textual(path: Path) -> bool:
    try:
        chunk = path.read_bytes()[:_SNIFF_BYTES]
    except OSError:
        return False
    if not chunk:
        return True
    if b"\x00" in chunk:
        return False
    try:
        chunk.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True
