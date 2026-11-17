import sys
sys.path.insert(0, r"D:\HandWriteStudio")
from PySide6.QtWidgets import QApplication

app = QApplication([])
from app.editor import Editor
from app.renderer import HandRenderer
from app.settings import HandStyle

e = Editor()
e.setHtml('<h1 style="text-align:center;">实 习 日 记</h1><p>正文</p>')
html = e.content_html()
start = html.find("<h1")
print("HTML:", html[start:start + 400])
r = HandRenderer(html, HandStyle())
block = r.doc.begin()
print("block text:", repr(block.text()))
print("char font:", block.charFormat().font().pointSizeF(), "heading:", block.blockFormat().headingLevel())
print("ranges:", [(s, en, f.font().pointSizeF()) for s, en, f in r._block_formats[block.blockNumber()]])
print("page:", r.page_count())
