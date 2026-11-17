"""Word 导入：mammoth 转成语义化 HTML（图片自动转 data URI）。"""
from __future__ import annotations

import re


def _normalize(html: str) -> str:
    # 表格加边框和内边距；Qt 的 HTML 子集对 CSS border 支持不完整，用属性最稳
    html = re.sub(
        r"<table\b",
        '<table border="1" cellspacing="0" cellpadding="6" width="100%"',
        html,
        flags=re.IGNORECASE,
    )
    # 链接只保留文字，避免导出后带一堆蓝字下划线
    html = re.sub(
        r"<a\b[^>]*>(.*?)</a>",
        r"\1",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return html


def _apply_image_sizes(html: str, sizes: list[tuple[float, float]]) -> str:
    """按 Word 里图片的显示尺寸给 <img> 补 width/height（单位 pt）。

    mammoth 不带图片显示尺寸，Qt 会把图片按原始像素当 pt 画，常大出一倍。
    """
    if not sizes:
        return html
    index = 0

    def repl(match: re.Match) -> str:
        nonlocal index
        attrs = match.group(1).rstrip()
        if attrs.endswith("/"):
            attrs = attrs[:-1].rstrip()
        if index < len(sizes):
            w, h = sizes[index]
            if "width=" not in attrs.lower():
                attrs += f' width="{max(1, round(w))}"'
            if "height=" not in attrs.lower():
                attrs += f' height="{max(1, round(h))}"'
        index += 1
        return f"<img{attrs}>"

    return re.sub(r"<img\b([^>]*)>", repl, html, flags=re.IGNORECASE)


def _inline_picture_sizes(path: str) -> list[tuple[float, float]]:
    try:
        from docx import Document
        from docx.enum.shape import WD_INLINE_SHAPE

        doc = Document(path)
        sizes: list[tuple[float, float]] = []
        for shape in doc.inline_shapes:
            if shape.type == WD_INLINE_SHAPE.PICTURE:
                sizes.append((shape.width.pt, shape.height.pt))
        return sizes
    except Exception:
        return []


def import_docx(path: str) -> tuple[str, list[str]]:
    import mammoth

    # Word 的 Title/Subtitle 样式 mammoth 默认不认识，会退化成普通段落
    style_map = (
        "p[style-name='Title'] => h1:fresh\n"
        "p[style-name='Subtitle'] => h2:fresh"
    )
    with open(path, "rb") as f:
        result = mammoth.convert_to_html(f, style_map=style_map)
    messages = [m.message for m in result.messages]
    html = _normalize(result.value)
    html = _apply_image_sizes(html, _inline_picture_sizes(path))
    return html, messages
