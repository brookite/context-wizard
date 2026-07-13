"""Конфигурация проекта: setup.toml и загрузка переменных."""

from context_wizard.config.loader import (
    ENV_DIR,
    PROMPTS_DIR,
    SETUP_FILENAME,
    SURVEYS_DIR,
    list_prompts,
    load_global_vars,
    load_prompt_vars,
    load_setup,
    prompt_id_of,
    resolve_project_root,
)
from context_wizard.config.model import AnswerTargetConfig, SetupConfig
from context_wizard.config.vars import load_vars_file

__all__ = [
    "ENV_DIR",
    "PROMPTS_DIR",
    "SETUP_FILENAME",
    "SURVEYS_DIR",
    "AnswerTargetConfig",
    "SetupConfig",
    "list_prompts",
    "load_global_vars",
    "load_prompt_vars",
    "load_setup",
    "load_vars_file",
    "prompt_id_of",
    "resolve_project_root",
]
