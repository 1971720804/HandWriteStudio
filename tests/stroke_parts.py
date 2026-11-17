import sys
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QGuiApplication,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
)

root = Path(r"D:\HandWriteStudio")
app = QGuiApplication(sys.argv)
fid = QFontDatabase.addApplicationFont(str(root / "assets" / "fonts" / "李国夫手写体.ttf"))
family = QFontDatabase.applicationFontFamilies(fid)[0]


def subpaths(path: QPainterPath) -> list[QPainterPath]:
    out = []
    cur = None
    i = 0
    while i < path.elementCount():
        e = path.elementAt(i)
        if e.type == QPainterPath.ElementType.MoveToElement:
            if cur is not None and cur.elementCount():
                out.append(cur)
            cur = QPainterPath()
            cur.moveTo(e.x, e.y)
            i += 1
        elif e.type == QPainterPath.ElementType.LineToElement:
            if cur is None:
                cur = QPainterPath()
                cur.moveTo(e.x, e.y)
            else:
                cur.lineTo(e.x, e.y)
            i += 1
        elif e.type == QPainterPath.ElementType.CurveToElement:
            if cur is None or i + 2 >= path.elementCount():
                break
            c1 = path.elementAt(i)
            c2 = path.elementAt(i + 1)
            end = path.elementAt(i + 2)
            cur.cubicTo(c1.x, c1.y, c2.x, c2.y, end.x, end.y)
            i += 3
        else:
            i += 1
    if cur is not None and cur.elementCount():
        out.append(cur)
    return out


font = QFont(family)
font.setPointSizeF(100)
base = QPainterPath()
base.addText(0, 0, font, "永")
parts = subpaths(base)
print("bbox", base.boundingRect())
for i, part in enumerate(parts):
    br = part.boundingRect()
    print(i, "bbox", round(br.x(), 2), round(br.y(), 2), round(br.width(), 2), round(br.height(), 2),
          "area", round(part.area() if hasattr(part, "area") else -1, 2),
          "contains0", part.contains(parts[0].boundingRect().center()))

colors = ["#e6194b", "#3cb44b", "#ffe119", "#4363d8", "#f58231", "#911eb4", "#46f0f0", "#f032e6"]
canvas = QImage(1000, 800, QImage.Format.Format_RGB32)
canvas.fill(QColor("white"))
p = QPainter(canvas)
p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
p.translate(60, 620)
p.scale(5.0, 5.0)
for i, part in enumerate(parts):
    p.setPen(QPen(QColor("#333333"), 0.3))
    p.setBrush(QColor(colors[i % len(colors)]))
    p.drawPath(part)
p.end()
out = root / "samples" / "stroke_parts.png"
canvas.save(str(out))
print(out)
