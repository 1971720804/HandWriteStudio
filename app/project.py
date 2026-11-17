"""项目文件（.hws）：HTML + 手写参数，JSON 存储。"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .settings import HandStyle

PROJECT_VERSION = 1
PROJECT_SUFFIX = ".hws"


def save_project(path: str, html: str, style: HandStyle) -> None:
    data = {
        "app": "HandWriteStudio",
        "version": PROJECT_VERSION,
        "html": html,
        "style": style.to_dict(),
    }
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=target.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


def load_project(path: str) -> tuple[str, HandStyle]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or "html" not in data:
        raise ValueError("不是有效的 HandWriteStudio 项目文件")
    style = HandStyle.from_dict(data.get("style") or {})
    return str(data["html"]), style
