import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication

from app.renderer import HandRenderer
from app.settings import HandStyle

app = QApplication([])
text = "系统参数。最后，在仿真环境中编写了简单的RAPID程序，使机器人各轴回归至机械零点。" * 3
for name, align in (("align", True), ("flow", False)):
    style = HandStyle()
    style.grid_mode = True
    style.grid_align_cols = align
    style.grid_justify = False
    style.grid_rows = 20
    style.grid_cols = 38
    style.font_size = 12
    style.letter_spacing = 4.0 if not align else 0.0
    renderer = HandRenderer(f"<p>{text}</p>", style)
    image = renderer.render_page_image(0, 120)
    image.save(str(Path(__file__).resolve().parent.parent / "samples" / f"grid_{name}_toggle.png"))
    xs = []
    for y in range(image.height()):
        for x in range(image.width()):
            if image.pixelColor(x, y).red() < 128:
                xs.append(x)
    print(name, "pages", renderer.page_count(), "ink", min(xs), max(xs))
