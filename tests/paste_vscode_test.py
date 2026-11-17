from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QMimeData
from PySide6.QtWidgets import QApplication

from app.editor import Editor
from app.renderer import HandRenderer
from app.settings import HandStyle

app = QApplication([])
editor = Editor()

# 模拟 VS Code 复制出来的 HTML：深色底、浅色字、Consolas
lines = []
for i in range(80):
    lines.append(
        f'<span style="color:#d4d4d4;background-color:#1e1e1e;'
        f'font-family:Consolas,monospace;">def f{i}(x): return x + {i}</span><br>'
    )
html = "".join(lines)
mime = QMimeData()
mime.setHtml(html)
mime.setText("def f(x): return x\n" * 80)
start = time.time()
try:
    editor.insertFromMimeData(mime)
    print("insert ok", len(editor.toHtml()), time.time() - start)
    style = HandStyle()
    renderer = HandRenderer(editor.content_html(), style)
    print("render ok pages", renderer.page_count(), time.time() - start)
    image = renderer.render_page_image(0, 120)
    image.save(str(Path(__file__).resolve().parent.parent / "samples" / "paste_vscode.png"))
    print("image", image.width(), image.height(), time.time() - start)
except Exception as exc:
    print("ERROR", type(exc).__name__, exc)
