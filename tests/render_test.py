"""离屏渲染自测：验证透明文字 + 逐字手写 + 表格/图片/分页。"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtWidgets import QApplication

from app.renderer import HandRenderer
from app.settings import HandStyle


def make_png_data_uri() -> str:
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


def main() -> int:
    app = QApplication(sys.argv)
    data_uri = make_png_data_uri()
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
    <p style="text-align:center;"><img src="{data_uri}" width="180" height="125"></p>
    <p style="text-indent:0;">明天要把接口文档再看一遍，争取自己先跑通一遍流程。</p>
    """
    style = HandStyle()
    renderer = HandRenderer(html, style)
    print("pages:", renderer.page_count())
    out = Path(__file__).resolve().parent.parent / "samples" / "test_page1.png"
    img = renderer.render_page_image(0, 150)
    img.save(str(out))
    print("saved", out, img.width(), img.height())

    # 打印块坐标，确认表格内文字有绝对坐标
    layout = renderer.doc.documentLayout()
    block = renderer.doc.begin()
    n = 0
    while block.isValid() and n < 12:
        r = layout.blockBoundingRect(block)
        print(n, repr(block.text()[:16]), round(r.left(), 1), round(r.top(), 1), round(r.width(), 1), round(r.height(), 1))
        block = block.next()
        n += 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
