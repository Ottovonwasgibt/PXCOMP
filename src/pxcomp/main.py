from __future__ import annotations

import multiprocessing
import sys
from PySide6 import QtWidgets

from pxcomp.ui import MainWindow


def main() -> int:
    multiprocessing.freeze_support()
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("PXCOMP")
    app.setOrganizationName("PXCOMP")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
