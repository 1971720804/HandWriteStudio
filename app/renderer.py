"""手写渲染器：用 QTextDocument 排版，再把文字逐字“写”出来。

思路：
1. 文档照常排版（表格、图片、分页由 Qt 负责）；
2. 把所有文字设成全透明，让 Qt 只画表格线、底纹、图片；
3. 按 Qt 算好的每个字坐标，叠加随机字号 / 位移 / 旋转 / 墨色。
这样排版和手写效果互不打架，表格跨页也不用自己处理。
"""
from __future__ import annotations

import base64
import copy
import math
import random
import re
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSizeF, Qt, QUrl
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontDatabase,
    QFontMetricsF,
    QImage,
    QImageReader,
    QPainter,
    QPen,
    QTextBlockFormat,
    QTextCursor,
    QTextDocument,
    QTextFrameFormat,
    QTextImageFormat,
    QTextLength,
    QTextOption,
)

from .settings import HandStyle
from . import glyph_parts

DATA_IMAGE_RE = re.compile(
    r'src=(["\'])(data:image/([a-zA-Z0-9.+-]+);base64,([^"\']+))\1',
    re.IGNORECASE,
)

BASE_EDITOR_SIZE = 12.0
_FONT_CACHE: dict[str, str] = {}
_BG_CACHE: dict[str, QImage] = {}


def extract_data_images(html: str) -> tuple[str, list[tuple[QUrl, QImage]], dict[str, str]]:
    """把 HTML 里的 data:image 换成自定义资源 URL，返回 (html, 资源, 反查表)。"""
    resources: list[tuple[QUrl, QImage]] = []
    restore: dict[str, str] = {}

    def repl(match: re.Match) -> str:
        data_uri = match.group(2)
        b64 = match.group(4)
        try:
            raw = base64.b64decode(b64)
        except Exception:
            return match.group(0)
        image = QImage.fromData(raw)
        if image.isNull():
            return match.group(0)
        url = f"hwres://img/{len(resources)}"
        resources.append((QUrl(url), image))
        restore[url] = data_uri
        return f'src="{url}"'

    return DATA_IMAGE_RE.sub(repl, html), resources, restore


def image_to_data_uri(image: QImage, fmt: str = "PNG") -> str:
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice

    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buf, fmt)
    buf.close()
    return "data:image/png;base64," + bytes(ba.toBase64()).decode("ascii")


class HandRenderer:
    """把一份 HTML 文档渲染成手写风格页面。"""

    def __init__(self, html: str, style: HandStyle, preserve_blocks: bool = False):
        self.style = style
        self.html = html
        self._preserve_blocks = preserve_blocks
        self.resources: list[tuple[QUrl, QImage]] = []
        self.font_family = self._load_font(style.font_path)
        self._block_formats: dict[int, list[tuple[int, int, QTextCharFormat]]] = {}
        self._grid_line_h: float | None = None
        self._grid_spread: dict[tuple[int, int], float] = {}
        self._grid_row_of: dict[tuple[int, int], int] = {}
        self._grid_page_count: int = 1
        self.doc = self._build_document(html)
        # 格子模式只用「单页行数」决定固定行距；内容不足时底部留白，
        # 不再按实际行数把整页撑满。
        self._grid_spread = {}

    # ---------- 构建 ----------

    @staticmethod
    def _load_font(path: str) -> str:
        path = path or ""
        if path and Path(path).exists():
            cached = _FONT_CACHE.get(path)
            if cached:
                return cached
            font_id = QFontDatabase.addApplicationFont(path)
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                _FONT_CACHE[path] = families[0]
                return families[0]
        # 兜底：系统里比较像手写的字体
        for name in ("楷体", "KaiTi", "Microsoft YaHei"):
            if name in QFontDatabase.families():
                return name
        return QFont().family()

    def _build_document(self, html: str) -> QTextDocument:
        doc = QTextDocument()
        doc.setUndoRedoEnabled(False)
        doc.setDocumentMargin(0)

        clean_html, self.resources, _ = extract_data_images(html)
        for url, image in self.resources:
            doc.addResource(QTextDocument.ImageResource, url, image)

        default_font = QFont(self.font_family)
        default_font.setPointSizeF(max(1.0, self.style.font_size))
        doc.setDefaultFont(default_font)
        # Qt 的富文本默认会把连续空格/制表符压成一个；编辑器里敲的缩进要原样保留。
        # pre-wrap 既不丢空白，也允许在空白处正常换行。
        doc.setDefaultStyleSheet(
            "p, div, li, td, th { white-space: pre-wrap; }"
        )
        doc.setHtml(clean_html)

        # 格子模式一字一格，英文/数字也要允许在任意字符处换行，
        # 否则长单词会整段顶出右边距。
        if bool(getattr(self.style, "grid_mode", False)):
            option = doc.defaultTextOption()
            option.setWrapMode(QTextOption.WrapMode.WrapAnywhere)
            doc.setDefaultTextOption(option)
            if bool(getattr(self.style, "grid_align_cols", True)) and not self._preserve_blocks:
                self._insert_grid_breaks(doc)

        self._apply_style(doc)
        doc.setPageSize(QSizeF(self.style.page_width, self.style.page_height))
        # 触发一次排版
        doc.documentLayout().documentSize()
        if bool(getattr(self.style, "grid_mode", False)):
            if not self._preserve_blocks:
                # 自然换行时一个 block 可能跨很多行；先按视觉行拆块，
                # 否则 block 级分页无法把一段长文从行中间截断。
                self._explode_grid_lines(doc)
                doc.documentLayout().documentSize()
                self._apply_grid_page_breaks(doc)
                # 分页策略写入后要再排一次，pageCount/行位置才按新分页更新
                doc.documentLayout().documentSize()
            self._build_grid_row_map(doc)
        return doc

    def _insert_grid_breaks(self, doc: QTextDocument) -> None:
        """按格子列数给正文插硬换行。

        Qt 自己的换行按字形实际 advance 算，英文长单词/数字串往往能塞进
        一行，但格子模式是一字一格，必须按字符数断行。
        """
        cols = int(getattr(self.style, "grid_cols", 0) or 0)
        if cols <= 0:
            return
        first_limit = max(1, cols - int(round(self.style.first_indent)))
        cuts: list[int] = []
        block = doc.begin()
        while block.isValid():
            try:
                if QTextCursor(block).currentTable() is not None:
                    block = block.next()
                    continue
            except Exception:
                pass
            text = block.text()
            if len(text) > first_limit:
                count = 0
                limit = first_limit
                for i, _ch in enumerate(text):
                    if count >= limit:
                        cuts.append(block.position() + i)
                        count = 0
                        limit = cols
                    count += 1
            block = block.next()

        # 从后往前插，前面的绝对位置不会因为插入而漂移。
        for pos in sorted(set(cuts), reverse=True):
            cursor = QTextCursor(doc)
            cursor.setPosition(pos)
            cursor.insertText("\n")
            fmt = QTextBlockFormat()
            fmt.setTextIndent(-1.0)
            cursor.setBlockFormat(fmt)

    def _explode_grid_lines(self, doc: QTextDocument) -> None:
        """把每个自然换行后的视觉行拆成独立 block。

        这样“单页行数”分页可以在任意一行前断开；否则一个长段落
        作为一个 block，页前分页无法阻止它跨页。
        """
        layout = doc.documentLayout()
        layout.documentSize()
        cuts: list[tuple[int, QTextBlockFormat]] = []
        block = doc.begin()
        while block.isValid():
            try:
                if QTextCursor(block).currentTable() is not None:
                    block = block.next()
                    continue
            except Exception:
                pass
            lay = block.layout()
            if lay is not None and lay.lineCount() > 1:
                base = block.position()
                bf = block.blockFormat()
                for i in range(1, lay.lineCount()):
                    cuts.append((base + lay.lineAt(i).textStart(), bf))
            block = block.next()

        for pos, bf in sorted(cuts, key=lambda x: x[0], reverse=True):
            cursor = QTextCursor(doc)
            cursor.setPosition(pos)
            cursor.insertText("\n")
            nf = QTextBlockFormat(bf)
            nf.setTextIndent(-1.0)
            cursor.setBlockFormat(nf)

    def _build_grid_row_map(self, doc: QTextDocument) -> None:
        """给每个视觉行编号；文本绘制按行号分页，完全不依赖 block 分页。"""
        rows = int(getattr(self.style, "grid_rows", 0) or 0)
        self._grid_row_of.clear()
        if rows <= 0:
            self._grid_page_count = max(1, doc.pageCount())
            return
        row = 0
        cell_h = max(1.0, self._grid_metrics()[1])
        block = doc.begin()
        while block.isValid():
            try:
                in_table = QTextCursor(block).currentTable() is not None
            except Exception:
                in_table = False
            lay = block.layout()
            if not in_table and lay is not None:
                # 图片不是文字行，但会占若干格高；跳过对应行，避免后面文字压到图上
                image_h = 0.0
                it = block.begin()
                while not it.atEnd():
                    frag = it.fragment()
                    if frag.isValid() and frag.charFormat().isImageFormat():
                        image_h = max(
                            image_h,
                            float(QTextImageFormat(frag.charFormat()).height()),
                        )
                    try:
                        it += 1
                    except TypeError:
                        it = it.__iadd__(1)  # type: ignore[attr-defined]
                if image_h > 0:
                    row += max(1, math.ceil((image_h + 2.0) / cell_h))
                    block = block.next()
                    continue
                for li in range(lay.lineCount()):
                    self._grid_row_of[(block.blockNumber(), li)] = row
                    row += 1
            block = block.next()
        self._grid_page_count = max(1, math.ceil(row / rows))

    def _apply_grid_page_breaks(self, doc: QTextDocument) -> None:
        """按单页行数分页，按实际行数计数（自然换行时一个 block 可能多行）。"""
        rows = int(getattr(self.style, "grid_rows", 0) or 0)
        if rows <= 0:
            return
        layout = doc.documentLayout()
        layout.documentSize()
        used = 0
        block = doc.begin()
        while block.isValid():
            try:
                in_table = QTextCursor(block).currentTable() is not None
            except Exception:
                in_table = False
            if not in_table and block.text().strip():
                lay = block.layout()
                line_count = max(1, lay.lineCount()) if lay is not None else 1
                if used and used + line_count > rows:
                    fmt = block.blockFormat()
                    fmt.setPageBreakPolicy(
                        fmt.pageBreakPolicy()
                        | QTextBlockFormat.PageBreakFlag.PageBreak_AlwaysBefore
                    )
                    cursor = QTextCursor(block)
                    cursor.setBlockFormat(fmt)
                    used = 0
                used += line_count
            block = block.next()

    def _grid_metrics(self, style=None) -> tuple[float, float]:
        style = style or self.style
        content_w = max(1.0, style.page_width - style.left_margin - style.right_margin)
        content_h = max(1.0, style.page_height - style.top_margin - style.bottom_margin)
        cols = int(getattr(style, "grid_cols", 0) or 0)
        rows = int(getattr(style, "grid_rows", 0) or 0)
        if cols <= 0:
            cols = max(1, round(content_w / max(1.0, style.font_size + style.letter_spacing)))
        if rows <= 0:
            rows = max(
                1,
                round(content_h / max(1.0, style.font_size * 1.2 * max(0.5, style.line_spacing))),
            )
        return content_w / cols, content_h / rows

    def _compute_grid_spread(self) -> None:
        """逐页把格子模式的行距撑开，首行贴顶、末行贴底。"""
        style = self.style
        if not bool(getattr(style, "grid_mode", False)):
            return
        layout = self.doc.documentLayout()
        layout.documentSize()
        page_h = max(1.0, style.page_height)
        top_m = max(0.0, style.top_margin)
        bottom_m = max(0.0, style.bottom_margin)
        content_h = max(1.0, page_h - top_m - bottom_m)
        glyph_h = max(1.0, style.font_size * 1.5)

        entries: list[tuple[int, int, float]] = []
        block = self.doc.begin()
        while block.isValid():
            try:
                if QTextCursor(block).currentTable() is not None:
                    block = block.next()
                    continue
            except Exception:
                pass
            lay = block.layout()
            if lay is not None:
                rect = layout.blockBoundingRect(block)
                for li in range(lay.lineCount()):
                    line = lay.lineAt(li)
                    entries.append((block.blockNumber(), li, rect.top() + line.y()))
            block = block.next()
        if not entries:
            return

        pages: dict[int, list[tuple[int, int, float]]] = {}
        for entry in entries:
            page = max(0, int((entry[2] - top_m + 0.5) // page_h))
            pages.setdefault(page, []).append(entry)
        for page, items in pages.items():
            n = len(items)
            step = (content_h - glyph_h) / (n - 1) if n > 1 else 0.0
            for row, (block_no, line_no, _) in enumerate(items):
                self._grid_spread[(block_no, line_no)] = (
                    page * page_h + top_m + row * step
                )

    def _apply_grid_justify(self) -> None:
        """单页格子模式下，把行距撑到首行贴顶、末行贴底。"""
        style = self.style
        if not bool(getattr(style, "grid_mode", False)):
            return
        if not bool(getattr(style, "grid_justify", False)):
            return
        doc = self.doc
        doc.documentLayout().documentSize()
        if doc.pageCount() != 1:
            return
        line_count = 0
        block = doc.begin()
        while block.isValid():
            lay = block.layout()
            if lay is not None:
                line_count += lay.lineCount()
            block = block.next()
        if line_count <= 1:
            return
        content_h = max(
            1.0,
            style.page_height - style.top_margin - style.bottom_margin,
        )
        glyph_h = max(1.0, style.font_size * 1.5)
        step = (content_h - glyph_h) / (line_count - 1)
        _, cell_h = self._grid_metrics()
        if step <= cell_h * 1.001:
            return
        self._grid_line_h = step
        self._apply_style(doc)
        doc.documentLayout().documentSize()

    def _apply_style(self, doc: QTextDocument) -> None:
        style = self.style
        transparent = QColor(0, 0, 0, 0)
        self._block_formats.clear()
        grid = bool(getattr(style, "grid_mode", False))
        align_cols = bool(getattr(style, "grid_align_cols", True))
        cell_w, cell_h = self._grid_metrics() if grid else (0.0, 0.0)

        # 行距 / 首行缩进 / 统一字体
        block = doc.begin()
        while block.isValid():
            fmt = block.blockFormat()
            if grid:
                fmt.setLineHeight(
                    max(1.0, self._grid_line_h or cell_h),
                    QTextBlockFormat.LineHeightTypes.FixedHeight.value,
                )
                fmt.setTopMargin(0)
                fmt.setBottomMargin(0)
            else:
                fmt.setLineHeight(
                    max(0.5, style.line_spacing) * 100.0,
                    QTextBlockFormat.LineHeightTypes.ProportionalHeight.value,
                )
            heading = fmt.headingLevel()

            # 找块内第一个有字的 fragment，用它判断是不是标题
            first_size = 0.0
            probe = block.begin()
            while not probe.atEnd():
                frag = probe.fragment()
                if frag.isValid() and frag.text().strip():
                    first_size = frag.charFormat().font().pointSizeF()
                    break
                try:
                    probe += 1
                except TypeError:
                    probe = probe.__iadd__(1)  # type: ignore[attr-defined]

            in_table = False
            try:
                in_table = QTextCursor(block).currentTable() is not None
            except Exception:
                in_table = False
            if grid and in_table:
                # 表格单元格不套网格固定行高，否则单元格会被撑成整格高
                fmt.setLineHeight(
                    max(0.5, style.line_spacing) * 100.0,
                    QTextBlockFormat.LineHeightTypes.ProportionalHeight.value,
                )

            # 图片行不能按格子固定行高，否则图片会压到下一行文字上
            has_image = False
            image_h = 0.0
            probe_img = block.begin()
            while not probe_img.atEnd():
                frag_img = probe_img.fragment()
                if frag_img.isValid() and frag_img.charFormat().isImageFormat():
                    has_image = True
                    image_h = max(image_h, float(QTextImageFormat(frag_img.charFormat()).height()))
                try:
                    probe_img += 1
                except TypeError:
                    probe_img = probe_img.__iadd__(1)  # type: ignore[attr-defined]
            if grid and has_image:
                fmt.setLineHeight(
                    max(1.0, cell_h, image_h + 4.0),
                    QTextBlockFormat.LineHeightTypes.FixedHeight.value,
                )
            centered = bool(
                fmt.alignment()
                & (
                    Qt.AlignmentFlag.AlignHCenter
                    | Qt.AlignmentFlag.AlignRight
                    | Qt.AlignmentFlag.AlignJustify
                )
            )
            body_ref = max(BASE_EDITOR_SIZE, style.font_size)
            headingish = heading > 0 or first_size > body_ref * 1.05
            existing_indent = fmt.textIndent()
            if existing_indent < 0:
                fmt.setTextIndent(0)
            elif centered or headingish or in_table or block.textList() is not None:
                fmt.setTextIndent(0)
            else:
                indent_unit = cell_w if (grid and align_cols) else style.font_size
                fmt.setTextIndent(style.first_indent * indent_unit)
            block_cursor = QTextCursor(block)
            fmt.setBackground(QBrush())
            block_cursor.setBlockFormat(fmt)

            # 逐 fragment 改字体、透明，同时记下每个字的字符格式，
            # 供逐字绘制时还原加粗/斜体/下划线/标题字号。
            ranges: list[tuple[int, int, QTextCharFormat]] = []
            block_pos = block.position()
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid():
                    cfmt = frag.charFormat()
                    if cfmt.isImageFormat():
                        pass
                    else:
                        cfmt.setFontFamily(self.font_family)
                        size = cfmt.font().pointSizeF()
                        block_size = block.charFormat().font().pointSizeF()
                        # HTML 的 xx-large / 标题继承只体现在 block 字符格式上，
                        # fragment 里读到的可能还是 12pt，要用 block 尺寸兜底。
                        if size <= 0:
                            size = block_size
                        if size <= BASE_EDITOR_SIZE * 1.05 and block_size > BASE_EDITOR_SIZE * 1.05:
                            size = block_size
                        if size <= 0 or size <= body_ref * 1.05:
                            target = style.font_size
                        else:
                            target = style.font_size * (size / BASE_EDITOR_SIZE)
                        cfmt.setFontPointSize(max(1.0, target))
                        cfmt.setFontLetterSpacingType(
                            QFont.SpacingType.AbsoluteSpacing
                        )
                        if grid and align_cols:
                            probe = QFont(cfmt.font())
                            probe.setPointSizeF(max(1.0, target))
                            advance_ratio = (
                                QFontMetricsF(probe).horizontalAdvance("永")
                                / max(1.0, target)
                            )
                            letter_spacing = (
                                cell_w
                                - target * max(0.4, advance_ratio)
                                - 0.05
                            )
                        else:
                            letter_spacing = float(style.letter_spacing)
                        cfmt.setFontLetterSpacing(
                            max(-100.0, min(100.0, letter_spacing))
                        )
                        cfmt.setForeground(transparent)
                        cfmt.clearBackground()
                        cursor = QTextCursor(doc)
                        cursor.setPosition(frag.position())
                        cursor.setPosition(
                            frag.position() + frag.length(),
                            QTextCursor.MoveMode.KeepAnchor,
                        )
                        cursor.setCharFormat(cfmt)
                        start = frag.position() - block_pos
                        ranges.append((start, start + frag.length(), cfmt))
                # 某些 PySide6 版本不支持 +=，用 next 兜底
                try:
                    it += 1
                except TypeError:
                    it = it.__iadd__(1)  # type: ignore[attr-defined]
            self._block_formats[block.blockNumber()] = ranges
            block = block.next()

        # 页边距
        frame_fmt = doc.rootFrame().frameFormat()
        frame_fmt.setLeftMargin(style.left_margin)
        frame_fmt.setTopMargin(style.top_margin)
        frame_fmt.setRightMargin(style.right_margin)
        frame_fmt.setBottomMargin(style.bottom_margin)
        frame_fmt.setBorder(0)
        frame_fmt.setPadding(0)
        doc.rootFrame().setFrameFormat(frame_fmt)

    # ---------- 页面 ----------

    def page_count(self) -> int:
        if bool(getattr(self.style, "grid_mode", False)):
            return max(1, getattr(self, "_grid_page_count", 1))
        return max(1, self.doc.pageCount())

    # 分页预设覆盖外观与页边距；纸张、字号、行距、格子行列
    # 仍按全局设置，否则每页分页会互相打架。
    _PAGE_VISUAL_KEYS = (
        "font_path",
        "ink_color",
        "background_path",
        "sharp_edges",
        "left_margin",
        "right_margin",
        "top_margin",
        "bottom_margin",
        "jitter_scale",
        "font_size_sigma",
        "word_spacing_sigma",
        "line_spacing_sigma",
        "x_sigma",
        "y_sigma",
        "theta_sigma",
        "line_theta_sigma",
        "alpha_sigma",
        "font_size_scale",
        "word_spacing_scale",
        "line_spacing_scale",
        "x_scale",
        "y_scale",
        "theta_scale",
        "line_theta_scale",
        "alpha_scale",
        "stroke_offset_scale",
        "stroke_theta_scale",
        "seed",
    )

    def _page_style(self, page: int):
        styles = getattr(self.style, "page_preset_styles", None) or []
        if not bool(getattr(self.style, "page_presets_enabled", False)) or not styles:
            return self.style
        data = styles[page % len(styles)]
        if not isinstance(data, dict):
            return self.style
        style = copy.copy(self.style)
        for key in self._PAGE_VISUAL_KEYS:
            if key in data:
                setattr(style, key, data[key])
        return style

    def _load_background(self, style=None) -> QImage | None:
        style = style or self.style
        path = style.background_path
        if path and Path(path).exists():
            cached = _BG_CACHE.get(path)
            if cached is not None:
                return cached
            # 原始纸张图可能几千万像素，Qt 默认会拒绝加载；先缩到够用的尺寸
            reader = QImageReader(path)
            reader.setAutoTransform(True)
            size = reader.size()
            if size.isValid() and (size.width() > 2400 or size.height() > 3400):
                reader.setScaledSize(
                    size.scaled(2400, 3400, Qt.AspectRatioMode.KeepAspectRatio)
                )
            image = reader.read()
            if not image.isNull():
                _BG_CACHE[path] = image
                return image
        return None

    def _draw_background(self, painter: QPainter, bg: QImage | None) -> None:
        w, h = self.style.page_width, self.style.page_height
        if bg is None:
            painter.fillRect(QRectF(0, 0, w, h), QColor("#ffffff"))
            return
        # 等比裁切铺满整页
        iw, ih = bg.width(), bg.height()
        target = w / h
        if iw / ih > target:
            crop_w = int(ih * target)
            src = QRectF((iw - crop_w) / 2, 0, crop_w, ih)
        else:
            crop_h = int(iw / target)
            src = QRectF(0, (ih - crop_h) / 2, iw, crop_h)
        painter.drawImage(QRectF(0, 0, w, h), bg, src)

    def paint_page(self, painter: QPainter, page: int, draw_background: bool = True) -> None:
        style = self.style
        page_style = self._page_style(page)
        if draw_background:
            self._draw_background(painter, self._load_background(page_style))

        painter.save()
        painter.translate(0, -page * style.page_height)
        page_rect = QRectF(0, page * style.page_height, style.page_width, style.page_height)
        # 注意：clip 要用文档坐标。translate 之后再用 (0,0,w,h) 会裁到画布外。
        painter.setClipRect(page_rect)
        # Qt 画表格线、单元格底色、图片；文字是透明的
        self.doc.drawContents(painter, page_rect)
        if page_style.sharp_edges:
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, False)
        self._draw_hand_text(painter, page, page_rect, style_override=page_style)
        painter.restore()

    def render_page_image(self, page: int, dpi: int = 150, draw_background: bool = True) -> QImage:
        style = self.style
        page_style = self._page_style(page)
        scale = dpi / 72.0
        image = QImage(
            max(1, round(style.page_width * scale)),
            max(1, round(style.page_height * scale)),
            QImage.Format.Format_ARGB32_Premultiplied,
        )
        image.fill(QColor("#ffffff"))
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, not page_style.sharp_edges)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.scale(scale, scale)
        self.paint_page(painter, page, draw_background)
        painter.end()
        return image

    # ---------- 手写字 ----------

    def _draw_hand_text(
        self, painter: QPainter, page: int, clip: QRectF, style_override=None
    ) -> None:
        style = style_override or self.style
        page_family = self._load_font(style.font_path) or self.font_family
        jitter = max(0.0, style.jitter_scale)
        rng = random.Random(style.seed + page * 7919)
        ink = QColor(style.ink_color)
        if not ink.isValid():
            ink = QColor("#202020")

        layout = self.doc.documentLayout()
        grid = bool(getattr(style, "grid_mode", False))
        align_cols = bool(getattr(style, "grid_align_cols", True))
        cell_w, cell_h = self._grid_metrics(style) if grid else (0.0, 0.0)
        page_dx = float(getattr(style, "left_margin", self.style.left_margin)) - self.style.left_margin
        page_dy = float(getattr(style, "top_margin", self.style.top_margin)) - self.style.top_margin
        page_left = max(0.0, float(getattr(style, "left_margin", self.style.left_margin)))
        block = self.doc.begin()
        grid_rows = max(1, int(getattr(style, "grid_rows", 0) or 1))
        while block.isValid():
            rect = layout.blockBoundingRect(block)
            text = block.text()
            in_table = QTextCursor(block).currentTable() is not None
            if (not grid or in_table) and (
                rect.bottom() < clip.top() or rect.top() > clip.bottom()
            ):
                block = block.next()
                continue

            snap_grid = grid and not in_table
            snap_cols = snap_grid and align_cols
            block_font = block.charFormat().font()
            line_layout = block.layout()
            grid_leading = (
                line_layout.lineAt(0).y()
                if snap_grid and line_layout is not None and line_layout.lineCount()
                else 0.0
            )
            if line_layout is not None:
                for li in range(line_layout.lineCount()):
                    line = line_layout.lineAt(li)
                    row_index = self._grid_row_of.get((block.blockNumber(), li))
                    target_top = None
                    if snap_grid and row_index is not None:
                        if row_index // grid_rows != page:
                            continue
                        target_top = (
                            page * style.page_height
                            + style.top_margin
                            + (row_index % grid_rows) * cell_h
                        )
                    baseline = rect.top() + page_dy + line.y() + line.ascent()
                    text_start = line.textStart()
                    text_len = line.textLength()
                    indent_pt = block.blockFormat().textIndent()
                    indent_cells = 0
                    if snap_cols and text_start == 0 and indent_pt > 0:
                        indent_cells = max(0, round(indent_pt / cell_w))
                    if snap_grid:
                        line_dy = 0.0
                        line_tilt = 0.0
                    else:
                        line_dy = rng.gauss(
                            0.0,
                            style.line_spacing_sigma
                            * style.line_spacing_scale
                            * style.font_size
                            * jitter,
                        )
                        line_tilt = rng.gauss(
                            0.0,
                            style.line_theta_sigma * style.line_theta_scale * jitter,
                        )
                    tan_tilt = math.tan(math.radians(line_tilt))

                    for i in range(text_len):
                        pos = text_start + i
                        if pos < 0 or pos >= len(text):
                            continue
                        ch = text[pos]
                        if ch in ("\n", "\u2029", "\ufffc", "\r"):
                            continue
                        if ch.isspace():
                            continue

                        cfmt = self._format_at(block.blockNumber(), pos, block_font)
                        font = QFont(cfmt.font()) if cfmt else QFont(block_font)
                        font.setFamily(page_family)
                        if style.sharp_edges:
                            font.setStyleStrategy(QFont.StyleStrategy.NoAntialias)
                        size = font.pointSizeF()
                        if size <= 0:
                            size = style.font_size
                        size_factor = 1.0 + rng.gauss(
                            0.0, style.font_size_sigma * style.font_size_scale * jitter
                        )
                        # 字距是排版时定死的，字号再放太大会互相压笔画
                        size_factor = min(1.10, max(0.90, size_factor))
                        font.setPointSizeF(max(1.0, size * size_factor))
                        fm = QFontMetricsF(font)

                        if snap_cols:
                            # 已经按列数插过硬换行，这里直接一字一格。
                            # 用 line.x() 处理首行缩进，续行 x 为 0。
                            advance = max(1.0, cell_w)
                            cols = max(1, int(getattr(style, "grid_cols", 0) or 1))
                            start_col = int(round(line.x() / cell_w))
                            col = max(0, min(cols - 1, start_col + i))
                            center_x = page_left + col * cell_w + cell_w / 2.0
                        else:
                            x0, _ = line.cursorToX(pos)
                            x1, _ = line.cursorToX(pos + 1)
                            advance = abs(x1 - x0)
                            if advance <= 0.01:
                                advance = fm.horizontalAdvance(ch)
                            if advance <= 0.01:
                                continue
                            start_x = rect.left() + page_dx + line.x() + min(x0, x1)
                            center_x = start_x + advance / 2.0
                            center_x += rng.gauss(
                                0.0,
                                style.word_spacing_sigma
                                * style.word_spacing_scale
                                * size
                                * jitter,
                            )
                            center_x += rng.gauss(
                                0.0, style.x_sigma * style.x_scale * size * jitter
                            )

                        dy_tilt = tan_tilt * (center_x - rect.left())
                        if snap_grid:
                            if target_top is not None:
                                baseline_y = (
                                    target_top
                                    + fm.ascent()
                                    + min(2.0, max(0.5, cell_h * 0.04))
                                )
                            else:
                                # 固定行高会在行上方留 leading，先扣掉它，
                                # 让字顶贴着格子/页边距的上边界。
                                baseline_y = (
                                    rect.top()
                                    + line.y()
                                    - grid_leading
                                    + fm.ascent()
                                    + min(2.0, max(0.5, cell_h * 0.04))
                                )
                        else:
                            baseline_y = baseline + line_dy + dy_tilt
                            baseline_y += rng.gauss(
                                0.0, style.y_sigma * style.y_scale * size * jitter
                            )
                        angle = line_tilt + rng.gauss(
                            0.0, style.theta_sigma * style.theta_scale * jitter
                        )

                        # 按 handright 的做法：把字拆成连通墨块，每块整体平移/旋转。
                        # 没有墨块的字符退回普通 drawText。
                        parts = None
                        if style.stroke_offset_scale > 0 or style.stroke_theta_scale > 0:
                            parts = glyph_parts.glyph_parts(ch, font)

                        fm = QFontMetricsF(font)
                        ascent = fm.ascent()
                        painter.save()
                        painter.translate(center_x, baseline_y - ascent / 2.0)
                        painter.rotate(angle)
                        painter.setFont(font)
                        alpha = int(
                            max(
                                120,
                                min(
                                    255,
                                    ink.alpha()
                                    - abs(
                                        rng.gauss(
                                            0.0,
                                            style.alpha_sigma * style.alpha_scale,
                                        )
                                    )
                                    * 255,
                                ),
                            )
                        )
                        color = QColor(ink)
                        color.setAlpha(alpha)
                        if parts is not None:
                            # 先把整字按 160px 画好，再把每个连通墨块
                            # 在整字内部做刚体平移/旋转，最后整字缩放。
                            offset = 7.0 * style.stroke_offset_scale * jitter
                            theta = 3.0 * style.stroke_theta_scale * jitter
                            assembled = QImage(
                                parts.width,
                                parts.height,
                                QImage.Format.Format_ARGB32_Premultiplied,
                            )
                            assembled.fill(Qt.GlobalColor.transparent)
                            ap = QPainter(assembled)
                            ap.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                            ap.setRenderHint(
                                QPainter.RenderHint.SmoothPixmapTransform, True
                            )
                            for part in parts.parts:
                                dx = rng.gauss(0.0, offset) if offset else 0.0
                                dy = rng.gauss(0.0, offset) if offset else 0.0
                                ang = rng.gauss(0.0, theta) if theta else 0.0
                                ap.save()
                                ap.translate(
                                    parts.pad + part.cx + dx,
                                    parts.pad + parts.ascent + part.cy + dy,
                                )
                                ap.rotate(ang)
                                ap.drawImage(
                                    QRectF(
                                        -part.image.width() / 2.0,
                                        -part.image.height() / 2.0,
                                        part.image.width(),
                                        part.image.height(),
                                    ),
                                    part.image,
                                )
                                ap.restore()
                            ap.end()
                            tinted = assembled
                            tp = QPainter(tinted)
                            tp.setCompositionMode(
                                QPainter.CompositionMode.CompositionMode_SourceIn
                            )
                            tp.fillRect(tinted.rect(), color)
                            tp.end()
                            # 字间距只改变排版时的槽宽，不能拿来缩放字形；
                            # 否则拉开字距会把每个字横向拉长。
                            actual_size = font.pointSizeF()
                            sx = actual_size / glyph_parts.CANON_PT
                            sy = actual_size / glyph_parts.CANON_PT
                            target = QRectF(
                                -advance / 2.0 - parts.pad * sx,
                                ascent / 2.0
                                - (parts.pad + parts.ascent) * sy,
                                parts.width * sx,
                                parts.height * sy,
                            )
                            painter.setRenderHint(
                                QPainter.RenderHint.Antialiasing, True
                            )
                            painter.setRenderHint(
                                QPainter.RenderHint.SmoothPixmapTransform, True
                            )
                            painter.drawImage(target, tinted)
                        else:
                            pen = QPen(color)
                            pen.setWidthF(0.0)
                            painter.setPen(pen)
                            painter.drawText(QPointF(-advance / 2.0, ascent / 2.0), ch)
                        if cfmt.fontUnderline() if cfmt else block_font.underline():
                            underline_pen = QPen(color)
                            underline_pen.setWidthF(max(0.8, size * 0.055))
                            painter.setPen(underline_pen)
                            uy = ascent / 2.0 + size * 0.12
                            painter.drawLine(
                                QPointF(-advance / 2.0, uy),
                                QPointF(advance / 2.0, uy),
                            )
                        painter.restore()

            block = block.next()

    def _format_at(self, block_number: int, index: int, fallback: QFont):
        for start, end, fmt in self._block_formats.get(block_number, ()):
            if start <= index < end:
                return fmt
        return None

_PAGE_LAYOUT_KEYS = (
    "font_size",
    "line_spacing",
    "letter_spacing",
    "first_indent",
    "grid_mode",
    "grid_align_cols",
    "grid_rows",
    "grid_cols",
)


def page_style_for(style: HandStyle, page: int):
    """完整应用某一页预设：外观 + 页边距 + 字号/行距/格子行列。"""
    styles = getattr(style, "page_preset_styles", None) or []
    if not bool(getattr(style, "page_presets_enabled", False)) or not styles:
        return style
    data = styles[page % len(styles)]
    if not isinstance(data, dict):
        return style
    out = copy.copy(style)
    for key in HandRenderer._PAGE_VISUAL_KEYS + _PAGE_LAYOUT_KEYS:
        if key in data:
            value = data[key]
            if key == "grid_align_cols":
                value = bool(value)
            setattr(out, key, value)
    return out


def _first_line_position(doc: QTextDocument, page_height: float, bottom_margin: float) -> int:
    """找第一页内容结束处的字符位置；找不到返回 0。"""
    layout = doc.documentLayout()
    content_bottom = max(1.0, page_height - bottom_margin)
    block = doc.begin()
    while block.isValid():
        rect = layout.blockBoundingRect(block)
        # 只在 block 边界切分，避免把一段文字的视觉行拆成多个段落。
        if rect.top() >= content_bottom or rect.bottom() > content_bottom:
            return block.position()
        block = block.next()
    return 0


def _grid_cut_position(renderer: HandRenderer, rows: int) -> int:
    if rows <= 0:
        return 0
    for (block_no, line_no), row in sorted(
        renderer._grid_row_of.items(), key=lambda item: (item[1], item[0])
    ):
        if row < rows:
            continue
        block = renderer.doc.findBlockByNumber(block_no)
        if not block.isValid() or block.layout() is None:
            continue
        if line_no >= block.layout().lineCount():
            continue
        line = block.layout().lineAt(line_no)
        return block.position() + line.textStart()
    return 0


def _split_at(doc: QTextDocument, pos: int) -> tuple[str, str]:
    before = QTextCursor(doc)
    before.setPosition(0)
    before.setPosition(pos, QTextCursor.MoveMode.KeepAnchor)
    after = QTextCursor(doc)
    after.setPosition(pos)
    after.movePosition(
        QTextCursor.MoveOperation.End, QTextCursor.MoveMode.KeepAnchor
    )
    return before.selection().toHtml(), after.selection().toHtml()


def _html_units(html: str) -> list[str]:
    """把整份 HTML 拆成顶层块单元（段落/标题/列表/表格/图片）。"""
    try:
        from lxml import html as lxml_html
    except Exception:
        return [html]
    try:
        root = lxml_html.fromstring(html)
    except Exception:
        return [html]
    body = root.find("body")
    container = body if body is not None else root
    units: list[str] = []
    for child in container:
        if not isinstance(child.tag, str):
            continue
        tag = child.tag.lower()
        if tag in ("p", "h1", "h2", "h3", "h4", "h5", "h6",
                   "li", "table", "ul", "ol", "blockquote", "pre",
                   "img", "hr", "div"):
            if tag == "div":
                inner = [lxml_html.tostring(c, encoding="unicode") for c in child]
                units.extend(inner or [lxml_html.tostring(child, encoding="unicode")])
            else:
                units.append(lxml_html.tostring(child, encoding="unicode"))
    if not units:
        text = container.text_content()
        units = [f"<p>{text}</p>"] if text.strip() else ["<p></p>"]
    return units


def _split_html_unit(unit: str) -> list[str]:
    """把一个过高的段落/标题按句号切成多个块；表格/图片不拆。"""
    try:
        from lxml import html as lxml_html
    except Exception:
        return [unit]
    try:
        el = lxml_html.fromstring(unit)
    except Exception:
        return [unit]
    tag = (el.tag or "").lower()
    if tag not in ("p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote"):
        return [unit]
    text = el.text_content()
    if len(text) <= 1:
        return [unit]
    parts = [p.strip() for p in re.split(r"(?<=[。！？!?])\s*", text) if p.strip()]
    if len(parts) <= 1:
        # 短句没有句末标点时不要硬拆，否则整句会被拆成半句/单字；
        # 只有很长的无标点段落才按长度兜底切分。
        if len(text) < 80:
            return [unit]
        size = 120
        parts = [text[i:i + size] for i in range(0, len(text), size)]
    if len(parts) <= 1:
        return [unit]
    style = el.get("style") or ""
    out = []
    for i, part in enumerate(parts):
        st = style
        if i > 0 and "text-indent" not in st:
            st += ";text-indent:0"
        out.append(f'<p style="{st}">{_escape(part)}</p>')
    return out


def _escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;"))


class PagedHandRenderer:
    """逐页排版渲染器：每一页用该页预设重新建文档、重新分页。

    只在启用逐页预设时使用；未启用时等价于 HandRenderer。
    """

    def __init__(self, html: str, style: HandStyle):
        self.style = style
        self.html = html
        self.pages: list[HandRenderer] = []
        if not bool(getattr(style, "page_presets_enabled", False)):
            self.pages = [HandRenderer(html, style)]
            return
        units = _html_units(html)
        index = 0
        guard = 0
        while index < len(units) and guard < 500:
            guard += 1
            page_style = page_style_for(style, len(self.pages))
            # 这个 renderer 只代表一页，不能再按 page 0 二次套用整组逐页预设；
            # 否则第 2 页会被第 1 页的背景/字体/页边距覆盖。
            page_style.page_presets_enabled = False
            # 贪心：逐步加单元，直到这一页排版超过一页
            end = index
            accepted = None
            while end < len(units):
                candidate = "".join(units[index:end + 1])
                renderer = HandRenderer(candidate, page_style, preserve_blocks=True)
                count = (renderer._grid_page_count
                         if bool(getattr(page_style, "grid_mode", False))
                         else renderer.page_count())
                if count <= 1:
                    accepted = (end + 1, renderer)
                    end += 1
                else:
                    break
            if accepted is None:
                # 单个单元本身就超页：拆成句子/片段再试
                pieces = _split_html_unit(units[index])
                if len(pieces) > 1:
                    units[index:index + 1] = pieces
                    continue
                accepted = (index + 1,
                            HandRenderer(units[index], page_style, preserve_blocks=True))
            # 下一页的第一个单元太长，导致本页明明还有空位却直接换页：
            # 把那个单元拆成句子/片段，继续试着填满当前页。
            # 下一页第一个单元太长、当前页还剩空位时，只尝试追加“整句”片段；
            # 放不下就整句留给下一页，不能再把句子拆碎，否则会出现一字一行。
            if end < len(units) and end > index:
                pieces = _split_html_unit(units[end])
                if len(pieces) > 1:
                    add = 0
                    for piece in pieces:
                        trial = "".join(units[index:end] + pieces[:add] + [piece])
                        trial_r = HandRenderer(trial, page_style, preserve_blocks=True)
                        trial_count = (
                            trial_r._grid_page_count
                            if bool(getattr(page_style, "grid_mode", False))
                            else trial_r.page_count()
                        )
                        if trial_count > 1:
                            break
                        add += 1
                    units[end:end + 1] = pieces[add:]
                    if add:
                        accepted = (
                            end + add,
                            HandRenderer(
                                "".join(units[index:end + add]),
                                page_style,
                                preserve_blocks=True,
                            ),
                        )
            index, renderer = accepted
            self.pages.append(renderer)
        if not self.pages:
            self.pages = [HandRenderer(html, style)]


    def page_count(self) -> int:
        return max(1, len(self.pages))

    def render_page_image(self, page: int, dpi: int = 150, draw_background: bool = True) -> QImage:
        page = max(0, min(page, len(self.pages) - 1))
        return self.pages[page].render_page_image(0, dpi, draw_background)

    def paint_page(self, painter: QPainter, page: int, draw_background: bool = True) -> None:
        page = max(0, min(page, len(self.pages) - 1))
        self.pages[page].paint_page(painter, 0, draw_background)


def make_renderer(html: str, style: HandStyle):
    if bool(getattr(style, "page_presets_enabled", False)):
        return PagedHandRenderer(html, style)
    return HandRenderer(html, style)
