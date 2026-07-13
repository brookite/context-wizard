"""Формирование и запись результата сборки."""

from context_wizard.output.dto import RichPromptDTO
from context_wizard.output.writer import (
    PROMPT_FILENAME,
    OutputOptions,
    resolve_output_options,
    write_output,
)

__all__ = [
    "PROMPT_FILENAME",
    "OutputOptions",
    "RichPromptDTO",
    "resolve_output_options",
    "write_output",
]
