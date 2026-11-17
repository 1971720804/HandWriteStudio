import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QFont, QTextDocument, QGuiApplication
from PySide6.QtCore import QSizeF

app = QGuiApplication([])

doc = QTextDocument()
doc.setDefaultFont(QFont("Microsoft YaHei", 12))
doc.setPageSize(QSizeF(200, 800))
doc.setHtml("<p>今天是到公司实习的第三周。早上提前二十分钟到了工位，打开电脑。</p>")
doc.documentLayout().documentSize()

block = doc.begin()
while block.isValid():
    lay = block.layout()
    text = block.text()
    print("block text len", len(text), repr(text[:10]))
    for li in range(lay.lineCount()):
        line = lay.lineAt(li)
        ts, tl = line.textStart(), line.textLength()
        print(" line", li, "start", ts, "len", tl, "text", repr(text[ts:ts + tl]))
        for probe in (0, ts, ts + 1, tl, ts + tl):
            print("   cursorToX(%d) =" % probe, line.cursorToX(probe))
    block = block.next()
