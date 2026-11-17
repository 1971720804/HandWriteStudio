"""打包后的自检：验证字体、Word 导入和手写渲染在冻结环境里能跑。"""
from __future__ import annotations

import os
import traceback
from pathlib import Path


def run_selftest() -> int:
    out = Path(os.environ.get("HWS_SELFTEST_DIR", str(Path.home() / "HandWriteStudio_selftest")))
    out.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    try:
        import mammoth  # noqa: F401

        lines.append("mammoth ok")

        from docx import Document

        doc = Document()
        doc.add_heading("自检标题", 0)
        doc.add_paragraph("这是一段用来检查打包环境的中文正文。")
        sample = out / "selftest.docx"
        doc.save(str(sample))
        lines.append("python-docx ok")

        from .docx_import import import_docx

        html, messages = import_docx(str(sample))
        lines.append(f"docx html={len(html)} messages={messages}")

        from .renderer import HandRenderer
        from .settings import HandStyle, default_font

        font = default_font()
        lines.append(f"font={font}")
        renderer = HandRenderer(html, HandStyle())
        image = renderer.render_page_image(0, 100)
        image.save(str(out / "selftest.png"))
        lines.append(f"render={image.width()}x{image.height()} pages={renderer.page_count()}")

        stroke_style = HandStyle()
        stroke_style.stroke_offset_scale = 1.0
        stroke_style.stroke_theta_scale = 1.0
        stroke_renderer = HandRenderer(html, stroke_style)
        stroke_image = stroke_renderer.render_page_image(0, 100)
        stroke_image.save(str(out / "selftest_stroke.png"))
        lines.append(f"stroke_changed={image != stroke_image}")
        lines.append("OK")
    except Exception:
        lines.append(traceback.format_exc())
    (out / "result.txt").write_text("\n".join(lines), encoding="utf-8")
    return 0
