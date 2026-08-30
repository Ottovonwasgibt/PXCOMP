from __future__ import annotations

from pathlib import Path
import traceback

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from . import __version__
from .alloc import generate_ownership, validate_ownership
from .exports import export_jpeg, export_png, export_psd, export_tiff
from .imaging import SUPPORTED_EXTENSIONS, supported_file_filter
from .model import ALGORITHM_VERSION, Project, SourceSpec, load_project, save_project
from .render import render_preview_composite, render_preview_source


class CanvasView(QtWidgets.QLabel):
    dragged = QtCore.Signal(float, float)
    filesDropped = QtCore.Signal(list)
    zoomRequested = QtCore.Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(520, 420)
        self.setAcceptDrops(True)
        self.setStyleSheet(
            "background:#0d0d0d; color:#777; border:1px solid #2b2b2b;"
        )
        self._last_pos: QtCore.QPointF | None = None
        self._image: QtGui.QImage | None = None
        self._preview_width = 1
        self._preview_height = 1
        self._canvas_width = 1
        self._canvas_height = 1
        self._drag_enabled = True

    def set_drag_enabled(self, enabled: bool) -> None:
        self._drag_enabled = enabled
        self.setCursor(
            QtCore.Qt.CursorShape.OpenHandCursor
            if enabled and self._image is not None
            else QtCore.Qt.CursorShape.ArrowCursor
        )

    def set_array(self, array: np.ndarray, canvas_width: int, canvas_height: int) -> None:
        array = np.ascontiguousarray(array, dtype=np.uint8)
        height, width = array.shape[:2]
        self._image = QtGui.QImage(
            array.data,
            width,
            height,
            int(array.strides[0]),
            QtGui.QImage.Format.Format_RGB888,
        ).copy()
        self._canvas_width = max(1, int(canvas_width))
        self._canvas_height = max(1, int(canvas_height))
        self.setText("")
        self._refresh_pixmap()
        self.set_drag_enabled(self._drag_enabled)

    def _refresh_pixmap(self) -> None:
        if self._image is None:
            return
        target_width = max(1, self.width() - 28)
        target_height = max(1, self.height() - 28)
        pixmap = QtGui.QPixmap.fromImage(self._image).scaled(
            target_width,
            target_height,
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(pixmap)
        self._preview_width = max(1, pixmap.width())
        self._preview_height = max(1, pixmap.height())

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._refresh_pixmap()

    def clear_image(self) -> None:
        self._image = None
        self.setPixmap(QtGui.QPixmap())
        self.setText(
            "DROP PHOTOGRAPHS HERE\n\n"
            "or use ‘Add photographs’ in the left panel\n\n"
            "JPG · PNG · TIFF · RAW · WebP · AVIF"
        )
        self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)

    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dropEvent(self, event: QtGui.QDropEvent) -> None:
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.filesDropped.emit(paths)
            event.acceptProposedAction()
            return
        super().dropEvent(event)

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        if self._drag_enabled and self._image is not None and event.angleDelta().y():
            self.zoomRequested.emit(5 if event.angleDelta().y() > 0 else -5)
            event.accept()
            return
        super().wheelEvent(event)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if (
            self._drag_enabled
            and self._image is not None
            and event.button() == QtCore.Qt.MouseButton.LeftButton
        ):
            self._last_pos = event.position()
            self.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._drag_enabled and self._last_pos is not None:
            current = event.position()
            delta = current - self._last_pos
            self._last_pos = current
            dx = delta.x() * self._canvas_width / max(1, self._preview_width)
            dy = delta.y() * self._canvas_height / max(1, self._preview_height)
            self.dragged.emit(dx, dy)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        self._last_pos = None
        if self._drag_enabled and self._image is not None:
            self.setCursor(QtCore.Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(event)


class SourceListWidget(QtWidgets.QListWidget):
    orderChanged = QtCore.Signal(list)
    filesDropped = QtCore.Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(QtCore.Qt.DropAction.MoveAction)
        self.setDropIndicatorShown(True)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QtGui.QDragMoveEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event: QtGui.QDropEvent) -> None:
        if event.mimeData().hasUrls():
            paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
            if paths:
                self.filesDropped.emit(paths)
                event.acceptProposedAction()
                return
        super().dropEvent(event)
        order = [
            int(self.item(index).data(QtCore.Qt.ItemDataRole.UserRole))
            for index in range(self.count())
        ]
        self.orderChanged.emit(order)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.project = Project()
        self.owners: np.ndarray | None = None
        self.active_index = -1
        self.project_path: Path | None = None
        self.view_mode = "empty"
        self._busy = False

        self._preview_timer = QtCore.QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self.show_active_source)

        self.setAcceptDrops(True)
        self.resize(1500, 930)
        self.setMinimumSize(980, 680)
        self._apply_style()
        self._build_ui()
        self._build_menus()
        self._load_controls_from_project()
        self.canvas.clear_image()
        self._update_window_title()
        self._set_status("Ready. Drop photographs onto the canvas or click Add photographs.")

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background:#111111; color:#e8e8e8; font-size:12px; }
            QScrollArea { border:0; background:#141414; }
            QGroupBox {
                border:1px solid #303030; border-radius:6px; margin-top:14px;
                padding:12px 10px 10px 10px; font-weight:600; background:#151515;
            }
            QGroupBox::title { subcontrol-origin:margin; left:10px; padding:0 6px; color:#d7d7d7; }
            QPushButton {
                background:#232323; border:1px solid #3b3b3b; border-radius:5px;
                padding:7px 9px; min-height:18px;
            }
            QPushButton:hover { background:#2c2c2c; border-color:#555555; }
            QPushButton:pressed { background:#1a1a1a; }
            QPushButton:disabled { color:#666666; background:#191919; border-color:#292929; }
            QPushButton#primaryButton {
                background:#eeeeee; color:#111111; border-color:#ffffff;
                font-weight:700; min-height:30px;
            }
            QPushButton#primaryButton:hover { background:#ffffff; }
            QLineEdit, QSpinBox, QComboBox {
                background:#1c1c1c; border:1px solid #373737; border-radius:4px;
                padding:5px 7px; min-height:22px;
            }
            QComboBox::drop-down { border:0; width:24px; }
            QListWidget {
                background:#0f0f0f; border:1px solid #323232; border-radius:5px;
                padding:3px; outline:0;
            }
            QListWidget::item { padding:7px 6px; border-radius:3px; }
            QListWidget::item:selected { background:#343434; color:#ffffff; }
            QSlider::groove:horizontal { height:4px; background:#343434; border-radius:2px; }
            QSlider::handle:horizontal {
                background:#e8e8e8; width:14px; margin:-5px 0; border-radius:7px;
            }
            QProgressBar {
                border:1px solid #333333; border-radius:3px; background:#191919;
                text-align:center; max-height:10px;
            }
            QStatusBar { background:#0d0d0d; border-top:1px solid #262626; }
            QMenuBar, QMenu { background:#171717; color:#eeeeee; }
            QMenu::item:selected { background:#353535; }
            """
        )

    def _build_ui(self) -> None:
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        self.setCentralWidget(splitter)

        sidebar_scroll = QtWidgets.QScrollArea()
        sidebar_scroll.setWidgetResizable(True)
        sidebar_scroll.setMinimumWidth(350)
        sidebar_scroll.setMaximumWidth(470)
        sidebar = QtWidgets.QWidget()
        panel = QtWidgets.QVBoxLayout(sidebar)
        panel.setContentsMargins(14, 14, 14, 18)
        panel.setSpacing(10)
        sidebar_scroll.setWidget(sidebar)
        splitter.addWidget(sidebar_scroll)

        header_row = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("PXCOMP")
        title.setStyleSheet("font-size:24px; font-weight:800; letter-spacing:1px;")
        version = QtWidgets.QLabel(f"v{__version__}")
        version.setStyleSheet("color:#777; font-size:11px;")
        header_row.addWidget(title)
        header_row.addStretch(1)
        header_row.addWidget(version)
        panel.addLayout(header_row)

        subtitle = QtWidgets.QLabel(
            "One canvas. Multiple moments. Every output pixel has exactly one owner."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color:#8d8d8d; margin-bottom:2px;")
        panel.addWidget(subtitle)

        self.source_summary = QtWidgets.QLabel("No photographs loaded")
        self.source_summary.setStyleSheet(
            "color:#cfcfcf; padding:7px 9px; background:#1b1b1b; "
            "border-radius:4px; font-weight:600;"
        )
        panel.addWidget(self.source_summary)

        sources_box, sources_layout = self._group("1  Sources")
        self.add_button = QtWidgets.QPushButton("＋  Add photographs / RAW files")
        self.add_button.setMinimumHeight(34)
        self.add_button.clicked.connect(self.add_sources)
        sources_layout.addWidget(self.add_button)

        drop_hint = QtWidgets.QLabel(
            "You can also drag files onto this list or directly onto the canvas."
        )
        drop_hint.setWordWrap(True)
        drop_hint.setStyleSheet("color:#747474; font-size:11px;")
        sources_layout.addWidget(drop_hint)

        self.source_list = SourceListWidget()
        self.source_list.setMinimumHeight(175)
        self.source_list.currentRowChanged.connect(self.select_source)
        self.source_list.orderChanged.connect(self._sources_reordered)
        self.source_list.filesDropped.connect(self._handle_dropped_paths)
        sources_layout.addWidget(self.source_list)

        order_hint = QtWidgets.QLabel(
            "Drag to reorder. Source order matters because ownership is allocated sequentially."
        )
        order_hint.setWordWrap(True)
        order_hint.setStyleSheet("color:#747474; font-size:10px;")
        sources_layout.addWidget(order_hint)

        source_nav = QtWidgets.QHBoxLayout()
        self.previous_button = QtWidgets.QPushButton("← Previous")
        self.next_button = QtWidgets.QPushButton("Next →")
        self.previous_button.clicked.connect(lambda: self._select_relative_source(-1))
        self.next_button.clicked.connect(lambda: self._select_relative_source(1))
        source_nav.addWidget(self.previous_button)
        source_nav.addWidget(self.next_button)
        sources_layout.addLayout(source_nav)

        source_manage = QtWidgets.QHBoxLayout()
        self.move_up_button = QtWidgets.QPushButton("↑")
        self.move_up_button.setToolTip("Move selected source earlier in the sequence")
        self.move_down_button = QtWidgets.QPushButton("↓")
        self.move_down_button.setToolTip("Move selected source later in the sequence")
        self.remove_button = QtWidgets.QPushButton("Remove")
        self.clear_button = QtWidgets.QPushButton("Clear all")
        self.move_up_button.clicked.connect(lambda: self.move_source(-1))
        self.move_down_button.clicked.connect(lambda: self.move_source(1))
        self.remove_button.clicked.connect(self.remove_source)
        self.clear_button.clicked.connect(self.clear_sources)
        source_manage.addWidget(self.move_up_button)
        source_manage.addWidget(self.move_down_button)
        source_manage.addWidget(self.remove_button)
        source_manage.addWidget(self.clear_button)
        sources_layout.addLayout(source_manage)
        panel.addWidget(sources_box)

        canvas_box, canvas_layout = self._group("2  Canvas & crop")
        dims = QtWidgets.QHBoxLayout()
        width_label = QtWidgets.QLabel("W")
        width_label.setStyleSheet("color:#888;")
        self.width_spin = QtWidgets.QSpinBox()
        self.width_spin.setRange(1, 30000)
        self.width_spin.setSuffix(" px")
        height_label = QtWidgets.QLabel("H")
        height_label.setStyleSheet("color:#888;")
        self.height_spin = QtWidgets.QSpinBox()
        self.height_spin.setRange(1, 30000)
        self.height_spin.setSuffix(" px")
        dims.addWidget(width_label)
        dims.addWidget(self.width_spin, 1)
        dims.addWidget(height_label)
        dims.addWidget(self.height_spin, 1)
        canvas_layout.addLayout(dims)
        self.width_spin.valueChanged.connect(self._canvas_size_changed)
        self.height_spin.valueChanged.connect(self._canvas_size_changed)

        ratio_row = QtWidgets.QHBoxLayout()
        self.ratio_combo = QtWidgets.QComboBox()
        self.ratio_combo.addItem("Set aspect ratio…", None)
        for label, ratio in [
            ("Square 1:1", 1.0),
            ("Portrait 4:5", 4 / 5),
            ("Landscape 5:4", 5 / 4),
            ("Photo 3:2", 3 / 2),
            ("Portrait 2:3", 2 / 3),
            ("Screen 16:9", 16 / 9),
            ("Portrait 9:16", 9 / 16),
        ]:
            self.ratio_combo.addItem(label, ratio)
        self.ratio_combo.currentIndexChanged.connect(self._apply_ratio_preset)
        swap_button = QtWidgets.QPushButton("Swap W/H")
        swap_button.clicked.connect(self.swap_canvas_dimensions)
        ratio_row.addWidget(self.ratio_combo, 1)
        ratio_row.addWidget(swap_button)
        canvas_layout.addLayout(ratio_row)

        crop_label = QtWidgets.QLabel("Active photograph crop")
        crop_label.setStyleSheet("font-weight:600; color:#cfcfcf; margin-top:4px;")
        canvas_layout.addWidget(crop_label)

        zoom_row = QtWidgets.QHBoxLayout()
        zoom_text = QtWidgets.QLabel("Zoom")
        zoom_text.setStyleSheet("color:#888;")
        self.zoom_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(100, 500)
        self.zoom_slider.setSingleStep(1)
        self.zoom_value = QtWidgets.QLabel("1.00×")
        self.zoom_value.setMinimumWidth(42)
        zoom_row.addWidget(zoom_text)
        zoom_row.addWidget(self.zoom_slider, 1)
        zoom_row.addWidget(self.zoom_value)
        canvas_layout.addLayout(zoom_row)
        self.zoom_slider.valueChanged.connect(self._zoom_changed)

        crop_actions = QtWidgets.QHBoxLayout()
        self.center_crop_button = QtWidgets.QPushButton("Center")
        self.reset_crop_button = QtWidgets.QPushButton("Reset crop")
        self.center_crop_button.clicked.connect(self.center_crop)
        self.reset_crop_button.clicked.connect(self.reset_crop)
        crop_actions.addWidget(self.center_crop_button)
        crop_actions.addWidget(self.reset_crop_button)
        canvas_layout.addLayout(crop_actions)

        crop_help = QtWidgets.QLabel(
            "Drag the image on the canvas to reposition it. Mouse wheel zooms. "
            "Crop edits are non-destructive."
        )
        crop_help.setWordWrap(True)
        crop_help.setStyleSheet("color:#747474; font-size:11px;")
        canvas_layout.addWidget(crop_help)
        panel.addWidget(canvas_box)

        composition_box, composition_layout = self._group("3  Composition")
        self.mode_combo = QtWidgets.QComboBox()
        self.mode_combo.addItem("Pixel Random", "pixel")
        self.mode_combo.addItem("Organic Territories", "organic")
        self.mode_combo.addItem("Vector Cutouts", "vector")
        self.mode_combo.currentIndexChanged.connect(self._mode_changed)
        composition_layout.addWidget(self.mode_combo)

        self.mode_help = QtWidgets.QLabel()
        self.mode_help.setWordWrap(True)
        self.mode_help.setStyleSheet(
            "color:#8a8a8a; font-size:11px; padding:7px; "
            "background:#1a1a1a; border-left:2px solid #484848;"
        )
        composition_layout.addWidget(self.mode_help)

        self.territory_label = QtWidgets.QLabel("Territory size")
        self.territory_label.setStyleSheet("color:#9a9a9a; font-size:11px;")
        composition_layout.addWidget(self.territory_label)
        territory_row = QtWidgets.QHBoxLayout()
        self.territory_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.territory_slider.setRange(0, 100)
        self.territory_value = QtWidgets.QLabel("55")
        self.territory_value.setMinimumWidth(34)
        territory_row.addWidget(self.territory_slider, 1)
        territory_row.addWidget(self.territory_value)
        composition_layout.addLayout(territory_row)
        self.territory_slider.valueChanged.connect(self._territory_changed)

        self.vector_points_label = QtWidgets.QLabel("Max primitive points")
        self.vector_points_label.setStyleSheet("color:#9a9a9a; font-size:11px;")
        composition_layout.addWidget(self.vector_points_label)
        self.vector_points_spin = QtWidgets.QSpinBox()
        self.vector_points_spin.setRange(1, 32)
        self.vector_points_spin.setSuffix(" max")
        self.vector_points_spin.valueChanged.connect(self._vector_points_changed)
        composition_layout.addWidget(self.vector_points_spin)

        self.point_spread_label = QtWidgets.QLabel("Point spread")
        self.point_spread_label.setStyleSheet("color:#9a9a9a; font-size:11px;")
        composition_layout.addWidget(self.point_spread_label)
        point_spread_row = QtWidgets.QHBoxLayout()
        self.point_spread_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.point_spread_slider.setRange(1, 100)
        self.point_spread_value = QtWidgets.QLabel("100%")
        self.point_spread_value.setMinimumWidth(38)
        point_spread_row.addWidget(self.point_spread_slider, 1)
        point_spread_row.addWidget(self.point_spread_value)
        composition_layout.addLayout(point_spread_row)
        self.point_spread_slider.valueChanged.connect(self._point_spread_changed)

        seed_label = QtWidgets.QLabel("Seed")
        seed_label.setStyleSheet("color:#9a9a9a; font-size:11px;")
        composition_layout.addWidget(seed_label)
        seed_row = QtWidgets.QHBoxLayout()
        self.seed_spin = QtWidgets.QSpinBox()
        self.seed_spin.setRange(0, 2147483647)
        self.seed_spin.valueChanged.connect(self._allocation_changed)
        random_seed = QtWidgets.QPushButton("New seed")
        random_seed.setToolTip("Generate a new deterministic arrangement (Ctrl+R)")
        random_seed.clicked.connect(self.randomize_seed)
        seed_row.addWidget(self.seed_spin, 1)
        seed_row.addWidget(random_seed)
        composition_layout.addLayout(seed_row)

        self.generate_button = QtWidgets.QPushButton("GENERATE COMPOSITE")
        self.generate_button.setObjectName("primaryButton")
        self.generate_button.clicked.connect(self.generate_composite)
        composition_layout.addWidget(self.generate_button)
        panel.addWidget(composition_box)

        output_box, output_layout = self._group("4  Project & export")
        project_row = QtWidgets.QHBoxLayout()
        open_button = QtWidgets.QPushButton("Open project")
        self.save_button = QtWidgets.QPushButton("Save project")
        open_button.clicked.connect(self.load_project_dialog)
        self.save_button.clicked.connect(self.save_project)
        project_row.addWidget(open_button)
        project_row.addWidget(self.save_button)
        output_layout.addLayout(project_row)

        self.export_combo = QtWidgets.QComboBox()
        self.export_combo.addItem("PNG — 8-bit", "png")
        self.export_combo.addItem("JPEG — 8-bit", "jpeg")
        self.export_combo.addItem("TIFF — 8-bit", "tiff8")
        self.export_combo.addItem("TIFF — 16-bit master", "tiff16")
        self.export_combo.addItem("PSD — editable masked layers", "psd")
        output_layout.addWidget(self.export_combo)

        self.export_button = QtWidgets.QPushButton("Export…")
        self.export_button.setMinimumHeight(32)
        self.export_button.clicked.connect(self.export_selected)
        output_layout.addWidget(self.export_button)

        output_help = QtWidgets.QLabel(
            "TIFF 16-bit is the high-precision master path. PSD keeps one masked "
            "full-canvas layer per source."
        )
        output_help.setWordWrap(True)
        output_help.setStyleSheet("color:#747474; font-size:10px;")
        output_layout.addWidget(output_help)
        panel.addWidget(output_box)
        panel.addStretch(1)

        workspace = QtWidgets.QWidget()
        workspace_layout = QtWidgets.QVBoxLayout(workspace)
        workspace_layout.setContentsMargins(18, 14, 18, 16)
        workspace_layout.setSpacing(10)

        workspace_header = QtWidgets.QHBoxLayout()
        self.view_badge = QtWidgets.QLabel("EMPTY")
        self.view_badge.setStyleSheet(
            "font-weight:700; color:#d7d7d7; padding:5px 8px; "
            "background:#1c1c1c; border:1px solid #333; border-radius:4px;"
        )
        self.view_details = QtWidgets.QLabel("Drop photographs to begin")
        self.view_details.setStyleSheet("color:#777;")
        self.view_details.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.crop_view_button = QtWidgets.QPushButton("Edit active crop")
        self.crop_view_button.clicked.connect(self.show_active_source)
        workspace_header.addWidget(self.view_badge)
        workspace_header.addWidget(self.view_details, 1)
        workspace_header.addWidget(self.crop_view_button)
        workspace_layout.addLayout(workspace_header)

        self.canvas = CanvasView()
        self.canvas.dragged.connect(self.drag_active_source)
        self.canvas.filesDropped.connect(self._handle_dropped_paths)
        self.canvas.zoomRequested.connect(self._wheel_zoom)
        workspace_layout.addWidget(self.canvas, 1)

        splitter.addWidget(workspace)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([390, 1110])

        self.status_message = QtWidgets.QLabel("Ready.")
        self.status_message.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedWidth(120)
        self.progress.setTextVisible(False)
        self.progress.hide()
        self.statusBar().addWidget(self.status_message, 1)
        self.statusBar().addPermanentWidget(self.progress)

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        source_menu = self.menuBar().addMenu("&Source")
        composition_menu = self.menuBar().addMenu("&Composition")
        export_menu = self.menuBar().addMenu("&Export")

        self._add_action(file_menu, "Add photographs…", self.add_sources, "Ctrl+I")
        self._add_action(
            file_menu, "Open project…", self.load_project_dialog, QtGui.QKeySequence.StandardKey.Open
        )
        self._add_action(
            file_menu, "Save project", self.save_project, QtGui.QKeySequence.StandardKey.Save
        )
        self._add_action(
            file_menu, "Save project as…", self.save_project_as_dialog, QtGui.QKeySequence.StandardKey.SaveAs
        )
        file_menu.addSeparator()
        self._add_action(file_menu, "New project", self.new_project, "Ctrl+N")
        file_menu.addSeparator()
        self._add_action(file_menu, "Exit", self.close, "Alt+F4")

        self._add_action(
            source_menu, "Previous source", lambda: self._select_relative_source(-1), "PgUp"
        )
        self._add_action(
            source_menu, "Next source", lambda: self._select_relative_source(1), "PgDown"
        )
        source_menu.addSeparator()
        self._add_action(source_menu, "Center crop", self.center_crop)
        self._add_action(source_menu, "Reset crop", self.reset_crop, "Ctrl+0")
        source_menu.addSeparator()
        self._add_action(source_menu, "Remove selected", self.remove_source, "Delete")

        self._add_action(
            composition_menu, "Generate composite", self.generate_composite, "Ctrl+Return"
        )
        self._add_action(
            composition_menu, "New random seed", self.randomize_seed, "Ctrl+R"
        )

        self._add_action(export_menu, "PNG — 8-bit…", self.export_png_dialog)
        self._add_action(export_menu, "JPEG — 8-bit…", self.export_jpeg_dialog)
        self._add_action(export_menu, "TIFF — 8-bit…", lambda: self.export_tiff_dialog(8))
        self._add_action(
            export_menu, "TIFF — 16-bit master…", lambda: self.export_tiff_dialog(16)
        )
        self._add_action(export_menu, "PSD — editable masked layers…", self.export_psd_dialog)

    def _add_action(self, menu: QtWidgets.QMenu, text: str, callback, shortcut=None) -> QtGui.QAction:
        action = QtGui.QAction(text, self)
        if shortcut is not None:
            action.setShortcut(shortcut)
        action.triggered.connect(callback)
        menu.addAction(action)
        return action

    @staticmethod
    def _group(title: str) -> tuple[QtWidgets.QGroupBox, QtWidgets.QVBoxLayout]:
        box = QtWidgets.QGroupBox(title)
        layout = QtWidgets.QVBoxLayout(box)
        layout.setSpacing(7)
        layout.setContentsMargins(10, 14, 10, 10)
        return box, layout

    def _update_window_title(self) -> None:
        project_name = self.project_path.name if self.project_path else "Untitled"
        self.setWindowTitle(f"{project_name} — PXCOMP v{__version__}")

    def _sync_project_from_controls(self) -> None:
        self.project.width = self.width_spin.value()
        self.project.height = self.height_spin.value()
        self.project.mode = str(self.mode_combo.currentData())
        self.project.seed = self.seed_spin.value()
        self.project.territory = self.territory_slider.value()
        self.project.vector_points = self.vector_points_spin.value()
        self.project.point_spread = self.point_spread_slider.value()
        self.project.validate()

    def _load_controls_from_project(self) -> None:
        blockers = [
            QtCore.QSignalBlocker(self.width_spin),
            QtCore.QSignalBlocker(self.height_spin),
            QtCore.QSignalBlocker(self.mode_combo),
            QtCore.QSignalBlocker(self.seed_spin),
            QtCore.QSignalBlocker(self.territory_slider),
            QtCore.QSignalBlocker(self.vector_points_spin),
            QtCore.QSignalBlocker(self.point_spread_slider),
        ]
        self.width_spin.setValue(self.project.width)
        self.height_spin.setValue(self.project.height)
        self.seed_spin.setValue(max(0, min(2147483647, self.project.seed)))
        self.territory_slider.setValue(self.project.territory)
        self.territory_value.setText(str(self.project.territory))
        self.vector_points_spin.setValue(self.project.vector_points)
        self.point_spread_slider.setValue(self.project.point_spread)
        self.point_spread_value.setText(f"{self.project.point_spread}%")
        mode_index = self.mode_combo.findData(self.project.mode)
        self.mode_combo.setCurrentIndex(max(0, mode_index))
        del blockers
        self._refresh_mode_controls()
        self._rebuild_source_list()
        self._update_source_summary()
        self._update_source_controls()

    def _refresh_mode_controls(self) -> None:
        mode = str(self.mode_combo.currentData())
        is_vector = mode == "vector"
        is_spatial = mode in {"organic", "vector"}

        self.territory_label.setVisible(is_spatial)
        self.territory_slider.setVisible(is_spatial)
        self.territory_value.setVisible(is_spatial)
        self.vector_points_label.setVisible(is_vector)
        self.vector_points_spin.setVisible(is_vector)
        self.point_spread_label.setVisible(is_vector)
        self.point_spread_slider.setVisible(is_vector)
        self.point_spread_value.setVisible(is_vector)

        if mode == "pixel":
            self.mode_help.setText(
                "Independent random pixel ownership. Best for fine-grain / pointillist interference."
            )
        elif mode == "organic":
            self.territory_label.setText("Territory size")
            self.mode_help.setText(
                "Smooth random fields create broad soft islands. Increase Territory size "
                "for larger spatial masses."
            )
        else:
            self.territory_label.setText("Cutout scale")
            if str(self.project.algorithm_version).startswith("1.1"):
                self.mode_help.setText(
                    "Legacy v0.2 vector recipe. Fixed polygon point count is preserved for "
                    "reproducibility; changing a vector control upgrades it to the current grammar."
                )
            else:
                self.mode_help.setText(
                    "Hard cut-paper grammar. Each primitive randomly chooses 1..Max points: "
                    "1 = stamp, 2 = ribbon, 3+ = polygon. Point spread controls how far its "
                    "control points may reach across the canvas."
                )

    def _update_source_summary(self) -> None:
        count = len(self.project.sources)
        if count:
            self.source_summary.setText(
                f"{count} photograph{'s' if count != 1 else ''}  •  "
                f"{100.0 / count:.3f}% target share each"
            )
        else:
            self.source_summary.setText("No photographs loaded")

    def _update_source_controls(self) -> None:
        count = len(self.project.sources)
        row = self.active_index
        has_source = 0 <= row < count
        self.previous_button.setEnabled(has_source and row > 0)
        self.next_button.setEnabled(has_source and row < count - 1)
        self.move_up_button.setEnabled(has_source and row > 0)
        self.move_down_button.setEnabled(has_source and row < count - 1)
        self.remove_button.setEnabled(has_source)
        self.clear_button.setEnabled(count > 0)
        self.center_crop_button.setEnabled(has_source)
        self.reset_crop_button.setEnabled(has_source)
        self.zoom_slider.setEnabled(has_source)
        self.crop_view_button.setEnabled(has_source)
        self.generate_button.setEnabled(count > 0)
        self.export_button.setEnabled(count > 0)

    def _rebuild_source_list(self) -> None:
        current = self.active_index
        blocker = QtCore.QSignalBlocker(self.source_list)
        self.source_list.clear()
        for index, source in enumerate(self.project.sources):
            item = QtWidgets.QListWidgetItem(f"{index + 1:02d}   {source.name}")
            item.setData(QtCore.Qt.ItemDataRole.UserRole, index)
            item.setToolTip(source.path)
            self.source_list.addItem(item)
        if self.project.sources:
            self.active_index = min(max(current, 0), len(self.project.sources) - 1)
            self.source_list.setCurrentRow(self.active_index)
        else:
            self.active_index = -1
        del blocker

    def _canvas_size_changed(self, *_args) -> None:
        self.owners = None
        self._sync_project_from_controls()
        if self.view_mode == "crop" and self.active_index >= 0:
            self._schedule_crop_preview(100)
        elif self.view_mode == "composite":
            self._mark_composite_stale("Canvas size changed")

    def _allocation_changed(self, *_args) -> None:
        if str(self.mode_combo.currentData()) == "vector":
            self.project.algorithm_version = ALGORITHM_VERSION
        self.owners = None
        self._sync_project_from_controls()
        self._refresh_mode_controls()
        if self.view_mode == "composite":
            self._mark_composite_stale("Composition settings changed")

    def _mode_changed(self, *_args) -> None:
        self._allocation_changed()

    def _territory_changed(self, value: int) -> None:
        self.territory_value.setText(str(value))
        self._allocation_changed()

    def _vector_points_changed(self, _value: int) -> None:
        self._allocation_changed()

    def _point_spread_changed(self, value: int) -> None:
        self.point_spread_value.setText(f"{value}%")
        self._allocation_changed()

    def _zoom_changed(self, value: int) -> None:
        self.zoom_value.setText(f"{value / 100:.2f}×")
        if 0 <= self.active_index < len(self.project.sources):
            self.project.sources[self.active_index].zoom = value / 100.0
            self.view_mode = "crop"
            self._schedule_crop_preview(90)

    def _wheel_zoom(self, delta: int) -> None:
        if not 0 <= self.active_index < len(self.project.sources):
            return
        value = int(
            np.clip(
                self.zoom_slider.value() + delta,
                self.zoom_slider.minimum(),
                self.zoom_slider.maximum(),
            )
        )
        self.zoom_slider.setValue(value)

    def _schedule_crop_preview(self, delay_ms: int = 80) -> None:
        if 0 <= self.active_index < len(self.project.sources):
            self._preview_timer.start(max(0, int(delay_ms)))

    def _mark_composite_stale(self, reason: str) -> None:
        self.view_badge.setText("COMPOSITE · UPDATE NEEDED")
        self.view_details.setText(f"{reason}. Press Generate to refresh.")
        self._set_status(f"{reason}. Generate the composite again to refresh the preview.")

    def _apply_ratio_preset(self, index: int) -> None:
        ratio = self.ratio_combo.itemData(index)
        if ratio is None:
            return
        ratio = float(ratio)
        width = self.width_spin.value()
        height = max(1, min(30000, int(round(width / ratio))))
        blocker = QtCore.QSignalBlocker(self.height_spin)
        self.height_spin.setValue(height)
        del blocker
        reset = QtCore.QSignalBlocker(self.ratio_combo)
        self.ratio_combo.setCurrentIndex(0)
        del reset
        self._canvas_size_changed()

    def swap_canvas_dimensions(self) -> None:
        width = self.width_spin.value()
        height = self.height_spin.value()
        blockers = [
            QtCore.QSignalBlocker(self.width_spin),
            QtCore.QSignalBlocker(self.height_spin),
        ]
        self.width_spin.setValue(height)
        self.height_spin.setValue(width)
        del blockers
        self._canvas_size_changed()

    def add_sources(self) -> None:
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, "Add photographs", "", supported_file_filter()
        )
        if paths:
            self.add_source_paths(paths)

    def add_source_paths(self, paths: list[str]) -> None:
        valid_paths = [
            str(Path(path))
            for path in paths
            if Path(path).suffix.lower() in SUPPORTED_EXTENSIONS
        ]
        if not valid_paths:
            self._set_status("No supported image files were added.")
            return

        first_new = len(self.project.sources)
        for path in valid_paths:
            self.project.sources.append(SourceSpec(path=path))
        self.owners = None
        self.active_index = first_new
        self._rebuild_source_list()
        self._update_source_summary()
        self._update_source_controls()
        self.source_list.setCurrentRow(self.active_index)
        self.select_source(self.active_index)
        self._set_status(
            f"Added {len(valid_paths)} source(s). "
            f"{len(self.project.sources)} total · "
            f"{100.0 / len(self.project.sources):.3f}% target share each."
        )

    def _handle_dropped_paths(self, paths: list[str]) -> None:
        local_paths = [str(Path(path)) for path in paths if path]
        project_files = [path for path in local_paths if Path(path).suffix.lower() == ".pxcomp"]
        if len(local_paths) == 1 and project_files:
            self.open_project_path(project_files[0])
            return
        image_paths = [
            path for path in local_paths if Path(path).suffix.lower() in SUPPORTED_EXTENSIONS
        ]
        self.add_source_paths(image_paths)

    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dropEvent(self, event: QtGui.QDropEvent) -> None:
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self._handle_dropped_paths(paths)
            event.acceptProposedAction()
            return
        super().dropEvent(event)

    def _sources_reordered(self, order: list[int]) -> None:
        count = len(self.project.sources)
        if len(order) != count or sorted(order) != list(range(count)):
            self._rebuild_source_list()
            return
        active_source = (
            self.project.sources[self.active_index]
            if 0 <= self.active_index < count
            else None
        )
        old_sources = list(self.project.sources)
        self.project.sources = [old_sources[index] for index in order]
        self.active_index = (
            next(
                (
                    index
                    for index, source in enumerate(self.project.sources)
                    if source is active_source
                ),
                0,
            )
            if self.project.sources
            else -1
        )
        self.owners = None
        self._rebuild_source_list()
        self._update_source_controls()
        if self.active_index >= 0:
            self.source_list.setCurrentRow(self.active_index)
            self.show_active_source()
        self._set_status("Source order changed. Generate again to refresh ownership.")

    def move_source(self, delta: int) -> None:
        row = self.active_index
        target = row + int(delta)
        if not (0 <= row < len(self.project.sources)) or not (
            0 <= target < len(self.project.sources)
        ):
            return
        source = self.project.sources.pop(row)
        self.project.sources.insert(target, source)
        self.active_index = target
        self.owners = None
        self._rebuild_source_list()
        self._update_source_controls()
        self.source_list.setCurrentRow(target)
        self.show_active_source()
        self._set_status("Source order changed. Generate again to refresh ownership.")

    def remove_source(self) -> None:
        row = self.active_index
        if not 0 <= row < len(self.project.sources):
            return
        removed = self.project.sources.pop(row)
        self.owners = None
        self.active_index = min(row, len(self.project.sources) - 1)
        self._rebuild_source_list()
        self._update_source_summary()
        self._update_source_controls()
        if self.project.sources:
            self.source_list.setCurrentRow(self.active_index)
            self.select_source(self.active_index)
        else:
            self.view_mode = "empty"
            self.canvas.clear_image()
            self.view_badge.setText("EMPTY")
            self.view_details.setText("Drop photographs to begin")
        self._set_status(f"Removed {removed.name}.")

    def clear_sources(self) -> None:
        if not self.project.sources:
            return
        answer = QtWidgets.QMessageBox.question(
            self,
            "Clear all sources?",
            "Remove all photographs from this project?",
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No,
        )
        if answer != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        self.project.sources.clear()
        self.owners = None
        self.active_index = -1
        self.view_mode = "empty"
        self._rebuild_source_list()
        self._update_source_summary()
        self._update_source_controls()
        self.canvas.clear_image()
        self.view_badge.setText("EMPTY")
        self.view_details.setText("Drop photographs to begin")
        self._set_status("All sources removed.")

    def _select_relative_source(self, delta: int) -> None:
        if not self.project.sources:
            return
        row = int(
            np.clip(
                self.active_index + delta,
                0,
                len(self.project.sources) - 1,
            )
        )
        self.source_list.setCurrentRow(row)

    def select_source(self, row: int) -> None:
        if not 0 <= row < len(self.project.sources):
            self._update_source_controls()
            return
        self.active_index = row
        source = self.project.sources[row]
        blocker = QtCore.QSignalBlocker(self.zoom_slider)
        self.zoom_slider.setValue(int(round(source.zoom * 100)))
        del blocker
        self.zoom_value.setText(f"{source.zoom:.2f}×")
        self._update_source_controls()
        self.show_active_source()

    def center_crop(self) -> None:
        if 0 <= self.active_index < len(self.project.sources):
            source = self.project.sources[self.active_index]
            source.offset_x = 0.0
            source.offset_y = 0.0
            self.show_active_source()

    def reset_crop(self) -> None:
        if 0 <= self.active_index < len(self.project.sources):
            source = self.project.sources[self.active_index]
            source.zoom = 1.0
            source.offset_x = 0.0
            source.offset_y = 0.0
            blocker = QtCore.QSignalBlocker(self.zoom_slider)
            self.zoom_slider.setValue(100)
            del blocker
            self.zoom_value.setText("1.00×")
            self.show_active_source()

    def drag_active_source(self, dx: float, dy: float) -> None:
        if 0 <= self.active_index < len(self.project.sources):
            source = self.project.sources[self.active_index]
            source.offset_x += dx
            source.offset_y += dy
            self.view_mode = "crop"
            self._schedule_crop_preview(60)

    def show_active_source(self) -> None:
        if not 0 <= self.active_index < len(self.project.sources):
            return
        try:
            self._sync_project_from_controls()
            self._set_busy("Rendering crop preview…")
            array = render_preview_source(self.project, self.active_index)
            self.canvas.set_array(array, self.project.width, self.project.height)
            self.canvas.set_drag_enabled(True)
            self.view_mode = "crop"
            source = self.project.sources[self.active_index]
            self.view_badge.setText("CROP")
            self.view_details.setText(
                f"{self.active_index + 1}/{len(self.project.sources)} · {source.name} · "
                f"{source.zoom:.2f}× · x {source.offset_x:.0f}px · y {source.offset_y:.0f}px"
            )
            self._set_status(
                "Crop mode · drag to reposition · mouse wheel to zoom · "
                "PageUp/PageDown changes source."
            )
        except Exception as exc:
            self._show_error("Could not render source", exc)

    def _ensure_owners(self) -> np.ndarray:
        self._sync_project_from_controls()
        if not self.project.sources:
            raise ValueError("Add at least one source image")
        if self.owners is None or self.owners.shape != (
            self.project.height,
            self.project.width,
        ):
            self._set_busy("Generating exact ownership map…")
            self.owners = generate_ownership(
                self.project.width,
                self.project.height,
                len(self.project.sources),
                self.project.seed,
                self.project.mode,
                self.project.territory,
                self.project.vector_points,
                self.project.point_spread,
                self.project.algorithm_version,
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
            self.view_mode = "composite"
            counts = np.bincount(owners.reshape(-1), minlength=len(self.project.sources))
            shares = counts * 100.0 / owners.size
            mode_name = self.mode_combo.currentText()
            self.view_badge.setText("COMPOSITE")
            self.view_details.setText(
                f"{mode_name} · seed {self.project.seed} · "
                f"{len(self.project.sources)} sources · "
                f"{shares.min():.3f}%–{shares.max():.3f}%"
            )
            self._set_status(
                f"Composite ready · {owners.size:,} pixels · "
                "0 overlap · 0 holes · exact integer quotas."
            )
        except Exception as exc:
            self._show_error("Could not generate composite", exc)

    def randomize_seed(self) -> None:
        seed = int(np.random.default_rng().integers(0, 2147483647))
        self.seed_spin.setValue(seed)
        self._set_status(f"Seed changed to {seed}. Generate to preview the new arrangement.")

    def new_project(self) -> None:
        if self.project.sources:
            answer = QtWidgets.QMessageBox.question(
                self,
                "New project?",
                "Start a new project? Unsaved project changes will be discarded.",
                QtWidgets.QMessageBox.StandardButton.Yes
                | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.No,
            )
            if answer != QtWidgets.QMessageBox.StandardButton.Yes:
                return
        self.project = Project()
        self.owners = None
        self.active_index = -1
        self.project_path = None
        self.view_mode = "empty"
        self._load_controls_from_project()
        self.canvas.clear_image()
        self.view_badge.setText("EMPTY")
        self.view_details.setText("Drop photographs to begin")
        self._update_window_title()
        self._set_status("New project.")

    def save_project(self) -> None:
        if self.project_path is None:
            self.save_project_as_dialog()
            return
        self._sync_project_from_controls()
        try:
            save_project(self.project, self.project_path)
            self._set_status(f"Project saved: {self.project_path}")
        except Exception as exc:
            self._show_error("Could not save project", exc)

    def save_project_as_dialog(self) -> None:
        self._sync_project_from_controls()
        start = (
            str(self.project_path)
            if self.project_path
            else str(Path.home() / "PXCOMP-project.pxcomp")
        )
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save PXCOMP project",
            start,
            "PXCOMP project (*.pxcomp)",
        )
        if not path:
            return
        try:
            self.project_path = Path(path)
            save_project(self.project, self.project_path)
            self._update_window_title()
            self._set_status(f"Project saved: {self.project_path}")
        except Exception as exc:
            self._show_error("Could not save project", exc)

    def save_project_dialog(self) -> None:
        self.save_project_as_dialog()

    def load_project_dialog(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open PXCOMP project", "", "PXCOMP project (*.pxcomp)"
        )
        if path:
            self.open_project_path(path)

    def open_project_path(self, path: str | Path) -> None:
        try:
            self.project = load_project(path)
            self.project_path = Path(path)
            self.owners = None
            self.active_index = 0 if self.project.sources else -1
            self.view_mode = "empty" if not self.project.sources else "crop"
            self._load_controls_from_project()
            self._update_window_title()
            if self.project.sources:
                self.source_list.setCurrentRow(self.active_index)
                self.show_active_source()
            else:
                self.canvas.clear_image()
                self.view_badge.setText("EMPTY")
                self.view_details.setText("Drop photographs to begin")
            self._set_status(f"Project loaded: {path}")
        except Exception as exc:
            self._show_error("Could not load project", exc)

    def export_selected(self) -> None:
        selected = str(self.export_combo.currentData())
        if selected == "png":
            self.export_png_dialog()
        elif selected == "jpeg":
            self.export_jpeg_dialog()
        elif selected == "tiff8":
            self.export_tiff_dialog(8)
        elif selected == "tiff16":
            self.export_tiff_dialog(16)
        elif selected == "psd":
            self.export_psd_dialog()

    def _default_output_path(self, name: str) -> str:
        if self.project_path is not None:
            return str(self.project_path.parent / name)
        return str(Path.home() / name)

    def export_png_dialog(self) -> None:
        self._export_dialog(
            "PNG image (*.png)",
            "PXCOMP-composite.png",
            lambda p, o: export_png(self.project, o, p),
        )

    def export_jpeg_dialog(self) -> None:
        self._export_dialog(
            "JPEG image (*.jpg *.jpeg)",
            "PXCOMP-composite.jpg",
            lambda p, o: export_jpeg(self.project, o, p),
        )

    def export_tiff_dialog(self, bit_depth: int) -> None:
        self._export_dialog(
            "TIFF image (*.tif *.tiff)",
            f"PXCOMP-composite-{bit_depth}bit.tif",
            lambda p, o: export_tiff(self.project, o, p, bit_depth=bit_depth),
        )

    def export_psd_dialog(self) -> None:
        self._export_dialog(
            "Photoshop document (*.psd)",
            "PXCOMP-composite-layered.psd",
            lambda p, o: export_psd(self.project, o, p),
        )

    def _export_dialog(self, file_filter: str, default_name: str, exporter) -> None:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Export",
            self._default_output_path(default_name),
            file_filter,
        )
        if not path:
            return
        try:
            owners = self._ensure_owners()
            self._set_busy(f"Rendering full-resolution export: {Path(path).name} …")
            exporter(path, owners)
            self._set_status(f"Export complete: {path}")
        except Exception as exc:
            self._show_error("Export failed", exc)

    def _set_busy(self, message: str) -> None:
        self.status_message.setText(message)
        self.progress.show()
        if not self._busy:
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
            self._busy = True
        QtWidgets.QApplication.processEvents()

    def _set_status(self, message: str) -> None:
        self.status_message.setText(message)
        self.progress.hide()
        if self._busy:
            QtWidgets.QApplication.restoreOverrideCursor()
            self._busy = False
        QtWidgets.QApplication.processEvents()

    def _show_error(self, title: str, exc: Exception) -> None:
        details = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        self._set_status(f"{title}: {details}")
        QtWidgets.QMessageBox.critical(self, title, details)
