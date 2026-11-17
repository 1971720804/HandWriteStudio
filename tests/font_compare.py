import sys

sys.path.insert(0, r"D:\HandWriteStudio")

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtWidgets import QApplication

from app.renderer import HandRenderer
from app.settings import HandStyle

app = QApplication([])

base = r"D:\HandWriteStudio\assets\fonts"
items = [
    ("李国夫手写体", "李国夫手写体.ttf"),
    ("演示悠然小楷", "演示悠然小楷.ttf"),
    ("寒蝉手拙体", "寒蝉手拙体.ttf"),
    ("沐瑶软笔手写体", "沐瑶软笔手写体.ttf"),
    ("江西拙楷2.0", "江西拙楷2.0.ttf"),
    ("钟齐志莽行书", "钟齐志莽行书.ttf"),
    ("霞鹜文楷", "霞鹜文楷.ttf"),
]
html = (
    '<p style="text-align:center"><span style="font-size:26pt">永和九年</span></p>'
    "<p>岁在癸丑，暮春之初，会于会稽山阴之兰亭。</p>"
    "<p>Hello 123! 手写模拟器</p>"
)
rendered = []
for label, filename in items:
    style = HandStyle()
    style.font_path = base + "\\" + filename
    style.font_size = 18
    style.sharp_edges = False
    renderer = HandRenderer(html, style)
    page = renderer.render_page_image(0, 150)
    rendered.append((label, page.copy(QRect(120, 120, 1400, 900))))

width = 1500
height = 500
out = QImage(width, height * len(rendered), QImage.Format.Format_RGB32)
out.fill(0xFFFFFFFF)
painter = QPainter(out)
painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
painter.setFont(QFont("Microsoft YaHei UI", 16))
for index, (label, image) in enumerate(rendered):
    y = index * height
    painter.setPen(QColor("#333333"))
    painter.drawText(24, y + 40, label)
    painter.drawImage(
        180,
        y + 20,
        image.scaledToWidth(
            1150, Qt.TransformationMode.SmoothTransformation
        ),
    )
painter.end()
out.save(r"D:\HandWriteStudio\samples\font_compare_all.png")
print("saved", out.width(), out.height())
