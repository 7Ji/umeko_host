from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import numpy as np
from PySide6.QtWidgets import QApplication

from umeko_host.main_window import MainWindow
from umeko_host.protocol import FrameFormat, ThermalFrame


def test_window_renders_and_exports_a_frame(tmp_path) -> None:
    application = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    frame = ThermalFrame(
        format=FrameFormat.UMEKO_LEGACY,
        width=32,
        height=24,
        temperatures=np.linspace(20, 40, 768, dtype=np.float32).reshape(24, 32),
        reported_max=40,
        reported_min=20,
        reported_avg=30,
        received_at=datetime.now().astimezone(),
        sequence=1,
    )
    window._session._set_latest(frame)
    application.processEvents()
    snapshot = window.grab()
    assert window.protocol_label.text().startswith("Protocol: Umeko MLX90640")
    assert window.maximum_label.text() == "Maximum: 40.00 °C"
    assert window.save_png_button.isEnabled()
    assert not snapshot.isNull()
    png_path = tmp_path / "thermal.png"
    csv_path = tmp_path / "thermal.csv"
    with patch(
        "umeko_host.main_window.QFileDialog.getSaveFileName",
        return_value=(str(png_path), "PNG 图片 (*.png)"),
    ):
        window.save_png()
    with patch(
        "umeko_host.main_window.QFileDialog.getSaveFileName",
        return_value=(str(csv_path), "CSV 文件 (*.csv)"),
    ):
        window.save_csv()
    assert png_path.read_bytes().startswith(b"\x89PNG")
    rows = csv_path.read_text(encoding="utf-8").splitlines()
    assert rows[0].startswith("y/x,0,1,2")
    assert len(rows) == 25
    window.close()


def test_window_language_selector_translates_immediately() -> None:
    application = QApplication.instance() or QApplication([])
    window = MainWindow()
    assert window.language_combo.currentData() == "system"

    window.language_combo.setCurrentIndex(window.language_combo.findData("zh_CN"))
    application.processEvents()
    assert window.windowTitle() == "Umeko 热成像"
    assert window.connect_action.text() == "连接"
    assert window.language_combo.currentData() == "zh_CN"

    window.language_combo.setCurrentIndex(window.language_combo.findData("en"))
    application.processEvents()
    assert window.windowTitle() == "Umeko Thermal Imaging"
    assert window.connect_action.text() == "Connect"
    window.close()
