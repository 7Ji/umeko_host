from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .i18n import tr
from .palettes import colorize, make_lut


class ThermalCanvas(QWidget):
    probe_changed = Signal(int, int, float)
    probe_left = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setMinimumSize(480, 360)
        self._temperatures: np.ndarray | None = None
        self._image: QImage | None = None
        self._image_rect = QRectF()
        self._minimum = 0.0
        self._maximum = 1.0
        self._palette = "Iron"
        self._smooth = True

    def set_smooth(self, enabled: bool) -> None:
        self._smooth = enabled
        self.update()

    def set_frame(self, matrix: np.ndarray, minimum: float, maximum: float, palette: str) -> None:
        self._temperatures = np.asarray(matrix, dtype=np.float32)
        self._minimum = minimum
        self._maximum = maximum
        self._palette = palette
        rgb = colorize(self._temperatures, minimum, maximum, palette)
        height, width, _ = rgb.shape
        self._image = QImage(rgb.data, width, height, width * 3, QImage.Format.Format_RGB888).copy()
        self.update()

    def clear_frame(self) -> None:
        self._temperatures = None
        self._image = None
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#151719"))
        if self._image is None or self._temperatures is None:
            painter.setPen(QColor("#b6bcc2"))
            painter.setFont(QFont("Sans Serif", 15))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, tr("Waiting for thermal image data"))
            return

        margin = 18
        scale_width = 72
        available = QRectF(margin, margin, self.width() - scale_width - margin * 3, self.height() - margin * 2)
        ratio = self._image.width() / self._image.height()
        width = available.width()
        height = width / ratio
        if height > available.height():
            height = available.height()
            width = height * ratio
        self._image_rect = QRectF(
            available.x() + (available.width() - width) / 2,
            available.y() + (available.height() - height) / 2,
            width,
            height,
        )
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, self._smooth)
        painter.drawImage(self._image_rect, self._image)
        painter.setPen(QPen(QColor("#6f767d"), 1))
        painter.drawRect(self._image_rect)
        self._draw_extrema(painter)
        self._draw_scale(painter, self._image_rect.right() + 20, self._image_rect.top(), 20, self._image_rect.height())

    def _draw_extrema(self, painter: QPainter) -> None:
        assert self._temperatures is not None
        for index, color, label in (
            (int(np.argmax(self._temperatures)), QColor("#ff3b30"), "H"),
            (int(np.argmin(self._temperatures)), QColor("#42a5ff"), "L"),
        ):
            row, column = np.unravel_index(index, self._temperatures.shape)
            x = self._image_rect.left() + (column + 0.5) * self._image_rect.width() / self._temperatures.shape[1]
            y = self._image_rect.top() + (row + 0.5) * self._image_rect.height() / self._temperatures.shape[0]
            painter.setPen(QPen(color, 2))
            painter.drawEllipse(QPointF(x, y), 7, 7)
            painter.drawText(QPointF(x + 9, y - 7), label)

    def _draw_scale(self, painter: QPainter, x: float, y: float, width: float, height: float) -> None:
        lut = np.ascontiguousarray(np.flipud(make_lut(self._palette).reshape(256, 1, 3)))
        image = QImage(lut.data, 1, 256, 3, QImage.Format.Format_RGB888).copy()
        painter.drawImage(QRectF(x, y, width, height), image)
        painter.setPen(QColor("#e5e8eb"))
        painter.drawText(QPointF(x + width + 6, y + 10), f"{self._maximum:.1f}°")
        painter.drawText(QPointF(x + width + 6, y + height), f"{self._minimum:.1f}°")

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._temperatures is None or not self._image_rect.contains(event.position()):
            self.probe_left.emit()
            return
        x = int((event.position().x() - self._image_rect.left()) / self._image_rect.width() * self._temperatures.shape[1])
        y = int((event.position().y() - self._image_rect.top()) / self._image_rect.height() * self._temperatures.shape[0])
        x = min(max(x, 0), self._temperatures.shape[1] - 1)
        y = min(max(y, 0), self._temperatures.shape[0] - 1)
        self.probe_changed.emit(x, y, float(self._temperatures[y, x]))

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.probe_left.emit()
        super().leaveEvent(event)
