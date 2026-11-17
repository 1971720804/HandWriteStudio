import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtWidgets import QApplication

from app.mainwindow import MainWindow


def sample_image_uri() -> str:
    img = QImage(260, 180, QImage.Format.Format_ARGB32)
    img.fill(QColor("#d9ecff"))
    p = QPainter(img)
    p.setPen(QColor("#2b6cb0"))
    p.setFont(QFont("Microsoft YaHei", 18))
    p.drawText(img.rect(), 0x84, "示例图片")
    p.end()
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return "data:image/png;base64," + bytes(ba.toBase64()).decode()


app = QApplication(sys.argv)
win = MainWindow()
win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
win.preview.status_message.disconnect()
win.preview.status_message.connect(lambda msg: print("PREVIEW ERROR:\n", msg))
html = f"""
<h1 style="text-align:center;">实 习 日 记</h1>
<p style="text-align:right;">2026 年 11 月 9 日</p>
<p>今天是我到公司实习的第三周。早上提前二十分钟到了工位，把昨天没整理完的测试记录补完，又跟着师傅过了一遍接口文档。</p>
<p>下午开了个短会，讨论下周的版本计划。我发现自己在描述问题时还是容易绕，得练着把话说短一点。</p>
<table border="1" cellspacing="0" cellpadding="6" width="100%">
  <tr><td><b>时间</b></td><td><b>事项</b></td><td><b>备注</b></td></tr>
  <tr><td>09:00</td><td>整理测试记录</td><td>已补完</td></tr>
  <tr><td>14:00</td><td>版本计划会</td><td>记了三条待办</td></tr>
</table>
<p style="text-align:center;"><img src="{sample_image_uri()}" width="180" height="125"></p>
<p style="text-indent:0;">明天要把接口文档再看一遍，争取自己先跑通一遍流程。</p>
"""
win.editor.setHtml(html)
win.show()
app.processEvents()
win._refresh_preview()
app.processEvents()
out = Path(__file__).resolve().parent.parent / "samples" / "ui_shot.png"
ok = win.grab().save(str(out))
print("saved", out, ok, "size", win.size().width(), win.size().height())
print("status:", win.status_pages.text(), win.status_words.text(), win.status_render.text())
print("html head:", win.editor.content_html()[:400])
