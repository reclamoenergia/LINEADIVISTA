# -*- coding: utf-8 -*-
import os
from pathlib import Path

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QDoubleSpinBox,
    QVBoxLayout,
    QWidget,
)
from qgis.core import QgsProject, QgsRasterLayer, QgsVectorLayer

from .map_tools import ManualLineMapTool
from .plot_export import ObjectSpec, render_profile_png
from .profile_logic import (
    assert_dem_metric,
    compute_visibility,
    dem_pixel_step,
    extract_line_geometries,
    extract_profile_from_points,
    feature_label,
    geometry_to_vertices,
    layer_is_single_line,
    sanitize_filename,
    transform_geometry_to_dem_crs,
    unique_output_path,
)


class LineaDiVistaDialog(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent or iface.mainWindow())
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.setWindowTitle("LineaDiVista")
        self.resize(720, 620)

        self.manual_geom = None
        self.manual_tool = ManualLineMapTool(self.canvas)
        self.previous_map_tool = None
        self.manual_tool.lineCompleted.connect(self._on_manual_line_complete)
        self.manual_tool.canceled.connect(self._on_manual_canceled)

        self._build_ui()
        self._connect_signals()
        self.refresh_layers()

    def closeEvent(self, event):
        self._stop_draw_mode()
        super().closeEvent(event)

    def _build_ui(self):
        root = QVBoxLayout(self)

        # DEM
        dem_box = QGroupBox("DEM")
        dem_form = QFormLayout(dem_box)
        self.dem_combo = QComboBox()
        dem_form.addRow("DEM raster:", self.dem_combo)
        root.addWidget(dem_box)

        # Mode
        mode_box = QGroupBox("Profile Source")
        mode_layout = QHBoxLayout(mode_box)
        self.manual_radio = QRadioButton("Manual draw")
        self.layer_radio = QRadioButton("Line layer")
        self.manual_radio.setChecked(True)
        mode_layout.addWidget(self.manual_radio)
        mode_layout.addWidget(self.layer_radio)
        root.addWidget(mode_box)

        self.stack_manual = self._build_manual_group()
        self.stack_layer = self._build_layer_group()
        root.addWidget(self.stack_manual)
        root.addWidget(self.stack_layer)

        # Observer/object
        params_box = QGroupBox("Observer and Final Object")
        params_form = QFormLayout(params_box)

        self.observer_height = QDoubleSpinBox()
        self.observer_height.setRange(0.0, 200.0)
        self.observer_height.setValue(1.60)
        self.observer_height.setDecimals(2)
        self.observer_height.setSuffix(" m")
        params_form.addRow("Observer height:", self.observer_height)

        self.object_type = QComboBox()
        self.object_type.addItem("Vertical obstacle", "obstacle")
        self.object_type.addItem("Wind turbine", "turbine")
        params_form.addRow("Object type:", self.object_type)

        self.obstacle_height = QDoubleSpinBox()
        self.obstacle_height.setRange(0.0, 3000.0)
        self.obstacle_height.setValue(50.0)
        self.obstacle_height.setSuffix(" m")
        params_form.addRow("Obstacle height:", self.obstacle_height)

        self.hub_height = QDoubleSpinBox()
        self.hub_height.setRange(0.0, 3000.0)
        self.hub_height.setValue(90.0)
        self.hub_height.setSuffix(" m")
        params_form.addRow("Hub height:", self.hub_height)

        self.rotor_diameter = QDoubleSpinBox()
        self.rotor_diameter.setRange(0.0, 2000.0)
        self.rotor_diameter.setValue(120.0)
        self.rotor_diameter.setSuffix(" m")
        params_form.addRow("Rotor diameter:", self.rotor_diameter)
        root.addWidget(params_box)

        # Actions
        btns = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh layers")
        self.run_btn = QPushButton("Run")
        self.close_btn = QPushButton("Close")
        btns.addWidget(self.refresh_btn)
        btns.addStretch(1)
        btns.addWidget(self.run_btn)
        btns.addWidget(self.close_btn)
        root.addLayout(btns)

        self._update_mode_ui()
        self._update_object_ui()

    def _build_manual_group(self):
        box = QGroupBox("Manual mode")
        form = QFormLayout(box)
        self.draw_btn = QPushButton("Draw line on canvas")
        self.draw_status = QLabel("No line captured")
        self.draw_status.setStyleSheet("color: #666;")
        self.manual_label = QLineEdit("Observer")

        path_row = QWidget()
        path_layout = QHBoxLayout(path_row)
        path_layout.setContentsMargins(0, 0, 0, 0)
        self.manual_output_path = QLineEdit()
        self.manual_browse_file = QPushButton("Browse")
        path_layout.addWidget(self.manual_output_path)
        path_layout.addWidget(self.manual_browse_file)

        form.addRow("Draw:", self.draw_btn)
        form.addRow("Status:", self.draw_status)
        form.addRow("Observer label:", self.manual_label)
        form.addRow("Output PNG:", path_row)
        return box

    def _build_layer_group(self):
        box = QGroupBox("Layer mode")
        form = QFormLayout(box)
        self.line_layer_combo = QComboBox()
        self.selected_only = QCheckBox("Process selected features only")
        self.filename_field_combo = QComboBox()
        self.label_field_combo = QComboBox()

        folder_row = QWidget()
        folder_layout = QHBoxLayout(folder_row)
        folder_layout.setContentsMargins(0, 0, 0, 0)
        self.output_folder = QLineEdit()
        self.browse_folder = QPushButton("Browse")
        folder_layout.addWidget(self.output_folder)
        folder_layout.addWidget(self.browse_folder)

        form.addRow("Line layer:", self.line_layer_combo)
        form.addRow("", self.selected_only)
        form.addRow("Filename field:", self.filename_field_combo)
        form.addRow("Observer label field:", self.label_field_combo)
        form.addRow("Output folder:", folder_row)
        return box

    def _connect_signals(self):
        self.close_btn.clicked.connect(self.close)
        self.refresh_btn.clicked.connect(self.refresh_layers)
        self.manual_radio.toggled.connect(self._update_mode_ui)
        self.layer_radio.toggled.connect(self._update_mode_ui)
        self.object_type.currentIndexChanged.connect(self._update_object_ui)
        self.draw_btn.clicked.connect(self._start_draw_mode)
        self.manual_browse_file.clicked.connect(self._choose_manual_file)
        self.browse_folder.clicked.connect(self._choose_folder)
        self.line_layer_combo.currentIndexChanged.connect(self._refresh_layer_fields)
        self.run_btn.clicked.connect(self.run_processing)

    def _update_mode_ui(self):
        manual = self.manual_radio.isChecked()
        self.stack_manual.setVisible(manual)
        self.stack_layer.setVisible(not manual)

    def _update_object_ui(self):
        is_turbine = self.object_type.currentData() == "turbine"
        self.obstacle_height.setEnabled(not is_turbine)
        self.hub_height.setEnabled(is_turbine)
        self.rotor_diameter.setEnabled(is_turbine)

    def refresh_layers(self):
        self.dem_combo.clear()
        self.line_layer_combo.clear()

        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsRasterLayer):
                self.dem_combo.addItem(layer.name(), layer.id())
            elif isinstance(layer, QgsVectorLayer) and layer_is_single_line(layer):
                self.line_layer_combo.addItem(layer.name(), layer.id())

        self._refresh_layer_fields()

    def _layer_by_combo(self, combo) -> object:
        layer_id = combo.currentData()
        return QgsProject.instance().mapLayer(layer_id) if layer_id else None

    def _refresh_layer_fields(self):
        self.filename_field_combo.clear()
        self.label_field_combo.clear()
        layer = self._layer_by_combo(self.line_layer_combo)
        if not layer:
            return
        for f in layer.fields():
            self.filename_field_combo.addItem(f.name())
            self.label_field_combo.addItem(f.name())

    def _start_draw_mode(self):
        self.previous_map_tool = self.canvas.mapTool()
        self.canvas.setMapTool(self.manual_tool)
        self.draw_status.setText("Drawing... left-click to add vertices, right-click to finish")

    def _stop_draw_mode(self):
        if self.canvas.mapTool() == self.manual_tool:
            self.canvas.unsetMapTool(self.manual_tool)
        if self.previous_map_tool:
            self.canvas.setMapTool(self.previous_map_tool)
            self.previous_map_tool = None

    def _on_manual_line_complete(self, geom):
        self.manual_geom = geom
        self.draw_status.setText("Line captured")
        self._stop_draw_mode()

    def _on_manual_canceled(self):
        self.draw_status.setText("Drawing canceled")
        self._stop_draw_mode()

    def _choose_manual_file(self):
        path, _ = QFileDialog.getSaveFileName(self, "Choose output PNG", "", "PNG (*.png)")
        if path:
            if not path.lower().endswith(".png"):
                path += ".png"
            self.manual_output_path.setText(path)

    def _choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose output folder")
        if folder:
            self.output_folder.setText(folder)

    def _current_object_spec(self) -> ObjectSpec:
        return ObjectSpec(
            kind=self.object_type.currentData(),
            obstacle_height=self.obstacle_height.value(),
            hub_height=self.hub_height.value(),
            rotor_diameter=self.rotor_diameter.value(),
        )

    def _require_dem(self):
        dem = self._layer_by_combo(self.dem_combo)
        if not dem:
            raise ValueError("Please select a DEM raster.")
        assert_dem_metric(dem)
        return dem

    def run_processing(self):
        try:
            dem = self._require_dem()
            step = dem_pixel_step(dem)
            if step <= 0:
                raise ValueError("Invalid DEM resolution.")
            if self.manual_radio.isChecked():
                self._run_manual(dem, step)
            else:
                self._run_layer_mode(dem, step)
            QMessageBox.information(self, "LineaDiVista", "Processing completed.")
        except Exception as ex:
            QMessageBox.critical(self, "LineaDiVista", str(ex))

    def _profile_and_export(self, dem, points, output_path, observer_label):
        profile = extract_profile_from_points(dem, points, step=dem_pixel_step(dem))
        obj = self._current_object_spec()
        object_ground = profile.terrain_elevations[-1]
        if obj.kind == "turbine":
            top = object_ground + obj.hub_height + obj.rotor_diameter / 2.0
        else:
            top = object_ground + obj.obstacle_height
        vis = compute_visibility(profile, self.observer_height.value(), top)
        render_profile_png(
            output_path=output_path,
            profile=profile,
            visibility=vis,
            observer_height=self.observer_height.value(),
            observer_label=observer_label,
            obj=obj,
        )

    def _run_manual(self, dem, step):
        if not self.manual_geom:
            raise ValueError("Please draw a manual line first.")
        output_path = self.manual_output_path.text().strip()
        if not output_path:
            raise ValueError("Please choose an output PNG path.")

        geom = transform_geometry_to_dem_crs(self.manual_geom, self.canvas.mapSettings().destinationCrs(), dem.crs())
        points = geometry_to_vertices(geom)
        label = self.manual_label.text().strip() or "Observer"
        self._profile_and_export(dem, points, output_path, label)

    def _run_layer_mode(self, dem, step):
        layer = self._layer_by_combo(self.line_layer_combo)
        if not layer:
            raise ValueError("Please select a linear vector layer.")
        if not layer_is_single_line(layer):
            raise ValueError("Layer must be a line geometry layer.")
        folder = self.output_folder.text().strip()
        if not folder:
            raise ValueError("Please select an output folder.")
        if not os.path.isdir(folder):
            raise ValueError("Output folder does not exist.")

        features = extract_line_geometries(layer, self.selected_only.isChecked())
        if not features:
            raise ValueError("No features to process.")

        name_field = self.filename_field_combo.currentText()
        label_field = self.label_field_combo.currentText()
        used = set()
        fallback_counter = 1
        errors = []

        for ft in features:
            try:
                geom = transform_geometry_to_dem_crs(ft.geometry(), layer.crs(), dem.crs())
                points = geometry_to_vertices(geom)

                raw_name = feature_label(ft, name_field, f"auto_{fallback_counter:03d}")
                safe = sanitize_filename(raw_name)
                if not safe:
                    safe = f"auto_{fallback_counter:03d}"
                fallback_counter += 1
                out = unique_output_path(folder, f"lineadivista_{safe}", used)

                label = feature_label(ft, label_field, "Observer")
                self._profile_and_export(dem, points, out, label)
            except Exception as ex:
                errors.append(f"Feature {ft.id()}: {ex}")

        if errors:
            raise ValueError("Some features failed:\n" + "\n".join(errors))
