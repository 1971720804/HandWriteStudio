import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "windows")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.mainwindow import MainWindow

app = QApplication(sys.argv)
win = MainWindow()
win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
win.jitter_item_sliders["stroke_offset_scale"].setValue(100)
win.jitter_item_sliders["stroke_theta_scale"].setValue(100)
win.editor.setHtml(
    "<h1 style='text-align:center;'>逐笔测试</h1>"
    "<p>永和九年，岁在癸丑，暮春之初，会于会稽山阴之兰亭。</p>"
    "<p>Hello, 123! 标点符号也要能回退。</p>"
)
win.show()
app.processEvents()
win._refresh_preview()
QTest.qWait(900)
out = Path(__file__).resolve().parent.parent / "samples" / "stroke_ui_shot.png"
win.grab().save(str(out))
print("saved", out, "size", win.size().width(), win.size().height())
print("status:", win.status_pages.text(), win.status_render.text())
