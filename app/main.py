"""程序入口：python -m app.main"""
from __future__ import annotations

import faulthandler
import sys
from pathlib import Path

from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from .mainwindow import MainWindow
from .settings import ASSETS_DIR

_CRASH_LOG = None


def _enable_crash_log() -> None:
    global _CRASH_LOG
    try:
        log_path = Path.home() / ".handwrite_crash.log"
        _CRASH_LOG = open(log_path, "a", encoding="utf-8", buffering=1)
        faulthandler.enable(_CRASH_LOG, all_threads=True)
    except Exception:
        pass


def main() -> int:
    _enable_crash_log()
    app = QApplication(sys.argv)
    app.setApplicationName("HandWriteStudio")
    app.setOrganizationName("HandWriteStudio")
    app.setStyle("Fusion")
    app.setFont(QFont("Microsoft YaHei UI", 10))
    icon_path = ASSETS_DIR / "icon.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    if "--selftest" in sys.argv:
        from .selftest import run_selftest

        return run_selftest()
    window = MainWindow()
    window.show()
    if "--demo" in sys.argv:
        from .demo import run_demo

        run_demo(window)
    elif "--demo-notes" in sys.argv:
        from .demo_notes import run_demo_notes

        idx = sys.argv.index("--demo-notes")
        hws = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else ""
        run_demo_notes(window, hws)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
