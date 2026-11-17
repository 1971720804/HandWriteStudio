from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.mainwindow import MainWindow

text = """查到了：VS Code 复制出来的 HTML 带着 background-color:#1e1e1e、浅色文字、Consolas 这一整套主题样式。原软件直接把它插进编辑区，所以黑底也一起进来了；渲染器又没清字符背景，预览会一片黑，看起来就像崩了。

现在两头都处理了：

粘贴时先清洗：去掉颜色、背景、字体、字号这些样式，只保留段落、换行、加粗、表格、图片。
渲染时再把字符和段落的背景刷子清掉，旧项目里已经带进来的黑底也不会再画出来。
新包：D:\\HandWriteStudio\\HandWriteStudio_v0.4.3.zip，自检过了。

你拿一段 VS Code 代码再粘一次试试；要是还崩，把当时的操作和有没有报错窗口发我，我再往下挖。
"""

app = QApplication([])
app.clipboard().setText(text)
win = MainWindow()
win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
win.show()
win.grid_check.setChecked(True)
QTest.qWait(100)
win.editor.setFocus()
QTest.keyClick(win.editor, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
QTest.qWait(800)
print("alive", win.editor.toPlainText()[:20], len(win.editor.toPlainText()), flush=True)
win.grab().save(str(Path(__file__).resolve().parent.parent / "samples" / "paste_gui.png"))
print("saved", flush=True)
