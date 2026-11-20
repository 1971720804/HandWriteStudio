"""主窗口：编辑区 + 实时手写预览 + 参数面板。"""
from __future__ import annotations

import traceback
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QAction,
    QColor,
    QDesktopServices,
    QFont,
    QIcon,
    QKeySequence,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QStyle,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QWidget,
    QToolBar,
    QToolButton,
    QVBoxLayout,
)

from . import __version__
from .docx_import import import_docx
from .editor import BASE_FONT_SIZE, Editor
from .export import export_pdf, export_pngs
from .preview import PreviewPanel
from .presets import load_presets, save_presets
from .project import PROJECT_SUFFIX, load_project, save_project
from .renderer import HandRenderer, make_renderer
from .settings import (
    ASSETS_DIR,
    DEFAULT_STYLE,
    FONT_DIR,
    OUTPUT_PDF_DIR,
    OUTPUT_PNG_DIR,
    OUTPUT_ROOT,
    PAPER_DIR,
    HandStyle,
    ensure_output_dirs,
)

PAPER_SIZES = {
    "A4（210 × 297 mm）": (595.0, 842.0),
    "B5（176 × 250 mm）": (499.0, 709.0),
    "A5（148 × 210 mm）": (420.0, 595.0),
    "Letter（216 × 279 mm）": (612.0, 792.0),
}

PARAGRAPH_STYLES = [
    ("正文", 12.0, False),
    ("标题 1", 22.0, True),
    ("标题 2", 18.0, True),
    ("标题 3", 15.0, True),
    ("强调", 12.0, True),
]


class TableDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("插入表格")
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.rows = QSpinBox()
        self.rows.setRange(1, 50)
        self.rows.setValue(3)
        self.cols = QSpinBox()
        self.cols.setRange(1, 20)
        self.cols.setValue(3)
        form.addRow("行数", self.rows)
        form.addRow("列数", self.cols)
        lay.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def values(self) -> tuple[int, int]:
        return self.rows.value(), self.cols.value()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        ensure_output_dirs()
        self.style = HandStyle()
        self.presets = load_presets()
        self.current_path: str | None = None
        self._dirty = False
        self._loading_ui = False
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(300)
        self._preview_timer.timeout.connect(self._refresh_preview)

        from .watermark import watermark_lines

        _wa, _wb, _wc = watermark_lines()
        self.setWindowTitle(f"HandWriteStudio　{_wa} · {_wb} · {_wc}")
        icon_path = ASSETS_DIR / "icon.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.resize(1480, 940)
        self.setMinimumSize(1080, 700)

        self._build_actions()
        self._build_ui()
        self._build_menus()
        self._build_toolbars()
        self._build_settings_dock()
        self._wire()
        self._paper_watcher = QFileSystemWatcher(self)
        if PAPER_DIR.exists():
            self._paper_watcher.addPath(str(PAPER_DIR))
        self._paper_watcher.directoryChanged.connect(self._on_paper_dir_changed)

        self.editor.document().setModified(False)
        QTimer.singleShot(120, self._refresh_preview)

    # ---------- 构建 ----------

    def _icon(self, pixmap: QStyle.StandardPixmap):
        return self.style().standardIcon(pixmap)

    def _make_action(self, text: str, slot=None, shortcut=None, checkable: bool = False) -> QAction:
        action = QAction(text, self)
        if shortcut is not None:
            action.setShortcut(QKeySequence(shortcut))
        if slot is not None:
            action.triggered.connect(slot)
        action.setCheckable(checkable)
        return action

    def _build_actions(self) -> None:
        self.act_new = self._make_action("新建", self.new_document, QKeySequence.StandardKey.New)
        self.act_open = self._make_action("打开", self.open_project, QKeySequence.StandardKey.Open)
        self.act_save = self._make_action("保存", self.save_project, QKeySequence.StandardKey.Save)
        self.act_save_as = self._make_action(
            "另存为…", self.save_project_as, QKeySequence.StandardKey.SaveAs
        )
        self.act_import = self._make_action("导入 Word…", self.import_word)
        self.act_export_png = self._make_action("导出 PNG…", self.export_png)
        self.act_export_pdf = self._make_action("导出 PDF…", self.export_pdf)
        self.act_open_output = self._make_action("打开输出文件夹", self.open_output_folder)
        self.act_quit = self._make_action("退出", self.close, QKeySequence.StandardKey.Quit)

        self.act_undo = self._make_action("撤销", self._undo, QKeySequence.StandardKey.Undo)
        self.act_redo = self._make_action("重做", self._redo, QKeySequence.StandardKey.Redo)
        self.act_cut = self._make_action("剪切", self._cut, QKeySequence.StandardKey.Cut)
        self.act_copy = self._make_action("复制", self._copy, QKeySequence.StandardKey.Copy)
        self.act_paste = self._make_action("粘贴", self._paste, QKeySequence.StandardKey.Paste)
        self.act_select_all = self._make_action(
            "全选", self._select_all, QKeySequence.StandardKey.SelectAll
        )

        self.act_insert_table = self._make_action("插入表格…", self.insert_table)
        self.act_add_row = self._make_action("加一行", self._add_row)
        self.act_add_col = self._make_action("加一列", self._add_col)
        self.act_del_row = self._make_action("删一行", self._del_row)
        self.act_del_col = self._make_action("删一列", self._del_col)
        self.act_del_table = self._make_action("删除表格", self._del_table)

        self.act_insert_image = self._make_action("插入图片…", self.insert_image)

        self.act_bold = self._make_action("加粗", self.toggle_bold, QKeySequence.StandardKey.Bold, True)
        self.act_italic = self._make_action("斜体", self.toggle_italic, QKeySequence.StandardKey.Italic, True)
        self.act_underline = self._make_action(
            "下划线", self.toggle_underline, QKeySequence.StandardKey.Underline, True
        )

        self.act_align_left = self._make_action("左对齐", self._align_left)
        self.act_align_center = self._make_action("居中", self._align_center)
        self.act_align_right = self._make_action("右对齐", self._align_right)
        self.act_align_justify = self._make_action("两端对齐", self._align_justify)
        self.act_indent = self._make_action("首行缩进 2 字", self.toggle_indent, checkable=True)
        self.act_indent.setChecked(True)

        self.act_settings = self._make_action("手写设置", self._toggle_settings, checkable=True)
        self.act_settings.setChecked(True)
        self.act_zoom_in = self._make_action("放大预览", lambda: self.preview.zoom_by(1.12))
        self.act_zoom_out = self._make_action("缩小预览", lambda: self.preview.zoom_by(1 / 1.12))
        self.act_zoom_fit = self._make_action("适应窗口", lambda: self.preview.fit_width())
        self.act_about = self._make_action("使用说明", self.show_help)

    # 编辑动作的延迟绑定：动作在编辑区创建前就要存在
    def _undo(self) -> None:
        self.editor.undo()

    def _redo(self) -> None:
        self.editor.redo()

    def _cut(self) -> None:
        self.editor.cut()

    def _copy(self) -> None:
        self.editor.copy()

    def _paste(self) -> None:
        self.editor.paste()

    def _select_all(self) -> None:
        self.editor.selectAll()

    def _align_left(self) -> None:
        self.editor.set_alignment(Qt.AlignmentFlag.AlignLeft)

    def _align_center(self) -> None:
        self.editor.set_alignment(Qt.AlignmentFlag.AlignHCenter)

    def _align_right(self) -> None:
        self.editor.set_alignment(Qt.AlignmentFlag.AlignRight)

    def _align_justify(self) -> None:
        self.editor.set_alignment(Qt.AlignmentFlag.AlignJustify)

    def _add_row(self) -> None:
        self.editor.table_add_row()
        self._preview_timer.start()

    def _add_col(self) -> None:
        self.editor.table_add_column()
        self._preview_timer.start()

    def _del_row(self) -> None:
        self.editor.table_delete_row()
        self._preview_timer.start()

    def _del_col(self) -> None:
        self.editor.table_delete_column()
        self._preview_timer.start()

    def _del_table(self) -> None:
        self.editor.delete_current_table()
        self._preview_timer.start()

    def _toggle_settings(self, checked: bool) -> None:
        self.dock.setVisible(checked)

    def _build_ui(self) -> None:
        self.editor = Editor(self)
        self.preview = PreviewPanel(self)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(10, 10, 6, 10)
        left_lay.setSpacing(8)
        hint = QLabel("编辑区（显示为普通字体，右侧是实际手写效果）")
        hint.setStyleSheet("color:#8a929e; font-size:12px;")
        left_lay.addWidget(hint)
        left_lay.addWidget(self.editor, 1)
        self.splitter.addWidget(left)
        self.splitter.addWidget(self.preview)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([720, 720])
        self.setCentralWidget(self.splitter)

        self.status_pages = QLabel("1 页")
        self.status_words = QLabel("0 字")
        self.status_render = QLabel("")
        for w in (self.status_pages, self.status_words, self.status_render):
            w.setStyleSheet("color:#5f6875; padding: 0 8px;")
        from .watermark import watermark_lines

        _a, _b, _c = watermark_lines()
        self.watermark_label = QLabel(f"{_a} · {_b} · {_c}")
        self.watermark_label.setStyleSheet(
            "QLabel { color:#ffffff; background:#b3261e;"
            " border-radius:5px; padding:2px 10px; font-size:12px; font-weight:600; }"
        )
        self.watermark_label.setToolTip(f"{_a}｜{_b}｜{_c}")
        self.statusBar().addPermanentWidget(self.watermark_label)
        self.statusBar().addPermanentWidget(self.status_pages)
        self.statusBar().addPermanentWidget(self.status_words)
        self.statusBar().addPermanentWidget(self.status_render)
        self.statusBar().setToolTip(f"{_a} · {_b} · {_c}")
        self.statusBar().showMessage("就绪", 3000)

    def _build_menus(self) -> None:
        bar = self.menuBar()
        m_file = bar.addMenu("文件")
        for a in (self.act_new, self.act_open, self.act_save, self.act_save_as):
            m_file.addAction(a)
        m_file.addSeparator()
        m_file.addAction(self.act_import)
        m_file.addAction(self.act_export_png)
        m_file.addAction(self.act_export_pdf)
        m_file.addAction(self.act_open_output)
        m_file.addSeparator()
        m_file.addAction(self.act_quit)

        m_edit = bar.addMenu("编辑")
        for a in (
            self.act_undo,
            self.act_redo,
            None,
            self.act_cut,
            self.act_copy,
            self.act_paste,
            self.act_select_all,
        ):
            if a is None:
                m_edit.addSeparator()
            else:
                m_edit.addAction(a)

        m_insert = bar.addMenu("插入")
        m_insert.addAction(self.act_insert_table)
        m_insert.addAction(self.act_insert_image)
        m_insert.addSeparator()
        for a in (self.act_add_row, self.act_add_col, self.act_del_row, self.act_del_col, self.act_del_table):
            m_insert.addAction(a)

        m_format = bar.addMenu("格式")
        m_format.addAction(self.act_bold)
        m_format.addAction(self.act_italic)
        m_format.addAction(self.act_underline)
        m_format.addSeparator()
        for a in (self.act_align_left, self.act_align_center, self.act_align_right, self.act_align_justify):
            m_format.addAction(a)
        m_format.addSeparator()
        m_format.addAction(self.act_indent)

        m_view = bar.addMenu("视图")
        m_view.addAction(self.act_settings)
        m_view.addSeparator()
        m_view.addAction(self.act_zoom_in)
        m_view.addAction(self.act_zoom_out)
        m_view.addAction(self.act_zoom_fit)

        m_help = bar.addMenu("帮助")
        m_help.addAction(self.act_about)

    def _build_toolbars(self) -> None:
        main = QToolBar("主工具栏", self)
        main.setMovable(False)
        main.setFloatable(False)
        main.setIconSize(QSize(18, 18))
        main.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, main)
        for a in (self.act_new, self.act_open, self.act_save):
            main.addAction(a)
        main.addSeparator()
        main.addAction(self.act_import)
        main.addAction(self.act_export_png)
        main.addAction(self.act_export_pdf)
        main.addSeparator()
        main.addAction(self.act_undo)
        main.addAction(self.act_redo)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        main.addWidget(spacer)
        self.action_settings = main.addAction(self.act_settings)
        main.setStyleSheet(
            "QToolBar { background:#f5f7fa; border-bottom:1px solid #dde2e8; spacing:4px; padding:3px; }"
            "QToolButton { padding:4px 9px; border-radius:5px; }"
            "QToolButton:hover { background:#e6eefb; }"
        )

        fmt = QToolBar("格式工具栏", self)
        fmt.setMovable(False)
        fmt.setFloatable(False)
        fmt.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.addToolBarBreak(Qt.ToolBarArea.TopToolBarArea)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, fmt)
        self.addToolBarBreak(Qt.ToolBarArea.TopToolBarArea)

        fmt.addWidget(QLabel(" 样式 "))
        self.style_combo = QComboBox()
        for name, _size, _bold in PARAGRAPH_STYLES:
            self.style_combo.addItem(name)
        self.style_combo.setFixedWidth(96)
        fmt.addWidget(self.style_combo)

        fmt.addWidget(QLabel(" 字号 "))
        self.size_combo = QComboBox()
        self.size_combo.setEditable(True)
        for s in (9, 10.5, 12, 14, 16, 18, 22, 26, 30, 36):
            self.size_combo.addItem(f"{s:g}")
        self.size_combo.setCurrentText("12")
        self.size_combo.setFixedWidth(68)
        fmt.addWidget(self.size_combo)

        fmt.addSeparator()
        fmt.addAction(self.act_bold)
        fmt.addAction(self.act_italic)
        fmt.addAction(self.act_underline)
        fmt.addSeparator()
        fmt.addAction(self.act_align_left)
        fmt.addAction(self.act_align_center)
        fmt.addAction(self.act_align_right)
        fmt.addAction(self.act_align_justify)
        fmt.addAction(self.act_indent)
        fmt.addSeparator()

        table_btn = QToolButton()
        table_btn.setText("表格 ▾")
        table_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        table_btn.setStyleSheet("QToolButton { padding:4px 8px; }")
        from PySide6.QtWidgets import QMenu

        table_menu = QMenu(table_btn)
        table_menu.addAction(self.act_insert_table)
        table_menu.addSeparator()
        for a in (self.act_add_row, self.act_add_col, self.act_del_row, self.act_del_col, self.act_del_table):
            table_menu.addAction(a)
        table_btn.setMenu(table_menu)
        fmt.addWidget(table_btn)
        fmt.addAction(self.act_insert_image)

        for a in (self.act_bold, self.act_italic, self.act_underline):
            a.setCheckable(True)
        fmt.setStyleSheet(
            "QToolBar { background:#fbfcfd; border-bottom:1px solid #e3e7ed; spacing:3px; padding:3px 6px; }"
            "QToolButton { padding:3px 8px; border-radius:5px; }"
            "QToolButton:hover { background:#eaf1fb; }"
            "QToolButton:checked { background:#d8e8ff; }"
            "QComboBox { padding:2px 6px; }"
        )

    # ---------- 设置面板 ----------

    def _build_settings_dock(self) -> None:
        self.dock = QDockWidget("手写设置", self)
        self.dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea)
        self.dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable | QDockWidget.DockWidgetFeature.DockWidgetClosable)
        self.dock.setMinimumWidth(300)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        panel = QWidget()
        form = QFormLayout(panel)
        form.setContentsMargins(12, 12, 12, 12)
        form.setSpacing(9)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        preset_group = QGroupBox("参数预设")
        pg = QVBoxLayout(preset_group)
        pg.setContentsMargins(8, 10, 8, 8)
        pg.setSpacing(6)
        self.preset_combo = QComboBox()
        self.preset_combo.setToolTip("选择已保存的参数预设")
        pg.addWidget(self.preset_combo)
        preset_row = QHBoxLayout()
        preset_row.setContentsMargins(0, 0, 0, 0)
        preset_row.setSpacing(6)
        self.preset_load_btn = QPushButton("载入")
        self.preset_save_btn = QPushButton("保存当前…")
        self.preset_delete_btn = QPushButton("删除")
        for button in (self.preset_load_btn, self.preset_save_btn, self.preset_delete_btn):
            button.setFixedHeight(26)
            preset_row.addWidget(button)
        pg.addLayout(preset_row)
        form.addRow(preset_group)
        self._refresh_preset_combo()

        self.page_preset_group = QGroupBox("逐页预设轮换")
        ppg = QVBoxLayout(self.page_preset_group)
        ppg.setContentsMargins(8, 10, 8, 8)
        ppg.setSpacing(6)
        self.page_preset_check = QCheckBox("启用逐页预设轮换")
        self.page_preset_check.setToolTip(
            "每页按顺序套用一个参数预设，超出列表后从第一个循环。\n"
            "只换字体、背景、墨色和抖动等外观；纸张、页边距、字号、行数等排版参数仍按右侧全局设置。"
        )
        ppg.addWidget(self.page_preset_check)
        self.page_preset_table = QTableWidget(0, 3)
        self.page_preset_table.setHorizontalHeaderLabels(["页", "参数预设", ""])
        self.page_preset_table.verticalHeader().setVisible(False)
        self.page_preset_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.page_preset_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.page_preset_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.page_preset_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.page_preset_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self.page_preset_table.setMaximumHeight(190)
        ppg.addWidget(self.page_preset_table)
        self.page_preset_add_btn = QPushButton("＋ 添加一页")
        self.page_preset_add_btn.setFixedHeight(26)
        ppg.addWidget(self.page_preset_add_btn)
        self.page_preset_hint = QLabel(
            "一页一风格，超出列表后从头循环。每页可换字体、背景、墨色、抖动和页边距；"
            "纸张、字号、行数等版式仍按右侧全局设置。"
        )
        self.page_preset_hint.setWordWrap(True)
        self.page_preset_hint.setStyleSheet("color:#777; font-size:11px;")
        ppg.addWidget(self.page_preset_hint)
        form.addRow(self.page_preset_group)

        self.font_combo = QComboBox()
        self._fill_font_combo()
        form.addRow("字体", self.font_combo)

        self.paper_combo = QComboBox()
        for name in PAPER_SIZES:
            self.paper_combo.addItem(name)
        form.addRow("纸张", self.paper_combo)

        self.bg_combo = QComboBox()
        self._fill_background_combo()
        self.bg_reload_btn = QPushButton("重载")
        self.bg_reload_btn.setFixedHeight(26)
        self.bg_reload_btn.setToolTip("重新读取背景纸文件夹")
        self.bg_reload_btn.clicked.connect(self._reload_backgrounds)
        bg_box = QWidget()
        self.bg_box = bg_box
        bg_row = QHBoxLayout(bg_box)
        bg_row.setContentsMargins(0, 0, 0, 0)
        bg_row.setSpacing(6)
        bg_row.addWidget(self.bg_combo, 1)
        bg_row.addWidget(self.bg_reload_btn)
        form.addRow("背景纸", bg_box)

        self.size_spin = QDoubleSpinBox()
        self.size_spin.setRange(7.0, 30.0)
        self.size_spin.setSingleStep(0.5)
        self.size_spin.setDecimals(1)
        self.size_spin.setValue(self.style.font_size)
        form.addRow("正文字号", self.size_spin)

        self.line_spin = QDoubleSpinBox()
        self.line_spin.setRange(1.0, 3.0)
        self.line_spin.setSingleStep(0.05)
        self.line_spin.setDecimals(2)
        self.line_spin.setValue(self.style.line_spacing)
        self.rows_spin = QSpinBox()
        self.rows_spin.setRange(1, 100)
        self.rows_spin.setValue(max(1, int(getattr(self.style, "grid_rows", 0) or 1)))
        self.rows_spin.setSuffix(" 行")
        self.rows_spin.setToolTip("格子对齐模式下，一页排多少行")
        self.line_label = QLabel("行距")
        self.line_stack = QStackedWidget()
        self.line_stack.addWidget(self.line_spin)
        self.line_stack.addWidget(self.rows_spin)
        form.addRow(self.line_label, self.line_stack)

        self.letter_spin = QDoubleSpinBox()
        self.letter_spin.setRange(-20.0, 30.0)
        self.letter_spin.setSingleStep(0.5)
        self.letter_spin.setDecimals(1)
        self.letter_spin.setSuffix(" pt")
        self.letter_spin.setValue(self.style.letter_spacing)
        self.cols_spin = QSpinBox()
        self.cols_spin.setRange(1, 100)
        self.cols_spin.setValue(max(1, int(getattr(self.style, "grid_cols", 0) or 1)))
        self.cols_spin.setSuffix(" 字")
        self.cols_spin.setToolTip("格子对齐模式下，一行排多少个字")
        self.grid_align_check = QCheckBox("按字数对齐")
        self.grid_align_check.setChecked(
            bool(getattr(self.style, "grid_align_cols", True))
        )
        self.grid_align_check.setToolTip(
            "勾选：每行严格按「单行字数」排，字距自动补到格宽；"
            "取消：文字直接排版到右边距换行，字间距可手动调"
        )
        self.letter_label = QLabel("字间距")
        self.letter_stack = QStackedWidget()
        self.letter_stack.addWidget(self.letter_spin)
        self.letter_stack.addWidget(self.cols_spin)
        self.letter_row = QWidget()
        letter_row_layout = QHBoxLayout(self.letter_row)
        letter_row_layout.setContentsMargins(0, 0, 0, 0)
        letter_row_layout.setSpacing(6)
        letter_row_layout.addWidget(self.letter_stack, 1)
        letter_row_layout.addWidget(self.grid_align_check)
        form.addRow(self.letter_label, self.letter_row)

        self.grid_check = QCheckBox("格子对齐模式（按单页行数 / 单行字数）")
        self.grid_check.setChecked(bool(getattr(self.style, "grid_mode", False)))
        self.grid_check.setToolTip("开启后行距/字间距切换为单页行数/单行字数，文字按格心对齐")
        form.addRow("", self.grid_check)

        margin_box = QWidget()
        self.margin_box = margin_box
        mg = QGridLayout(margin_box)
        mg.setContentsMargins(0, 0, 0, 0)
        mg.setSpacing(4)
        self.margin_spins: dict[str, QDoubleSpinBox] = {}
        for idx, (key, label) in enumerate(
            (("left", "左"), ("right", "右"), ("top", "上"), ("bottom", "下"))
        ):
            sp = QDoubleSpinBox()
            sp.setRange(0, 300)
            sp.setDecimals(0)
            sp.setSingleStep(4)
            sp.setValue(getattr(self.style, f"{key}_margin"))
            sp.setSuffix(" pt")
            self.margin_spins[key] = sp
            mg.addWidget(QLabel(label), idx // 2, (idx % 2) * 2)
            mg.addWidget(sp, idx // 2, (idx % 2) * 2 + 1)
        form.addRow("页边距", margin_box)

        self.export_dpi_combo = QComboBox()
        for dpi in (200, 300, 600, 900):
            self.export_dpi_combo.addItem("", dpi)
        idx = self.export_dpi_combo.findData(int(getattr(self.style, "export_dpi", 900)))
        self.export_dpi_combo.setCurrentIndex(max(0, idx))
        form.addRow("导出清晰度", self.export_dpi_combo)
        self._refresh_export_dpi_labels()

        self.sharp_box = QCheckBox("锐化边缘（关闭文字抗锯齿）")
        self.sharp_box.setChecked(bool(getattr(self.style, "sharp_edges", False)))
        self.sharp_box.setToolTip(
            "高分辨率导出时关闭文字抗锯齿，边缘更硬；预览里可能略显锯齿。"
        )
        form.addRow("", self.sharp_box)

        self.indent_spin = QDoubleSpinBox()
        self.indent_spin.setRange(0.0, 4.0)
        self.indent_spin.setSingleStep(0.5)
        self.indent_spin.setDecimals(1)
        self.indent_spin.setValue(self.style.first_indent)
        self.indent_spin.setSuffix(" 字")
        form.addRow("首行缩进", self.indent_spin)

        self.ink_btn = QPushButton()
        self.ink_btn.setFixedHeight(26)
        self.ink_btn.clicked.connect(self.pick_ink)
        form.addRow("墨色", self.ink_btn)
        self._update_ink_button()

        jitter_row = QWidget()
        self.jitter_row = jitter_row
        jl = QHBoxLayout(jitter_row)
        jl.setContentsMargins(0, 0, 0, 0)
        self.jitter_slider = QSlider(Qt.Orientation.Horizontal)
        self.jitter_slider.setRange(0, 400)
        self.jitter_slider.setValue(round(self.style.jitter_scale * 100))
        self.jitter_label = QLabel(f"{round(self.style.jitter_scale * 100)}%")
        self.jitter_label.setFixedWidth(40)
        jl.addWidget(self.jitter_slider, 1)
        jl.addWidget(self.jitter_label)
        form.addRow("整体强度", jitter_row)

        jitter_group = QGroupBox("抖动细节（各自独立）")
        self._jitter_group = jitter_group
        jg = QGridLayout(jitter_group)
        jg.setContentsMargins(8, 10, 8, 8)
        jg.setHorizontalSpacing(6)
        jg.setVerticalSpacing(4)
        self.jitter_item_sliders: dict[str, QSlider] = {}
        self.jitter_item_labels: dict[str, QLabel] = {}
        jitter_items = [
            ("x_scale", "左右偏移"),
            ("y_scale", "上下浮动"),
            ("theta_scale", "单字旋转"),
            ("stroke_offset_scale", "笔画随机偏移"),
            ("stroke_theta_scale", "笔画随机旋转"),
            ("font_size_scale", "字号浮动"),
            ("word_spacing_scale", "字距松紧"),
            ("line_spacing_scale", "基线浮动"),
            ("line_theta_scale", "整行倾斜"),
            ("alpha_scale", "墨色浓淡"),
        ]
        for row, (key, name) in enumerate(jitter_items):
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 400)
            slider.setValue(round(getattr(self.style, key) * 100))
            if key == "stroke_offset_scale":
                slider.setToolTip("每个笔画按中线随机平移；没有笔画数据的字符不生效")
            elif key == "stroke_theta_scale":
                slider.setToolTip("每个笔画按中线随机旋转；没有笔画数据的字符不生效")
            value_label = QLabel(f"{round(getattr(self.style, key) * 100)}%")
            value_label.setFixedWidth(40)
            slider.valueChanged.connect(
                lambda value, k=key: self._on_jitter_item_changed(k, value)
            )
            self.jitter_item_sliders[key] = slider
            self.jitter_item_labels[key] = value_label
            jg.addWidget(QLabel(name), row, 0)
            jg.addWidget(slider, row, 1)
            jg.addWidget(value_label, row, 2)
        jg.setColumnStretch(1, 1)
        form.addRow(jitter_group)

        seed_row = QWidget()
        self.seed_row = seed_row
        sl = QHBoxLayout(seed_row)
        sl.setContentsMargins(0, 0, 0, 0)
        self.seed_spin = QSpinBox()
        self.seed_spin.setRange(0, 99999999)
        self.seed_spin.setValue(self.style.seed)
        self.reroll_btn = QPushButton("换一版")
        self.reroll_btn.clicked.connect(self.reroll_seed)
        sl.addWidget(self.seed_spin, 1)
        sl.addWidget(self.reroll_btn)
        form.addRow("随机种子", seed_row)

        self.reset_btn = QPushButton("恢复默认参数")
        self.reset_btn.clicked.connect(self.reset_style)
        form.addRow("", self.reset_btn)

        tip = QLabel(
            "提示：预览显示的就是导出效果；\n"
            "图片点选后拖边角缩放、拖图身移动，右键可裁剪/调位置；\n"
            "表格右键增删行列、调位置，拖内边框调列宽，拖外边缘调整体宽度。\n"
            "参数预设可把当前整套设置存起来，下次直接载入。\n"
            "背景纸旁「重载」可重新读取文件夹，文件夹变动会自动刷新。\n"
            "格子对齐按一字一格排，配格子纸时把行数/字数调到和纸面一致。\n"
            "「垂直撑满」让首行贴顶、末行贴底；要严格对格子纸的行就关掉。\n"
            "锐化边缘会关掉文字抗锯齿，边缘更硬，预览可能略糙。"
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#8a929e; font-size:12px; line-height:1.6;")
        self.tip_label = tip
        form.addRow(tip)

        self._collect_style_widgets(form)
        self._sync_page_presets()

        scroll.setWidget(panel)
        self.dock.setWidget(scroll)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)

    def _fill_font_combo(self) -> None:
        self.font_combo.clear()
        fonts = sorted(FONT_DIR.glob("*.ttf")) + sorted(FONT_DIR.glob("*.otf"))
        for p in fonts:
            self.font_combo.addItem(p.stem, str(p))
        if not fonts:
            self.font_combo.addItem("系统楷体", "")
        current = self.style.font_path
        idx = self.font_combo.findData(current)
        if idx < 0 and current:
            self.font_combo.addItem(Path(current).stem, current)
            idx = self.font_combo.count() - 1
        if idx >= 0:
            self.font_combo.setCurrentIndex(idx)

    # ---------- 信号 ----------

    def _wire(self) -> None:
        self.editor.textChanged.connect(self._on_text_changed)
        self.editor.cursorPositionChanged.connect(self._sync_format_ui)
        self.editor.selectionChanged.connect(self._sync_format_ui)
        self.editor.document().modificationChanged.connect(self._on_modified)

        self.style_combo.activated.connect(self.apply_paragraph_style)
        self.size_combo.activated.connect(self.apply_size_from_combo)
        self.size_combo.lineEdit().editingFinished.connect(self.apply_size_from_combo)

        self.font_combo.currentIndexChanged.connect(self._on_style_control)
        self.paper_combo.currentIndexChanged.connect(self._on_style_control)
        self.bg_combo.currentIndexChanged.connect(self._on_style_control)
        self.size_spin.valueChanged.connect(self._on_style_control)
        self.line_spin.valueChanged.connect(self._on_style_control)
        self.letter_spin.valueChanged.connect(self._on_style_control)
        self.grid_check.toggled.connect(self._on_grid_mode_toggled)
        self.grid_align_check.toggled.connect(self._on_grid_align_toggled)
        self.rows_spin.valueChanged.connect(self._on_grid_value_changed)
        self.cols_spin.valueChanged.connect(self._on_grid_value_changed)
        self.export_dpi_combo.currentIndexChanged.connect(self._on_style_control)
        self.sharp_box.toggled.connect(self._on_style_control)
        self.indent_spin.valueChanged.connect(self._on_style_control)
        for sp in self.margin_spins.values():
            sp.valueChanged.connect(self._on_style_control)
        self.jitter_slider.valueChanged.connect(self._on_jitter_changed)
        self.seed_spin.valueChanged.connect(self._on_style_control)

        self.preset_load_btn.clicked.connect(self.load_preset)
        self.preset_save_btn.clicked.connect(self.save_preset)
        self.preset_delete_btn.clicked.connect(self.delete_preset)
        self.page_preset_check.toggled.connect(self._on_page_preset_toggled)
        self.page_preset_add_btn.clicked.connect(self._add_page_preset_row)

        self.dock.visibilityChanged.connect(self.act_settings.setChecked)
        self.preview.rendered.connect(self._on_preview_rendered)
        self.preview.status_message.connect(self._on_preview_error)
        self.preview.margins_changed.connect(self._on_preview_margins)

        self._sync_format_ui()

    # ---------- 预览 ----------

    def _on_text_changed(self) -> None:
        self._update_word_count()
        self._set_dirty(True)
        self._preview_timer.start()

    def _refresh_preview(self) -> None:
        if not hasattr(self, "preview"):
            return
        self.preview.set_document(self.editor.content_html(), self.style, immediate=True)

    def _on_preview_margins(self, left: float, top: float, right: float, bottom: float) -> None:
        self.style.left_margin = float(left)
        self.style.top_margin = float(top)
        self.style.right_margin = float(right)
        self.style.bottom_margin = float(bottom)
        self._loading_ui = True
        try:
            for key, value in (
                ("left", left),
                ("top", top),
                ("right", right),
                ("bottom", bottom),
            ):
                self.margin_spins[key].setValue(value)
        finally:
            self._loading_ui = False
        self._set_dirty(True)
        self._preview_timer.start()

    def _on_preview_rendered(self, pages: int, ms: float) -> None:
        self.status_pages.setText(f"{pages} 页")
        self.status_render.setText(f"渲染 {ms:.0f} ms")

    def _on_preview_error(self, message: str) -> None:
        self.statusBar().showMessage("预览渲染失败", 5000)
        QMessageBox.warning(self, "预览渲染失败", message)

    def _update_word_count(self) -> None:
        text = self.editor.toPlainText()
        count = sum(1 for ch in text if not ch.isspace())
        self.status_words.setText(f"{count} 字")

    # ---------- 样式面板 ----------

    def _refresh_export_dpi_labels(self) -> None:
        if not hasattr(self, "export_dpi_combo"):
            return
        for i in range(self.export_dpi_combo.count()):
            dpi = int(self.export_dpi_combo.itemData(i))
            w = round(self.style.page_width / 72.0 * dpi)
            h = round(self.style.page_height / 72.0 * dpi)
            self.export_dpi_combo.setItemText(i, f"{dpi} dpi（{w}×{h}）")

    def _estimate_grid(self) -> tuple[int, int]:
        content_w = max(1.0, self.style.page_width - self.style.left_margin - self.style.right_margin)
        content_h = max(1.0, self.style.page_height - self.style.top_margin - self.style.bottom_margin)
        line_h = max(1.0, self.style.font_size * 1.2 * max(0.5, self.style.line_spacing))
        char_w = max(1.0, self.style.font_size + self.style.letter_spacing)
        rows = max(1, min(100, round(content_h / line_h)))
        cols = max(1, min(100, round(content_w / char_w)))
        return rows, cols

    def _sync_grid_widgets(self) -> None:
        grid = bool(getattr(self.style, "grid_mode", False))
        align = bool(getattr(self.style, "grid_align_cols", True))
        if grid:
            rows = int(getattr(self.style, "grid_rows", 0) or 0)
            cols = int(getattr(self.style, "grid_cols", 0) or 0)
            if rows <= 0 or cols <= 0:
                est_rows, est_cols = self._estimate_grid()
                rows = rows or est_rows
                cols = cols or est_cols
                self.style.grid_rows = rows
                self.style.grid_cols = cols
            self.rows_spin.setValue(rows)
            self.cols_spin.setValue(cols)
        self.grid_check.setChecked(grid)
        self.line_stack.setCurrentIndex(1 if grid else 0)
        self.line_label.setText("单页行数" if grid else "行距")
        self.grid_align_check.setVisible(grid)
        self.grid_align_check.setChecked(align)
        if grid and align:
            self.letter_stack.setCurrentIndex(1)
            self.letter_label.setText("单行字数")
        else:
            self.letter_stack.setCurrentIndex(0)
            self.letter_label.setText("字间距")
        if hasattr(self, "size_spin"):
            self.size_spin.setEnabled(True)
            self.size_spin.setToolTip(
                "网格模式下字号可调，字距会自动按格子补齐"
                if grid and align
                else "正文字号"
            )

    def _on_grid_mode_toggled(self, checked: bool) -> None:
        if self._loading_ui:
            return
        self.style.grid_mode = bool(checked)
        if checked and (
            int(getattr(self.style, "grid_rows", 0) or 0) <= 0
            or int(getattr(self.style, "grid_cols", 0) or 0) <= 0
        ):
            rows, cols = self._estimate_grid()
            self.style.grid_rows = rows
            self.style.grid_cols = cols
        self._sync_grid_widgets()
        self._set_dirty(True)
        self._preview_timer.start()

    def _on_grid_align_toggled(self, checked: bool) -> None:
        if self._loading_ui:
            return
        self.style.grid_align_cols = bool(checked)
        self._sync_grid_widgets()
        self._set_dirty(True)
        self._preview_timer.start()

    def _on_grid_value_changed(self, *args) -> None:
        if self._loading_ui:
            return
        self.style.grid_rows = int(self.rows_spin.value())
        self.style.grid_cols = int(self.cols_spin.value())
        self._set_dirty(True)
        self._preview_timer.start()

    def _on_style_control(self, *args) -> None:
        if self._loading_ui:
            return
        self.style.font_path = self.font_combo.currentData() or ""
        key = self.paper_combo.currentText()
        if key in PAPER_SIZES:
            self.style.page_width, self.style.page_height = PAPER_SIZES[key]
            self._refresh_export_dpi_labels()
        bg = self.bg_combo.currentData()
        if bg == "__open_folder__":
            self._open_paper_folder()
            self._loading_ui = True
            idx = self.bg_combo.findData(self.style.background_path or "")
            self.bg_combo.setCurrentIndex(max(0, idx))
            self._loading_ui = False
            return
        if bg == "__custom__":
            self._choose_background()
            return
        self.style.background_path = bg or ""
        self.style.font_size = float(self.size_spin.value())
        self.style.line_spacing = float(self.line_spin.value())
        self.style.letter_spacing = float(self.letter_spin.value())
        for k, sp in self.margin_spins.items():
            setattr(self.style, f"{k}_margin", float(sp.value()))
        self.style.export_dpi = int(self.export_dpi_combo.currentData() or 900)
        self.style.sharp_edges = self.sharp_box.isChecked()
        self.style.first_indent = float(self.indent_spin.value())
        self.style.seed = int(self.seed_spin.value())
        self._set_dirty(True)
        self._preview_timer.start()

    def _on_jitter_changed(self, value: int) -> None:
        self.jitter_label.setText(f"{value}%")
        if self._loading_ui:
            return
        self.style.jitter_scale = value / 100.0
        self._set_dirty(True)
        self._preview_timer.start()

    def _on_jitter_item_changed(self, key: str, value: int) -> None:
        self.jitter_item_labels[key].setText(f"{value}%")
        if self._loading_ui:
            return
        setattr(self.style, key, value / 100.0)
        self._set_dirty(True)
        self._preview_timer.start()

    def _fill_background_combo(self) -> None:
        current = self.bg_combo.currentData() if self.bg_combo.count() else None
        if not current:
            current = self.style.background_path or ""
        if current in ("__custom__", "__open_folder__"):
            current = self.style.background_path or ""
        self.bg_combo.blockSignals(True)
        self.bg_combo.clear()
        self.bg_combo.addItem("无（纯白）", "")
        for p in sorted(PAPER_DIR.glob("*")):
            if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".bmp"):
                self.bg_combo.addItem(p.stem, str(p))
        self.bg_combo.addItem("自定义图片…", "__custom__")
        self.bg_combo.addItem("打开背景纸文件夹…", "__open_folder__")
        idx = self.bg_combo.findData(current)
        if idx < 0 and current and current not in ("__custom__", "__open_folder__"):
            custom_idx = self.bg_combo.findText("自定义图片…")
            self.bg_combo.insertItem(max(0, custom_idx), Path(current).stem, current)
            idx = self.bg_combo.findData(current)
        self.bg_combo.setCurrentIndex(max(0, idx))
        self.bg_combo.blockSignals(False)

    def _reload_backgrounds(self) -> None:
        self._fill_background_combo()
        count = max(0, self.bg_combo.count() - 3)
        self.statusBar().showMessage(f"背景纸列表已重载（{count} 张）", 3000)

    def _on_paper_dir_changed(self, path: str) -> None:
        QTimer.singleShot(300, self._fill_background_combo)

    def _open_paper_folder(self) -> None:
        PAPER_DIR.mkdir(parents=True, exist_ok=True)
        if str(PAPER_DIR) not in self._paper_watcher.directories():
            self._paper_watcher.addPath(str(PAPER_DIR))
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(PAPER_DIR)))

    def _choose_background(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择背景纸", str(PAPER_DIR), "图片 (*.jpg *.jpeg *.png *.bmp)"
        )
        if not path:
            idx = self.bg_combo.findData(self.style.background_path)
            if idx >= 0:
                self.bg_combo.setCurrentIndex(idx)
            return
        idx = self.bg_combo.findData(path)
        if idx < 0:
            custom_idx = self.bg_combo.findText("自定义图片…")
            self.bg_combo.insertItem(max(0, custom_idx), Path(path).stem, path)
            idx = self.bg_combo.findData(path)
        self._loading_ui = True
        self.bg_combo.setCurrentIndex(idx)
        self._loading_ui = False
        self.style.background_path = path
        self._set_dirty(True)
        self._preview_timer.start()

    def pick_ink(self) -> None:
        color = QColorDialog.getColor(QColor(self.style.ink_color), self, "选择墨色")
        if color.isValid():
            self.style.ink_color = color.name()
            self._update_ink_button()
            self._set_dirty(True)
            self._preview_timer.start()

    def _update_ink_button(self) -> None:
        c = QColor(self.style.ink_color)
        self.ink_btn.setText(self.style.ink_color)
        self.ink_btn.setStyleSheet(
            f"QPushButton {{ background:{c.name()}; color:"
            f"{'#ffffff' if c.lightness() < 140 else '#202020'};"
            " border:1px solid #c8ced8; border-radius:5px; }"
        )

    def reroll_seed(self) -> None:
        import random

        self.seed_spin.setValue(random.randint(1, 99999999))

    def reset_style(self) -> None:
        self.style = HandStyle()
        self._sync_style_controls()
        self._set_dirty(True)
        self._preview_timer.start()

    def _sync_style_controls(self) -> None:
        self._loading_ui = True
        try:
            idx = self.font_combo.findData(self.style.font_path)
            if idx < 0 and self.style.font_path:
                self.font_combo.addItem(Path(self.style.font_path).stem, self.style.font_path)
                idx = self.font_combo.count() - 1
            if idx >= 0:
                self.font_combo.setCurrentIndex(idx)
            for name, (w, h) in PAPER_SIZES.items():
                if abs(w - self.style.page_width) < 0.5 and abs(h - self.style.page_height) < 0.5:
                    self.paper_combo.setCurrentText(name)
                    break
            idx = self.bg_combo.findData(self.style.background_path)
            if idx < 0 and self.style.background_path:
                custom_idx = self.bg_combo.findText("自定义图片…")
                self.bg_combo.insertItem(
                    max(0, custom_idx),
                    Path(self.style.background_path).stem,
                    self.style.background_path,
                )
                idx = self.bg_combo.findData(self.style.background_path)
            self.bg_combo.setCurrentIndex(max(0, idx))
            self.size_spin.setValue(self.style.font_size)
            self.line_spin.setValue(self.style.line_spacing)
            self.letter_spin.setValue(self.style.letter_spacing)
            self.indent_spin.setValue(self.style.first_indent)
            for k, sp in self.margin_spins.items():
                sp.setValue(getattr(self.style, f"{k}_margin"))
            self._refresh_export_dpi_labels()
            idx = self.export_dpi_combo.findData(int(getattr(self.style, "export_dpi", 900)))
            self.export_dpi_combo.setCurrentIndex(max(0, idx))
            self.sharp_box.setChecked(bool(getattr(self.style, "sharp_edges", False)))
            self.jitter_slider.setValue(round(self.style.jitter_scale * 100))
            self.jitter_label.setText(f"{round(self.style.jitter_scale * 100)}%")
            for key, slider in self.jitter_item_sliders.items():
                value = round(getattr(self.style, key) * 100)
                slider.setValue(value)
                self.jitter_item_labels[key].setText(f"{value}%")
            self.seed_spin.setValue(self.style.seed)
            self._update_ink_button()
            self._sync_grid_widgets()
            self._sync_page_presets()
        finally:
            self._loading_ui = False

    # ---------- 参数预设 ----------

    def _refresh_preset_combo(self, select: str | None = None) -> None:
        current = self.preset_combo.currentData() if select is None else select
        self.preset_combo.blockSignals(True)
        try:
            self.preset_combo.clear()
            self.preset_combo.addItem("默认设置", "")
            for name in sorted(self.presets):
                self.preset_combo.addItem(name, name)
            idx = self.preset_combo.findData(current)
            self.preset_combo.setCurrentIndex(max(0, idx))
        finally:
            self.preset_combo.blockSignals(False)
        self._sync_page_presets()

    def load_preset(self) -> None:
        name = self.preset_combo.currentData() or ""
        old_page = (
            bool(getattr(self.style, "page_presets_enabled", False)),
            list(getattr(self.style, "page_preset_names", [])),
            list(getattr(self.style, "page_preset_styles", [])),
        )
        if name:
            data = self.presets.get(name)
            if data is None:
                return
            try:
                self.style = HandStyle.from_dict(data)
            except (TypeError, ValueError) as exc:
                QMessageBox.warning(self, "载入预设失败", str(exc))
                return
        else:
            self.style = HandStyle()
        self.style.page_presets_enabled, self.style.page_preset_names, self.style.page_preset_styles = old_page
        self._sync_style_controls()
        self._set_dirty(True)
        self._preview_timer.start()
        self.statusBar().showMessage(f"已载入预设：{name or '默认设置'}", 3000)

    def save_preset(self) -> None:
        suggested = self.preset_combo.currentData() or f"我的设置 {len(self.presets) + 1}"
        name, ok = QInputDialog.getText(
            self, "保存参数预设", "预设名称：", text=str(suggested)
        )
        if not ok:
            return
        name = name.strip()
        if not name:
            return
        if name == "默认设置":
            QMessageBox.information(self, "保存参数预设", "「默认设置」是内置名称，换一个名字吧。")
            return
        if name in self.presets:
            answer = QMessageBox.question(
                self,
                "覆盖预设",
                f"预设「{name}」已存在，要覆盖它吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        data = self.style.to_dict()
        # 分页预设是“页级外观”，不跟着整套参数预设走
        for key in ("page_presets_enabled", "page_preset_names", "page_preset_styles"):
            data.pop(key, None)
        self.presets[name] = data
        try:
            save_presets(self.presets)
        except OSError as exc:
            QMessageBox.warning(self, "保存预设失败", f"无法写入预设文件：\n{exc}")
            return
        self._refresh_preset_combo(name)
        self.statusBar().showMessage(f"已保存预设：{name}", 3000)

    def delete_preset(self) -> None:
        name = self.preset_combo.currentData() or ""
        if not name:
            QMessageBox.information(self, "删除预设", "默认设置不能删除。")
            return
        answer = QMessageBox.question(
            self,
            "删除预设",
            f"确定删除预设「{name}」吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.presets.pop(name, None)
        try:
            save_presets(self.presets)
        except OSError as exc:
            QMessageBox.warning(self, "删除预设失败", f"无法写入预设文件：\n{exc}")
            return
        self._refresh_preset_combo("")
        self.statusBar().showMessage(f"已删除预设：{name}", 3000)

    # ---------- 分页参数预设 ----------

    def _collect_style_widgets(self, form: QFormLayout) -> None:
        """收集普通排版控件，启用逐页预设时整组隐藏。"""
        if not hasattr(self, "_jitter_group"):
            for box in self.findChildren(QGroupBox):
                if box.title().startswith("抖动细节"):
                    self._jitter_group = box
                    break
        widgets = [
            self.font_combo,
            self.paper_combo,
            self.bg_box,
            self.size_spin,
            self.line_stack,
            self.letter_row,
            self.grid_check,
            self.margin_box,
            self.export_dpi_combo,
            self.sharp_box,
            self.indent_spin,
            self.ink_btn,
            self.jitter_row,
            getattr(self, "_jitter_group", None),
            self.seed_row,
            self.reset_btn,
            self.tip_label,
        ]
        self._style_widgets: list[tuple[QWidget, QWidget | None]] = []
        for widget in widgets:
            if widget is None:
                continue
            label = form.labelForField(widget)
            self._style_widgets.append((widget, label))

    def _set_style_controls_visible(self, visible: bool) -> None:
        for widget, label in getattr(self, "_style_widgets", []):
            widget.setVisible(visible)
            if label is not None:
                label.setVisible(visible)

    def _page_preset_style(self, name: str) -> dict:
        if name:
            return dict(self.presets.get(name, {}))
        return {}

    def _append_page_preset_row(self, index: int, name: str) -> None:
        table = self.page_preset_table
        table.setRowCount(index + 1)
        table.setItem(index, 0, QTableWidgetItem(f"第 {index + 1} 页"))
        combo = QComboBox()
        combo.addItem("默认设置", "")
        for preset_name in sorted(self.presets):
            combo.addItem(preset_name, preset_name)
        combo.setProperty("row", index)
        idx = combo.findData(name)
        combo.setCurrentIndex(max(0, idx))
        combo.currentIndexChanged.connect(
            lambda _i, c=combo: self._on_page_preset_combo_changed(c)
        )
        table.setCellWidget(index, 1, combo)
        remove = QPushButton("删除")
        remove.setFixedHeight(24)
        remove.clicked.connect(lambda _c=False, r=index: self._remove_page_preset_row(r))
        table.setCellWidget(index, 2, remove)
        table.setRowHeight(index, 30)

    def _sync_page_presets(self) -> None:
        if not hasattr(self, "page_preset_table"):
            return
        enabled = bool(getattr(self.style, "page_presets_enabled", False))
        self.page_preset_check.blockSignals(True)
        self.page_preset_check.setChecked(enabled)
        self.page_preset_check.blockSignals(False)
        # 分组和开关始终显示；只有启用后才展开表格和提示。
        self.page_preset_group.setVisible(True)
        self.page_preset_table.setVisible(enabled)
        self.page_preset_add_btn.setVisible(enabled)
        self.page_preset_hint.setVisible(enabled)
        self._set_style_controls_visible(not enabled)

        names = list(getattr(self.style, "page_preset_names", []))
        styles = list(getattr(self.style, "page_preset_styles", []))
        if len(styles) < len(names):
            styles += [{}] * (len(names) - len(styles))
        # 预设可能被覆盖/改名：引用名字优先取最新保存的版本
        for i, name in enumerate(names):
            if name and name in self.presets:
                styles[i] = dict(self.presets[name])
        self.style.page_preset_names = names[: len(names)]
        self.style.page_preset_styles = styles[: len(names)]

        table = self.page_preset_table
        table.blockSignals(True)
        try:
            table.clearContents()
            table.setRowCount(0)
            for i, name in enumerate(names):
                self._append_page_preset_row(i, name)
        finally:
            table.blockSignals(False)
        table.setFixedHeight(min(190, 36 + 30 * max(1, len(names))))

    def _on_page_preset_toggled(self, checked: bool) -> None:
        self.style.page_presets_enabled = bool(checked)
        if checked and not getattr(self.style, "page_preset_names", []):
            self.style.page_preset_names = [""]
            self.style.page_preset_styles = [{}]
        self._sync_page_presets()
        self._set_dirty(True)
        self._preview_timer.start()

    def _add_page_preset_row(self) -> None:
        names = list(getattr(self.style, "page_preset_names", []))
        name = sorted(self.presets)[0] if self.presets else ""
        names.append(name)
        self.style.page_preset_names = names
        self.style.page_preset_styles = list(
            getattr(self.style, "page_preset_styles", [])
        ) + [self._page_preset_style(name)]
        self._sync_page_presets()
        self._set_dirty(True)
        self._preview_timer.start()

    def _remove_page_preset_row(self, row: int) -> None:
        names = list(getattr(self.style, "page_preset_names", []))
        styles = list(getattr(self.style, "page_preset_styles", []))
        if 0 <= row < len(names):
            names.pop(row)
            if 0 <= row < len(styles):
                styles.pop(row)
        self.style.page_preset_names = names
        self.style.page_preset_styles = styles
        self._sync_page_presets()
        self._set_dirty(True)
        self._preview_timer.start()

    def _on_page_preset_combo_changed(self, combo: QComboBox) -> None:
        row = int(combo.property("row") or 0)
        names = list(getattr(self.style, "page_preset_names", []))
        styles = list(getattr(self.style, "page_preset_styles", []))
        name = combo.currentData() or ""
        if row < len(names):
            names[row] = name
        while len(styles) <= row:
            styles.append({})
        styles[row] = self._page_preset_style(name)
        self.style.page_preset_names = names
        self.style.page_preset_styles = styles
        self._set_dirty(True)
        self._preview_timer.start()

    # ---------- 编辑格式 ----------

    def toggle_bold(self) -> None:
        self.editor.toggle_bold()
        self._sync_format_ui()
        self._preview_timer.start()

    def toggle_italic(self) -> None:
        self.editor.toggle_italic()
        self._sync_format_ui()
        self._preview_timer.start()

    def toggle_underline(self) -> None:
        self.editor.toggle_underline()
        self._sync_format_ui()
        self._preview_timer.start()

    def toggle_indent(self) -> None:
        self.editor.set_first_line_indent(2.0 if self.act_indent.isChecked() else 0.0)
        self._preview_timer.start()

    def apply_paragraph_style(self, index: int) -> None:
        if 0 <= index < len(PARAGRAPH_STYLES):
            _name, size, bold = PARAGRAPH_STYLES[index]
            self.editor.apply_paragraph_style(size, bold)
            self.size_combo.setCurrentText(f"{size:g}")
            self._preview_timer.start()

    def apply_size_from_combo(self, *args) -> None:
        try:
            size = float(self.size_combo.currentText())
        except ValueError:
            return
        if size < 4:
            return
        self.editor.set_font_size(size)
        self._preview_timer.start()

    def _sync_format_ui(self) -> None:
        if not hasattr(self, "act_bold"):
            return
        fmt = self.editor.currentCharFormat()
        size = fmt.font().pointSizeF()
        if size > 0:
            self.size_combo.setCurrentText(f"{size:g}")
        self.act_bold.blockSignals(True)
        self.act_bold.setChecked(fmt.fontWeight() >= QFont.Weight.Bold)
        self.act_bold.blockSignals(False)
        self.act_italic.blockSignals(True)
        self.act_italic.setChecked(fmt.fontItalic())
        self.act_italic.blockSignals(False)
        self.act_underline.blockSignals(True)
        self.act_underline.setChecked(fmt.fontUnderline())
        self.act_underline.blockSignals(False)

    # ---------- 插入 ----------

    def insert_table(self) -> None:
        dlg = TableDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            rows, cols = dlg.values()
            self.editor.insert_table(rows, cols)
            self._preview_timer.start()

    def insert_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "插入图片", "", "图片 (*.png *.jpg *.jpeg *.bmp *.gif *.webp)"
        )
        if path:
            self.editor.insert_image_file(path)
            self._preview_timer.start()

    # ---------- 文件 ----------

    def _maybe_save(self) -> bool:
        if not self._dirty:
            return True
        box = QMessageBox(self)
        box.setWindowTitle("保存更改")
        box.setText("当前文档有未保存的更改，要先保存吗？")
        box.setStandardButtons(
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel
        )
        box.setDefaultButton(QMessageBox.StandardButton.Save)
        ret = box.exec()
        if ret == QMessageBox.StandardButton.Save:
            return self.save_project()
        if ret == QMessageBox.StandardButton.Cancel:
            return False
        return True

    def new_document(self) -> None:
        if not self._maybe_save():
            return
        self.editor.clear()
        self.editor.document().setModified(False)
        self.current_path = None
        self._set_dirty(False)
        self._update_word_count()
        self._refresh_preview()

    def open_project(self) -> None:
        if not self._maybe_save():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "打开项目", "", f"手写项目 (*{PROJECT_SUFFIX});;所有文件 (*)"
        )
        if not path:
            return
        try:
            html, style = load_project(path)
        except Exception as e:
            QMessageBox.critical(self, "打开失败", f"{e}")
            return
        self.style = style
        self.editor.load_html(html)
        self.editor.document().setModified(False)
        self.current_path = path
        self._set_dirty(False)
        self._sync_style_controls()
        self._sync_format_ui()
        self._update_word_count()
        self._refresh_preview()
        self.statusBar().showMessage(f"已打开 {path}", 4000)

    def save_project(self) -> bool:
        if not self.current_path:
            return self.save_project_as()
        try:
            save_project(self.current_path, self.editor.content_html(), self.style)
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"{e}")
            return False
        self._set_dirty(False)
        self.statusBar().showMessage(f"已保存 {self.current_path}", 3000)
        return True

    def save_project_as(self) -> bool:
        path, _ = QFileDialog.getSaveFileName(
            self, "保存项目", "手写稿" + PROJECT_SUFFIX, f"手写项目 (*{PROJECT_SUFFIX})"
        )
        if not path:
            return False
        if not path.lower().endswith(PROJECT_SUFFIX):
            path += PROJECT_SUFFIX
        self.current_path = path
        return self.save_project()

    def import_word(self) -> None:
        if not self._maybe_save():
            return
        path, _ = QFileDialog.getOpenFileName(self, "导入 Word 文档", "", "Word 文档 (*.docx)")
        if not path:
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            html, messages = import_docx(path)
        except Exception as e:
            QMessageBox.critical(self, "导入失败", f"{e}\n\n{traceback.format_exc(limit=2)}")
            return
        finally:
            QApplication.restoreOverrideCursor()
        if not html.strip():
            QMessageBox.information(self, "导入结果", "这个文档里没有可导入的内容。")
            return
        self.editor.setHtml(html)
        self.editor.document().setModified(False)
        self.current_path = None
        self._set_dirty(True)
        self._update_word_count()
        self._refresh_preview()
        msg = f"已导入 {Path(path).name}"
        if messages:
            msg += f"，{len(messages)} 条提示（复杂版式可能未完全还原）"
        self.statusBar().showMessage(msg, 6000)

    def _make_renderer(self):
        return make_renderer(self.editor.content_html(), self.style)

    def export_png(self) -> None:
        ensure_output_dirs()
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        directory = OUTPUT_PNG_DIR / stamp
        suffix = 2
        while directory.exists():
            directory = OUTPUT_PNG_DIR / f"{stamp}_{suffix}"
            suffix += 1
        directory.mkdir(parents=True)
        dpi = int(getattr(self.style, "export_dpi", 900))
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        dialog = None
        cancelled = False
        try:
            renderer = self._make_renderer()
            dialog = QProgressDialog(
                "正在导出 PNG…", "取消", 0, max(1, renderer.page_count()), self
            )
            dialog.setWindowTitle(f"导出 PNG（{dpi} dpi）")
            dialog.setWindowModality(Qt.WindowModality.WindowModal)
            dialog.setMinimumDuration(0)
            dialog.setValue(0)

            def progress(done: int, total: int) -> bool:
                nonlocal cancelled
                dialog.setMaximum(total)
                dialog.setValue(done)
                QApplication.processEvents()
                if dialog.wasCanceled():
                    cancelled = True
                    return False
                return True

            paths = export_pngs(
                renderer,
                str(directory),
                dpi=dpi,
                progress=progress,
                numbered=True,
                start_index=0,
            )
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"{e}")
            return
        finally:
            if dialog is not None:
                dialog.close()
            QApplication.restoreOverrideCursor()
        if cancelled:
            self.statusBar().showMessage(f"已取消导出（已完成 {len(paths)} 页）", 6000)
            return
        self.statusBar().showMessage(f"已导出 {len(paths)} 张 PNG（{dpi} dpi）到 {directory}", 6000)
        QMessageBox.information(
            self, "导出完成", f"已导出 {len(paths)} 张 PNG（{dpi} dpi）：\n{directory}"
        )

    def export_pdf(self) -> None:
        ensure_output_dirs()
        prefix = Path(self.current_path).stem if self.current_path else "手写稿"
        default = str(OUTPUT_PDF_DIR / f"{prefix}.pdf")
        path, _ = QFileDialog.getSaveFileName(self, "导出 PDF", default, "PDF (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            renderer = self._make_renderer()
            export_pdf(renderer, path, dpi=200)
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"{e}")
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.statusBar().showMessage(f"已导出 {path}", 6000)
        QMessageBox.information(self, "导出完成", f"PDF 已保存到：\n{path}")

    # ---------- 杂项 ----------

    def open_output_folder(self) -> None:
        ensure_output_dirs()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(OUTPUT_ROOT)))

    def show_help(self) -> None:
        QMessageBox.information(
            self,
            "使用说明",
            "1. 在左边像普通文档一样写，右边实时显示手写效果。\n"
            "2. 工具栏可以设标题、字号、加粗、对齐、首行缩进。\n"
            "3. 「表格」菜单能插入表格、加行加列、删行删列。\n"
            "4. 图片可以直接粘贴或拖进编辑区。\n"
            "5. 「导入 Word」支持 .docx；复杂版式（浮动图、文本框、分栏）可能还原不全。\n"
            "6. 右上角「手写设置」换字体、纸张、背景、行距、字间距、抖动强度。\n"
            "7. 导出 PNG 会自动在「导出\\PNG」下按日期时间建子文件夹，里面从 0.png 开始编号；\n"
            "8. 导出 PDF 默认保存到「导出\\PDF」；「文件 → 打开输出文件夹」可直接打开默认位置。",
        )

    def _on_modified(self, modified: bool) -> None:
        if modified:
            self._set_dirty(True)

    def _set_dirty(self, dirty: bool) -> None:
        self._dirty = dirty
        name = Path(self.current_path).name if self.current_path else "未命名"
        star = " *" if dirty else ""
        from .watermark import watermark_lines

        _a, _b, _c = watermark_lines()
        self.setWindowTitle(
            f"{name}{star} — HandWriteStudio v{__version__}　{_a} · {_b} · {_c}"
        )

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._maybe_save():
            event.accept()
        else:
            event.ignore()
