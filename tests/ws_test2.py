import sys
sys.path.insert(0, r'D:\HandWriteStudio')
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QTextDocument, QFont

app = QApplication([])
cases = [
    ('body-style', '<html><body style="white-space: pre-wrap;"><p>A    B</p></body></html>'),
    ('default-css', '<p>A    B</p>', 'p { white-space: pre-wrap; }'),
    ('div-wrap', '<div style="white-space: pre-wrap;"><p>A    B</p></div>'),
]
for case in cases:
    name, html = case[0], case[1]
    d = QTextDocument()
    d.setDefaultFont(QFont('Arial', 20))
    if len(case) > 2:
        d.setDefaultStyleSheet(case[2])
    d.setHtml(html)
    print(name, repr(d.toPlainText()))
