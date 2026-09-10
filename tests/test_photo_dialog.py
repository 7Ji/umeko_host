from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication
import numpy as np

from umeko_host.photo_dialog import PhotoDialog
from umeko_host.photos import PhotoInfo, StoredPhoto


class ResponseEmitter(QObject):
    response = Signal(str, object, object)


class IdleSession:
    running = True

    def request_photo_list(self) -> None:
        pass

    def request_photo_download(self, filename: str) -> None:
        pass


def test_photo_probe_shows_coordinates_and_temperature() -> None:
    application = QApplication.instance() or QApplication([])
    emitter = ResponseEmitter()
    dialog = PhotoDialog(IdleSession(), emitter.response)
    matrix = np.linspace(20, 40, 768, dtype=np.float32).reshape(24, 32)
    photo = StoredPhoto(
        info=PhotoInfo(0, "photo_0.dat", 3080),
        raw=b"\0" * 3080,
        temperatures=matrix,
        reported_max=40.0,
        reported_min=20.0,
    )
    dialog._show_photo(photo)
    application.processEvents()

    dialog.canvas.probe_changed.emit(7, 8, 31.234)
    assert dialog.probe_label.text() == "Mouse position: (7, 8) 31.23 °C"
    dialog.canvas.probe_left.emit()
    assert dialog.probe_label.text() == "Mouse position: --"
    dialog.close()
