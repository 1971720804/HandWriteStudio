"""编辑区：一个面向排版的 QTextEdit 包装。

编辑区本身用系统字体显示，保证可读；真正的排版结果由右侧手写预览呈现。
这里只负责富文本编辑、表格、图片、粘贴和 HTML 读写。
"""
from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QEvent, QMimeData, QPoint, QPointF, QRect, QRectF, Qt, QUrl
from PySide6.QtGui import (
    QAction,
    QColor,
    QContextMenuEvent,
    QFont,
    QImage,
    QMouseEvent,
    QPainter,
    QPen,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextFrameFormat,
    QTextImageFormat,
    QTextLength,
    QTextTableFormat,
)
from PySide6.QtWidgets import QMenu, QTextEdit

from .image_tools import CropDialog, ImageSizeDialog
from .renderer import image_to_data_uri

BASE_FONT_SIZE = 12.0
MAX_IMAGE_WIDTH = 400.0

_DROP_STYLE_PROPS = re.compile(
    r"^\s*(?:color|background|background-color|font-family|font-size|"
    r"line-height|white-space)\s*:",
    re.IGNORECASE,
)


def _clean_style_attr(match: re.Match) -> str:
    """保留粗体/斜体等排版样式，去掉深色主题的颜色和背景。"""
    quote = match.group(1)
    body = match.group(2)
    kept = [
        part.strip()
        for part in body.split(";")
        if part.strip() and not _DROP_STYLE_PROPS.match(part)
    ]
    if not kept:
        return ""
    return f" style={quote}{'; '.join(kept)}{quote}"


def clean_pasted_html(html: str) -> str:
    """清洗 VS Code / 网页复制来的 HTML。

    只去掉会污染编辑区和手写预览的颜色、背景、字体设置，
    保留段落、换行、加粗、斜体、下划线、表格和图片结构。
    """
    # <style> 块和 meta/link 会带整套主题，先整段删掉。
    html = re.sub(
        r"(?is)<(?:style|script|meta|link|title)\b.*?</(?:style|script|meta|link|title)\s*>",
        "",
        html,
    )
    html = re.sub(
        r"(?is)<(?:style|script|meta|link|title)\b[^>]*?/?>",
        "",
        html,
    )
    # style="..." 里按声明逐条过滤；颜色/背景/字体/字号/行高都去掉。
    html = re.sub(
        r"""(?is)\sstyle\s*=\s*(["'])(.*?)\1""",
        _clean_style_attr,
        html,
    )
    # 旧式 HTML 颜色属性也去掉。
    html = re.sub(
        r"""(?is)\s(?:bgcolor|color|face|background)\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)""",
        "",
        html,
    )
    return html
IMAGE_HANDLE = 7.0
TABLE_EDGE = 5.0


class Editor(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptRichText(True)
        self.setAcceptDrops(True)
        self.setUndoRedoEnabled(True)
        self.setFont(QFont("Microsoft YaHei", int(BASE_FONT_SIZE)))
        self.document().setDefaultFont(QFont("Microsoft YaHei", int(BASE_FONT_SIZE)))
        self.setPlaceholderText("在这里写正文，或从 Word 导入……右上角实时预览手写效果")
        self.setStyleSheet(
            "QTextEdit { background: #ffffff; border: 1px solid #d8dce3;"
            " border-radius: 8px; padding: 18px 22px; selection-background-color: #cfe6ff; }"
        )
        self.setTabStopDistance(32)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)

        self._sel_image_pos: int | None = None
        self._image_rect: QRectF | None = None
        self._image_drag: dict | None = None
        self._table_drag: dict | None = None
        self.verticalScrollBar().valueChanged.connect(self._refresh_image_rect)

    # ---------- HTML ----------

    def content_html(self) -> str:
        # 确保刚拖完表格列宽/行高时布局已刷新，避免 toHtml 导出旧宽度。
        self.document().documentLayout().documentSize()
        return self.toHtml()

    def load_html(self, html: str) -> None:
        self.setHtml(html)
        self.clear_image_selection()

    def plain_text(self) -> str:
        return self.toPlainText()

    # ---------- 字符格式 ----------

    def _merge_char_format(self, fmt: QTextCharFormat) -> None:
        cursor = self.textCursor()
        if cursor.hasSelection():
            cursor.mergeCharFormat(fmt)
            self.setTextCursor(cursor)
        else:
            self.mergeCurrentCharFormat(fmt)

    def set_font_size(self, size: float) -> None:
        fmt = QTextCharFormat()
        fmt.setFontPointSize(max(4.0, float(size)))
        self._merge_char_format(fmt)

    def toggle_bold(self) -> None:
        fmt = QTextCharFormat()
        current = self.currentCharFormat().fontWeight()
        fmt.setFontWeight(
            QFont.Weight.Normal if current >= QFont.Weight.Bold else QFont.Weight.Bold
        )
        self._merge_char_format(fmt)

    def toggle_italic(self) -> None:
        fmt = QTextCharFormat()
        fmt.setFontItalic(not self.currentCharFormat().fontItalic())
        self._merge_char_format(fmt)

    def toggle_underline(self) -> None:
        fmt = QTextCharFormat()
        fmt.setFontUnderline(not self.currentCharFormat().fontUnderline())
        self._merge_char_format(fmt)

    def set_ink_color_for_editor(self, color: QColor) -> None:
        # 编辑区不显示手写墨色，但允许给文字上色当标记？先不做逐字颜色。
        pass

    # ---------- 段落 ----------

    def set_alignment(self, alignment: Qt.AlignmentFlag) -> None:
        self.setAlignment(alignment)

    def apply_paragraph_style(self, size: float, bold: bool) -> None:
        cursor = self.textCursor()
        doc = self.document()
        start = cursor.selectionStart()
        end = max(cursor.selectionEnd(), start)
        block = doc.findBlock(start)
        first = True
        while block.isValid() and (block.position() <= end or first):
            first = False
            bfmt = block.blockFormat()
            bfmt.setHeadingLevel(0)
            QTextCursor(block).setBlockFormat(bfmt)

            cfmt = QTextCharFormat()
            cfmt.setFontPointSize(float(size))
            cfmt.setFontWeight(QFont.Weight.Bold if bold else QFont.Weight.Normal)

            text_end = block.position() + max(0, block.length() - 1)
            bcur = QTextCursor(block)
            bcur.setPosition(block.position())
            bcur.setPosition(text_end, QTextCursor.MoveMode.KeepAnchor)
            if text_end > block.position():
                bcur.mergeCharFormat(cfmt)
            else:
                QTextCursor(block).setBlockCharFormat(cfmt)
            block = block.next()

    def set_first_line_indent(self, indent_chars: float) -> None:
        cursor = self.textCursor()
        doc = self.document()
        start = cursor.selectionStart()
        end = max(cursor.selectionEnd(), start)
        block = doc.findBlock(start)
        first = True
        while block.isValid() and (block.position() <= end or first):
            first = False
            bfmt = block.blockFormat()
            if indent_chars > 0:
                bfmt.setTextIndent(indent_chars * BASE_FONT_SIZE)
            else:
                bfmt.setTextIndent(-1.0)
            QTextCursor(block).setBlockFormat(bfmt)
            block = block.next()

    # ---------- 表格 ----------

    def insert_table(self, rows: int = 3, cols: int = 3) -> None:
        cursor = self.textCursor()
        fmt = QTextTableFormat()
        fmt.setBorder(1)
        fmt.setBorderBrush(QColor("#8a8f98"))
        fmt.setBorderStyle(QTextFrameFormat.BorderStyle.BorderStyle_Solid)
        fmt.setCellPadding(6)
        fmt.setCellSpacing(0)
        fmt.setWidth(QTextLength(QTextLength.Type.PercentageLength, 100))
        cursor.insertTable(max(1, rows), max(1, cols), fmt)
        self.setTextCursor(cursor)

    def _current_table(self):
        return self.textCursor().currentTable()

    def table_add_row(self) -> None:
        self.table_insert_row(above=False)

    def table_insert_row(self, above: bool = False) -> None:
        table = self._current_table()
        if table is None:
            return
        cell = table.cellAt(self.textCursor())
        row = cell.row() if above else cell.row() + cell.rowSpan()
        table.insertRows(row, 1)
        self.setTextCursor(
            table.cellAt(min(row, table.rows() - 1), min(cell.column(), table.columns() - 1))
            .firstCursorPosition()
        )

    def table_add_column(self) -> None:
        self.table_insert_column(left=False)

    def table_insert_column(self, left: bool = False) -> None:
        table = self._current_table()
        if table is None:
            return
        cell = table.cellAt(self.textCursor())
        col = cell.column() if left else cell.column() + cell.columnSpan()
        table.insertColumns(col, 1)
        self.setTextCursor(
            table.cellAt(min(cell.row(), table.rows() - 1), min(col, table.columns() - 1))
            .firstCursorPosition()
        )

    def table_delete_row(self) -> None:
        table = self._current_table()
        if table is None:
            return
        cell = table.cellAt(self.textCursor())
        row, col = cell.row(), cell.column()
        if table.rows() > 1:
            table.removeRows(row, 1)
            row = min(row, table.rows() - 1)
            col = min(col, table.columns() - 1)
            self.setTextCursor(table.cellAt(row, col).firstCursorPosition())
        else:
            self.delete_current_table()

    def table_delete_column(self) -> None:
        table = self._current_table()
        if table is None:
            return
        cell = table.cellAt(self.textCursor())
        row, col = cell.row(), cell.column()
        if table.columns() > 1:
            table.removeColumns(col, 1)
            row = min(row, table.rows() - 1)
            col = min(col, table.columns() - 1)
            self.setTextCursor(table.cellAt(row, col).firstCursorPosition())
        else:
            self.delete_current_table()

    def delete_current_table(self) -> None:
        table = self._current_table()
        if table is None:
            return
        cursor = QTextCursor(table.firstCursorPosition())
        cursor.setPosition(
            table.lastCursorPosition().position() + 1,
            QTextCursor.MoveMode.KeepAnchor,
        )
        cursor.removeSelectedText()
        self.setTextCursor(cursor)

    # ---------- 图片 ----------

    def insert_image(self, image: QImage) -> None:
        if image.isNull():
            return
        uri = image_to_data_uri(image)
        fmt = QTextImageFormat()
        fmt.setName(uri)
        w, h = float(image.width()), float(image.height())
        if w > MAX_IMAGE_WIDTH:
            h *= MAX_IMAGE_WIDTH / w
            w = MAX_IMAGE_WIDTH
        elif w < 1 or h < 1:
            w, h = 120.0, 120.0
        fmt.setWidth(w)
        fmt.setHeight(h)
        self.textCursor().insertImage(fmt)

    def insert_image_file(self, path: str) -> None:
        image = QImage(path)
        if not image.isNull():
            self.insert_image(image)

    # ---------- 图片：选中、缩放、裁剪 ----------

    def _image_format_at(self, start: int) -> QTextImageFormat | None:
        if start < 0 or start >= self.document().characterCount() - 1:
            return None
        cursor = QTextCursor(self.document())
        cursor.setPosition(start + 1)
        fmt = cursor.charFormat()
        if not fmt.isImageFormat():
            return None
        return QTextImageFormat(fmt)

    def _image_resource(self, fmt: QTextImageFormat) -> QImage:
        res = self.document().resource(QTextDocument.ResourceType.ImageResource, QUrl(fmt.name()))
        if isinstance(res, QImage):
            return res
        if hasattr(res, "toImage"):
            return res.toImage()
        return QImage()

    def _image_rect_at(self, start: int, fmt: QTextImageFormat | None = None) -> QRectF | None:
        fmt = fmt or self._image_format_at(start)
        if fmt is None:
            return None
        cursor = QTextCursor(self.document())
        cursor.setPosition(min(start + 1, self.document().characterCount() - 1))
        r = self.cursorRect(cursor)
        image = self._image_resource(fmt)
        w = float(fmt.width()) if fmt.width() > 0 else float(image.width())
        h = float(fmt.height()) if fmt.height() > 0 else float(image.height())
        if w <= 0 or h <= 0:
            return None
        return QRectF(r.left() - w, r.top(), w, h)

    def _image_at(self, view_pos: QPoint) -> tuple[int, QTextImageFormat, QRectF] | None:
        cursor = self.cursorForPosition(view_pos)
        for p in (cursor.position(), cursor.position() + 1):
            if p <= 0:
                continue
            fmt = self._image_format_at(p - 1)
            if fmt is None:
                continue
            rect = self._image_rect_at(p - 1, fmt)
            if rect is not None and rect.adjusted(-IMAGE_HANDLE, -IMAGE_HANDLE, IMAGE_HANDLE, IMAGE_HANDLE).contains(QPointF(view_pos)):
                return p - 1, fmt, rect
        return None

    def _select_image(self, start: int) -> None:
        self._sel_image_pos = start
        self._refresh_image_rect()
        self.viewport().update()

    def clear_image_selection(self) -> None:
        if self._sel_image_pos is not None:
            self._sel_image_pos = None
            self._image_rect = None
            self.viewport().update()

    def _refresh_image_rect(self) -> None:
        if self._sel_image_pos is None:
            return
        fmt = self._image_format_at(self._sel_image_pos)
        if fmt is None:
            self.clear_image_selection()
            return
        self._image_rect = self._image_rect_at(self._sel_image_pos, fmt)

    def _handle_at(self, pos: QPoint) -> str | None:
        r = self._image_rect
        if r is None:
            return None
        points = {
            "tl": r.topLeft(),
            "tr": r.topRight(),
            "bl": r.bottomLeft(),
            "br": r.bottomRight(),
            "t": QPointF(r.center().x(), r.top()),
            "b": QPointF(r.center().x(), r.bottom()),
            "l": QPointF(r.left(), r.center().y()),
            "r": QPointF(r.right(), r.center().y()),
        }
        for name in ("tl", "tr", "bl", "br"):
            p = points[name]
            if abs(pos.x() - p.x()) <= IMAGE_HANDLE and abs(pos.y() - p.y()) <= IMAGE_HANDLE:
                return name
        for name in ("t", "b", "l", "r"):
            p = points[name]
            if abs(pos.x() - p.x()) <= IMAGE_HANDLE and abs(pos.y() - p.y()) <= IMAGE_HANDLE:
                return name
        # 只要靠近边线也算，方便点中细边
        if abs(pos.x() - r.left()) <= 3 and r.top() <= pos.y() <= r.bottom():
            return "l"
        if abs(pos.x() - r.right()) <= 3 and r.top() <= pos.y() <= r.bottom():
            return "r"
        if abs(pos.y() - r.top()) <= 3 and r.left() <= pos.x() <= r.right():
            return "t"
        if abs(pos.y() - r.bottom()) <= 3 and r.left() <= pos.x() <= r.right():
            return "b"
        return None

    def _apply_image_size(self, start: int, width: float, height: float) -> None:
        cursor = QTextCursor(self.document())
        cursor.setPosition(start)
        cursor.setPosition(min(start + 1, self.document().characterCount() - 1), QTextCursor.MoveMode.KeepAnchor)
        fmt = cursor.charFormat()
        if not fmt.isImageFormat():
            return
        image_fmt = QTextImageFormat(fmt)
        image_fmt.setWidth(max(12.0, float(width)))
        image_fmt.setHeight(max(12.0, float(height)))
        cursor.setCharFormat(image_fmt)
        self._sel_image_pos = start
        self._refresh_image_rect()
        self.viewport().update()

    def _edit_image_size(self, start: int) -> None:
        fmt = self._image_format_at(start)
        if fmt is None:
            return
        image = self._image_resource(fmt)
        w = float(fmt.width()) if fmt.width() > 0 else float(image.width())
        h = float(fmt.height()) if fmt.height() > 0 else float(image.height())
        dialog = ImageSizeDialog(w, h, self)
        if dialog.exec():
            nw, nh = dialog.image_size()
            self._apply_image_size(start, nw, nh)

    def _crop_image(self, start: int) -> None:
        fmt = self._image_format_at(start)
        if fmt is None:
            return
        image = self._image_resource(fmt)
        if image.isNull():
            return
        dialog = CropDialog(image, self)
        if not dialog.exec():
            return
        cropped = dialog.crop_image()
        if cropped.isNull():
            return
        old_w = float(fmt.width()) if fmt.width() > 0 else float(image.width())
        old_h = float(fmt.height()) if fmt.height() > 0 else float(image.height())
        ratio = cropped.width() / max(1, image.width())
        ratio_h = cropped.height() / max(1, image.height())
        new_fmt = QTextImageFormat(fmt)
        new_fmt.setName(image_to_data_uri(cropped))
        new_fmt.setWidth(max(12.0, old_w * ratio))
        new_fmt.setHeight(max(12.0, old_h * ratio_h))
        cursor = QTextCursor(self.document())
        cursor.setPosition(start)
        cursor.setPosition(min(start + 1, self.document().characterCount() - 1), QTextCursor.MoveMode.KeepAnchor)
        cursor.setCharFormat(new_fmt)
        self._sel_image_pos = start
        self._refresh_image_rect()
        self.viewport().update()

    def _restore_image_size(self, start: int) -> None:
        fmt = self._image_format_at(start)
        if fmt is None:
            return
        image = self._image_resource(fmt)
        if image.isNull():
            return
        self._apply_image_size(start, image.width(), image.height())

    def _delete_image(self, start: int) -> None:
        cursor = QTextCursor(self.document())
        cursor.setPosition(start)
        cursor.setPosition(min(start + 1, self.document().characterCount() - 1), QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()
        self.clear_image_selection()

    def _show_image_menu(self, start: int, global_pos: QPoint) -> None:
        menu = QMenu(self)
        act_size = QAction("修改大小…", menu)
        act_size.triggered.connect(lambda: self._edit_image_size(start))
        act_crop = QAction("裁剪图片…", menu)
        act_crop.triggered.connect(lambda: self._crop_image(start))
        act_original = QAction("恢复原始大小", menu)
        act_original.triggered.connect(lambda: self._restore_image_size(start))
        act_delete = QAction("删除图片", menu)
        act_delete.triggered.connect(lambda: self._delete_image(start))
        menu.addAction(act_size)
        menu.addAction(act_crop)
        menu.addAction(act_original)
        menu.addSeparator()
        pos_menu = menu.addMenu("图片位置")
        for label, flag in (
            ("靠左", Qt.AlignmentFlag.AlignLeft),
            ("居中", Qt.AlignmentFlag.AlignHCenter),
            ("靠右", Qt.AlignmentFlag.AlignRight),
        ):
            act = QAction(label, pos_menu)
            act.triggered.connect(lambda _=False, f=flag: self._set_image_alignment(start, f))
            pos_menu.addAction(act)
        pos_menu.addSeparator()
        act_up = QAction("上移", pos_menu)
        act_up.triggered.connect(lambda: self._move_image_vertical(start, -12.0))
        act_down = QAction("下移", pos_menu)
        act_down.triggered.connect(lambda: self._move_image_vertical(start, 12.0))
        pos_menu.addAction(act_up)
        pos_menu.addAction(act_down)
        menu.addSeparator()
        menu.addAction(act_delete)
        menu.exec(global_pos)

    def _image_block_format(self, start: int):
        cursor = QTextCursor(self.document())
        cursor.setPosition(max(0, min(start, self.document().characterCount() - 1)))
        return cursor, cursor.block().blockFormat()

    def _set_image_alignment(self, start: int, flag) -> None:
        cursor, fmt = self._image_block_format(start)
        fmt.setAlignment(flag)
        cursor.setBlockFormat(fmt)
        self._refresh_image_rect()
        self.viewport().update()

    def _move_image_vertical(self, start: int, delta: float) -> None:
        cursor, fmt = self._image_block_format(start)
        fmt.setTopMargin(max(0.0, fmt.topMargin() + delta))
        cursor.setBlockFormat(fmt)
        self._refresh_image_rect()
        self.viewport().update()

    # ---------- 表格：右键与边框拖动 ----------

    def _table_hit(self, view_pos: QPoint) -> tuple[object, str, int] | None:
        cursor = self.cursorForPosition(view_pos)
        table = cursor.currentTable()
        if table is None:
            # 点在表格外边缘外侧 1–5px 时，cursorForPosition 会落到表格后面；
            # 往表内偏一点再取一次，保证边框本身也能拖。
            for dx in (-2, 2, -4, 4, -6, 6):
                probe = self.cursorForPosition(QPoint(view_pos.x() + dx, view_pos.y()))
                if probe.currentTable() is not None:
                    cursor = probe
                    table = probe.currentTable()
                    break
        if table is None:
            return None
        cell = table.cellAt(cursor)
        if not cell.isValid():
            return None
        first = self.cursorRect(cell.firstCursorPosition())
        last = self.cursorRect(cell.lastCursorPosition())
        top = min(first.top(), last.top())
        bottom = max(first.bottom(), last.bottom())
        col = cell.column()
        left = first.left()
        if col > 0 and abs(view_pos.x() - left) <= TABLE_EDGE:
            return table, "col", col - 1
        if col + 1 < table.columns():
            right = self.cursorRect(table.cellAt(cell.row(), col + 1).firstCursorPosition()).left() - 2
        else:
            first_left = self.cursorRect(table.cellAt(0, 0).firstCursorPosition()).left()
            right = first_left - table.format().cellPadding() + self._table_width(table)
        if abs(view_pos.x() - right) <= TABLE_EDGE:
            if col == table.columns() - 1:
                return table, "table", 0
            return table, "col", col
        if abs(view_pos.y() - bottom) <= TABLE_EDGE:
            return table, "row", cell.row()
        return None

    def _table_width(self, table) -> float:
        length = table.format().width()
        if length.type() == QTextLength.Type.PercentageLength:
            page = self.document().pageSize().width()
            margins = self.document().rootFrame().frameFormat().leftMargin() * 2
            return max(80.0, (page - margins) * length.rawValue() / 100.0)
        if length.type() == QTextLength.Type.FixedLength:
            return max(80.0, float(length.rawValue()))
        return max(80.0, float(self.viewport().width() - 32))

    def _table_column_widths(self, table) -> list[float]:
        self.document().documentLayout().documentSize()
        widths = []
        table_width = self._table_width(table)
        first_left = self.cursorRect(table.cellAt(0, 0).firstCursorPosition()).left()
        table_right = first_left - table.format().cellPadding() + table_width
        for col in range(table.columns()):
            left = self.cursorRect(table.cellAt(0, col).firstCursorPosition()).left()
            if col + 1 < table.columns():
                right = self.cursorRect(table.cellAt(0, col + 1).firstCursorPosition()).left() - 2
            else:
                right = table_right
            widths.append(max(24.0, float(right - left)))
        return widths

    def _set_table_column_widths(self, table, widths: list[float]) -> None:
        fmt = table.format()
        total = sum(max(1.0, float(w)) for w in widths)
        # 用百分比而不是固定磅值：编辑区比 A4 正文宽，固定磅值会让表格在预览/导出时溢出页面。
        fmt.setColumnWidthConstraints(
            [
                QTextLength(QTextLength.Type.PercentageLength, max(1.0, float(w)) / total * 100.0)
                for w in widths
            ]
        )
        table.setFormat(fmt)

    def _start_table_drag(self, table, kind: str, index: int, pos: QPoint) -> None:
        if kind == "col":
            widths = self._table_column_widths(table)
            self._table_drag = {
                "table": table,
                "kind": kind,
                "index": index,
                "start": pos,
                "widths": widths,
                "base": widths[index] if index < len(widths) else 80.0,
            }
        elif kind == "table":
            length = table.format().width()
            pct = float(length.rawValue()) if length.type() == QTextLength.Type.PercentageLength else 100.0
            self._table_drag = {
                "table": table,
                "kind": kind,
                "start": pos,
                "base_width": self._table_width(table),
                "base_pct": pct,
            }
        else:
            pads = []
            for c in range(table.columns()):
                cell = table.cellAt(index, c)
                if cell.isValid():
                    fmt = cell.format().toTableCellFormat()
                    pads.append((c, fmt.topPadding(), fmt.bottomPadding()))
            self._table_drag = {
                "table": table,
                "kind": kind,
                "index": index,
                "start": pos,
                "base_height": self.cursorRect(table.cellAt(index, 0).firstCursorPosition()).height(),
                "pads": pads,
            }

    def _drag_table(self, pos: QPoint) -> None:
        drag = self._table_drag
        if drag is None:
            return
        table = drag["table"]
        if drag["kind"] == "table":
            delta = pos.x() - drag["start"].x()
            base = max(80.0, drag["base_width"])
            pct = drag["base_pct"] * max(0.15, (base + delta) / base)
            pct = max(15.0, min(100.0, pct))
            fmt = table.format()
            fmt.setWidth(QTextLength(QTextLength.Type.PercentageLength, pct))
            table.setFormat(fmt)
            self.viewport().update()
            return
        if drag["kind"] == "col":
            delta = pos.x() - drag["start"].x()
            widths = list(drag["widths"])
            index = drag["index"]
            total = sum(widths)
            old = widths[index]
            new = max(24.0, min(total - 24.0 * (len(widths) - 1), drag["base"] + delta))
            widths[index] = new
            # 只带动相邻的一列，保持总宽不变；否则整张表会越拖越宽/越窄。
            neighbor = index + 1 if index + 1 < len(widths) else index - 1
            if 0 <= neighbor < len(widths):
                widths[neighbor] = max(24.0, widths[neighbor] - (new - old))
            total_after = sum(widths)
            if total_after > 0:
                widths = [w * total / total_after for w in widths]
            self._set_table_column_widths(table, widths)
        else:
            delta = pos.y() - drag["start"].y()
            half = delta / 2.0
            for col, top_pad, bottom_pad in drag["pads"]:
                cell = table.cellAt(drag["index"], col)
                if not cell.isValid():
                    continue
                fmt = cell.format().toTableCellFormat()
                fmt.setTopPadding(max(0.0, top_pad + half))
                fmt.setBottomPadding(max(0.0, bottom_pad + half))
                cell.setFormat(fmt)
        self.viewport().update()

    def _show_table_menu(self, cursor: QTextCursor, global_pos: QPoint) -> None:
        table = cursor.currentTable()
        if table is None:
            return
        menu = QMenu(self)
        act_above = QAction("在上方插入行", menu)
        act_above.triggered.connect(lambda: self._table_insert_row_at(cursor, True))
        act_below = QAction("在下方插入行", menu)
        act_below.triggered.connect(lambda: self._table_insert_row_at(cursor, False))
        act_left = QAction("在左侧插入列", menu)
        act_left.triggered.connect(lambda: self._table_insert_column_at(cursor, True))
        act_right = QAction("在右侧插入列", menu)
        act_right.triggered.connect(lambda: self._table_insert_column_at(cursor, False))
        menu.addAction(act_above)
        menu.addAction(act_below)
        menu.addSeparator()
        menu.addAction(act_left)
        menu.addAction(act_right)
        menu.addSeparator()
        act_del_row = QAction("删除当前行", menu)
        act_del_row.triggered.connect(self.table_delete_row)
        act_del_col = QAction("删除当前列", menu)
        act_del_col.triggered.connect(self.table_delete_column)
        act_del_table = QAction("删除表格", menu)
        act_del_table.triggered.connect(self.delete_current_table)
        menu.addAction(act_del_row)
        menu.addAction(act_del_col)
        menu.addAction(act_del_table)
        menu.addSeparator()
        pos_menu = menu.addMenu("表格位置")
        for label, flag in (
            ("靠左", Qt.AlignmentFlag.AlignLeft),
            ("居中", Qt.AlignmentFlag.AlignHCenter),
            ("靠右", Qt.AlignmentFlag.AlignRight),
        ):
            act = QAction(label, pos_menu)
            act.triggered.connect(lambda _=False, f=flag: self._set_table_alignment(cursor, f))
            pos_menu.addAction(act)
        pos_menu.addSeparator()
        act_up = QAction("上移", pos_menu)
        act_up.triggered.connect(lambda: self._move_table_vertical(cursor, -12.0))
        act_down = QAction("下移", pos_menu)
        act_down.triggered.connect(lambda: self._move_table_vertical(cursor, 12.0))
        pos_menu.addAction(act_up)
        pos_menu.addAction(act_down)
        act_full = QAction("整体宽度 100%", menu)
        act_full.triggered.connect(lambda: self._set_table_width(cursor, 100.0))
        menu.addAction(act_full)
        menu.exec(global_pos)

    def _set_table_alignment(self, cursor: QTextCursor, flag) -> None:
        table = cursor.currentTable()
        if table is None:
            return
        fmt = table.format()
        fmt.setAlignment(flag)
        table.setFormat(fmt)

    def _set_table_width(self, cursor: QTextCursor, pct: float) -> None:
        table = cursor.currentTable()
        if table is None:
            return
        fmt = table.format()
        fmt.setWidth(QTextLength(QTextLength.Type.PercentageLength, max(15.0, min(100.0, pct))))
        table.setFormat(fmt)

    def _move_table_vertical(self, cursor: QTextCursor, delta: float) -> None:
        table = cursor.currentTable()
        if table is None:
            return
        fmt = table.format()
        fmt.setTopMargin(max(0.0, fmt.topMargin() + delta))
        table.setFormat(fmt)

    def _table_insert_row_at(self, cursor: QTextCursor, above: bool) -> None:
        table = cursor.currentTable()
        if table is None:
            return
        cell = table.cellAt(cursor)
        row = cell.row() if above else cell.row() + cell.rowSpan()
        table.insertRows(row, 1)
        self.setTextCursor(table.cellAt(min(row, table.rows() - 1), min(cell.column(), table.columns() - 1)).firstCursorPosition())

    def _table_insert_column_at(self, cursor: QTextCursor, left: bool) -> None:
        table = cursor.currentTable()
        if table is None:
            return
        cell = table.cellAt(cursor)
        col = cell.column() if left else cell.column() + cell.columnSpan()
        table.insertColumns(col, 1)
        self.setTextCursor(table.cellAt(min(cell.row(), table.rows() - 1), min(col, table.columns() - 1)).firstCursorPosition())

    # ---------- 鼠标事件 ----------

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            image_hit = self._image_at(pos)
            if image_hit is not None:
                start, fmt, rect = image_hit
                self._select_image(start)
                handle = self._handle_at(pos)
                if handle:
                    self._image_drag = {
                        "mode": "resize",
                        "start": start,
                        "handle": handle,
                        "origin": pos,
                        "rect": rect,
                        "width": rect.width(),
                        "height": rect.height(),
                    }
                else:
                    cursor = QTextCursor(self.document())
                    cursor.setPosition(start)
                    self._image_drag = {
                        "mode": "move",
                        "start": start,
                        "origin": pos,
                        "rect": rect,
                        "base_margin": cursor.block().blockFormat().topMargin(),
                    }
                event.accept()
                return
            if self._sel_image_pos is not None:
                self.clear_image_selection()
            table_hit = self._table_hit(pos)
            if table_hit is not None:
                table, kind, index = table_hit
                self._start_table_drag(table, kind, index, pos)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        pos = event.position().toPoint()
        if self._image_drag is not None:
            self._drag_image(pos)
            event.accept()
            return
        if self._table_drag is not None:
            self._drag_table(pos)
            event.accept()
            return

        if self._sel_image_pos is not None:
            handle = self._handle_at(pos)
            if handle:
                self.viewport().setCursor(self._handle_cursor(handle))
                event.accept()
                return
            if self._image_rect is not None and self._image_rect.contains(QPointF(pos)):
                self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
                event.accept()
                return

        table_hit = self._table_hit(pos)
        if table_hit is not None:
            self.viewport().setCursor(
                Qt.CursorShape.SizeHorCursor
                if table_hit[1] in ("col", "table")
                else Qt.CursorShape.SizeVerCursor
            )
        else:
            self.viewport().setCursor(Qt.CursorShape.IBeamCursor)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._image_drag is not None:
            self._image_drag = None
            self._refresh_image_rect()
            event.accept()
            return
        if self._table_drag is not None:
            self._table_drag = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    @staticmethod
    def _handle_cursor(handle: str):
        if handle in ("tl", "br"):
            return Qt.CursorShape.SizeFDiagCursor
        if handle in ("tr", "bl"):
            return Qt.CursorShape.SizeBDiagCursor
        if handle in ("l", "r"):
            return Qt.CursorShape.SizeHorCursor
        return Qt.CursorShape.SizeVerCursor

    def _drag_image(self, pos: QPoint) -> None:
        drag = self._image_drag
        if drag is None:
            return
        dx = pos.x() - drag["origin"].x()
        dy = pos.y() - drag["origin"].y()
        if drag.get("mode") == "move":
            if abs(dx) < 3 and abs(dy) < 3:
                return
            cursor = QTextCursor(self.document())
            cursor.setPosition(drag["start"])
            fmt = cursor.block().blockFormat()
            width = max(1, self.viewport().width())
            if pos.x() < width / 3:
                fmt.setAlignment(Qt.AlignmentFlag.AlignLeft)
            elif pos.x() < width * 2 / 3:
                fmt.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            else:
                fmt.setAlignment(Qt.AlignmentFlag.AlignRight)
            fmt.setTopMargin(max(0.0, drag["base_margin"] + dy))
            cursor.setBlockFormat(fmt)
            self._refresh_image_rect()
            self.viewport().update()
            return
        handle = drag["handle"]
        w = drag["width"]
        h = drag["height"]
        if "l" in handle:
            w = drag["width"] - dx
        if "r" in handle:
            w = drag["width"] + dx
        if "t" in handle:
            h = drag["height"] - dy
        if "b" in handle:
            h = drag["height"] + dy
        if len(handle) == 2:
            ratio = drag["width"] / max(1.0, drag["height"])
            if abs(dx) >= abs(dy):
                h = w / ratio
            else:
                w = h * ratio
        self._apply_image_size(drag["start"], max(20.0, w), max(20.0, h))

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        if self._sel_image_pos is None:
            return
        self._refresh_image_rect()
        r = self._image_rect
        if r is None:
            return
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor("#2f7bdc"), 1.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(r)
        painter.setBrush(QColor("#ffffff"))
        for p in (
            r.topLeft(),
            r.topRight(),
            r.bottomLeft(),
            r.bottomRight(),
            QPointF(r.center().x(), r.top()),
            QPointF(r.center().x(), r.bottom()),
            QPointF(r.left(), r.center().y()),
            QPointF(r.right(), r.center().y()),
        ):
            painter.drawRect(QRectF(p.x() - 3, p.y() - 3, 6, 6))
        painter.end()

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:  # noqa: N802
        pos = event.pos()
        image_hit = self._image_at(pos)
        if image_hit is not None:
            start, fmt, rect = image_hit
            self._select_image(start)
            self._show_image_menu(start, event.globalPos())
            return
        cursor = self.cursorForPosition(pos)
        if cursor.currentTable() is not None:
            self.setTextCursor(cursor)
            self._show_table_menu(cursor, event.globalPos())
            return
        super().contextMenuEvent(event)

    # ---------- 粘贴 / 拖放 ----------

    def canInsertFromMimeData(self, source: QMimeData) -> bool:  # noqa: N802
        if source.hasImage() or source.hasUrls():
            return True
        return super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source: QMimeData) -> None:  # noqa: N802
        if source.hasImage():
            data = source.imageData()
            image = data if isinstance(data, QImage) else QImage(data)
            if not image.isNull():
                self.insert_image(image)
                return
        if source.hasUrls():
            inserted = False
            for url in source.urls():
                if url.isLocalFile():
                    path = url.toLocalFile()
                    if Path(path).suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"):
                        self.insert_image_file(path)
                        inserted = True
            if inserted:
                return
        if source.hasHtml():
            raw_html = source.html()
            plain = source.text().replace("\x00", "")
            lower = raw_html.lower()
            # 代码/网页复制过来的 HTML 往往带大量主题 span；直接按纯文本
            # 粘贴，避免 Qt 的富文本解析器在异常样式上崩溃。
            if "<table" not in lower and "<img" not in lower:
                if plain.strip():
                    cursor = self.textCursor()
                    cursor.insertText(plain)
                    self.setTextCursor(cursor)
                    return
            cleaned = clean_pasted_html(raw_html)
            if cleaned.strip():
                cursor = self.textCursor()
                try:
                    cursor.insertHtml(cleaned)
                except Exception:
                    cursor.insertText(plain)
                self.setTextCursor(cursor)
                return
        super().insertFromMimeData(source)

    def insertFromMimeDataWithFormat(self, source: QMimeData) -> None:  # pragma: no cover
        self.insertFromMimeData(source)
