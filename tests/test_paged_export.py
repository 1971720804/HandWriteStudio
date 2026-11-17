import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication

from app.export import export_pdf, export_pngs
from app.renderer import make_renderer
from app.settings import HandStyle

app = QApplication([])

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

html = "".join("<p>第%d段测试文字，用来检查逐页预设导出。</p>" % i for i in range(1, 21))
r = make_renderer(html, s)
out = Path(__file__).resolve().parent.parent / "samples" / "paged_export"
out.mkdir(parents=True, exist_ok=True)
files = export_pngs(r, str(out), "page", dpi=100, numbered=True, start_index=0)
print("png", len(files), files[:3])
pdf = out / "test.pdf"
export_pdf(r, str(pdf), dpi=100)
print("pdf", pdf.exists(), pdf.stat().st_size if pdf.exists() else 0)
