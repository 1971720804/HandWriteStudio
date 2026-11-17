import sys
sys.path.insert(0, r'D:\HandWriteStudio')
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QTextDocument, QFont, QImage, QPainter
from PySide6.QtCore import Qt

app = QApplication([])
htmls = [
    '<p>A    B</p>',
    '<p style="white-space: pre-wrap">A    B</p>',
    '<p>A&nbsp;&nbsp;&nbsp;&nbsp;B</p>',
    '<p>A\tB</p>',
    '<p style="white-space: pre">A    B</p>',
]
for i, h in enumerate(htmls):
    d = QTextDocument()
    d.setDefaultFont(QFont('Arial', 20))
    d.setHtml(h)
    d.setTextWidth(400)
    img = QImage(400, 80, QImage.Format_ARGB32)
    img.fill(Qt.GlobalColor.white)
    p = QPainter(img)
    d.drawContents(p)
    p.end()
    img.save(fr'D:\HandWriteStudio\samples\ws_test_{i}.png')
    print(i, repr(h), repr(d.toPlainText()), d.size().width())
