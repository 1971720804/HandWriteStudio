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
chars = "永我你"

canvas = QImage(1200, 600, QImage.Format.Format_RGB32)
canvas.fill(QColor("white"))
p = QPainter(canvas)
p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

for col, ch in enumerate(chars):
    base = QPainterPath()
    base.addText(0, 0, font, ch)
    parts = subpaths(base)
    # 找父子关系，把洞和外壳归为一组
    rects = [part.boundingRect() for part in parts]
    parent = [-1] * len(parts)
    for i, ri in enumerate(rects):
        best = -1
        best_area = 1e18
        for j, rj in enumerate(rects):
            if i == j:
                continue
            if rj.adjusted(-0.01, -0.01, 0.01, 0.01).contains(ri):
                area = rj.width() * rj.height()
                if area < best_area:
                    best, best_area = j, area
        parent[i] = best
    roots = [i for i in range(len(parts)) if parent[i] == -1]
    groups = {i: [i] for i in roots}
    for i, par in enumerate(parent):
        if par != -1:
            groups.setdefault(par, []).append(i)
    print(ch, "parts", len(parts), "roots", len(roots), "parents", parent)

    for variant in range(2):
        out = QPainterPath()
        out.setFillRule(Qt.FillRule.WindingFill)
        for root_idx in roots:
            group = groups[root_idx]
            union = QPainterPath()
            for idx in group:
                union.addPath(parts[idx])
            c = union.boundingRect().center()
            t = QTransform()
            t.translate(c.x() + rng.gauss(0, 2.5), c.y() + rng.gauss(0, 2.5))
            t.rotate(rng.gauss(0, 3.0))
            t.translate(-c.x(), -c.y())
            for idx in group:
                out.addPath(t.map(parts[idx]))
        p.save()
        p.translate(180 + col * 380 + variant * 130, 420)
        p.scale(2.0, 2.0)
        p.setPen(QPen(Qt.PenStyle.NoPen))
        p.setBrush(QColor("#202020"))
        p.drawPath(out)
        p.restore()

p.end()
target = root / "samples" / "stroke_group_proto.png"
canvas.save(str(target))
print(target)
