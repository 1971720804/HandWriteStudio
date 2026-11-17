from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication

from app.renderer import HandRenderer
from app.settings import HandStyle

app = QApplication([])
style = HandStyle()
style.grid_mode = True
style.grid_justify = True
style.grid_rows = 31
style.grid_cols = 38
style.font_size = 12

cases = {
    "en": "RAPID" * 20,
    "mixed": "系统参数 RAPID 程序 1234567890 测试",
    "cn": "系统参数。最后，在仿真环境中编写了简单的RAPID程序，使机器人各轴回归至机械零点。" * 3,
}
content_right = round((style.page_width - style.right_margin) * 120 / 72)
for name, text in cases.items():
    renderer = HandRenderer(f"<p>{text}</p>", style)
    image = renderer.render_page_image(0, 120)
    xs: list[int] = []
    for y in range(0, image.height(), 2):
        for x in range(0, image.width(), 2):
            if image.pixelColor(x, y).red() < 128:
                xs.append(x)
    print(name, "ink right", max(xs) if xs else None, "content right", content_right, "pages", renderer.doc.pageCount())
    image.save(fr"D:\HandWriteStudio\samples\grid_{name}_wrap.png")
