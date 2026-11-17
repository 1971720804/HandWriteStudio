"""手写参数预设的保存与读取。"""
from __future__ import annotations

import json
import os
from pathlib import Path

from PySide6.QtCore import QStandardPaths


def _config_dir() -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation)
    path = Path(base) if base else Path.home() / ".handwrite_studio"
    path.mkdir(parents=True, exist_ok=True)
    return path


def presets_path() -> Path:
    return _config_dir() / "presets.json"


def load_presets() -> dict[str, dict]:
    path = presets_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(name): value for name, value in data.items() if isinstance(value, dict)}


def save_presets(presets: dict[str, dict]) -> None:
    path = presets_path()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(presets, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp, path)
