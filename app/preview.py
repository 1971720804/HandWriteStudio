"""右侧手写预览：把渲染器输出的页面图片按页竖排显示。"""
from __future__ import annotations

import time
import traceback

from PySide6.QtCore import QEvent, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .renderer import HandRenderer, make_renderer
from .settings import HandStyle
from .watermark import watermark_lines, watermark_short

PREVIEW_DPI = 150


class PreviewCanvas(QWidget):
    margins_changed = Signal(float, float, float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.images: list[QImage] = []
        self.page_w = 595.0
        self.page_h = 842.0
        self.zoom = 0.8
        self.gap = 26
        self.margins = (72.0, 72.0, 72.0, 72.0)
        self.page_preset_enabled = False
        self.page_preset_styles: list[dict] = []
        self.bg_color = QColor("#e9edf2")
        self._drag_guide: str | None = None
        self._drag_page = 0
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def set_pages(self, images: list[QImage], page_w: float, page_h: float) -> None:
        self.images = images
        self.page_w = page_w
        self.page_h = page_h
        self._resize()
        self.update()

    def set_zoom(self, zoom: float) -> None:
        self.zoom = max(0.18, min(4.0, zoom))
        self._resize()
        self.update()

    def set_margins(self, left: float, top: float, right: float, bottom: float) -> None:
        self.margins = (float(left), float(top), float(right), float(bottom))
        self.update()

    def set_page_presets(self, enabled: bool, styles: list[dict]) -> None:
        self.page_preset_enabled = bool(enabled)
        self.page_preset_styles = list(styles or [])
        self.update()

    def _margins_for_page(self, idx: int) -> tuple[float, float, float, float]:
        if self.page_preset_enabled and self.page_preset_styles:
            data = self.page_preset_styles[idx % len(self.page_preset_styles)]
            if isinstance(data, dict):
                return (
                    float(data.get("left_margin", self.margins[0])),
                    float(data.get("top_margin", self.margins[1])),
                    float(data.get("right_margin", self.margins[2])),
                    float(data.get("bottom_margin", self.margins[3])),
                )
        return self.margins

    def set_background(self, color: QColor) -> None:
        self.bg_color = QColor(color)
        self.update()

    def page_size(self) -> QSize:
        return QSize(round(self.page_w * self.zoom), round(self.page_h * self.zoom))

    def _resize(self) -> None:
        w = round(self.page_w * self.zoom) + 80
        h = max(1, len(self.images)) * (round(self.page_h * self.zoom) + self.gap) + self.gap
        self.resize(max(200, w), max(200, h))

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(
            round(self.page_w * self.zoom) + 80,
            max(200, len(self.images)) * (round(self.page_h * self.zoom) + self.gap) + self.gap,
        )

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.bg_color)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        pw = round(self.page_w * self.zoom)
        ph = round(self.page_h * self.zoom)
        x = 38.0
        if not self.images:
            painter.setPen(QColor("#8a929e"))
            painter.drawText(
                QRectF(0, 40, self.width(), 60),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                "没有内容",
            )
            return

        for idx, image in enumerate(self.images):
            y = self.gap + idx * (ph + self.gap)
            # 页影
            painter.setPen(Qt.PenStyle.NoPen)
            for i, alpha in enumerate((26, 18, 10)):
                painter.setBrush(QColor(30, 40, 55, alpha))
                painter.drawRoundedRect(
                    QRectF(x - 3 - i * 2, y + 3 + i * 2, pw + 6 + i * 4, ph + 6 + i * 4),
                    3,
                    3,
                )
            painter.setBrush(QColor("#ffffff"))
            painter.setPen(QPen(QColor("#d2d7de"), 1))
            painter.drawRect(QRectF(x, y, pw, ph))
            painter.drawImage(QRectF(x, y, pw, ph), image)
            painter.setPen(QColor("#9aa3ae"))
            painter.drawText(
                QRectF(x, y + ph + 2, pw, 20),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                f"第 {idx + 1} 页",
            )
            self._draw_guides(painter, x, y, pw, ph, idx)
        painter.end()

    def _draw_guides(
        self, painter: QPainter, x: float, y: float, pw: float, ph: float, page: int = 0
    ) -> None:
        left, top, right, bottom = self._margins_for_page(page)
        z = self.zoom
        lx = x + left * z
        rx = x + pw - right * z
        ty = y + top * z
        by = y + ph - bottom * z
        pen = QPen(QColor(214, 74, 74, 210), 1.0, Qt.PenStyle.DashLine)
        pen.setDashPattern([5.0, 4.0])
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(QPointF(lx, y), QPointF(lx, y + ph))
        painter.drawLine(QPointF(rx, y), QPointF(rx, y + ph))
        painter.drawLine(QPointF(x, ty), QPointF(x + pw, ty))
        painter.drawLine(QPointF(x, by), QPointF(x + pw, by))

    def _guide_at(self, pos) -> tuple[str, int] | None:
        if not self.images or self.page_preset_enabled:
            return None
        pw = round(self.page_w * self.zoom)
        ph = round(self.page_h * self.zoom)
        x = 38.0
        best: tuple[float, str, int] | None = None
        for idx in range(len(self.images)):
            y = self.gap + idx * (ph + self.gap)
            if not (x - 8 <= pos.x() <= x + pw + 8 and y - 8 <= pos.y() <= y + ph + 8):
                continue
            left, top, right, bottom = self._margins_for_page(idx)
            guides = {
                "left": (x + left * self.zoom, pos.y()),
                "right": (x + pw - right * self.zoom, pos.y()),
                "top": (pos.x(), y + top * self.zoom),
                "bottom": (pos.x(), y + ph - bottom * self.zoom),
            }
            for kind, (gx, gy) in guides.items():
                dist = abs(pos.x() - gx) if kind in ("left", "right") else abs(pos.y() - gy)
                if dist <= 6 and (best is None or dist < best[0]):
                    best = (dist, kind, idx)
        return None if best is None else (best[1], best[2])

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            hit = self._guide_at(event.position())
            if hit is not None:
                self._drag_guide, self._drag_page = hit
                self.setCursor(
                    Qt.CursorShape.SizeHorCursor
                    if hit[0] in ("left", "right")
                    else Qt.CursorShape.SizeVerCursor
                )
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_guide is not None:
            self._drag_margin(event.position())
            event.accept()
            return
        hit = self._guide_at(event.position())
        if hit is not None:
            self.setCursor(
                Qt.CursorShape.SizeHorCursor
                if hit[0] in ("left", "right")
                else Qt.CursorShape.SizeVerCursor
            )
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._drag_guide is not None:
            self._drag_guide = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _drag_margin(self, pos) -> None:
        if self.page_preset_enabled:
            return
        pw = round(self.page_w * self.zoom)
        ph = round(self.page_h * self.zoom)
        x = 38.0
        y = self.gap + self._drag_page * (ph + self.gap)
        left, top, right, bottom = self.margins
        z = max(0.01, self.zoom)
        if self._drag_guide == "left":
            left = max(0.0, min(300.0, (pos.x() - x) / z, self.page_w - right - 40.0))
        elif self._drag_guide == "right":
            right = max(0.0, min(300.0, (x + pw - pos.x()) / z, self.page_w - left - 40.0))
        elif self._drag_guide == "top":
            top = max(0.0, min(300.0, (pos.y() - y) / z, self.page_h - bottom - 40.0))
        elif self._drag_guide == "bottom":
            bottom = max(0.0, min(300.0, (y + ph - pos.y()) / z, self.page_h - top - 40.0))
        left, top, right, bottom = (round(v) for v in (left, top, right, bottom))
        self.margins = (left, top, right, bottom)
        self.margins_changed.emit(left, top, right, bottom)
        self.update()


class PreviewWindow(QDialog):
    """全屏预览：滚轮上下滚动，Ctrl+滚轮缩放，Esc 退出。"""

    margins_changed = Signal(float, float, float, float)

    def __init__(
        self,
        pages,
        page_w: float,
        page_h: float,
        margins,
        page_preset_enabled: bool = False,
        page_preset_styles=None,
        parent=None,
    ):
        super().__init__(parent)
        self._page_preset_enabled = bool(page_preset_enabled)
        self._page_preset_styles = list(page_preset_styles or [])
        self.setWindowTitle("HandWriteStudio · 全屏预览")
        self.setWindowFlags(Qt.WindowType.Window)
        self.setStyleSheet("QDialog { background:#151a21; }")
        self.setMinimumSize(640, 480)
        self._fit_mode = "width"

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        bar = QWidget()
        bar.setStyleSheet("background:#1d232c; border-bottom:1px solid #2b3441;")
        bar_lay = QHBoxLayout(bar)
        bar_lay.setContentsMargins(16, 8, 16, 8)
        bar_lay.setSpacing(10)
        title = QLabel("全屏预览")
        title.setStyleSheet("color:#f0f4fa; font-weight:600; font-size:14px;")
        bar_lay.addWidget(title)
        hint = QLabel("滚轮滚动 · Ctrl+滚轮缩放 · Esc 退出")
        hint.setStyleSheet("color:#93a0b1; font-size:12px;")
        bar_lay.addWidget(hint)
        bar_lay.addStretch(1)
        self.zoom_label = QLabel("")
        self.zoom_label.setStyleSheet("color:#b9c5d4; font-size:12px;")
        bar_lay.addWidget(self.zoom_label)
        btn_width = QPushButton("适应宽度")
        btn_page = QPushButton("整页")
        btn_close = QPushButton("关闭")
        for b in (btn_width, btn_page, btn_close):
            b.setStyleSheet(
                "QPushButton { color:#e8eef6; background:#2a3441; border:1px solid #3b4858;"
                " border-radius:5px; padding:4px 10px; }"
                "QPushButton:hover { background:#344254; }"
            )
            bar_lay.addWidget(b)
        btn_width.clicked.connect(self.fit_width)
        btn_page.clicked.connect(self.fit_page)
        btn_close.clicked.connect(self.close)
        root.addWidget(bar)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(False)
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.scroll.setStyleSheet("QScrollArea { background:#151a21; border:none; }")
        self.scroll.viewport().setStyleSheet("background:#151a21;")
        self.canvas = PreviewCanvas()
        self.canvas.set_background(QColor("#151a21"))
        self.canvas.margins_changed.connect(self.margins_changed)
        self.scroll.setWidget(self.canvas)
        root.addWidget(self.scroll, 1)
        self.canvas.installEventFilter(self)
        self.scroll.viewport().installEventFilter(self)
        self._watermark = None

        self.set_pages(pages, page_w, page_h, margins)

    def set_pages(
        self,
        pages,
        page_w: float,
        page_h: float,
        margins,
        page_preset_enabled=None,
        page_preset_styles=None,
    ) -> None:
        if page_preset_enabled is not None:
            self._page_preset_enabled = bool(page_preset_enabled)
        if page_preset_styles is not None:
            self._page_preset_styles = list(page_preset_styles or [])
        self.canvas.set_margins(*margins)
        self.canvas.set_page_presets(
            self._page_preset_enabled, self._page_preset_styles
        )
        self.canvas.set_pages(pages, page_w, page_h)
        self._update_zoom_label()

    def _update_zoom_label(self) -> None:
        self.zoom_label.setText(f"{self.canvas.zoom * 100:.0f}%")

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        QTimer.singleShot(0, self.fit_width)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._place_watermark()
        if self._fit_mode == "width":
            QTimer.singleShot(0, self.fit_width)
        elif self._fit_mode == "page":
            QTimer.singleShot(0, self.fit_page)

    def _make_watermark(self) -> QLabel:
        label = QLabel(self.scroll.viewport())
        label.setText(watermark_short())
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(
            "QLabel { color: #eef4fb; background: rgba(18, 24, 32, 215);"
            " border: 1px solid rgba(120, 165, 210, 150);"
            " border-radius: 8px; }"
        )
        label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        label.raise_()
        return label

    def _place_watermark(self) -> None:
        label = getattr(self, "_watermark", None)
        if label is None or self.scroll is None:
            return
        vp = self.scroll.viewport()
        fm = label.fontMetrics()
        w = fm.horizontalAdvance(label.text()) + 28
        h = fm.height() + 14
        label.setFixedSize(w, h)
        label.move(vp.width() - w - 18, vp.height() - h - 16)
        label.raise_()

    def fit_width(self) -> None:
        self._fit_mode = "width"
        vw = self.scroll.viewport().width()
        if vw > 80:
            self.canvas.set_zoom((vw - 90.0) / max(1.0, self.canvas.page_w))
            self._update_zoom_label()

    def fit_page(self) -> None:
        self._fit_mode = "page"
        vw = self.scroll.viewport().width()
        vh = self.scroll.viewport().height()
        if vw > 80 and vh > 80:
            self.canvas.set_zoom(
                min((vw - 60.0) / max(1.0, self.canvas.page_w), (vh - 50.0) / max(1.0, self.canvas.page_h))
            )
            self._update_zoom_label()

    def zoom_by(self, factor: float) -> None:
        self._fit_mode = ""
        self.canvas.set_zoom(self.canvas.zoom * factor)
        self._update_zoom_label()

    def eventFilter(self, obj, event):  # noqa: N802
        if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
            self.close()
            return True
        if event.type() == QEvent.Type.Wheel:
            delta = event.angleDelta().y()
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self.zoom_by(1.15 if delta > 0 else 1 / 1.15)
            else:
                bar = self.scroll.verticalScrollBar()
                bar.setValue(bar.value() - delta)
            event.accept()
            return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        if event.key() == Qt.Key.Key_F11:
            self.showNormal()
            return
        super().keyPressEvent(event)


class PreviewPanel(QWidget):
    rendered = Signal(int, float)  # 页数, 毫秒
    status_message = Signal(str)
    margins_changed = Signal(float, float, float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.style: HandStyle | None = None
        self.html = ""
        self.last_render_ms = 0.0
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(320)
        self._timer.timeout.connect(self._render)
        self._renderer: HandRenderer | None = None
        self._has_rendered = False
        self._fullscreen: PreviewWindow | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        bar = QWidget()
        bar.setStyleSheet("background:#f5f7fa; border-bottom:1px solid #dde2e8;")
        bar_lay = QHBoxLayout(bar)
        bar_lay.setContentsMargins(12, 6, 12, 6)
        bar_lay.setSpacing(8)
        title = QLabel("手写预览")
        title.setStyleSheet("font-weight:600; color:#3a4150;")
        bar_lay.addWidget(title)
        self.status = QLabel("")
        self.status.setStyleSheet("color:#8a929e; font-size:12px;")
        bar_lay.addWidget(self.status)
        bar_lay.addStretch(1)
        self.btn_full = QPushButton("全屏")
        self.btn_full.setFixedWidth(54)
        self.btn_full.setToolTip("全屏预览（滚轮滚动，Ctrl+滚轮缩放）")
        self.btn_full.clicked.connect(self.open_fullscreen)
        self.btn_minus = QPushButton("−")
        self.btn_minus.setFixedWidth(30)
        self.btn_minus.setToolTip("缩小")
        self.btn_fit = QPushButton("适应")
        self.btn_fit.setFixedWidth(48)
        self.btn_fit.setToolTip("适应窗口宽度")
        self.btn_plus = QPushButton("+")
        self.btn_plus.setFixedWidth(30)
        self.btn_plus.setToolTip("放大")
        self.btn_minus.clicked.connect(lambda: self.zoom_by(0.9))
        self.btn_plus.clicked.connect(lambda: self.zoom_by(1.1))
        self.btn_fit.clicked.connect(self.fit_width)
        for b in (self.btn_full, self.btn_minus, self.btn_fit, self.btn_plus):
            b.setStyleSheet(
                "QPushButton { border:1px solid #d0d6de; border-radius:5px; background:#fff;"
                " padding:2px 4px; } QPushButton:hover { background:#eef3fa; }"
            )
            bar_lay.addWidget(b)
        root.addWidget(bar)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(False)
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.canvas = PreviewCanvas()
        self.canvas.margins_changed.connect(self.margins_changed)
        self.scroll.setWidget(self.canvas)
        root.addWidget(self.scroll, 1)
        self.scroll.viewport().installEventFilter(self)
        self._watermark = None

    # ---------- 外部接口 ----------

    def set_document(self, html: str, style: HandStyle, immediate: bool = False) -> None:
        if (
            self.canvas.page_w != style.page_width
            or self.canvas.page_h != style.page_height
        ):
            # 换纸张后重新适应窗口宽度，避免沿用上一张纸的缩放
            self._has_rendered = False
        self.html = html
        self.style = style
        self.canvas.set_margins(
            style.left_margin, style.top_margin, style.right_margin, style.bottom_margin
        )
        self.canvas.set_page_presets(
            bool(getattr(style, "page_presets_enabled", False)),
            list(getattr(style, "page_preset_styles", []) or []),
        )
        if immediate:
            self._timer.stop()
            self._render()
        else:
            self.status.setText("正在排版…")
            self._timer.start()

    def open_fullscreen(self) -> None:
        if not self.canvas.images:
            self._render()
        if not self.canvas.images:
            return
        if self._fullscreen is None:
            self._fullscreen = PreviewWindow(
                self.canvas.images,
                self.canvas.page_w,
                self.canvas.page_h,
                self.canvas.margins,
                page_preset_enabled=self.canvas.page_preset_enabled,
                page_preset_styles=self.canvas.page_preset_styles,
                parent=self.window(),
            )
            self._fullscreen.margins_changed.connect(self.margins_changed)
        else:
            self._fullscreen.set_pages(
                self.canvas.images,
                self.canvas.page_w,
                self.canvas.page_h,
                self.canvas.margins,
                page_preset_enabled=self.canvas.page_preset_enabled,
                page_preset_styles=self.canvas.page_preset_styles,
            )
        self._fullscreen.showFullScreen()
        self._fullscreen.raise_()
        self._fullscreen.activateWindow()

    def zoom_by(self, factor: float) -> None:
        self.canvas.set_zoom(self.canvas.zoom * factor)

    def fit_width(self) -> None:
        vw = self.scroll.viewport().width()
        if vw > 120:
            self.canvas.set_zoom((vw - 90.0) / self.page_width())

    def page_width(self) -> float:
        return self.style.page_width if self.style else 595.0

    def _make_watermark(self) -> QLabel:
        label = QLabel(self.scroll.viewport())
        label.setText(watermark_short())
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(
            "QLabel { color: #eef4fb; background: rgba(18, 24, 32, 215);"
            " border: 1px solid rgba(120, 165, 210, 150);"
            " border-radius: 8px; }"
        )
        label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        label.raise_()
        return label

    def _place_watermark(self) -> None:
        label = getattr(self, "_watermark", None)
        if label is None or self.scroll is None:
            return
        vp = self.scroll.viewport()
        fm = label.fontMetrics()
        w = fm.horizontalAdvance(label.text()) + 28
        h = fm.height() + 14
        label.setFixedSize(w, h)
        label.move(vp.width() - w - 16, vp.height() - h - 14)
        label.raise_()

    def eventFilter(self, obj, event):  # noqa: N802
        if obj is self.scroll.viewport() and event.type() == QEvent.Type.Resize:
            if not self._has_rendered:
                QTimer.singleShot(0, self.fit_width)
        return super().eventFilter(obj, event)

    # ---------- 渲染 ----------

    def _render(self) -> None:
        if not self.html or self.style is None:
            self.canvas.set_pages([], 595, 842)
            self.status.setText("")
            return
        start = time.perf_counter()
        self.status.setText("渲染中…")
        try:
            renderer = make_renderer(self.html, self.style)
            self._renderer = renderer
            pages = [
                renderer.render_page_image(i, PREVIEW_DPI)
                for i in range(renderer.page_count())
            ]
            self.canvas.set_pages(pages, self.style.page_width, self.style.page_height)
            if self._fullscreen is not None:
                self._fullscreen.set_pages(
                    pages,
                    self.style.page_width,
                    self.style.page_height,
                    self.canvas.margins,
                    page_preset_enabled=self.canvas.page_preset_enabled,
                    page_preset_styles=self.canvas.page_preset_styles,
                )
            if not self._has_rendered:
                self._has_rendered = True
                self.fit_width()
            elapsed = (time.perf_counter() - start) * 1000.0
            self.last_render_ms = elapsed
            self.status.setText(f"{len(pages)} 页 · {elapsed:.0f} ms")
            self.rendered.emit(len(pages), elapsed)
        except Exception:
            self.status.setText("渲染失败")
            self.canvas.set_pages([], self.style.page_width, self.style.page_height)
            self.status_message.emit(traceback.format_exc(limit=3))
