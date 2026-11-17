import json
import math
import random
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
                x1, y1, x2, y2, x, y = cx + x1, cy + y1, cx + x2, cy + y2, cx + x, cy + y
            path.cubicTo(x1, y1, x2, y2, x, y)
            cx, cy = x, y
        else:
            i += 1
    return path


def load_data(ch: str):
    data = json.loads((root / "tests" / f"hanzi_{ch}.json").read_text(encoding="utf-8-sig"))
    strokes = [svg_path(s) for s in data["strokes"]]
    union = QPainterPath()
    for s in strokes:
        union.addPath(s)
    font = QFont(family)
    font.setPointSizeF(100)
    glyph = QPainterPath()
    glyph.addText(0, 0, font, ch)
    gbox = glyph.boundingRect()
    sbox = union.boundingRect()
    t = QTransform()
    t.translate(gbox.left() - sbox.left() * gbox.width() / sbox.width(),
                gbox.top() - sbox.top() * gbox.height() / sbox.height())
    t.scale(gbox.width() / sbox.width(), gbox.height() / sbox.height())
    medians = []
    for med in data["medians"]:
        pts = [t.map(QPointF(x, y)) for x, y in med]
        medians.append(pts)
    return glyph, medians


def dist_to_polyline(px, py, pts):
    best = 1e18
    for i in range(len(pts) - 1):
        ax, ay = pts[i].x(), pts[i].y()
        bx, by = pts[i + 1].x(), pts[i + 1].y()
        vx, vy = bx - ax, by - ay
        wx, wy = px - ax, py - ay
        den = vx * vx + vy * vy
        t = 0.0 if den == 0 else max(0.0, min(1.0, (wx * vx + wy * vy) / den))
        qx, qy = ax + vx * t, ay + vy * t
        d = math.hypot(px - qx, py - qy)
        if d < best:
            best = d
    return best


def deformed(glyph, medians, rng, offset_amp, rot_amp):
    infos = []
    for pts in medians:
        cx = sum(p.x() for p in pts) / len(pts)
        cy = sum(p.y() for p in pts) / len(pts)
        infos.append((pts, cx, cy, rng.gauss(0, offset_amp), rng.gauss(0, offset_amp),
                      math.radians(rng.gauss(0, rot_amp))))
    sigma = 16.0

    def move(x, y):
        tw = 0.0
        dx = dy = 0.0
        for pts, cx, cy, ox, oy, ang in infos:
            d = dist_to_polyline(x, y, pts)
            w = math.exp(-(d * d) / (2 * sigma * sigma))
            if w < 1e-4:
                continue
            tw += w
            dx += w * (ox - math.sin(ang) * (y - cy) + (math.cos(ang) - 1) * (x - cx))
            dy += w * (oy + math.sin(ang) * (x - cx) + (math.cos(ang) - 1) * (y - cy))
        if tw > 1e-9:
            x += dx / tw
            y += dy / tw
        return x, y

    out = QPainterPath()
    i = 0
    while i < glyph.elementCount():
        e = glyph.elementAt(i)
        if e.type == QPainterPath.ElementType.MoveToElement:
            x, y = move(e.x, e.y)
            out.moveTo(x, y)
            i += 1
        elif e.type == QPainterPath.ElementType.LineToElement:
            x, y = move(e.x, e.y)
            out.lineTo(x, y)
            i += 1
        elif e.type == QPainterPath.ElementType.CurveToElement:
            x1, y1 = move(e.x, e.y)
            e2 = glyph.elementAt(i + 1)
            x2, y2 = move(e2.x, e2.y)
            e3 = glyph.elementAt(i + 2)
            x3, y3 = move(e3.x, e3.y)
            out.cubicTo(x1, y1, x2, y2, x3, y3)
            i += 3
        else:
            i += 1
    return out


chars = "永我"
canvas = QImage(1400, 800, QImage.Format.Format_RGB32)
canvas.fill(QColor("white"))
p = QPainter(canvas)
p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
rng = random.Random(11)
for row, ch in enumerate(chars):
    glyph, medians = load_data(ch)
    for col in range(3):
        path = glyph if col == 0 else deformed(glyph, medians, rng, 4.5 if col > 1 else 0, 4.0)
        p.save()
        p.translate(160 + col * 420, 350 + row * 390)
        p.scale(2.6, 2.6)
        p.setPen(QPen(Qt.PenStyle.NoPen))
        p.setBrush(QColor("#202020"))
        p.drawPath(path)
        p.restore()
p.end()
out = root / "samples" / "stroke_deform_proto.png"
canvas.save(str(out))
print(out)
