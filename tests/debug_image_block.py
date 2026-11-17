import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QBuffer, QByteArray
from PySide6.QtGui import QColor, QImage, QTextImageFormat
from PySide6.QtWidgets import QApplication

from app.renderer import make_renderer
from app.settings import HandStyle

app = QApplication([])

im = QImage(240, 140, QImage.Format.Format_RGB32)
im.fill(QColor("#5b8fd1"))
ba = QByteArray()
buf = QBuffer(ba)
buf.open(QBuffer.OpenModeFlag.WriteOnly)
im.save(buf, "PNG")
uri = "data:image/png;base64," + bytes(ba.toBase64()).decode("ascii")

s = HandStyle()
s.grid_mode = True
s.grid_rows = 8
s.grid_cols = 30
s.font_size = 12

html = "<p>图片：</p><p><img src=\"" + uri + "\" width=\"240\" height=\"140\"></p><p>尾段1</p>"
r = make_renderer(html, s)
rr = r
b = rr.doc.begin()
while b.isValid():
    print("block", b.blockNumber(), repr(b.text()), "lineHeight", b.blockFormat().lineHeight(), "type", b.blockFormat().lineHeightType(), "rect", r.doc.documentLayout().blockBoundingRect(b))
    it = b.begin()
    while not it.atEnd():
        f = it.fragment()
        if f.charFormat().isImageFormat():
            print("  image height", QTextImageFormat(f.charFormat()).height(), "width", QTextImageFormat(f.charFormat()).width())
        try:
            it += 1
        except TypeError:
            it = it.__iadd__(1)
    b = b.next()
