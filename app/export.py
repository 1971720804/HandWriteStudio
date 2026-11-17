"""导出：PNG 图片和 PDF。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMarginsF, QSizeF
from PySide6.QtGui import QPageSize, QPainter, QPdfWriter

from .renderer import HandRenderer


def export_pngs(
    renderer: HandRenderer,
    directory: str,
    prefix: str = "手写稿",
    dpi: int = 900,
    progress=None,
    numbered: bool = False,
    start_index: int = 1,
) -> list[str]:
    out_dir = Path(directory)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    count = renderer.page_count()
    for i in range(count):
        if numbered:
            name = f"{i + start_index}.png"
        elif count == 1:
            name = f"{prefix}.png"
        else:
            name = f"{prefix}_{i + start_index}.png"
        path = out_dir / name
        image = renderer.render_page_image(i, dpi=dpi)
        if not image.save(str(path), "PNG"):
            raise OSError(f"保存失败：{path}")
        paths.append(str(path))
        if progress is not None and not progress(i + 1, count):
            break
    return paths


def export_pdf(renderer: HandRenderer, path: str, dpi: int = 200) -> None:
    """导出矢量 PDF。PDF 用 72dpi 的点坐标，不用再按 dpi 缩放。"""
    style = renderer.style
    writer = QPdfWriter(path)
    writer.setResolution(72)
    writer.setPageSize(
        QPageSize(QSizeF(style.page_width, style.page_height), QPageSize.Unit.Point)
    )
    writer.setPageMargins(QMarginsF(0, 0, 0, 0))
    writer.setTitle("HandWriteStudio")
    writer.setCreator("HandWriteStudio")

    painter = QPainter()
    if not painter.begin(writer):
        raise OSError("无法创建 PDF 文件")
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        for i in range(renderer.page_count()):
            if i > 0 and not writer.newPage():
                raise OSError("PDF 分页失败")
            painter.resetTransform()
            renderer.paint_page(painter, i, draw_background=True)
    finally:
        painter.end()
