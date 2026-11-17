import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QTextEdit
from PySide6.QtGui import QImage, QTextCursor, QTextImageFormat, QTextDocument

app = QApplication([])

# 1x1 red png
uri = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgwJ/lwY9WQAAAABJRU5ErkJggg=="

edit = QTextEdit()
edit.setHtml(f'<p>before</p><p><img src="{uri}" width="30" height="30"></p><p>after</p>')
print("--- inserted html ---")
print(edit.toHtml()[:2000])
print("doc resource:", edit.document().resource(QTextDocument.ImageResource, __import__("PySide6.QtCore", fromlist=["QUrl"]).QUrl(uri)))

# check image char format
block = edit.document().begin()
while block.isValid():
    it = block.begin()
    while not it.atEnd():
        frag = it.fragment()
        if frag.isValid() and frag.charFormat().isImageFormat():
            imf = frag.charFormat().toImageFormat()
            print("image name:", imf.name()[:80], "w", imf.width(), "h", imf.height())
        it += 1
    block = block.next()
