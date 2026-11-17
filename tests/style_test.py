import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication

from app.renderer import HandRenderer
from app.settings import FONT_DIR, PAPER_DIR, HandStyle

app = QApplication(sys.argv)
style = HandStyle()
style.font_path = str(FONT_DIR / "云烟体.ttf")
style.background_path = str(PAPER_DIR / "背景1.jpg")
html = (
    "<h1 style='text-align:center;'>云烟体 · 背景纸</h1>"
    "<p>今天把排版和手写效果对齐了一下，表格和图片都能跟着分页走。</p>"
    "<p>这段用来检查背景纸有没有铺满、文字有没有被纸张纹理吃掉。</p>"
    "<table border='1' cellspacing='0' cellpadding='6' width='100%'>"
    "<tr><td>项目</td><td>状态</td></tr><tr><td>导出 PNG</td><td>已通</td></tr></table>"
)
r = HandRenderer(html, style)
print("font family:", r.font_family, "pages:", r.page_count())
out = Path(r"D:\HandWriteStudio\samples\style_bg.png")
r.render_page_image(0, dpi=160).save(str(out))
print("saved", out, out.stat().st_size)
