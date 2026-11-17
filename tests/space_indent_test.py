import sys
sys.path.insert(0, r'D:\HandWriteStudio')
from PySide6.QtWidgets import QApplication, QTextEdit
from app.renderer import HandRenderer
from app.settings import HandStyle

app = QApplication([])
e = QTextEdit()
e.setPlainText('\tTab开头\n  两个空格开头\n文字中间    多空格\n制表\t夹在中间')
html = e.toHtml()
r = HandRenderer(html, HandStyle())
print(repr(r.doc.toPlainText()))
for b_i in range(r.doc.blockCount()):
    b = r.doc.findBlockByNumber(b_i)
    print(b_i, repr(b.text()))
r.render_page_image(0, 100).save(r'D:\HandWriteStudio\samples\space_indent_test.png')
