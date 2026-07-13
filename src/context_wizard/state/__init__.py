"""Управление состоянием сборщика: переменные и файловые артефакты."""

from context_wizard.state.artifacts import ArtifactRegistry
from context_wizard.state.store import Source, VariableStore

__all__ = ["ArtifactRegistry", "Source", "VariableStore"]
