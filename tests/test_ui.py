from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets

from pxcomp.ui import MainWindow


def test_main_window_constructs_and_exposes_refined_workflow():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = MainWindow()
    try:
        assert window.source_list is not None
        assert window.generate_button.text() == "GENERATE COMPOSITE"
        assert window.export_combo.count() == 5
        assert window.view_badge.text() == "EMPTY"
        assert window.source_summary.text() == "No photographs loaded"
        assert window.generate_button.isEnabled() is False
    finally:
        window.close()
        app.processEvents()


def test_aspect_ratio_preset_updates_canvas_once():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = MainWindow()
    try:
        window.width_spin.setValue(1600)
        index = window.ratio_combo.findText("Screen 16:9")
        window.ratio_combo.setCurrentIndex(index)
        assert window.height_spin.value() == 900
        assert window.ratio_combo.currentIndex() == 0
    finally:
        window.close()
        app.processEvents()
