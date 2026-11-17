import sys
sys.path.insert(0, r'D:\HandWriteStudio')
from PySide6.QtWidgets import QApplication
from app.renderer import PagedHandRenderer
from app.settings import HandStyle

app = QApplication([])
a = HandStyle()
a.grid_mode = True
a.grid_rows = 10
a.grid_cols = 30
b = HandStyle()
b.grid_mode = True
b.grid_rows = 10
b.grid_cols = 30
s = HandStyle()
s.page_presets_enabled = True
s.page_preset_styles = [a.to_dict(), b.to_dict()]
long_text = '这是一段很长的文字，用来检查当前页还没满时会不会提前换页。' * 30
html = (
    '<p>第一段短文字。</p>'
    '<p>第二段短文字。</p>'
    f'<p>{long_text}</p>'
    '<p>最后一段。</p>'
)
r = PagedHandRenderer(html, s)
print('pages', r.page_count())
for i, page in enumerate(r.pages):
    print(i, 'blocks', page.doc.blockCount(), 'chars', len(page.doc.toPlainText()))
    page.render_page_image(0, 100).save(fr'D:\HandWriteStudio\samples\paged_fill_{i}.png')
