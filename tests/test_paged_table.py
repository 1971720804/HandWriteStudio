import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QBuffer, QByteArray
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from app.renderer import make_renderer
from app.settings import HandStyle

app = QApplication([])

im = QImage(240, 140, QImage.Format.Format_RGB32)
im.fill(QColor("#5b8fd1"))
ba = QByteArray()
buf = QBuffer(ba)
buf.open(QBuffer.OpenModeFlag.WriteOnly)
im.save(buf, "PNG")
uri = "data:image/png;base64," + bytes(ba.toBase64()).decode("ascii")

a = HandStyle()
a.grid_mode = True
a.grid_rows = 8
a.grid_cols = 30
a.font_size = 12
b = HandStyle()
b.grid_mode = True
b.grid_rows = 5
b.grid_cols = 20
b.font_size = 18
s = HandStyle()
s.page_presets_enabled = True
s.page_preset_styles = [a.to_dict(), b.to_dict()]

html = (
    "".join("<p>第%d段测试文字，检查表格图片与分页。</p>" % i for i in range(1, 16))
    + '<table border="1" cellspacing="0" cellpadding="6">'
    + "<tr><td>时间</td><td>事项</td><td>备注</td></tr>"
    + "<tr><td>09:00</td><td>联调</td><td>完成</td></tr>"
    + "<tr><td>14:00</td><td>测试</td><td>待办</td></tr></table>"
    + "<p>图片：</p>"
    + '<p><img src="' + uri + '" width="240" height="140"></p>'
    + "".join("<p>尾段%d测试文字。</p>" % i for i in range(1, 12))
)

r = make_renderer(html, s)
print("pages", r.page_count())
for i in range(r.page_count()):
    path = Path(__file__).resolve().parent.parent / "samples" / f"paged_table_{i}.png"
    r.render_page_image(i, 100).save(str(path))
    print(path)
