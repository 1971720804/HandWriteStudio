import json
import math
import re
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


def svg_path(d: str) -> QPainterPath:
    tokens = re.findall(r"[MmLlQqCcZzHhVv]|-?\d*\.?\d+(?:[eE][-+]?\d+)?", d)
    path = QPainterPath()
    i = 0
    cmd = None
    cx = cy = 0.0
    sx = sy = 0.0

    def num():
        nonlocal i
        v = float(tokens[i])
        i += 1
        return v

    while i < len(tokens):
        if re.match(r"[A-Za-z]", tokens[i]):
            cmd = tokens[i]
            i += 1
            if cmd in "Zz":
                path.closeSubpath()
                cx, cy = sx, sy
                continue
        if cmd is None:
            break
        rel = cmd.islower()
        c = cmd.upper()
        if c == "M":
            x, y = num(), num()
            if rel:
                x, y = cx + x, cy + y
            path.moveTo(x, y)
            cx, cy = sx, sy = x, y
            cmd = "l" if rel else "L"
        elif c == "L":
            x, y = num(), num()
            if rel:
                x, y = cx + x, cy + y
            path.lineTo(x, y)
            cx, cy = x, y
        elif c == "H":
            x = num()
            if rel:
                x = cx + x
            path.lineTo(x, cy)
            cx = x
        elif c == "V":
            y = num()
            if rel:
                y = cy + y
            path.lineTo(cx, y)
            cy = y
        elif c == "Q":
            qx, qy = num(), num()
            x, y = num(), num()
            if rel:
                qx, qy, x, y = cx + qx, cy + qy, cx + x, cy + y
            path.quadTo(qx, qy, x, y)
            cx, cy = x, y
        elif c == "C":
            x1, y1 = num(), num()
            x2, y2 = num(), num()
            x, y = num(), num()
            if rel:
                x1, y1, x2, y2, x, y = (
                    cx + x1,
                    cy + y1,
                    cx + x2,
                    cy + y2,
                    cx + x,
                    cy + y,
                )
            path.cubicTo(x1, y1, x2, y2, x, y)
            cx, cy = x, y
        else:
            i += 1
    return path


data = json.loads((root / "tests" / "hanzi_永.json").read_text(encoding="utf-8-sig"))
strokes = [svg_path(s) for s in data["strokes"]]
font = QFont(family)
font.setPointSizeF(100)
glyph = QPainterPath()
glyph.addText(0, 0, font, "永")

union = QPainterPath()
for s in strokes:
    union.addPath(s)
gbox = glyph.boundingRect()
sbox = union.boundingRect()
sx = gbox.width() / sbox.width()
sy = gbox.height() / sbox.height()
tx = gbox.left() - sbox.left() * sx
ty = gbox.top() - sbox.top() * sy
t = QTransform()
t.translate(tx, ty)
t.scale(sx, sy)

pieces = []
for s in strokes:
    mapped = t.map(s)
    piece = glyph.intersected(mapped)
    pieces.append(piece)
    print("piece", piece.elementCount(), piece.boundingRect())

canvas = QImage(1200, 900, QImage.Format.Format_RGB32)
canvas.fill(QColor("white"))
p = QPainter(canvas)
p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
p.translate(80, 700)
p.scale(4.5, 4.5)
colors = ["#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#46f0f0"]
for idx, piece in enumerate(pieces):
    b = piece.boundingRect()
    c = b.center()
    # 往外炸开，方便看分割
    dx = (c.x() - gbox.center().x()) * 0.8 + idx * 3
    dy = (c.y() - gbox.center().y()) * 0.8
    p.save()
    p.translate(dx, dy)
    p.setPen(QPen(QColor("#333333"), 0.2))
    p.setBrush(QColor(colors[idx % len(colors)]))
    p.drawPath(piece)
    p.restore()
p.end()
out = root / "samples" / "hanzi_pieces.png"
canvas.save(str(out))
print("mapped bbox", gbox, "data bbox", sbox, "scale", sx, sy)
print(out)
