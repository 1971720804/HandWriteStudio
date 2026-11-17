import random
import sys
from pathlib import Path

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QGuiApplication,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QTransform,
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
rng = random.Random(7)
base = QPainterPath()
base.addText(0, 0, font, "永")
parts = subpaths(base)
print("subpaths", len(parts), [p.elementCount() for p in parts])

canvas = QImage(900, 520, QImage.Format.Format_RGB32)
canvas.fill(QColor("white"))
p = QPainter(canvas)
p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
p.translate(240, 380)
p.scale(2.6, 2.6)

for variant in range(3):
    out = QPainterPath()
    out.setFillRule(Qt.FillRule.WindingFill)
    for part in parts:
        b = part.boundingRect()
        c = b.center()
        dx = rng.gauss(0, 2.5)
        dy = rng.gauss(0, 2.5)
        ang = rng.gauss(0, 3.0)
        t = QTransform()
        t.translate(c.x() + dx, c.y() + dy)
        t.rotate(ang)
        t.translate(-c.x(), -c.y())
        out.addPath(t.map(part))
    p.save()
    p.translate(variant * 220, 0)
    p.setPen(QPen(Qt.PenStyle.NoPen))
    p.setBrush(QColor("#202020"))
    p.drawPath(out)
    p.restore()

p.end()
target = root / "samples" / "stroke_proto.png"
canvas.save(str(target))
print(target)
