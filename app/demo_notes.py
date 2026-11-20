# -*- coding: utf-8 -*-
"""演示录制模式（笔记复刻）：python -m app.main --demo-notes <hws 文件>

复刻「形势与政策笔记」那页，走主人真实用的路子：
粘原文（保留换行/空格/格式）→ 现场搓两个参数预设（前页/后页）→ 启用逐页预设轮换
→ 第 1 页前页、第 2 页后页 → 导出 PNG。

录制前会先把上次演示留下的两个预设和轮换配置清掉，避免软件里带着残留状态。
不弹需要人点的对话框；假光标只负责让录屏看起来像在操作。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QComboBox

from .demo import DemoCursor, _auto_box, _center
from .export import export_pngs
from .presets import save_presets
from .settings import OUTPUT_PNG_DIR, HandStyle, ensure_output_dirs

FRONT = "笔记前页"
BACK = "笔记后页"


def _privatize(html: str) -> str:
    return html.replace("徐老师", "周老师")


def _tool_button(window, text: str):
    from PySide6.QtWidgets import QToolButton

    for btn in window.findChildren(QToolButton):
        if text in btn.text():
            return btn
    return None


def _reset_presets(window) -> None:
    """清掉上次演示留下的两个预设和逐页轮换配置。"""
    changed = False
    for name in (FRONT, BACK):
        if name in window.presets:
            window.presets.pop(name, None)
            changed = True
    if changed:
        save_presets(window.presets)
    window.style.page_presets_enabled = False
    window.style.page_preset_names = []
    window.style.page_preset_styles = []
    window._refresh_preset_combo("")
    window._sync_page_presets()


def _apply_style(window, style: dict) -> None:
    window.style = HandStyle.from_dict(style)
    window._sync_style_controls()
    window._set_dirty(True)
    window._preview_timer.start()


def _save_preset_fake(window, name: str) -> None:
    """模拟点「保存当前...」：不弹输入框，直接把当前参数存成预设。"""
    data = window.style.to_dict()
    for key in ("page_presets_enabled", "page_preset_names", "page_preset_styles"):
        data.pop(key, None)
    window.presets[name] = data
    save_presets(window.presets)
    window._refresh_preset_combo(name)
    window.statusBar().showMessage(f"已保存预设：{name}", 3000)


def _page_combo(window, row: int) -> QComboBox | None:
    try:
        return window.page_preset_table.cellWidget(row, 1)
    except Exception:
        return None


def _set_page(window, row: int, name: str) -> None:
    combo = _page_combo(window, row)
    if combo is not None:
        idx = combo.findData(name)
        if idx >= 0:
            combo.setCurrentIndex(idx)


def run_demo_notes(window, hws_path: str) -> None:
    ensure_output_dirs()
    data = json.loads(Path(hws_path).read_text(encoding="utf-8"))
    html = _privatize(str(data.get("html") or ""))
    styles = data["style"].get("page_preset_styles") or [{}, {}]
    front_style = dict(styles[0])
    back_style = dict(styles[1]) if len(styles) > 1 else dict(styles[0])

    window.showMaximized()
    try:
        window.dock.setMinimumWidth(400)
        window.resizeDocks([window.dock], [400], Qt.Orientation.Horizontal)
    except Exception:
        pass

    _reset_presets(window)

    cur = DemoCursor()
    cur.move(60, 60)
    last_paths: list[str] = []

    def schedule(seconds: float, fn) -> None:
        QTimer.singleShot(int(seconds * 1000), fn)

    def click_widget(widget) -> None:
        if widget is None:
            return
        cur.glide_to(_center(widget))
        QTimer.singleShot(220, cur.press)

    def insert_text() -> None:
        window.editor.setHtml(html)
        window._preview_timer.start()

    def do_export() -> None:
        directory = OUTPUT_PNG_DIR / time.strftime("%Y-%m-%d_%H-%M-%S")
        directory.mkdir(parents=True, exist_ok=True)
        renderer = window._make_renderer()
        cur.press()
        from PySide6.QtWidgets import QApplication

        QApplication.processEvents()
        paths = export_pngs(
            renderer,
            str(directory),
            dpi=int(window.style.export_dpi),
            numbered=True,
            start_index=0,
        )
        last_paths[:] = paths
        window.statusBar().showMessage(f"已导出 {len(paths)} 张 PNG 到 {directory}", 8000)
        _auto_box(
            window,
            "导出完成",
            f"已导出 {len(paths)} 张 PNG（{window.style.export_dpi} dpi）：\n{directory}",
        )

    def scroll_preview() -> None:
        """导出前滚动预览，让人看到几页的效果。"""
        try:
            bar = window.preview.scroll.verticalScrollBar()
        except Exception:
            return
        bar.setValue(0)
        state = {"v": 0, "step": max(6, bar.maximum() // 70)}

        def tick() -> None:
            state["v"] += state["step"]
            if state["v"] >= bar.maximum():
                bar.setValue(bar.maximum())
                return
            bar.setValue(state["v"])
            QTimer.singleShot(45, tick)

        QTimer.singleShot(60, tick)

    # ---------- 时间线（链式：每步执行完再排下一步，避免渲染阻塞导致动作堆在一起）----------
    def steps() -> list[tuple[float, object]]:
        return [
            (1.0, lambda: window.editor.clear()),
            (0.6, insert_text),
            (1.4, lambda: click_widget(window.editor)),
            (1.2, lambda: _apply_style(window, front_style)),
            (1.6, lambda: click_widget(window.preset_save_btn)),
            (1.0, lambda: _save_preset_fake(window, FRONT)),
            (2.0, lambda: _apply_style(window, back_style)),
            (1.6, lambda: click_widget(window.preset_save_btn)),
            (1.0, lambda: _save_preset_fake(window, BACK)),
            (1.8, lambda: click_widget(window.page_preset_check)),
            (1.0, lambda: window.page_preset_check.setChecked(True)),
            (1.4, lambda: _set_page(window, 0, FRONT)),
            (1.6, lambda: click_widget(window.page_preset_add_btn)),
            (1.0, lambda: window.page_preset_add_btn.click()),
            (1.4, lambda: _set_page(window, 1, BACK)),
            (2.0, lambda: click_widget(window.preview)),
            (0.6, scroll_preview),
            (3.4, lambda: click_widget(_tool_button(window, "导出 PNG") or window.editor)),
            (1.0, do_export),
        ]

    chain = steps()

    def run(i: int = 0) -> None:
        if i >= len(chain):
            return
        delay, fn = chain[i]
        fn()
        QTimer.singleShot(int(delay * 1000), lambda: run(i + 1))

    QTimer.singleShot(300, run)
