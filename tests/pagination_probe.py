import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

from app.renderer import HandRenderer
from app.settings import HandStyle

app = QApplication(sys.argv)
style = HandStyle()
paras = "\n".join(f"<p>第 {i + 1} 段：测试自动分页的正文内容，看看第二页之后到底有没有东西。</p>" for i in range(70))
html = "<h1 style='text-align:center;'>长文分页测试</h1>" + paras
r = HandRenderer(html, style)
print("pageCount", r.doc.pageCount(), "docSize", r.doc.size())
layout = r.doc.documentLayout()

block = r.doc.begin()
n = 0
while block.isValid() and n < 40:
    rect = layout.blockBoundingRect(block)
    if 700 < rect.top() < 1800:
        print("block", n, "top", round(rect.top(), 1), "bottom", round(rect.bottom(), 1), "text", block.text()[:20])
    block = block.next()
    n += 1

# count blocks per page band
counts = {}
block = r.doc.begin()
while block.isValid():
    rect = layout.blockBoundingRect(block)
    page = int(rect.top() // style.page_height)
    counts[page] = counts.get(page, 0) + 1
    block = block.next()
print("blocks per page", counts)

# paint page 1/2 with debug: check images non-white pixel count
for page in (0, 1, 2):
    img = QImage(595, 842, QImage.Format.Format_ARGB32)
    img.fill(QColor("#ffffff"))
    p = QPainter(img)
    p.scale(1, 1)
    r.paint_page(p, page, draw_background=False)
    p.end()
    # count dark pixels
    dark = 0
    for y in range(0, img.height(), 8):
        for x in range(0, img.width(), 8):
            if QColor(img.pixel(x, y)).lightness() < 200:
                dark += 1
    print("page", page, "dark sample", dark)
