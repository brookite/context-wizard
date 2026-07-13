"""Загрузка переменных из ``.json`` и ``.env`` файлов.

Вложенные объекты JSON разворачиваются в плоские идентификаторы через точку:
``{"a": {"b": 1}}`` -> ``{"a.b": 1}``.
"""

from __future__ import annotations

import json
from pathlib import Path


def load_vars_file(path: Path) -> dict[str, object]:
    """Загрузить переменные из файла по расширению (.json или .env)."""
    suffix = path.suffix.lower()
    if suffix == ".json":
        return _load_json(path)
    if suffix == ".env":
        return _load_env(path)
    raise ValueError(f"Неподдерживаемое расширение файла переменных: {path.name!r}")


def _load_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Ожидался JSON-объект в {path.name!r}")
    flat: dict[str, object] = {}
    _flatten(data, prefix="", out=flat)
    return flat


def _flatten(obj: dict[str, object], *, prefix: str, out: dict[str, object]) -> None:
    for key, value in obj.items():
        full = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            _flatten(value, prefix=full, out=out)
        else:
            out[full] = value


def _load_env(path: Path) -> dict[str, object]:
    result: dict[str, object] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = _unquote(value.strip())
    return result


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value
