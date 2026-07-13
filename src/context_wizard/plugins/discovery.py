"""Обнаружение плагинов (drop-in ``.py``) из нескольких каталогов.

Порядок каталогов задаёт приоритет: плагины из более поздних каталогов переопределяют
одноимённые (по ``id``) из более ранних. Обычный порядок — глобальные/встроенные, затем
проектные (проект переопределяет глобальные).
"""

from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path

from context_wizard.plugins.base import AnswerTarget, ExternalTool
from context_wizard.plugins.registry import PluginRegistry

_BUILTINS_DIRNAME = "builtins"


def builtin_plugins_dir() -> Path:
    """Каталог встроенных/глобальных плагинов внутри исходников context-wizard.

    Сюда «устанавливаются» глобальные плагины (доступные всем проектам); здесь же лежат
    встроенные, например ``codex``.
    """
    return Path(__file__).resolve().parent.parent / _BUILTINS_DIRNAME


def discover_plugins(*plugins_dirs: Path) -> PluginRegistry:
    """Загрузить плагины из перечисленных каталогов в один реестр.

    Файлы, начинающиеся с ``_`` (в т.ч. ``__init__.py``), игнорируются. Классы
    регистрируются по атрибуту ``id``; классы без непустого ``id`` пропускаются.
    Каталоги сканируются по порядку — поздние переопределяют ранние по ``id``.
    """
    registry = PluginRegistry()
    for plugins_dir in plugins_dirs:
        _scan_dir(plugins_dir, registry)
    return registry


def _scan_dir(plugins_dir: Path, registry: PluginRegistry) -> None:
    if not plugins_dir.is_dir():
        return
    for path in sorted(plugins_dir.glob("*.py")):
        if path.name.startswith("_"):
            continue
        module = _load_module(path)
        _register_from_module(module, registry)


def _load_module(path: Path):
    token = format(abs(hash(str(path.parent))) % (16**8), "08x")
    module_name = f"context_wizard_plugin_{token}_{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Не удалось загрузить плагин: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _register_from_module(module: object, registry: PluginRegistry) -> None:
    for _, obj in inspect.getmembers(module, inspect.isclass):
        if obj is ExternalTool or obj is AnswerTarget:
            continue
        if not getattr(obj, "id", ""):
            continue
        if issubclass(obj, ExternalTool):
            registry.register_external(obj)
        elif issubclass(obj, AnswerTarget):
            registry.register_answer(obj)
