"""Система плагинов ContextWizard: внешние инструменты и приёмники ответа."""

from context_wizard.plugins.base import (
    AnswerTarget,
    ExternalTool,
    PluginContext,
)
from context_wizard.plugins.discovery import builtin_plugins_dir, discover_plugins
from context_wizard.plugins.registry import PluginRegistry
from context_wizard.plugins.staging import Stage, StagedTool, StageResult, drive_stages

__all__ = [
    "AnswerTarget",
    "ExternalTool",
    "PluginContext",
    "PluginRegistry",
    "Stage",
    "StageResult",
    "StagedTool",
    "builtin_plugins_dir",
    "discover_plugins",
    "drive_stages",
]
