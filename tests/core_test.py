import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QSizeF
from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtWidgets import QApplication

from app.docx_import import import_docx
from app.export import export_pdf, export_pngs
from app.project import load_project, save_project
from app.renderer import HandRenderer
from app.settings import HandStyle

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"
SAMPLES.mkdir(exist_ok=True)

app = QApplication(sys.argv)


def make_png(path: Path, w=360, h=220) -> None:
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(QColor("#d9ecff"))
    p = QPainter(img)
    p.setPen(QColor("#2b6cb0"))
    p.setFont(QFont("Microsoft YaHei", 22))
    p.drawText(img.rect(), 0x84, "示例插图")
    p.end()
    img.save(str(path))


def build_docx(path: Path) -> None:
    from docx import Document
    from docx.shared import Inches, Pt

    doc = Document()
    doc.add_heading("实习周记", level=1)
    p = doc.add_paragraph()
    run = p.add_run("这一周主要在做接口联调和测试记录整理，顺手把导入流程跑通了。")
    run.font.size = Pt(12)
    doc.add_paragraph("下周计划：补完边界用例，把周报模板定下来。")

    table = doc.add_table(rows=3, cols=3)
    table.style = "Table Grid"
    for r, row in enumerate([
        ("时间", "事项", "备注"),
        ("周一", "接口联调", "完成"),
        ("周三", "测试记录", "补完"),
    ]):
        for c, text in enumerate(row):
            table.cell(r, c).text = text

    img_path = SAMPLES / "_docx_img.png"
    make_png(img_path)
    doc.add_picture(str(img_path), width=Inches(2.4))
    doc.add_paragraph("以上。")
    doc.save(str(path))


# 1) docx 导入
docx_path = SAMPLES / "import_sample.docx"
build_docx(docx_path)
html, messages = import_docx(str(docx_path))
print("docx html len:", len(html), "messages:", messages)
print("has table:", "<table" in html.lower(), "has img:", "<img" in html.lower(), "has h1:", "<h1" in html.lower())
print("img preview:", html[html.lower().find("<img"):html.lower().find("<img") + 80])

style = HandStyle()
renderer = HandRenderer(html, style)
print("docx pages:", renderer.page_count())
out = SAMPLES / "docx_page.png"
renderer.render_page_image(0, dpi=150).save(str(out))
print("docx preview:", out, out.stat().st_size)

# 2) 项目保存/加载
proj = SAMPLES / "test_project.hws"
save_project(str(proj), html, style)
html2, style2 = load_project(str(proj))
print("project saved:", proj.stat().st_size, "html equal:", html2 == html, "style equal:", style2.to_dict() == style.to_dict())
print("project font:", style2.font_path, "page:", style2.page_width, style2.page_height)

# 3) 多页 + PNG/PDF 导出
long_paras = "\n".join(
    f"<p>第 {i + 1} 段：这是一段用来测试自动分页的正文，内容会随着页数增加一直往下排，检查表格和图片之外的纯文字分页是否稳定。</p>"
    for i in range(70)
)
long_html = "<h1 style='text-align:center;'>长文分页测试</h1>" + long_paras
long_renderer = HandRenderer(long_html, style)
pages = long_renderer.page_count()
print("long pages:", pages)
assert pages >= 2, "多页测试没分页"

export_dir = SAMPLES / "export_test"
png_paths = export_pngs(long_renderer, str(export_dir), prefix="长文", dpi=200)
print("exported png:", len(png_paths), [Path(p).name for p in png_paths], [Path(p).stat().st_size for p in png_paths])
img0 = QImage(png_paths[0])
print("png size:", img0.width(), img0.height())

pdf_path = export_dir / "长文.pdf"
export_pdf(long_renderer, str(pdf_path), dpi=200)
print("pdf:", pdf_path, pdf_path.stat().st_size)

from PySide6.QtPdf import QPdfDocument

pdf_doc = QPdfDocument()
err = pdf_doc.load(str(pdf_path))
print("pdf load:", err, "pdf pages:", pdf_doc.pageCount())
page_img = pdf_doc.render(0, QSizeF(595, 842).toSize())
print("pdf page image:", page_img.width(), page_img.height(), "null:", page_img.isNull())
if not page_img.isNull():
    page_img.save(str(SAMPLES / "pdf_page1.png"))
    pdf_doc.close()
