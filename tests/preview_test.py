import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.mainwindow import MainWindow

app = QApplication(sys.argv)
win = MainWindow()
win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
win.show()
app.processEvents()

paras = "\n".join(
    f"<p>第 {i + 1} 段：预览性能测试，看看长文档在右侧窗口里渲染多页要多久。正文会不断重复直到分页。</p>"
    for i in range(45)
)
win.editor.setHtml("<h1 style='text-align:center;'>预览性能测试</h1>" + paras)
start = time.perf_counter()
win._refresh_preview()
app.processEvents()
print("preview first:", round((time.perf_counter() - start) * 1000), "ms", win.status_pages.text(), "zoom", round(win.preview.canvas.zoom, 3), "canvas", win.preview.canvas.size().width(), win.preview.canvas.size().height())

# 换 B5 后应重新适应宽度
win.paper_combo.setCurrentText("B5（176 × 250 mm）")
win._refresh_preview()
app.processEvents()
print("after B5:", win.style.page_width, win.style.page_height, "zoom", round(win.preview.canvas.zoom, 3), "page px", win.preview.canvas.page_size().width(), win.preview.canvas.page_size().height())

win.grab().save(str(Path(r"D:\HandWriteStudio\samples\ui_multipage.png")))
print("saved ui_multipage.png")
