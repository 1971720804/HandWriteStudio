"""图片尺寸与裁剪对话框。"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class ImageSizeDialog(QDialog):
    """按像素修改编辑区里图片的显示宽高。"""

    def __init__(self, width: float, height: float, parent=None):
        super().__init__(parent)
        self.setWindowTitle("修改图片大小")
        self.setModal(True)
        self._ratio = width / height if height else 1.0

        self.width_spin = QSpinBox()
        self.width_spin.setRange(10, 6000)
        self.width_spin.setValue(max(10, round(width)))
        self.width_spin.setSuffix(" px")
        self.height_spin = QSpinBox()
        self.height_spin.setRange(10, 6000)
        self.height_spin.setValue(max(10, round(height)))
        self.height_spin.setSuffix(" px")

        self.lock_box = QCheckBox("保持宽高比")
        self.lock_box.setChecked(True)

        form = QHBoxLayout()
        form.addWidget(QLabel("宽"))
        form.addWidget(self.width_spin)
        form.addSpacing(10)
        form.addWidget(QLabel("高"))
        form.addWidget(self.height_spin)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.lock_box)
        layout.addWidget(buttons)

        self._syncing = False
        self.width_spin.valueChanged.connect(self._width_changed)
        self.height_spin.valueChanged.connect(self._height_changed)

    def _width_changed(self, value: int) -> None:
        if self._syncing or not self.lock_box.isChecked():
            return
        self._syncing = True
        self.height_spin.setValue(max(10, round(value / self._ratio)))
        self._syncing = False

    def _height_changed(self, value: int) -> None:
        if self._syncing or not self.lock_box.isChecked():
            return
        self._syncing = True
        self.width_spin.setValue(max(10, round(value * self._ratio)))
        self._syncing = False

    def image_size(self) -> tuple[float, float]:
        return float(self.width_spin.value()), float(self.height_spin.value())


class _CropCanvas(QWidget):
    def __init__(self, image: QImage, parent=None):
        super().__init__(parent)
        self.image = image
        max_w, max_h = 560, 460
        self.display = image.scaled(
            max_w,
            max_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setFixedSize(self.display.size())
        self.selection = QRect(0, 0, self.display.width(), self.display.height())
        self._origin = QPoint()
        self._dragging = False

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.drawImage(0, 0, self.display)
        sel = self.selection.normalized().intersected(self.rect())
        if sel.isNull():
            return
        shade = QColor(0, 0, 0, 100)
        painter.fillRect(QRect(0, 0, self.width(), sel.top()), shade)
        painter.fillRect(QRect(0, sel.bottom() + 1, self.width(), self.height() - sel.bottom() - 1), shade)
        painter.fillRect(QRect(0, sel.top(), sel.left(), sel.height()), shade)
        painter.fillRect(QRect(sel.right() + 1, sel.top(), self.width() - sel.right() - 1, sel.height()), shade)
        painter.setPen(QPen(QColor("#2f7bdc"), 2, Qt.PenStyle.DashLine))
        painter.drawRect(sel.adjusted(0, 0, -1, -1))

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._origin = event.position().toPoint()
            self.selection = QRect(self._origin, self._origin)
            self._dragging = True
            self.update()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._dragging:
            self.selection = QRect(self._origin, event.position().toPoint()).normalized()
            self.selection = self.selection.intersected(self.rect())
            self.update()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            if self.selection.width() < 4 or self.selection.height() < 4:
                self.selection = QRect(0, 0, self.display.width(), self.display.height())
            self.update()
        else:
            super().mouseReleaseEvent(event)

    def crop_image(self) -> QImage:
        sel = self.selection.normalized().intersected(self.rect())
        if sel.width() < 4 or sel.height() < 4:
            sel = QRect(0, 0, self.display.width(), self.display.height())
        sx = self.image.width() / self.display.width()
        sy = self.image.height() / self.display.height()
        source = QRect(
            int(sel.left() * sx),
            int(sel.top() * sy),
            max(1, int(sel.width() * sx)),
            max(1, int(sel.height() * sy)),
        ).intersected(QRect(0, 0, self.image.width(), self.image.height()))
        return self.image.copy(source)


class CropDialog(QDialog):
    def __init__(self, image: QImage, parent=None):
        super().__init__(parent)
        self.setWindowTitle("裁剪图片")
        self.setModal(True)
        self.canvas = _CropCanvas(image, self)
        tip = QLabel("拖动框选要保留的区域，框外会被裁掉。")
        tip.setStyleSheet("color:#707784;")
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(self.canvas)
        layout.addWidget(tip)
        layout.addWidget(buttons)
        self.resize(self.canvas.width() + 40, self.canvas.height() + 110)

    def crop_image(self) -> QImage:
        return self.canvas.crop_image()
