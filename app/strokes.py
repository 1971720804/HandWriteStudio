"""汉字笔画数据：把字体轮廓按笔画中线的随机形变做出「每一笔各自动」的效果。

数据来自 hanzi-writer-data（Make Me a Hanzi / Arphic Public License），
放在 assets/hanzi-data/<char>.json。没有数据的字符自动退回普通绘制。
"""
from __future__ import annotations

import json
import math
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QFont, QPainterPath, QTransform

from .settings import ASSETS_DIR


_DATA_DIR = ASSETS_DIR / "hanzi-data"
_PREP_CACHE: dict[tuple, Optional["PreparedGlyph"]] = {}


def _svg_path(d: str) -> QPainterPath:
    """解析 hanzi-writer-data 里的 SVG 路径（M/L/Q/C/Z 及相对命令）。"""
    tokens = re.findall(r"[MmLlQqCcZzHhVv]|-?\d*\.?\d+(?:[eE][-+]?\d+)?", d)
    path = QPainterPath()
    i = 0
    cmd: str | None = None
    cx = cy = 0.0
    sx = sy = 0.0

    def take() -> float:
        nonlocal i
        value = float(tokens[i])
        i += 1
        return value

    while i < len(tokens):
        token = tokens[i]
        if re.match(r"[A-Za-z]", token):
            cmd = token
            i += 1
            if cmd in "Zz":
                path.closeSubpath()
                cx, cy = sx, sy
                continue
        if cmd is None:
            break
        relative = cmd.islower()
        op = cmd.upper()
        if op == "M":
            x, y = take(), take()
            if relative:
                x, y = cx + x, cy + y
            path.moveTo(x, y)
            cx, cy = sx, sy = x, y
            cmd = "l" if relative else "L"
        elif op == "L":
            x, y = take(), take()
            if relative:
                x, y = cx + x, cy + y
            path.lineTo(x, y)
            cx, cy = x, y
        elif op == "H":
            x = take()
            if relative:
                x += cx
            path.lineTo(x, cy)
            cx = x
        elif op == "V":
            y = take()
            if relative:
                y += cy
            path.lineTo(cx, y)
            cy = y
        elif op == "Q":
            qx, qy = take(), take()
            x, y = take(), take()
            if relative:
                qx, qy, x, y = cx + qx, cy + qy, cx + x, cy + y
            path.quadTo(qx, qy, x, y)
            cx, cy = x, y
        elif op == "C":
            x1, y1 = take(), take()
            x2, y2 = take(), take()
            x, y = take(), take()
            if relative:
                x1, y1, x2, y2, x, y = (
                    cx + x1, cy + y1, cx + x2, cy + y2, cx + x, cy + y
                )
            path.cubicTo(x1, y1, x2, y2, x, y)
            cx, cy = x, y
        else:
            i += 1
    return path


@dataclass
class PreparedGlyph:
    path: QPainterPath
    elements: list[tuple[int, int]]  # (element type, number of points)
    points: list[tuple[float, float]]
    weights: list[list[tuple[int, float]]]
    centers: list[tuple[float, float]]


def _dist2_to_polyline(px: float, py: float, segments: list[tuple[float, float, float, float]]) -> float:
    best = 1e30
    for ax, ay, bx, by in segments:
        vx, vy = bx - ax, by - ay
        wx, wy = px - ax, py - ay
        den = vx * vx + vy * vy
        t = 0.0 if den == 0.0 else (wx * vx + wy * vy) / den
        if t < 0.0:
            t = 0.0
        elif t > 1.0:
            t = 1.0
        qx, qy = ax + vx * t, ay + vy * t
        dx, dy = px - qx, py - qy
        d = dx * dx + dy * dy
        if d < best:
            best = d
    return best


def _prepare(ch: str, font: QFont) -> Optional[PreparedGlyph]:
    key = (ch, font.family(), int(font.weight()), bool(font.italic()))
    if key in _PREP_CACHE:
        return _PREP_CACHE[key]

    data_path = _DATA_DIR / f"{ch}.json"
    if not data_path.exists():
        _PREP_CACHE[key] = None
        return None
    try:
        data = json.loads(data_path.read_text(encoding="utf-8"))
        strokes = [_svg_path(s) for s in data.get("strokes", [])]
        medians_raw = data.get("medians", [])
        if not strokes or not medians_raw:
            raise ValueError("empty")
    except Exception:
        _PREP_CACHE[key] = None
        return None

    base_font = QFont(font)
    base_font.setPointSizeF(100.0)
    glyph = QPainterPath()
    glyph.addText(0, 0, base_font, ch)
    gbox = glyph.boundingRect()
    if gbox.width() <= 0 or gbox.height() <= 0:
        _PREP_CACHE[key] = None
        return None

    union = QPainterPath()
    for s in strokes:
        union.addPath(s)
    sbox = union.boundingRect()
    if sbox.width() <= 0 or sbox.height() <= 0:
        _PREP_CACHE[key] = None
        return None

    sx = gbox.width() / sbox.width()
    sy = gbox.height() / sbox.height()
    t = QTransform()
    t.translate(gbox.left() - sbox.left() * sx, gbox.top() - sbox.top() * sy)
    t.scale(sx, sy)

    median_segments: list[list[tuple[float, float, float, float]]] = []
    centers: list[tuple[float, float]] = []
    for med in medians_raw:
        pts = []
        for x, y in med:
            p = t.map(QPointF(float(x), float(y)))
            pts.append((p.x(), p.y()))
        if not pts:
            continue
        segs = []
        for j in range(len(pts) - 1):
            ax, ay = pts[j]
            bx, by = pts[j + 1]
            segs.append((ax, ay, bx, by))
        if not segs and len(pts) == 1:
            ax, ay = pts[0]
            segs.append((ax, ay, ax, ay))
        median_segments.append(segs)
        centers.append(
            (
                sum(p[0] for p in pts) / len(pts),
                sum(p[1] for p in pts) / len(pts),
            )
        )

    sigma = max(4.0, 0.075 * gbox.height())
    two_sigma2 = 2.0 * sigma * sigma

    elements: list[tuple[int, int]] = []
    points: list[tuple[float, float]] = []
    weights: list[list[tuple[int, float]]] = []
    i = 0
    while i < glyph.elementCount():
        e = glyph.elementAt(i)
        if e.type == QPainterPath.ElementType.MoveToElement:
            elements.append((QPainterPath.ElementType.MoveToElement.value, 1))
            pts = [(e.x, e.y)]
            i += 1
        elif e.type == QPainterPath.ElementType.LineToElement:
            elements.append((QPainterPath.ElementType.LineToElement.value, 1))
            pts = [(e.x, e.y)]
            i += 1
        elif e.type == QPainterPath.ElementType.CurveToElement:
            if i + 2 >= glyph.elementCount():
                break
            e2 = glyph.elementAt(i + 1)
            e3 = glyph.elementAt(i + 2)
            elements.append((QPainterPath.ElementType.CurveToElement.value, 3))
            pts = [(e.x, e.y), (e2.x, e2.y), (e3.x, e3.y)]
            i += 3
        else:
            i += 1
            continue

        for x, y in pts:
            points.append((x, y))
            ws = []
            for idx, segs in enumerate(median_segments):
                d2 = _dist2_to_polyline(x, y, segs)
                w = math.exp(-d2 / two_sigma2)
                if w > 1e-4:
                    ws.append((idx, w))
            if not ws:
                # 离所有中线都远的点（字形外缘/尖角）至少跟随最近的一笔，
                # 否则这些点完全静止，会在笔画边缘留下“没动”的硬边。
                idx = min(
                    range(len(centers)),
                    key=lambda k: (x - centers[k][0]) ** 2 + (y - centers[k][1]) ** 2,
                )
                ws.append((idx, 1.0))
            weights.append(ws)

    prepared = PreparedGlyph(glyph, elements, points, weights, centers)
    _PREP_CACHE[key] = prepared
    return prepared


def deformed_path(
    ch: str,
    font: QFont,
    rng: random.Random,
    offset_amp: float,
    rotate_amp: float,
) -> Optional[QPainterPath]:
    """按笔画中线随机偏移/旋转字体轮廓；没有笔画数据时返回 None。"""
    prep = _prepare(ch, font)
    if prep is None:
        return None

    moves = []
    for cx, cy in prep.centers:
        ox = rng.gauss(0.0, offset_amp) if offset_amp > 0 else 0.0
        oy = rng.gauss(0.0, offset_amp) if offset_amp > 0 else 0.0
        ang = math.radians(rng.gauss(0.0, rotate_amp)) if rotate_amp > 0 else 0.0
        moves.append((ox, oy, math.cos(ang), math.sin(ang), cx, cy))

    out = QPainterPath()
    out.setFillRule(prep.path.fillRule())
    pi = 0
    for _etype, n in prep.elements:
        coords: list[tuple[float, float]] = []
        for _ in range(n):
            x, y = prep.points[pi]
            raw = prep.weights[pi]
            # 让每个轮廓点主要听“最近的一笔”的指挥：不再把 4~5 笔的
            # 随机量平均掉（平均平移会互相抵消，平均旋转会变成剪切）。
            if raw:
                peak = max(w for _idx, w in raw)
                ws = [(idx, (w / peak) ** 4) for idx, w in raw]
            else:
                ws = []
            sw = 0.0
            sx = sy = 0.0
            for idx, w in ws:
                ox, oy, cos_a, sin_a, cx, cy = moves[idx]
                sw += w
                # 绕该笔画中线中心做小幅旋转，再叠加平移
                sx += w * (ox + (cos_a - 1.0) * (x - cx) - sin_a * (y - cy))
                sy += w * (oy + sin_a * (x - cx) + (cos_a - 1.0) * (y - cy))
            if sw > 1e-9:
                x += sx / sw
                y += sy / sw
            coords.append((x, y))
            pi += 1
        if n == 1:
            x, y = coords[0]
            if _etype == QPainterPath.ElementType.MoveToElement.value:
                out.moveTo(x, y)
            else:
                out.lineTo(x, y)
        elif n == 3:
            out.cubicTo(*coords[0], *coords[1], *coords[2])
    return out
