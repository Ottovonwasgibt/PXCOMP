from __future__ import annotations

from pathlib import Path
import traceback
import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from .alloc import generate_ownership, validate_ownership
from .exports import export_jpeg, export_png, export_psd, export_tiff
from .imaging import supported_file_filter
from .model import Project, SourceSpec, load_project, save_project
from .render import render_preview_composite, render_preview_source


class CanvasView(QtWidgets.QLabel):
    dragged = QtCore.Signal(float, float)

    def __init__(self) -> None:
        super().__init__()
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(520, 420)
        self.setStyleSheet("background:#111; border:1px solid #333;")
        self._last_pos: QtCore.QPointF | None = None
        self._preview_width = 1
        self._preview_height = 1
        self._canvas_width = 1
        self._canvas_height = 1
        self._drag_enabled = True

    def set_drag_enabled(self, enabled: bool) -> None:
        self._drag_enabled = enabled
        self.setCursor(
            QtCore.Qt.CursorShape.OpenHandCursor if enabled else QtCore.Qt.CursorShape.ArrowCursor
        )

    def set_array(self, array: np.ndarray, canvas_width: int, canvas_height: int) -> None:
        array = np.ascontiguousarray(array, dtype=np.uint8)
        height, width = array.shape[:2]
        image = QtGui.QImage(
            array.data, width, height, int(array.strides[0]), QtGui.QImage.Format.Format_RGB888
        ).copy()
        self.setPixmap(QtGui.QPixmap.fromImage(image))
        self._preview_width = width
        self._preview_height = height
        self._canvas_width = max(1, canvas_width)
        self._canvas_height = max(1, canvas_height)

    def clear_image(self) -> None:
        self.clear()
        self.setText("Add photographs to begin")
        self.setStyleSheet("background:#111; color:#777; border:1px solid #333;")

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._drag_enabled and event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._last_pos = event.position()
            self.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._drag_enabled and self._last_pos is not None:
            current = event.position()
            delta = current - self._last_pos
            self._last_pos = current
            dx = delta.x() * self._canvas_width / max(1, self._preview_width)
            dy = delta.y() * self._canvas_height / max(1, self._preview_height)
            self.dragged.emit(dx, dy)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        self._last_pos = None
        if self._drag_enabled:
            self.setCursor(QtCore.Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(event)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.project = Project()
        self.owners: np.ndarray | None = None
        self.active_index = -1
        self.setWindowTitle("PXCOMP — Pixel Layer Compositor")
        self.resize(1450, 900)
        self._build_ui()
        self._load_controls_from_project()
        self.canvas.clear_image()

    def _build_ui(self) -> None:
        central = QtWidgets.QWidget()
        root = QtWidgets.QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        self.setCentralWidget(central)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedWidth(350)
        panel = QtWidgets.QWidget()
        form = QtWidgets.QVBoxLayout(panel)
        form.setContentsMargins(16, 16, 16, 24)
        form.setSpacing(8)
        scroll.setWidget(panel)
        root.addWidget(scroll)

        title = QtWidgets.QLabel("PXCOMP")
        title.setStyleSheet("font-size:22px; font-weight:700;")
        form.addWidget(title)
        subtitle = QtWidgets.QLabel("Every output pixel belongs to exactly one moment.")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color:#888;")
        form.addWidget(subtitle)

        add_button = QtWidgets.QPushButton("Add photographs / RAW files")
        add_button.clicked.connect(self.add_sources)
        form.addWidget(add_button)

        remove_button = QtWidgets.QPushButton("Remove selected")
        remove_button.clicked.connect(self.remove_source)
        form.addWidget(remove_button)

        self.source_list = QtWidgets.QListWidget()
        self.source_list.setMinimumHeight(150)
        self.source_list.currentRowChanged.connect(self.select_source)
        form.addWidget(self.source_list)

        form.addWidget(self._heading("Canvas"))
        dims = QtWidgets.QHBoxLayout()
        self.width_spin = QtWidgets.QSpinBox()
        self.width_spin.setRange(1, 30000)
        self.width_spin.setSuffix(" px W")
        self.height_spin = QtWidgets.QSpinBox()
        self.height_spin.setRange(1, 30000)
        self.height_spin.setSuffix(" px H")
        dims.addWidget(self.width_spin)
        dims.addWidget(self.height_spin)
        form.addLayout(dims)
        self.width_spin.valueChanged.connect(self._allocation_changed)
        self.height_spin.valueChanged.connect(self._allocation_changed)

        form.addWidget(self._heading("Crop active photograph"))
        zoom_row = QtWidgets.QHBoxLayout()
        self.zoom_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(100, 500)
        self.zoom_value = QtWidgets.QLabel("1.00×")
        zoom_row.addWidget(self.zoom_slider)
        zoom_row.addWidget(self.zoom_value)
        form.addLayout(zoom_row)
        self.zoom_slider.valueChanged.connect(self._zoom_changed)
        reset_crop = QtWidgets.QPushButton("Reset active crop")
        reset_crop.clicked.connect(self.reset_crop)
        form.addWidget(reset_crop)
        crop_help = QtWidgets.QLabel("Drag the photograph on the large canvas to reposition it. Cropping is non-destructive.")
        crop_help.setWordWrap(True)
        crop_help.setStyleSheet("color:#777; font-size:11px;")
        form.addWidget(crop_help)

        form.addWidget(self._heading("Allocation"))
        self.mode_combo = QtWidgets.QComboBox()
        self.mode_combo.addItem("Pixel Random", "pixel")
        self.mode_combo.addItem("Organic Territories", "organic")
        self.mode_combo.currentIndexChanged.connect(self._allocation_changed)
        form.addWidget(self.mode_combo)

        territory_row = QtWidgets.QHBoxLayout()
        self.territory_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.territory_slider.setRange(0, 100)
        self.territory_value = QtWidgets.QLabel("55")
        territory_row.addWidget(self.territory_slider)
        territory_row.addWidget(self.territory_value)
        form.addLayout(territory_row)
        self.territory_slider.valueChanged.connect(self._territory_changed)

        seed_row = QtWidgets.QHBoxLayout()
        self.seed_spin = QtWidgets.QSpinBox()
        self.seed_spin.setRange(0, 2147483647)
        self.seed_spin.valueChanged.connect(self._allocation_changed)
        random_seed = QtWidgets.QPushButton("Random seed")
        random_seed.clicked.connect(self.randomize_seed)
        seed_row.addWidget(self.seed_spin)
        seed_row.addWidget(random_seed)
        form.addLayout(seed_row)

        generate = QtWidgets.QPushButton("GENERATE COMPOSITE")
        generate.setMinimumHeight(42)
        generate.setStyleSheet("font-weight:700;")
        generate.clicked.connect(self.generate_composite)
        form.addWidget(generate)

        preview_crop = QtWidgets.QPushButton("Return to crop preview")
        preview_crop.clicked.connect(self.show_active_source)
        form.addWidget(preview_crop)

        form.addWidget(self._heading("Project"))
        project_row = QtWidgets.QHBoxLayout()
        save_button = QtWidgets.QPushButton("Save .pxcomp")
        load_button = QtWidgets.QPushButton("Open .pxcomp")
        save_button.clicked.connect(self.save_project_dialog)
        load_button.clicked.connect(self.load_project_dialog)
        project_row.addWidget(save_button)
        project_row.addWidget(load_button)
        form.addLayout(project_row)

        form.addWidget(self._heading("Export"))
        for label, callback in [
            ("PNG — 8-bit", self.export_png_dialog),
            ("JPEG — 8-bit", self.export_jpeg_dialog),
            ("TIFF — 8-bit", lambda: self.export_tiff_dialog(8)),
            ("TIFF — 16-bit master", lambda: self.export_tiff_dialog(16)),
            ("PSD — editable masked layers", self.export_psd_dialog),
        ]:
            button = QtWidgets.QPushButton(label)
            button.clicked.connect(callback)
            form.addWidget(button)

        self.status = QtWidgets.QLabel("Ready.")
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        self.status.setStyleSheet("color:#999; padding-top:10px;")
        form.addWidget(self.status)
        form.addStretch(1)

        canvas_container = QtWidgets.QWidget()
        canvas_layout = QtWidgets.QVBoxLayout(canvas_container)
        canvas_layout.setContentsMargins(20, 20, 20, 20)
        self.canvas = CanvasView()
        self.canvas.dragged.connect(self.drag_active_source)
        canvas_layout.addWidget(self.canvas, 1, QtCore.Qt.AlignmentFlag.AlignCenter)
        root.addWidget(canvas_container, 1)

    @staticmethod
    def _heading(text: str) -> QtWidgets.QLabel:
        label = QtWidgets.QLabel(text)
        label.setStyleSheet("font-weight:600; margin-top:12px; color:#ccc;")
        return label

    def _sync_project_from_controls(self) -> None:
        self.project.width = self.width_spin.value()
        self.project.height = self.height_spin.value()
        self.project.mode = str(self.mode_combo.currentData())
        self.project.seed = self.seed_spin.value()
        self.project.territory = self.territory_slider.value()
        self.project.validate()

    def _load_controls_from_project(self) -> None:
        blockers = [
            QtCore.QSignalBlocker(self.width_spin),
            QtCore.QSignalBlocker(self.height_spin),
            QtCore.QSignalBlocker(self.mode_combo),
            QtCore.QSignalBlocker(self.seed_spin),
            QtCore.QSignalBlocker(self.territory_slider),
        ]
        self.width_spin.setValue(self.project.width)
        self.height_spin.setValue(self.project.height)
        self.seed_spin.setValue(max(0, min(2147483647, self.project.seed)))
        self.territory_slider.setValue(self.project.territory)
        self.territory_value.setText(str(self.project.territory))
        mode_index = self.mode_combo.findData(self.project.mode)
        self.mode_combo.setCurrentIndex(max(0, mode_index))
        del blockers
        self._rebuild_source_list()

    def _rebuild_source_list(self) -> None:
        self.source_list.clear()
        for index, source in enumerate(self.project.sources):
            self.source_list.addItem(f"{index + 1:02d}  {source.name}")
        if self.project.sources:
            self.source_list.setCurrentRow(min(max(self.active_index, 0), len(self.project.sources) - 1))
        else:
            self.active_index = -1

    def _allocation_changed(self, *_args) -> None:
        self.owners = None
        self._sync_project_from_controls()
        if self.active_index >= 0:
            self.show_active_source()

    def _territory_changed(self, value: int) -> None:
        self.territory_value.setText(str(value))
        self._allocation_changed()

    def _zoom_changed(self, value: int) -> None:
        self.zoom_value.setText(f"{value / 100:.2f}×")
        if 0 <= self.active_index < len(self.project.sources):
            self.project.sources[self.active_index].zoom = value / 100.0
            self.show_active_source()

    def add_sources(self) -> None:
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, "Add photographs", "", supported_file_filter()
        )
        if not paths:
            return
        for path in paths:
            self.project.sources.append(SourceSpec(path=str(Path(path))))
        self.owners = None
        self.active_index = len(self.project.sources) - len(paths)
        self._rebuild_source_list()
        self.source_list.setCurrentRow(self.active_index)
        self.status.setText(f"Loaded {len(self.project.sources)} source(s). Target share: {100 / len(self.project.sources):.4f}% each.")

    def remove_source(self) -> None:
        row = self.source_list.currentRow()
        if 0 <= row < len(self.project.sources):
            self.project.sources.pop(row)
            self.owners = None
            self.active_index = min(row, len(self.project.sources) - 1)
            self._rebuild_source_list()
            if not self.project.sources:
                self.canvas.clear_image()

    def select_source(self, row: int) -> None:
        if not 0 <= row < len(self.project.sources):
            return
        self.active_index = row
        source = self.project.sources[row]
        blocker = QtCore.QSignalBlocker(self.zoom_slider)
        self.zoom_slider.setValue(int(round(source.zoom * 100)))
        del blocker
        self.zoom_value.setText(f"{source.zoom:.2f}×")
        self.show_active_source()

    def reset_crop(self) -> None:
        if 0 <= self.active_index < len(self.project.sources):
            source = self.project.sources[self.active_index]
            source.zoom = 1.0
            source.offset_x = 0.0
            source.offset_y = 0.0
            self.zoom_slider.setValue(100)
            self.show_active_source()

    def drag_active_source(self, dx: float, dy: float) -> None:
        if 0 <= self.active_index < len(self.project.sources):
            source = self.project.sources[self.active_index]
            source.offset_x += dx
            source.offset_y += dy
            self.show_active_source()

    def show_active_source(self) -> None:
        if not 0 <= self.active_index < len(self.project.sources):
            return
        try:
            self._sync_project_from_controls()
            self._set_busy("Rendering crop preview…")
            array = render_preview_source(self.project, self.active_index)
            self.canvas.set_array(array, self.project.width, self.project.height)
            self.canvas.set_drag_enabled(True)
            source = self.project.sources[self.active_index]
            self.status.setText(
                f"Crop: {source.name}\nzoom {source.zoom:.2f}× · x {source.offset_x:.1f}px · y {source.offset_y:.1f}px"
            )
        except Exception as exc:
            self._show_error("Could not render source", exc)

    def _ensure_owners(self) -> np.ndarray:
        self._sync_project_from_controls()
        if not self.project.sources:
            raise ValueError("Add at least one source image")
        if self.owners is None or self.owners.shape != (self.project.height, self.project.width):
            self._set_busy("Generating exact ownership map…")
            self.owners = generate_ownership(
                self.project.width,
                self.project.height,
                len(self.project.sources),
                self.project.seed,
                self.project.mode,
                self.project.territory,
            )
            report = validate_ownership(self.owners, len(self.project.sources))
            if not report["valid"]:
                raise RuntimeError("Ownership invariant failed")
        return self.owners

    def generate_composite(self) -> None:
        try:
            owners = self._ensure_owners()
            self._set_busy("Rendering composite preview…")
            array = render_preview_composite(self.project, owners)
            self.canvas.set_array(array, self.project.width, self.project.height)
            self.canvas.set_drag_enabled(False)
            counts = np.bincount(owners.reshape(-1), minlength=len(self.project.sources))
            shares = counts * 100.0 / owners.size
            self.status.setText(
                f"Composite generated. {len(self.project.sources)} sources · {owners.size:,} pixels · "
                f"shares {shares.min():.4f}%–{shares.max():.4f}% · 0 overlap · 0 holes."
            )
        except Exception as exc:
            self._show_error("Could not generate composite", exc)

    def randomize_seed(self) -> None:
        seed = int(np.random.default_rng().integers(0, 2147483647))
        self.seed_spin.setValue(seed)

    def save_project_dialog(self) -> None:
        self._sync_project_from_controls()
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save PXCOMP project", "project.pxcomp", "PXCOMP project (*.pxcomp)")
        if path:
            try:
                save_project(self.project, path)
                self.status.setText(f"Project saved: {path}")
            except Exception as exc:
                self._show_error("Could not save project", exc)

    def load_project_dialog(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open PXCOMP project", "", "PXCOMP project (*.pxcomp)")
        if not path:
            return
        try:
            self.project = load_project(path)
            self.owners = None
            self.active_index = 0 if self.project.sources else -1
            self._load_controls_from_project()
            if self.project.sources:
                self.show_active_source()
            else:
                self.canvas.clear_image()
            self.status.setText(f"Project loaded: {path}")
        except Exception as exc:
            self._show_error("Could not load project", exc)

    def export_png_dialog(self) -> None:
        self._export_dialog("PNG image (*.png)", "composite.png", lambda p, o: export_png(self.project, o, p))

    def export_jpeg_dialog(self) -> None:
        self._export_dialog("JPEG image (*.jpg *.jpeg)", "composite.jpg", lambda p, o: export_jpeg(self.project, o, p))

    def export_tiff_dialog(self, bit_depth: int) -> None:
        self._export_dialog(
            "TIFF image (*.tif *.tiff)",
            f"composite-{bit_depth}bit.tif",
            lambda p, o: export_tiff(self.project, o, p, bit_depth=bit_depth),
        )

    def export_psd_dialog(self) -> None:
        self._export_dialog("Photoshop document (*.psd)", "composite-layered.psd", lambda p, o: export_psd(self.project, o, p))

    def _export_dialog(self, file_filter: str, default_name: str, exporter) -> None:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Export", default_name, file_filter)
        if not path:
            return
        try:
            owners = self._ensure_owners()
            self._set_busy(f"Rendering full-resolution export: {Path(path).name} …")
            exporter(path, owners)
            self.status.setText(f"Export complete: {path}")
        except Exception as exc:
            self._show_error("Export failed", exc)

    def _set_busy(self, message: str) -> None:
        self.status.setText(message)
        QtWidgets.QApplication.processEvents()

    def _show_error(self, title: str, exc: Exception) -> None:
        details = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        self.status.setText(f"{title}: {details}")
        QtWidgets.QMessageBox.critical(self, title, details)
