# LineaDiVista QGIS Plugin

LineaDiVista is a QGIS 3.28+ plugin that extracts orographic terrain profiles from a DEM and exports fixed-size PNG technical plots with observer/object visibility analysis.

## Implemented capabilities

- DEM-driven profile sampling (step = DEM pixel resolution).
- Cell value extraction via raster identify (no bilinear interpolation).
- Manual mode: draw a line on map canvas (click order controls direction).
- Layer mode: process line features from any loaded line vector layer.
- Optional "selected features only" processing in layer mode.
- Multipart geometry rejection.
- NoData interruption with explicit error reporting.
- Batch output naming from a selected field with fallback, sanitization, and duplicate suffixing.
- Observer at first profile point with configurable observer height (default 1.60 m).
- Final object at profile endpoint:
  - Vertical obstacle (height)
  - Wind turbine (hub height + rotor diameter, 3 blades at 120°)
- Visibility logic:
  - Most screening terrain point = max elevation angle from observer.
  - Draws observer→object-top line and observer→screening-point line.
  - Hidden object portions dashed.
  - Hidden sight-line segment dashed.
- PNG export: exactly `3200x1200`, technical style, axes, grid (500 m x / 100 m y), and 1:1 geometric scale preserved.

## Plugin structure

- `metadata.txt` - QGIS plugin metadata.
- `__init__.py` - plugin entry point.
- `lineadivista_plugin.py` - plugin bootstrap, toolbar/menu action.
- `lineadivista_dialog.py` - full UI/workflow and validation.
- `map_tools.py` - manual polyline map tool.
- `profile_logic.py` - geometry/profile extraction, visibility, naming helpers.
- `plot_export.py` - matplotlib rendering/export.

## Installation in QGIS

1. Copy this folder (`LINEADIVISTA`) into your QGIS profile plugins directory, e.g.:
   - Linux: `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/LINEADIVISTA`
   - Windows: `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\LINEADIVISTA`
2. Ensure `matplotlib` is available in your QGIS Python environment.
3. Open QGIS → **Plugins** → **Manage and Install Plugins** → enable **LineaDiVista**.

## Basic usage

1. Load a metric DEM raster and (optionally) a line vector layer.
2. Open **LineaDiVista** from toolbar/menu.
3. Select DEM.
4. Choose profile source mode:
   - Manual draw: draw line, set observer label text, set output PNG path.
   - Line layer: choose line layer, optional selected-only, filename field, observer label field, output folder.
5. Set observer height.
6. Choose final object type and dimensions.
7. Click **Run**.

## Notes and assumptions

- DEM CRS must be in meters.
- In layer mode, errors on one or more features are collected and reported after attempting all features.
- Only single-part, single continuous line geometries are accepted.
