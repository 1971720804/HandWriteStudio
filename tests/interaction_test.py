"""交互测试：图片手柄缩放、表格列宽/行高拖动、表格右键插入。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QImage, QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.editor import Editor


def find_image(editor: Editor) -> int:
    for pos in range(editor.document().characterCount()):
        if editor._image_format_at(pos) is not None:
            return pos
    return -1


def main() -> None:
    app = QApplication([])
    editor = Editor()
    editor.resize(900, 700)
    editor.show()
    app.processEvents()

    image = QImage(240, 140, QImage.Format.Format_RGB32)
    image.fill(0xFF4488CC)
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    editor.setTextCursor(cursor)
    editor.insert_image(image)
    app.processEvents()

    pos = find_image(editor)
    fmt = editor._image_format_at(pos)
    rect = editor._image_rect_at(pos, fmt)
    print("image pos", pos, "rect", rect, "size", fmt.width(), fmt.height())

    editor._select_image(pos)
    app.processEvents()
    handle = QPoint(round(rect.right()), round(rect.center().y()))
    QTest.mousePress(editor.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, handle)
    QTest.mouseMove(editor.viewport(), handle + QPoint(80, 0), 30)
    QTest.mouseRelease(editor.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, handle + QPoint(80, 0))
    app.processEvents()
    fmt2 = editor._image_format_at(pos)
    print("after drag width", fmt2.width(), "height", fmt2.height())
    assert fmt2.width() > fmt.width()
    editor._select_image(pos)
    app.processEvents()
    editor.grab().save(str(Path(__file__).resolve().parent.parent / "samples" / "image_selected.png"))

    # 表格：插表、拖列宽、拖行高
    editor.clear()
    editor.setHtml("<p>表前</p>")
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    editor.setTextCursor(cursor)
    editor.insert_table(2, 3)
    app.processEvents()
    table = editor.textCursor().currentTable()
    assert table is not None

    # 用真实鼠标事件拖第一列右边框
    cell = table.cellAt(0, 0)
    next_left = editor.cursorRect(table.cellAt(0, 1).firstCursorPosition()).left()
    edge_x = next_left - 2
    edge_y = editor.cursorRect(cell.firstCursorPosition()).center().y()
    hit = editor._table_hit(QPoint(edge_x, edge_y))
    print("table edge hit", hit[1:] if hit else None)
    assert hit is not None and hit[1] == "col"
    base = editor._table_column_widths(table)[0]
    QTest.mousePress(editor.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(edge_x, edge_y))
    QTest.mouseMove(editor.viewport(), QPoint(edge_x + 60, edge_y), 30)
    QTest.mouseRelease(editor.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(edge_x + 60, edge_y))
    app.processEvents()
    after = editor._table_column_widths(table)[0]
    print("column width via mouse", base, "->", after)
    assert after > base

    cell = table.cellAt(0, 0)
    before = cell.format().toTableCellFormat().topPadding()
    editor._start_table_drag(table, "row", 0, QPoint(100, 100))
    editor._drag_table(QPoint(100, 140))
    after_pad = table.cellAt(0, 0).format().toTableCellFormat().topPadding()
    print("row padding", before, "->", after_pad)
    assert after_pad > before

    # 右键插入行/列（直接调方法，避免菜单阻塞）
    table = editor.textCursor().currentTable()
    rows = table.rows()
    cols = table.columns()
    cell_cursor = table.cellAt(1, 1).firstCursorPosition()
    editor._table_insert_row_at(cell_cursor, True)
    editor._table_insert_column_at(cell_cursor, True)
    table = editor.textCursor().currentTable()
    print("table size", rows, cols, "->", table.rows(), table.columns())
    assert table.rows() == rows + 1
    assert table.columns() == cols + 1

    # 拖表格外边缘：整体宽度应缩小，而不是只拉最后一列
    table = editor.textCursor().currentTable()
    before_width = table.format().width().rawValue()
    first_left = editor.cursorRect(table.cellAt(0, 0).firstCursorPosition()).left()
    right = first_left - table.format().cellPadding() + editor._table_width(table)
    y = editor.cursorRect(table.cellAt(0, 0).firstCursorPosition()).center().y()
    hit = editor._table_hit(QPoint(round(right) - 2, y))
    print("table outer edge hit", hit[1:] if hit else None)
    assert hit is not None and hit[1] == "table"
    editor._start_table_drag(table, "table", 0, QPoint(round(right) - 2, y))
    editor._drag_table(QPoint(round(right) - 120, y))
    after_width = table.format().width().rawValue()
    print("table width", before_width, "->", after_width)
    assert after_width < before_width

    print("OK")


if __name__ == "__main__":
    main()
