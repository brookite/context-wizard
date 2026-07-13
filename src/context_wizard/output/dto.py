"""DTO готового богатого промпта."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RichPromptDTO:
    """Результат сборки — то, что передаётся приёмнику или выводится."""

    prompt: str
    """Готовый текст промпта со всеми подстановками."""
    attachments: list[Path] = field(default_factory=list)
    """Задействованные, не встроенные (не-inline) файлы."""
    root: Path = field(default_factory=Path)
    """Корень проекта."""
