# -*- coding: utf-8 -*-
"""应用内水印。

文本按 XOR + base64 分段存放，运行时再拼回来，避免被直接搜索明文删掉。
"""
from __future__ import annotations

import base64

_KEY = 0x5A

_LINE1 = "v9/Xsu7jv+bavODK"
_LINE2 = "vuL/vfzbv9rIv9fM"
_LINE3 = "svXtv9HlstDrs8jrsu73vuPqvcHNvdPS"


def _decode(text: str) -> str:
    raw = base64.b64decode(text)
    return bytes(b ^ _KEY for b in raw).decode("utf-8")


def watermark_lines() -> tuple[str, str, str]:
    """返回 (第一行, 第二行, 提示行)。"""
    return _decode(_LINE1), _decode(_LINE2), _decode(_LINE3)


def watermark_short() -> str:
    a, b, _ = watermark_lines()
    return f"{a} · {b}"


class WatermarkBadge:
    """延迟导入 Qt 的工厂，避免 watermark 模块被非 GUI 进程导入时报错。"""

    @staticmethod
    def make(parent):
        from PySide6.QtCore import QSize, Qt
        from PySide6.QtGui import QColor, QPainter, QPen
        from PySide6.QtWidgets import QWidget

        class _Badge(QWidget):
            def __init__(self, parent_widget):
                super().__init__(parent_widget)
                a, b, c = watermark_lines()
                self._text = f"{a} · {b} · {c}"
                self.setFont(self.font())
                self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                self.resize(self.sizeHint())

            def sizeHint(self) -> QSize:
                fm = self.fontMetrics()
                return QSize(fm.horizontalAdvance(self._text) + 30, fm.height() + 16)

            def paintEvent(self, event) -> None:  # noqa: N802
                painter = QPainter(self)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                painter.setBrush(QColor(18, 24, 32, 210))
                painter.setPen(QPen(QColor(120, 165, 210, 150), 1))
                painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 8, 8)
                painter.setPen(QColor(238, 244, 251))
                painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._text)

        return _Badge(parent)
