"""全局数据模型：手写样式参数。"""
from __future__ import annotations

import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = APP_DIR / "assets"
FONT_DIR = ASSETS_DIR / "fonts"
PAPER_DIR = ASSETS_DIR / "papers"


def app_root() -> Path:
    """应用根目录：源码版是项目根，打包版是 exe 所在目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return APP_DIR


OUTPUT_ROOT = app_root() / "导出"
OUTPUT_PNG_DIR = OUTPUT_ROOT / "PNG"
OUTPUT_PDF_DIR = OUTPUT_ROOT / "PDF"


def ensure_output_dirs() -> None:
    for path in (OUTPUT_PNG_DIR, OUTPUT_PDF_DIR):
        path.mkdir(parents=True, exist_ok=True)


def default_font() -> str:
    preferred = FONT_DIR / "李国夫手写体.ttf"
    if preferred.exists():
        return str(preferred)
    fonts = sorted(FONT_DIR.glob("*.ttf"))
    return str(fonts[0]) if fonts else ""


@dataclass
class HandStyle:
    # 版面（单位：pt，A4 = 595 x 842）
    page_width: float = 595.0
    page_height: float = 842.0
    font_path: str = field(default_factory=default_font)
    font_size: float = 12.0          # 正文字号
    line_spacing: float = 1.55       # 行距倍数
    letter_spacing: float = 0.0      # 字间距（pt，可负）
    left_margin: float = 72.0
    top_margin: float = 72.0
    right_margin: float = 72.0
    bottom_margin: float = 72.0
    first_indent: float = 2.0        # 首行缩进（字）
    ink_color: str = "#202020"
    background_path: str = ""
    export_dpi: int = 900            # PNG 导出分辨率；A4 900dpi ≈ 7438×10525
    sharp_edges: bool = True         # 关闭文字抗锯齿，让边缘更硬
    grid_mode: bool = False          # 格子对齐模式
    grid_rows: int = 0               # 单页行数；0 = 按当前行距估算
    grid_cols: int = 0               # 单行字数；0 = 按当前字距估算
    grid_align_cols: bool = True      # 按单行字数对齐；关掉后按页边距自然换行
    grid_justify: bool = True         # 垂直撑满：首行贴顶、末行贴底

    # 分页参数预设：每页按列表循环套用（只覆盖字体/背景/墨色/抖动等外观）
    page_presets_enabled: bool = False
    page_preset_names: list[str] = field(default_factory=list)
    page_preset_styles: list[dict] = field(default_factory=list)

    # 抖动强度（相对值，1.0 = 默认手感）
    jitter_scale: float = 1.0
    font_size_sigma: float = 0.035   # 字号浮动，比例
    word_spacing_sigma: float = 0.025  # 字距浮动，em
    line_spacing_sigma: float = 0.03   # 行基线浮动，字号比例
    x_sigma: float = 0.022           # 水平位移，em
    y_sigma: float = 0.022           # 垂直位移，em
    theta_sigma: float = 1.6         # 单字旋转，度
    line_theta_sigma: float = 0.35   # 整行倾斜，度
    alpha_sigma: float = 0.05        # 墨色深浅浮动

    # 每一项的独立倍率（1.0 = 默认；UI 里 100%）
    font_size_scale: float = 1.0
    word_spacing_scale: float = 1.0
    line_spacing_scale: float = 1.0
    x_scale: float = 1.0
    y_scale: float = 1.0
    theta_scale: float = 1.0
    stroke_offset_scale: float = 1.0
    stroke_theta_scale: float = 1.0
    line_theta_scale: float = 1.0
    alpha_scale: float = 1.0

    seed: int = 20261109

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "HandStyle":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})

    def effective(self, value: float, default: float) -> float:
        """把默认强度按 jitter_scale 缩放。"""
        return default * max(0.0, self.jitter_scale)


DEFAULT_STYLE = HandStyle()
