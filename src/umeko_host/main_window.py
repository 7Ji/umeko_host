from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStyle,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .i18n import detect_language, palette_label, set_language, tr
from .palettes import PALETTE_NAMES, orient
from .photo_dialog import PhotoDialog
from .protocol import FrameFormat, ThermalFrame
from .serial_io import ConnectionState, PortInfo, SerialSession, available_ports
from .thermal_canvas import ThermalCanvas


class MainWindow(QMainWindow):
    session_state = Signal(object, str)
    frame_available = Signal()
    photo_response = Signal(str, object, object)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(tr("Umeko Thermal Imaging"))
        self.resize(1120, 720)
        self.setMinimumSize(880, 580)
        self._ports: list[PortInfo] = []
        self._frame: ThermalFrame | None = None
        self._displayed_matrix: np.ndarray | None = None
        self._last_sequence = -1
        self._last_format: FrameFormat | None = None
        self._paused = False
        self._language_mode = "system"
        self._connection_state = ConnectionState.DISCONNECTED
        self._connection_detail = ""
        self._photo_dialog: PhotoDialog | None = None
        self._session = SerialSession(
            self.session_state.emit, self.frame_available.emit, self.photo_response.emit
        )

        self._build_toolbar()
        self._build_content()
        self._build_status_bar()
        self.session_state.connect(self._on_session_state)
        self.frame_available.connect(self._consume_latest_frame)
        self.refresh_ports()

    def _standard_icon(self, icon: QStyle.StandardPixmap) -> QIcon:
        return self.style().standardIcon(icon)

    def _populate_language_combo(self) -> None:
        self.language_combo.blockSignals(True)
        self.language_combo.clear()
        for label, mode in (
            (tr("Follow system"), "system"),
            ("English", "en"),
            (tr("Simplified Chinese"), "zh_CN"),
        ):
            self.language_combo.addItem(label, mode)
        self.language_combo.setCurrentIndex(self.language_combo.findData(self._language_mode))
        self.language_combo.blockSignals(False)

    @Slot(int)
    def _change_language(self, index: int) -> None:
        mode = self.language_combo.itemData(index)
        if mode not in ("system", "en", "zh_CN"):
            return
        self._language_mode = mode
        set_language(detect_language() if mode == "system" else mode)
        if self._photo_dialog is not None:
            self._photo_dialog.close()
            self._photo_dialog.deleteLater()
            self._photo_dialog = None
        self._retranslate_ui()

    def _retranslate_ui(self) -> None:
        self.setWindowTitle(tr("Umeko Thermal Imaging"))
        self.device_toolbar.setWindowTitle(tr("Device"))
        self.port_heading.setText(f"  {tr('Serial port')}  ")
        self.refresh_action.setText(tr("Refresh"))
        self.refresh_action.setToolTip(tr("Refresh serial port list"))
        self.connect_action.setToolTip(tr("Connect or disconnect the thermal camera"))
        self.pause_action.setToolTip(
            tr("Freeze or resume the image while continuing to receive data")
        )
        self.photos_action.setText(tr("Device photos"))
        self.photos_action.setToolTip(tr("Browse and export photos stored on the camera"))
        self.language_heading.setText(f"  {tr('Language')}  ")
        self._populate_language_combo()

        self.temperature_group.setTitle(tr("Temperature"))
        self.display_group.setTitle(tr("Display"))
        self.export_group.setTitle(tr("Export"))
        self.auto_range.setText(tr("Automatic range"))
        self.horizontal_flip.setText(tr("Flip horizontally"))
        self.vertical_flip.setText(tr("Flip vertically"))
        for field, text in (
            (self.palette_combo, "Palette"),
            (self.interpolation_combo, "Interpolation"),
            (self.range_min, "Lower limit °C"),
            (self.range_max, "Upper limit °C"),
        ):
            label = self.display_form.labelForField(field)
            if label is not None:
                label.setText(tr(text))
        # The rotation row is not exposed by QAction ownership; locate its form label by row.
        label_item = self.display_form.itemAt(7, QFormLayout.ItemRole.LabelRole)
        if label_item is not None and label_item.widget() is not None:
            label_item.widget().setText(tr("Rotation"))

        palette = self.palette_combo.currentData()
        self.palette_combo.blockSignals(True)
        for index in range(self.palette_combo.count()):
            self.palette_combo.setItemText(index, palette_label(self.palette_combo.itemData(index)))
        self.palette_combo.setCurrentIndex(self.palette_combo.findData(palette))
        self.palette_combo.blockSignals(False)
        interpolation = self.interpolation_combo.currentIndex()
        self.interpolation_combo.setItemText(0, tr("Bilinear"))
        self.interpolation_combo.setItemText(1, tr("Nearest neighbor"))
        self.interpolation_combo.setCurrentIndex(interpolation)

        self._on_session_state(self._connection_state, self._connection_detail)
        if not self._ports and not self._session.running:
            self.connection_label.setText(tr("No serial ports found"))
        if self._displayed_matrix is not None:
            self._update_statistics(self._displayed_matrix)
        else:
            self.maximum_label.setText(tr("Maximum: {value}", value="-- °C"))
            self.minimum_label.setText(tr("Minimum: {value}", value="-- °C"))
            self.average_label.setText(tr("Average: {value}", value="-- °C"))
            self.center_label.setText(tr("Center: {value}", value="-- °C"))
        self.probe_label.setText(tr("Mouse position: {value}", value="--"))
        if self._frame is None:
            self.protocol_label.setText(tr("Protocol: {value}", value="--"))
            self.frame_label.setText(tr("Frame: {value}", value="--"))
        else:
            self.protocol_label.setText(
                tr(
                    "Protocol: {value}",
                    value=f"{self._frame.format.value} · {self._frame.width}×{self._frame.height}",
                )
            )
            self.frame_label.setText(tr("Frame: {value}", value=self._frame.sequence))
        self.canvas.update()

    def _build_toolbar(self) -> None:
        toolbar = QToolBar(tr("Device"))
        self.device_toolbar = toolbar
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(toolbar)

        self.port_heading = QLabel(f"  {tr('Serial port')}  ")
        toolbar.addWidget(self.port_heading)
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(390)
        self.port_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        toolbar.addWidget(self.port_combo)

        self.refresh_action = QAction(
            self._standard_icon(QStyle.StandardPixmap.SP_BrowserReload), tr("Refresh"), self
        )
        self.refresh_action.setToolTip(tr("Refresh serial port list"))
        self.refresh_action.triggered.connect(self.refresh_ports)
        toolbar.addAction(self.refresh_action)

        self.connect_action = QAction(
            self._standard_icon(QStyle.StandardPixmap.SP_DialogYesButton), tr("Connect"), self
        )
        self.connect_action.setToolTip(tr("Connect or disconnect the thermal camera"))
        self.connect_action.triggered.connect(self.toggle_connection)
        toolbar.addAction(self.connect_action)

        toolbar.addSeparator()
        self.pause_action = QAction(
            self._standard_icon(QStyle.StandardPixmap.SP_MediaPause), tr("Pause"), self
        )
        self.pause_action.setCheckable(True)
        self.pause_action.setEnabled(False)
        self.pause_action.setToolTip(tr("Freeze or resume the image while continuing to receive data"))
        self.pause_action.toggled.connect(self._set_paused)
        toolbar.addAction(self.pause_action)

        toolbar.addSeparator()
        self.photos_action = QAction(
            self._standard_icon(QStyle.StandardPixmap.SP_DirIcon), tr("Device photos"), self
        )
        self.photos_action.setToolTip(tr("Browse and export photos stored on the camera"))
        self.photos_action.setEnabled(False)
        self.photos_action.triggered.connect(self.open_photos)
        toolbar.addAction(self.photos_action)

        toolbar.addSeparator()
        self.language_heading = QLabel(f"  {tr('Language')}  ")
        toolbar.addWidget(self.language_heading)
        self.language_combo = QComboBox()
        self._populate_language_combo()
        self.language_combo.currentIndexChanged.connect(self._change_language)
        toolbar.addWidget(self.language_combo)

    def _build_content(self) -> None:
        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        self.canvas = ThermalCanvas()
        self.canvas.probe_changed.connect(self._show_probe)
        self.canvas.probe_left.connect(lambda: self.probe_label.setText(tr("Mouse position: {value}", value="--")))
        layout.addWidget(self.canvas, 1)

        panel = QWidget()
        panel.setFixedWidth(250)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(10)

        self.temperature_group = QGroupBox(tr("Temperature"))
        temperature_layout = QVBoxLayout(self.temperature_group)
        self.maximum_label = QLabel(tr("Maximum: {value}", value="-- °C"))
        self.minimum_label = QLabel(tr("Minimum: {value}", value="-- °C"))
        self.average_label = QLabel(tr("Average: {value}", value="-- °C"))
        self.center_label = QLabel(tr("Center: {value}", value="-- °C"))
        self.probe_label = QLabel(tr("Mouse position: {value}", value="--"))
        for label in (
            self.maximum_label,
            self.minimum_label,
            self.average_label,
            self.center_label,
            self.probe_label,
        ):
            temperature_layout.addWidget(label)
        panel_layout.addWidget(self.temperature_group)

        self.display_group = QGroupBox(tr("Display"))
        self.display_form = QFormLayout(self.display_group)
        self.palette_combo = QComboBox()
        for palette in PALETTE_NAMES:
            self.palette_combo.addItem(palette_label(palette), palette)
        self.palette_combo.currentTextChanged.connect(self._rerender)
        self.display_form.addRow(tr("Palette"), self.palette_combo)

        self.interpolation_combo = QComboBox()
        self.interpolation_combo.addItems((tr("Bilinear"), tr("Nearest neighbor")))
        self.interpolation_combo.currentIndexChanged.connect(
            lambda index: self.canvas.set_smooth(index == 0)
        )
        self.display_form.addRow(tr("Interpolation"), self.interpolation_combo)

        self.auto_range = QCheckBox(tr("Automatic range"))
        self.auto_range.setChecked(True)
        self.auto_range.toggled.connect(self._range_mode_changed)
        self.display_form.addRow(self.auto_range)
        self.range_min = self._temperature_spin(-100.0, 1000.0, 20.0)
        self.range_max = self._temperature_spin(-100.0, 1000.0, 50.0)
        self.range_min.setEnabled(False)
        self.range_max.setEnabled(False)
        self.range_min.valueChanged.connect(self._rerender)
        self.range_max.valueChanged.connect(self._rerender)
        self.display_form.addRow(tr("Lower limit °C"), self.range_min)
        self.display_form.addRow(tr("Upper limit °C"), self.range_max)

        self.horizontal_flip = QCheckBox(tr("Flip horizontally"))
        self.vertical_flip = QCheckBox(tr("Flip vertically"))
        self.horizontal_flip.toggled.connect(self._rerender)
        self.vertical_flip.toggled.connect(self._rerender)
        self.display_form.addRow(self.horizontal_flip)
        self.display_form.addRow(self.vertical_flip)

        rotation_row = QWidget()
        rotation_layout = QHBoxLayout(rotation_row)
        rotation_layout.setContentsMargins(0, 0, 0, 0)
        self.rotation_actions = QActionGroup(self)
        self.rotation_actions.setExclusive(True)
        for angle in (0, 90, 180, 270):
            action = QAction(f"{angle}°", self, checkable=True)
            action.setData(angle)
            action.setChecked(angle == 0)
            action.triggered.connect(self._rerender)
            self.rotation_actions.addAction(action)
            button = QPushButton(action.text())
            button.setCheckable(True)
            button.setChecked(action.isChecked())
            button.clicked.connect(action.trigger)
            action.toggled.connect(button.setChecked)
            rotation_layout.addWidget(button)
        self.display_form.addRow(tr("Rotation"), rotation_row)
        panel_layout.addWidget(self.display_group)

        self.export_group = QGroupBox(tr("Export"))
        export_layout = QHBoxLayout(self.export_group)
        self.save_png_button = QPushButton(
            self._standard_icon(QStyle.StandardPixmap.SP_DialogSaveButton), "PNG"
        )
        self.save_csv_button = QPushButton(
            self._standard_icon(QStyle.StandardPixmap.SP_DialogSaveButton), "CSV"
        )
        self.save_png_button.clicked.connect(self.save_png)
        self.save_csv_button.clicked.connect(self.save_csv)
        self.save_png_button.setEnabled(False)
        self.save_csv_button.setEnabled(False)
        export_layout.addWidget(self.save_png_button)
        export_layout.addWidget(self.save_csv_button)
        panel_layout.addWidget(self.export_group)
        panel_layout.addStretch(1)
        layout.addWidget(panel)
        self.setCentralWidget(root)

    def _build_status_bar(self) -> None:
        self.connection_label = QLabel(tr("Not connected"))
        self.protocol_label = QLabel(tr("Protocol: {value}", value="--"))
        self.frame_label = QLabel(tr("Frame: {value}", value="--"))
        self.statusBar().addWidget(self.connection_label, 1)
        self.statusBar().addPermanentWidget(self.protocol_label)
        self.statusBar().addPermanentWidget(self.frame_label)

    @staticmethod
    def _temperature_spin(minimum: float, maximum: float, value: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(1)
        spin.setValue(value)
        return spin

    @Slot()
    def refresh_ports(self) -> None:
        selected = self.port_combo.currentData()
        self._ports = available_ports()
        self.port_combo.clear()
        for port in self._ports:
            self.port_combo.addItem(port.label, port.device)
        if selected:
            index = self.port_combo.findData(selected)
            if index >= 0:
                self.port_combo.setCurrentIndex(index)
        self.connect_action.setEnabled(bool(self._ports) or self._session.running)
        if not self._ports and not self._session.running:
            self.connection_label.setText(tr("No serial ports found"))

    @Slot()
    def toggle_connection(self) -> None:
        if self._session.running:
            self.connect_action.setEnabled(False)
            self._session.stop()
            return
        port = self.port_combo.currentData()
        if not port:
            QMessageBox.warning(self, tr("Unable to connect"), tr("Select a serial port."))
            return
        self.connect_action.setEnabled(False)
        self._session.start(str(port))

    @Slot(object, str)
    def _on_session_state(self, state: ConnectionState, detail: str) -> None:
        self._connection_state = state
        self._connection_detail = detail
        self.connection_label.setText(f"{tr(state.value)}{': ' + detail if detail else ''}")
        active = state in (ConnectionState.CONNECTING, ConnectionState.STREAMING)
        self.connect_action.setEnabled(True)
        self.connect_action.setText(tr("Disconnect") if active else tr("Connect"))
        self.connect_action.setIcon(
            self._standard_icon(
                QStyle.StandardPixmap.SP_DialogCancelButton
                if active
                else QStyle.StandardPixmap.SP_DialogYesButton
            )
        )
        self.pause_action.setEnabled(state is ConnectionState.STREAMING)
        self.photos_action.setEnabled(state is ConnectionState.STREAMING)
        if state in (ConnectionState.DISCONNECTED, ConnectionState.ERROR):
            self.pause_action.setChecked(False)
        if state is ConnectionState.ERROR:
            self.statusBar().showMessage(detail, 8000)

    @Slot()
    def open_photos(self) -> None:
        if not self._session.running:
            QMessageBox.warning(self, tr("Device not connected"), tr("Connect the camera first."))
            return
        if self._photo_dialog is None:
            self._photo_dialog = PhotoDialog(self._session, self.photo_response, self)
        self._photo_dialog.show()
        self._photo_dialog.raise_()
        self._photo_dialog.activateWindow()
        self._photo_dialog.refresh()

    @Slot()
    def _consume_latest_frame(self) -> None:
        if self._paused:
            return
        frame = self._session.latest_frame()
        if frame is None or frame.sequence == self._last_sequence:
            return
        self._frame = frame
        self._last_sequence = frame.sequence
        if frame.format is not self._last_format:
            self._last_format = frame.format
            self.horizontal_flip.blockSignals(True)
            self.vertical_flip.blockSignals(True)
            self.horizontal_flip.setChecked(frame.format is FrameFormat.HEIMANN)
            self.vertical_flip.setChecked(frame.format is not FrameFormat.HEIMANN)
            self.horizontal_flip.blockSignals(False)
            self.vertical_flip.blockSignals(False)
        self.protocol_label.setText(tr("Protocol: {value}", value=f"{frame.format.value} · {frame.width}×{frame.height}"))
        self.frame_label.setText(tr("Frame: {value}", value=frame.sequence))
        self._rerender()
        self.save_png_button.setEnabled(True)
        self.save_csv_button.setEnabled(True)

    def _rotation(self) -> int:
        action = self.rotation_actions.checkedAction()
        return int(action.data()) if action else 0

    @Slot()
    def _rerender(self) -> None:
        if self._frame is None:
            return
        matrix = orient(
            self._frame.temperatures,
            self.horizontal_flip.isChecked(),
            self.vertical_flip.isChecked(),
            self._rotation(),
        )
        self._displayed_matrix = matrix
        self._update_statistics(matrix)
        if self.auto_range.isChecked():
            minimum, maximum = float(np.min(matrix)), float(np.max(matrix))
            if maximum - minimum < 5.0:
                center = (minimum + maximum) / 2
                minimum, maximum = center - 2.5, center + 2.5
            self.range_min.blockSignals(True)
            self.range_max.blockSignals(True)
            self.range_min.setValue(minimum)
            self.range_max.setValue(maximum)
            self.range_min.blockSignals(False)
            self.range_max.blockSignals(False)
        else:
            minimum, maximum = self.range_min.value(), self.range_max.value()
            if maximum <= minimum:
                maximum = minimum + 0.1
        self.canvas.set_frame(matrix, minimum, maximum, self.palette_combo.currentData())

    def _update_statistics(self, matrix: np.ndarray) -> None:
        self.maximum_label.setText(tr("Maximum: {value}", value=f"{float(np.max(matrix)):.2f} °C"))
        self.minimum_label.setText(tr("Minimum: {value}", value=f"{float(np.min(matrix)):.2f} °C"))
        self.average_label.setText(tr("Average: {value}", value=f"{float(np.mean(matrix)):.2f} °C"))
        center = matrix[matrix.shape[0] // 2, matrix.shape[1] // 2]
        self.center_label.setText(tr("Center: {value}", value=f"{float(center):.2f} °C"))

    @Slot(bool)
    def _range_mode_changed(self, automatic: bool) -> None:
        self.range_min.setEnabled(not automatic)
        self.range_max.setEnabled(not automatic)
        self._rerender()

    @Slot(bool)
    def _set_paused(self, paused: bool) -> None:
        self._paused = paused
        self.pause_action.setText(tr("Resume") if paused else tr("Pause"))
        self.pause_action.setIcon(
            self._standard_icon(
                QStyle.StandardPixmap.SP_MediaPlay if paused else QStyle.StandardPixmap.SP_MediaPause
            )
        )
        if not paused:
            self._last_sequence = -1
            self._consume_latest_frame()

    @Slot(int, int, float)
    def _show_probe(self, x: int, y: int, temperature: float) -> None:
        self.probe_label.setText(tr("Mouse position: {value}", value=f"({x}, {y}) {temperature:.2f} °C"))

    def _default_filename(self, suffix: str) -> str:
        stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
        return str(Path.home() / f"thermal_{stamp}.{suffix}")

    @Slot()
    def save_png(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(
            self, tr("Save thermal image"), self._default_filename("png"), tr("PNG images (*.png)")
        )
        if filename and not self.canvas.grab().save(filename, "PNG"):
            QMessageBox.critical(self, tr("Save failed"), tr("Unable to write PNG file."))

    @Slot()
    def save_csv(self) -> None:
        if self._displayed_matrix is None:
            return
        filename, _ = QFileDialog.getSaveFileName(
            self, tr("Save temperature matrix"), self._default_filename("csv"), tr("CSV files (*.csv)")
        )
        if not filename:
            return
        try:
            with open(filename, "w", newline="", encoding="utf-8") as output:
                writer = csv.writer(output)
                writer.writerow(["y/x", *range(self._displayed_matrix.shape[1])])
                for row_index, row in enumerate(self._displayed_matrix):
                    writer.writerow([row_index, *(f"{float(value):.4f}" for value in row)])
        except OSError as error:
            QMessageBox.critical(self, tr("Save failed"), str(error))

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self._session.stop()
        event.accept()
