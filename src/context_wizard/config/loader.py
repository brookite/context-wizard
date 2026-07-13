"""Резолв корня проекта, загрузка ``setup.toml`` и переменных."""

from __future__ import annotations

import tomllib
from pathlib import Path

from context_wizard.config.model import SetupConfig
from context_wizard.config.vars import load_vars_file

SETUP_FILENAME = "setup.toml"
PROMPTS_DIR = "prompts"
ENV_DIR = "env"
SURVEYS_DIR = "surveys"

_AUTO_VARS_FILES = ("vars.json", "vars.env")
_VAR_EXTENSIONS = (".json", ".env")


def resolve_project_root(cli_path: str | None) -> Path:
    """Определить корень проекта: аргумент CLI, иначе текущий каталог."""
    root = Path(cli_path).expanduser() if cli_path else Path.cwd()
    root = root.resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"Каталог проекта не найден: {root}")
    return root


def load_setup(root: Path) -> SetupConfig:
    """Загрузить ``setup.toml`` из корня проекта (или вернуть значения по умолчанию)."""
    setup_path = root / SETUP_FILENAME
    if not setup_path.is_file():
        return SetupConfig()
    data = tomllib.loads(setup_path.read_text(encoding="utf-8"))
    return SetupConfig.model_validate(data)


def load_global_vars(root: Path, config: SetupConfig) -> dict[str, object]:
    """Загрузить глобальные переменные проекта (vars.json/vars.env или из vars_storage)."""
    if config.vars_storage:
        path = (root / config.vars_storage).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"vars_storage не найден: {path}")
        return load_vars_file(path)

    for candidate in _AUTO_VARS_FILES:
        path = root / candidate
        if path.is_file():
            return load_vars_file(path)
    return {}


def load_prompt_vars(root: Path, prompt_id: str) -> dict[str, object]:
    """Загрузить переменные для конкретного промпта из ``env/<prompt>.{json,env}``."""
    for ext in _VAR_EXTENSIONS:
        path = root / ENV_DIR / f"{prompt_id}{ext}"
        if path.is_file():
            return load_vars_file(path)
    return {}


def list_prompts(root: Path) -> list[Path]:
    """Список файлов промптов из каталога ``prompts/`` (отсортированный)."""
    prompts_dir = root / PROMPTS_DIR
    if not prompts_dir.is_dir():
        return []
    return sorted(p for p in prompts_dir.iterdir() if p.is_file())


def prompt_id_of(prompt_path: Path) -> str:
    """Идентификатор промпта — имя файла без расширения."""
    return prompt_path.stem
