from __future__ import annotations

from collections import deque
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QImage
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from .i18n import palette_label, tr
from .palettes import PALETTE_NAMES, colorize
from .photos import PhotoInfo, StoredPhoto, parse_photo_catalog, parse_photo_download, write_photo_csv
from .serial_io import SerialSession
from .thermal_canvas import ThermalCanvas


class PhotoDialog(QDialog):
    def __init__(self, session: SerialSession, response_signal: Signal, parent=None) -> None:
        super().__init__(parent)
        self._session = session
        self._photos: list[PhotoInfo] = []
        self._cache: dict[str, StoredPhoto] = {}
        self._current: StoredPhoto | None = None
        self._batch_queue: deque[PhotoInfo] = deque()
        self._batch_directory: Path | None = None
        self._batch_total = 0
        response_signal.connect(self._handle_response)

        self.setWindowTitle(tr("Device photos"))
        self.resize(1050, 680)
        self.setMinimumSize(820, 520)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        left = QWidget()
        left.setFixedWidth(210)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        heading = QLabel(tr("Photos on camera"))
        heading.setStyleSheet("font-weight: 600")
        left_layout.addWidget(heading)
        self.photo_list = QListWidget()
        self.photo_list.currentItemChanged.connect(self._selection_changed)
        left_layout.addWidget(self.photo_list, 1)
        self.refresh_button = QPushButton(
            self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload), tr("Refresh list")
        )
        self.refresh_button.clicked.connect(self.refresh)
        left_layout.addWidget(self.refresh_button)
        layout.addWidget(left)

        self.canvas = ThermalCanvas()
        self.canvas.setMinimumSize(430, 360)
        self.canvas.probe_changed.connect(self._show_probe)
        self.canvas.probe_left.connect(self._clear_probe)
        layout.addWidget(self.canvas, 1)

        right = QWidget()
        right.setFixedWidth(225)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)

        info_group = QGroupBox(tr("Photo information"))
        info_layout = QVBoxLayout(info_group)
        self.filename_label = QLabel(tr("File: {value}", value="--"))
        self.range_label = QLabel(tr("Range: {value}", value="-- °C"))
        self.average_label = QLabel(tr("Average: {value}", value="-- °C"))
        self.reported_label = QLabel(tr("Device values: {value}", value="-- °C"))
        self.probe_label = QLabel(tr("Mouse position: {value}", value="--"))
        self.reported_label.setWordWrap(True)
        for label in (
            self.filename_label,
            self.range_label,
            self.average_label,
            self.reported_label,
            self.probe_label,
        ):
            info_layout.addWidget(label)
        right_layout.addWidget(info_group)

        display_group = QGroupBox(tr("Display"))
        display_layout = QVBoxLayout(display_group)
        self.palette_combo = QComboBox()
        for palette in PALETTE_NAMES:
            self.palette_combo.addItem(palette_label(palette), palette)
        self.palette_combo.currentTextChanged.connect(self._render_current)
        display_layout.addWidget(self.palette_combo)
        right_layout.addWidget(display_group)

        export_group = QGroupBox(tr("Export current photo"))
        export_layout = QVBoxLayout(export_group)
        self.raw_button = QPushButton(tr("Raw DAT"))
        self.csv_button = QPushButton(tr("Temperature CSV"))
        self.png_button = QPushButton(tr("Thermal image PNG"))
        self.raw_button.clicked.connect(self.export_raw)
        self.csv_button.clicked.connect(self.export_csv)
        self.png_button.clicked.connect(self.export_png)
        for button in (self.raw_button, self.csv_button, self.png_button):
            button.setEnabled(False)
            export_layout.addWidget(button)
        right_layout.addWidget(export_group)

        self.batch_button = QPushButton(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon), tr("Export all")
        )
        self.batch_button.setEnabled(False)
        self.batch_button.clicked.connect(self.export_all)
        right_layout.addWidget(self.batch_button)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        right_layout.addWidget(self.progress)
        self.status_label = QLabel(tr("Click refresh to read the device list"))
        self.status_label.setWordWrap(True)
        right_layout.addWidget(self.status_label)
        right_layout.addStretch(1)
        layout.addWidget(right)

    @Slot()
    def refresh(self) -> None:
        if not self._session.running:
            QMessageBox.warning(self, tr("Device not connected"), tr("Connect the camera in the main window first."))
            return
        self.refresh_button.setEnabled(False)
        self.batch_button.setEnabled(False)
        self.status_label.setText(tr("Reading photo list..."))
        self._session.request_photo_list()

    @Slot(object, object)
    def _selection_changed(self, current: QListWidgetItem | None, previous) -> None:
        if current is None:
            return
        info: PhotoInfo = current.data(Qt.ItemDataRole.UserRole)
        cached = self._cache.get(info.filename)
        if cached is not None:
            self._show_photo(cached)
            return
        self.status_label.setText(tr("Downloading {filename}...", filename=info.filename))
        self.photo_list.setEnabled(False)
        self.batch_button.setEnabled(False)
        self._session.request_photo_download(info.filename)

    @Slot(str, object, object)
    def _handle_response(self, kind: str, response: bytes | None, error: str | None) -> None:
        if kind == "list":
            self.refresh_button.setEnabled(True)
            if error or response is None:
                self.status_label.setText(tr("Read failed: {error}", error=error))
                return
            try:
                self._photos = parse_photo_catalog(response)
            except ValueError as parse_error:
                self.status_label.setText(str(parse_error))
                return
            self.photo_list.clear()
            self._cache.clear()
            self._current = None
            self.canvas.clear_frame()
            self._clear_probe()
            for button in (self.raw_button, self.csv_button, self.png_button):
                button.setEnabled(False)
            for info in self._photos:
                item = QListWidgetItem(f"{info.index + 1:02d}  {info.filename}")
                item.setData(Qt.ItemDataRole.UserRole, info)
                item.setToolTip(f"{info.size} bytes")
                self.photo_list.addItem(item)
            self.status_label.setText(tr("{count} photos", count=len(self._photos)))
            self.batch_button.setEnabled(bool(self._photos))
            if self._photos:
                self.photo_list.setCurrentRow(0)
            return

        if not kind.startswith("download:"):
            return
        filename = kind.split(":", 1)[1]
        self.photo_list.setEnabled(self._batch_directory is None)
        info = next((item for item in self._photos if item.filename == filename), None)
        if error or response is None or info is None:
            self.status_label.setText(tr("Download of {filename} failed: {error}", filename=filename, error=error or tr("Unknown file")))
            self._cancel_batch()
            return
        try:
            photo = parse_photo_download(info, response)
        except ValueError as parse_error:
            self.status_label.setText(tr("Failed to parse {filename}: {error}", filename=filename, error=parse_error))
            self._cancel_batch()
            return
        self._cache[filename] = photo
        selected = self.photo_list.currentItem()
        if selected is not None and selected.data(Qt.ItemDataRole.UserRole).filename == filename:
            self._show_photo(photo)
        if self._batch_directory is not None:
            try:
                self._export_bundle(photo, self._batch_directory)
            except OSError as export_error:
                self.status_label.setText(tr("Export failed: {error}", error=export_error))
                self._cancel_batch()
            else:
                self._advance_batch()
        else:
            self.status_label.setText(tr("Loaded {filename}", filename=filename))
            self.batch_button.setEnabled(bool(self._photos))

    def _show_photo(self, photo: StoredPhoto) -> None:
        self._current = photo
        self._clear_probe()
        matrix = np.flipud(photo.temperatures)
        minimum, maximum = photo.minimum, photo.maximum
        if maximum - minimum < 5:
            center = (minimum + maximum) / 2
            minimum, maximum = center - 2.5, center + 2.5
        self.canvas.set_frame(matrix, minimum, maximum, self.palette_combo.currentData())
        self.filename_label.setText(tr("File: {value}", value=photo.info.filename))
        self.range_label.setText(tr("Range: {value}", value=f"{photo.minimum:.2f}–{photo.maximum:.2f} °C"))
        self.average_label.setText(tr("Average: {value}", value=f"{photo.average:.2f} °C"))
        self.reported_label.setText(
            tr("Device values: {value}", value=f"{photo.reported_min:.2f}–{photo.reported_max:.2f} °C")
        )
        for button in (self.raw_button, self.csv_button, self.png_button):
            button.setEnabled(True)

    @Slot(int, int, float)
    def _show_probe(self, x: int, y: int, temperature: float) -> None:
        self.probe_label.setText(tr("Mouse position: {value}", value=f"({x}, {y}) {temperature:.2f} °C"))

    @Slot()
    def _clear_probe(self) -> None:
        self.probe_label.setText(tr("Mouse position: {value}", value="--"))

    @Slot()
    def _render_current(self) -> None:
        if self._current is not None:
            self._show_photo(self._current)

    def _save_path(self, title: str, suffix: str, file_filter: str) -> str:
        if self._current is None:
            return ""
        default = str(Path.home() / Path(self._current.info.filename).with_suffix(suffix))
        filename, _ = QFileDialog.getSaveFileName(self, title, default, file_filter)
        return filename

    @Slot()
    def export_raw(self) -> None:
        filename = self._save_path(tr("Save original photo"), ".dat", tr("DAT files (*.dat)"))
        if filename and self._current is not None:
            self._write(lambda: Path(filename).write_bytes(self._current.raw))

    @Slot()
    def export_csv(self) -> None:
        filename = self._save_path(tr("Save temperature matrix"), ".csv", tr("CSV files (*.csv)"))
        if filename and self._current is not None:
            self._write(lambda: write_photo_csv(self._current, filename))

    @Slot()
    def export_png(self) -> None:
        filename = self._save_path(tr("Save thermal image"), ".png", tr("PNG images (*.png)"))
        if filename:
            self._write(lambda: self.canvas.grab().save(filename, "PNG") or self._raise_save())

    def _write(self, operation) -> None:
        try:
            operation()
            self.status_label.setText(tr("Export complete"))
        except OSError as error:
            QMessageBox.critical(self, tr("Export failed"), str(error))

    @staticmethod
    def _raise_save() -> None:
        raise OSError(tr("Unable to write PNG file."))

    @Slot()
    def export_all(self) -> None:
        if not self._photos:
            QMessageBox.information(self, tr("No photos"), tr("Refresh the photo list first."))
            return
        directory = QFileDialog.getExistingDirectory(self, tr("Select export directory"), str(Path.home()))
        if not directory:
            return
        self._batch_directory = Path(directory)
        self._batch_queue = deque(self._photos)
        self._batch_total = len(self._photos)
        self.progress.setRange(0, self._batch_total)
        self.progress.setValue(0)
        self.batch_button.setEnabled(False)
        self.refresh_button.setEnabled(False)
        self.photo_list.setEnabled(False)
        self._advance_batch()

    def _advance_batch(self) -> None:
        if self._batch_directory is None:
            return
        completed = self._batch_total - len(self._batch_queue)
        self.progress.setValue(completed)
        if not self._batch_queue:
            self.status_label.setText(tr("Exported {count} photos", count=self._batch_total))
            self.batch_button.setEnabled(True)
            self.refresh_button.setEnabled(True)
            self.photo_list.setEnabled(True)
            self._batch_directory = None
            return
        info = self._batch_queue.popleft()
        self.status_label.setText(tr("Exporting {filename}...", filename=info.filename))
        cached = self._cache.get(info.filename)
        if cached is not None:
            try:
                self._export_bundle(cached, self._batch_directory)
            except OSError as export_error:
                self.status_label.setText(tr("Export failed: {error}", error=export_error))
                self._cancel_batch()
            else:
                self._advance_batch()
        else:
            self._session.request_photo_download(info.filename)

    def _export_bundle(self, photo: StoredPhoto, directory: Path) -> None:
        stem = Path(photo.info.filename).stem
        (directory / f"{stem}.dat").write_bytes(photo.raw)
        write_photo_csv(photo, directory / f"{stem}.csv")
        matrix = np.flipud(photo.temperatures)
        rgb = np.ascontiguousarray(
            colorize(matrix, photo.minimum, photo.maximum, self.palette_combo.currentData())
        )
        image = QImage(
            rgb.data, rgb.shape[1], rgb.shape[0], rgb.shape[1] * 3, QImage.Format.Format_RGB888
        ).copy()
        image = image.scaled(
            960,
            720,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        if not image.save(str(directory / f"{stem}.png"), "PNG"):
            raise OSError(tr("Unable to export {filename}", filename=f"{stem}.png"))

    def _cancel_batch(self) -> None:
        self._batch_queue.clear()
        self._batch_directory = None
        self.batch_button.setEnabled(bool(self._photos))
        self.refresh_button.setEnabled(True)
        self.photo_list.setEnabled(True)
