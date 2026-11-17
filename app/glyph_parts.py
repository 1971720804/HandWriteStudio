"""按 handright 的思路，把字形拆成“连通墨块”。

handright 并不认识真正的笔画：它把字画成黑白位图，再用 4 邻域
DFS 找出一块块连在一起的墨。每一块整体做高斯平移 + 旋转，
所以看起来像手写，但不会把笔画拉扭。

这里把同样的做法收在“单个字”的范围内，方便配合 QTextDocument
已经算好的逐字坐标。
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter

# 字形先按这个像素高度画一次，之后按目标字号缩放。
CANON_PX = 160
# QFont.setPixelSize 用的是 96dpi 逻辑像素；换算成 pt 才是排版坐标里的字号。
CANON_PT = CANON_PX * 72.0 / 96.0
_ALPHA_THRESHOLD = 20
_PARTS_CACHE: dict[tuple, "GlyphParts | None"] = {}


@dataclass
class GlyphPart:
    image: QImage
    cx: float          # 相对“字左边”的 x，单位是 CANON_PX 像素
    cy: float          # 相对基线的 y，向下为正


@dataclass
class GlyphParts:
    parts: list[GlyphPart]
    advance: float
    ascent: float
    width: int
    height: int
    pad: int


def _components(image: QImage) -> list[tuple[QImage, int, int, int, int]]:
    """返回 [(裁切图, minx, miny, maxx, maxy)]，背景透明。"""
    if image.format() != QImage.Format.Format_ARGB32_Premultiplied:
        image = image.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    w, h = image.width(), image.height()
    bits = image.bits()
    stride = image.bytesPerLine()
    mask = bytearray(w * h)
    for y in range(h):
        row = y * stride
        for x in range(w):
            if bits[row + x * 4 + 3] >= _ALPHA_THRESHOLD:
                mask[y * w + x] = 1

    seen = bytearray(w * h)
    result: list[tuple[QImage, int, int, int, int]] = []
    for sy in range(h):
        for sx in range(w):
            start = sy * w + sx
            if not mask[start] or seen[start]:
                continue
            q = deque([start])
            seen[start] = 1
            pixels: list[int] = []
            minx, maxx, miny, maxy = sx, sx, sy, sy
            while q:
                idx = q.popleft()
                pixels.append(idx)
                y, x = divmod(idx, w)
                if x < minx:
                    minx = x
                if x > maxx:
                    maxx = x
                if y < miny:
                    miny = y
                if y > maxy:
                    maxy = y
                if x > 0:
                    n = idx - 1
                    if mask[n] and not seen[n]:
                        seen[n] = 1
                        q.append(n)
                if x + 1 < w:
                    n = idx + 1
                    if mask[n] and not seen[n]:
                        seen[n] = 1
                        q.append(n)
                if y > 0:
                    n = idx - w
                    if mask[n] and not seen[n]:
                        seen[n] = 1
                        q.append(n)
                if y + 1 < h:
                    n = idx + w
                    if mask[n] and not seen[n]:
                        seen[n] = 1
                        q.append(n)
            if len(pixels) < 2:
                continue

            bw, bh = maxx - minx + 1, maxy - miny + 1
            piece = image.copy(minx, miny, bw, bh)
            # 同一块连通墨的裁切图里会带进旁边别的墨块（抗锯齿边缘），
            # 直接画会在原位置留下重影。这里只保留本块 + 1px 抗锯齿边。
            keep = bytearray(bw * bh)
            for idx in pixels:
                py, px = divmod(idx, w)
                lx, ly = px - minx, py - miny
                for oy in (-1, 0, 1):
                    yy = ly + oy
                    if yy < 0 or yy >= bh:
                        continue
                    for ox in (-1, 0, 1):
                        xx = lx + ox
                        if 0 <= xx < bw:
                            keep[yy * bw + xx] = 1
            pbits = piece.bits()
            pstride = piece.bytesPerLine()
            for ly in range(bh):
                row = ly * pstride
                for lx in range(bw):
                    if not keep[ly * bw + lx]:
                        off = row + lx * 4
                        pbits[off] = pbits[off + 1] = pbits[off + 2] = pbits[off + 3] = 0
            result.append((piece, minx, miny, maxx, maxy))
    return result


def glyph_parts(ch: str, font: QFont) -> GlyphParts | None:
    """拆一个字；字形统一按 CANON_PX 画，之后整字缩放。"""
    key = (ch, font.family(), font.weight(), font.italic(), font.underline())
    if key in _PARTS_CACHE:
        return _PARTS_CACHE[key]

    f = QFont(font)
    f.setPixelSize(CANON_PX)
    fm = QFontMetricsF(f)
    advance = fm.horizontalAdvance(ch)
    ascent = fm.ascent()
    descent = fm.descent()
    if advance <= 0.1 or ascent + descent <= 1.0:
        _PARTS_CACHE[key] = None
        return None

    pad = int(CANON_PX * 0.30)
    width = int(advance + pad * 2 + 2)
    height = int(ascent + descent + pad * 2 + 2)
    canvas = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    canvas.fill(Qt.GlobalColor.transparent)
    p = QPainter(canvas)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    p.setFont(f)
    p.setPen(QColor(255, 255, 255, 255))
    p.drawText(QPointF(pad, pad + ascent), ch)
    p.end()

    raw = _components(canvas)
    if not raw:
        _PARTS_CACHE[key] = None
        return None

    parts: list[GlyphPart] = []
    for piece, minx, miny, maxx, maxy in raw:
        parts.append(
            GlyphPart(
                image=piece,
                cx=(minx + maxx) / 2.0 - pad,
                cy=(miny + maxy) / 2.0 - (pad + ascent),
            )
        )
    parts.sort(key=lambda pt: (pt.cy, pt.cx))
    out = GlyphParts(
        parts=parts,
        advance=advance,
        ascent=ascent,
        width=width,
        height=height,
        pad=pad,
    )
    _PARTS_CACHE[key] = out
    return out
