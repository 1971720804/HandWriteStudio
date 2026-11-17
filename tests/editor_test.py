import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QTextCursor
from PySide6.QtWidgets import QApplication

from app.editor import Editor
from app.mainwindow import MainWindow, PAPER_SIZES
from app.renderer import HandRenderer
from app.settings import HandStyle

app = QApplication(sys.argv)

# ---------- Editor ----------
editor = Editor()
editor.setHtml("<p>第一段</p><p>第二段</p>")
cur = editor.textCursor()
cur.movePosition(QTextCursor.MoveOperation.End)
editor.setTextCursor(cur)

editor.insert_table(2, 3)
table = editor.textCursor().currentTable()
print("table after insert:", table.rows(), table.columns())
editor.table_add_row()
editor.table_add_column()
table = editor.textCursor().currentTable()
print("table after add:", table.rows(), table.columns())
editor.table_delete_row()
editor.table_delete_column()
table = editor.textCursor().currentTable()
print("table after delete:", table.rows(), table.columns())

img = QImage(800, 400, QImage.Format.Format_ARGB32)
img.fill(QColor("#eef4ff"))
editor.insert_image(img)
html = editor.content_html()
print("html has table:", "<table" in html.lower(), "has data img:", "data:image/png;base64" in html)
r = HandRenderer(html, HandStyle())
print("editor render pages:", r.page_count())
r.render_page_image(0, dpi=100).save(str(Path(r"D:\HandWriteStudio\samples\editor_page.png")))

# ---------- MainWindow style sync ----------
win = MainWindow()
win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
win.show()
app.processEvents()

# switch paper + font via controls
win.paper_combo.setCurrentText("B5（176 × 250 mm）")
win.font_combo.setCurrentIndex(min(1, win.font_combo.count() - 1))
app.processEvents()
print("style paper:", win.style.page_width, win.style.page_height, "font:", Path(win.style.font_path).name)

# 保存成项目，再改样式，再用内部加载逻辑读回（绕开文件对话框）
from app.project import save_project, load_project

proj = Path(r"D:\HandWriteStudio\samples\ui_style_test.hws")
save_project(str(proj), win.editor.content_html(), win.style)
win.style = HandStyle()  # 改回默认
win._sync_style_controls()
print("after reset sync: font combo data:", win.font_combo.currentData())
html2, style2 = load_project(str(proj))
win.style = style2
win.editor.load_html(html2)
win._sync_style_controls()
print("after load sync: font combo data:", win.font_combo.currentData())
print("after load sync: paper text:", win.paper_combo.currentText())
print("style match:", win.style.to_dict() == style2.to_dict())

win._refresh_preview()
app.processEvents()
print("status:", win.status_pages.text(), win.status_words.text())
win.grab().save(str(Path(r"D:\HandWriteStudio\samples\ui_after_style.png")))
