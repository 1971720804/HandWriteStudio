"""逐笔形变回归：确保开启笔画抖动时出图、关闭时回退正常。"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QFont  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.renderer import HandRenderer  # noqa: E402
from app.settings import HandStyle  # noqa: E402
from app.strokes import deformed_path  # noqa: E402


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    html = (
        "<h1>逐笔测试</h1>"
        "<p>永和九年，岁在癸丑，暮春之初，会于会稽山阴之兰亭。</p>"
        "<p>Hello, 123! 标点符号也要能回退。</p>"
    )

    plain = HandStyle()
    plain.stroke_offset_scale = 0.0
    plain.stroke_theta_scale = 0.0
    r0 = HandRenderer(html, plain)
    t0 = time.time()
    img0 = r0.render_page_image(0, 120)
    ms0 = (time.time() - t0) * 1000

    stroke = HandStyle()
    stroke.stroke_offset_scale = 1.0
    stroke.stroke_theta_scale = 1.0
    r1 = HandRenderer(html, stroke)
    t1 = time.time()
    img1 = r1.render_page_image(0, 120)
    ms1 = (time.time() - t1) * 1000

    out = ROOT / "samples"
    out.mkdir(exist_ok=True)
    img1.save(str(out / "stroke_page_test.png"))

    # 同一文本、同一 seed，只改笔画参数，像素必须不同。
    print(f"plain {ms0:.0f}ms stroke {ms1:.0f}ms pages {r1.page_count()}")
    print("different:", img0 != img1)
    font = QFont(r1.font_family)
    print("font has stroke data:", deformed_path("永", font, __import__("random").Random(1), 0, 0) is not None)
    print("latin fallback:", deformed_path("A", font, __import__("random").Random(1), 0, 0) is None)
    return 0 if img0 != img1 else 1


if __name__ == "__main__":
    raise SystemExit(main())
