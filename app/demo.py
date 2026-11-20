# -*- coding: utf-8 -*-
"""演示录制模式：python -m app.main --demo

自动播放一段"使用 HandWriteStudio"的操作过程，供屏幕录制：
输入文字 → 插入表格/图片 → 调字号/行距 → 换背景纸 → 开启格子对齐 → 导出 PNG → 全屏看效果。

不弹任何需要人点的对话框；假光标只负责让录屏看起来像真的在操作。
"""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QLabel, QMessageBox, QToolButton

from .export import export_pngs
from .settings import OUTPUT_PNG_DIR, ensure_output_dirs

TITLE = "写给未来的自己"
BODY = (
    "今天下了点小雨，图书馆的窗上全是水汽。\n"
    "我把这一页慢慢写下来，留在明年再读。\n"
    "字写得慢一点，心就能静下来。"
)


class DemoCursor(QLabel):
    """顶层透明窗口里画的假光标。"""

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.resize(26, 26)
        self._normal = self._make_pix(QColor("#20242e"))
        self._pressed = self._make_pix(QColor("#3b6ea5"))
        self.setPixmap(self._normal)
        self.show()

    @staticmethod
    def _make_pix(color: QColor) -> QPixmap:
        pm = QPixmap(26, 26)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor("#ffffff"), 2.0))
        p.setBrush(color)
        pts = [
            QPoint(2, 2),
            QPoint(2, 20),
            QPoint(8, 15),
            QPoint(11, 24),
            QPoint(15, 22),
            QPoint(11, 13),
            QPoint(19, 13),
        ]
        p.drawPolygon(pts)
        p.end()
        return pm

    def glide_to(self, target: QPoint) -> None:
        start = self.pos()
        steps = 8

        def step(i: int = 1) -> None:
            if i > steps:
                return
            x = start.x() + (target.x() - start.x()) * i // steps
            y = start.y() + (target.y() - start.y()) * i // steps
            self.move(x, y)
            QTimer.singleShot(18, lambda: step(i + 1))

        step()

    def press(self) -> None:
        self.setPixmap(self._pressed)
        QTimer.singleShot(160, lambda: self.setPixmap(self._normal))


def _center(widget) -> QPoint:
    return widget.mapToGlobal(widget.rect().center())


def _tool_button(window, text: str):
    from PySide6.QtWidgets import QToolButton

    for btn in window.findChildren(QToolButton):
        if text in btn.text():
            return btn
    return None


def _auto_box(parent, title: str, text: str, ms: int = 2600) -> None:
    box = QMessageBox(
        QMessageBox.Icon.Information,
        title,
        text,
        QMessageBox.StandardButton.NoButton,
        parent,
    )
    box.setWindowModality(Qt.WindowModality.NonModal)
    box.show()
    QTimer.singleShot(ms, box.close)


def run_demo(window) -> None:
    ensure_output_dirs()
    # 最大化：录制时整屏就是软件界面
    window.showMaximized()
    try:
        window.dock.setMinimumWidth(400)
        window.resizeDocks([window.dock], [400], Qt.Orientation.Horizontal)
    except Exception:
        pass
    cur = DemoCursor()
    cur.move(60, 60)

    def _dump_geom() -> None:
        try:
            Path("D:/HandWriteStudio/promo/assets/_geom.txt").write_text(
                f"window={window.geometry()}\ndock={window.dock.geometry()}\n"
                f"editor={window.editor.geometry()}\npreview={window.preview.geometry()}\n"
                f"screen={window.screen().availableGeometry()}\n",
                encoding="utf-8",
            )
        except Exception:
            pass

    QTimer.singleShot(1500, _dump_geom)

    def schedule(seconds: float, fn) -> None:
        QTimer.singleShot(int(seconds * 1000), fn)

    def type_text(text: str, interval: int = 55) -> None:
        pos = {"i": 0}

        def step() -> None:
            i = pos["i"]
            if i >= len(text):
                return
            editor = window.editor
            cursor = editor.textCursor()
            ch = text[i]
            if ch == "\n":
                cursor.insertBlock()
            else:
                cursor.insertText(ch)
            pos["i"] = i + 1
            QTimer.singleShot(interval, step)

        step()

    def click_widget(widget) -> None:
        cur.glide_to(_center(widget))
        QTimer.singleShot(220, cur.press)

    def do_export() -> None:
        directory = OUTPUT_PNG_DIR / time.strftime("%Y-%m-%d_%H-%M-%S")
        directory.mkdir(parents=True, exist_ok=True)
        renderer = window._make_renderer()
        cur.press()
        QApplicationProcess()
        paths = export_pngs(
            renderer,
            str(directory),
            dpi=int(window.style.export_dpi),
            numbered=True,
            start_index=0,
        )
        last_paths[:] = paths
        window.statusBar().showMessage(f"已导出 {len(paths)} 张 PNG 到 {directory}", 8000)
        _auto_box(window, "导出完成", f"已导出 {len(paths)} 张 PNG（{window.style.export_dpi} dpi）：\n{directory}")

    def QApplicationProcess() -> None:
        from PySide6.QtWidgets import QApplication

        QApplication.processEvents()

    # ---------- 时间线 ----------
    schedule(0.7, lambda: window.editor.clear())
    schedule(1.0, lambda: click_widget(window.editor))
    schedule(1.5, lambda: type_text(TITLE + "\n" + BODY))

    # 表格按钮（工具栏里文字为“表格”的 QToolButton）
    def table_btn():
        for b in window.findChildren(QToolButton):
            if "表格" in b.text():
                return b
        return None

    def insert_table() -> None:
        window.editor.insert_table(3, 3)

    schedule(6.2, lambda: click_widget(table_btn() or window.editor))
    schedule(6.8, insert_table)

    # 字号 12 -> 15
    def set_size() -> None:
        window.size_spin.setValue(15.0)

    schedule(9.0, lambda: click_widget(window.size_spin))
    schedule(9.6, set_size)

    # 行距 1.55 -> 1.7
    def set_line() -> None:
        window.line_spin.setValue(1.7)

    schedule(11.4, lambda: click_widget(window.line_spin))
    schedule(12.0, set_line)

    # 背景纸切到 8mm 横线纸
    def set_paper() -> None:
        combo = window.bg_combo
        for i in range(combo.count()):
            text = combo.itemText(i)
            if "横线纸_8mm" in text:
                combo.setCurrentIndex(i)
                return
        combo.setCurrentIndex(0)

    schedule(13.4, lambda: click_widget(window.bg_combo))
    schedule(14.2, set_paper)

    # 格子对齐模式 + 行数
    def set_grid() -> None:
        window.grid_check.setChecked(True)
        window.rows_spin.setValue(31)

    schedule(16.2, lambda: click_widget(window.grid_check))
    schedule(17.0, set_grid)

    # 拖动预览里的页面边距线
    def drag_margin() -> None:
        canvas = window.preview.canvas
        left, top, right, bottom = canvas.margins
        steps = [6, 12, 20, 26, 30]
        state = {"i": 0}

        def tick() -> None:
            i = state["i"]
            if i >= len(steps):
                return
            new_left = left + steps[i]
            canvas.margins = (new_left, top, right, bottom)
            canvas.margins_changed.emit(new_left, top, right, bottom)
            canvas.update()
            state["i"] = i + 1
            QTimer.singleShot(110, tick)

        tick()

    def goto_margin() -> None:
        canvas = window.preview.canvas
        cur.glide_to(canvas.mapToGlobal(QPoint(int(canvas.width() * 0.2), int(canvas.height() * 0.3))))

    schedule(18.6, goto_margin)
    schedule(19.4, drag_margin)

    last_paths: list[str] = []

    # 导出 PNG
    schedule(22.2, lambda: click_widget(_tool_button(window, "导出 PNG") or window.editor))
    schedule(23.0, do_export)
