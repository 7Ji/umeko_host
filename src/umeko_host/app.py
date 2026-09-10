from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .main_window import MainWindow


def main() -> int:
    application = QApplication(sys.argv)
    application.setApplicationName("Umeko Host")
    application.setOrganizationName("Umeko")
    window = MainWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
