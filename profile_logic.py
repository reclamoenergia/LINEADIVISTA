# -*- coding: utf-8 -*-
import math
import os
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from qgis.core import (
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsRasterLayer,
    QgsRaster,
    QgsUnitTypes,
    QgsVectorLayer,
    QgsWkbTypes,
)


INVALID_NAME_PATTERN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


@dataclass
class ProfileData:
    distances: List[float]
    terrain_elevations: List[float]
    observer_point: QgsPointXY
    end_point: QgsPointXY


@dataclass
class VisibilityResult:
    screening_index: int
    screening_angle: float
    line_to_object_top_clearance: List[float]
    visible_base_ratio: float


def sanitize_filename(text: str) -> str:
    clean = INVALID_NAME_PATTERN.sub("_", str(text)).strip().strip(".")
    clean = re.sub(r"\s+", "_", clean)
    return clean[:120] if clean else ""


def unique_output_path(folder: str, base_name: str, used: set) -> str:
    candidate = base_name
    i = 1
    while candidate.lower() in used or os.path.exists(os.path.join(folder, f"{candidate}.png")):
        candidate = f"{base_name}_{i}"
        i += 1
    used.add(candidate.lower())
    return os.path.join(folder, f"{candidate}.png")


def layer_is_single_line(layer: QgsVectorLayer) -> bool:
    if not layer or layer.geometryType() != QgsWkbTypes.LineGeometry:
        return False
    return True


def extract_line_geometries(layer: QgsVectorLayer, only_selected: bool) -> List[QgsFeature]:
    feats = list(layer.selectedFeatures()) if only_selected else list(layer.getFeatures())
    return feats


def assert_dem_metric(dem_layer: QgsRasterLayer):
    unit = dem_layer.crs().mapUnits()
    if unit != QgsUnitTypes.DistanceMeters:
        raise ValueError("DEM CRS must use metric (meters) map units.")


def transform_geometry_to_dem_crs(geom: QgsGeometry, source_crs, dem_crs) -> QgsGeometry:
    if source_crs == dem_crs:
        return QgsGeometry(geom)
    tr = QgsProject.instance().transformContext()
    from qgis.core import QgsCoordinateTransform

    ct = QgsCoordinateTransform(source_crs, dem_crs, tr)
    g = QgsGeometry(geom)
    g.transform(ct)
    return g


def geometry_to_vertices(geom: QgsGeometry) -> List[QgsPointXY]:
    if geom.isEmpty():
        raise ValueError("Empty geometry is not supported.")
    if geom.isMultipart():
        raise ValueError("Multipart geometries are not supported.")

    if QgsWkbTypes.flatType(geom.wkbType()) not in (QgsWkbTypes.LineString, QgsWkbTypes.LineStringZ, QgsWkbTypes.LineStringM, QgsWkbTypes.LineStringZM):
        raise ValueError("Only single continuous line geometries are supported.")

    line = geom.asPolyline()
    if len(line) < 2:
        raise ValueError("Line geometry must have at least two vertices.")
    return [QgsPointXY(p) for p in line]


def _sample_raster_cell_value(dem_layer: QgsRasterLayer, point: QgsPointXY) -> Optional[float]:
    provider = dem_layer.dataProvider()
    ident = provider.identify(point, QgsRaster.IdentifyFormatValue)
    if not ident.isValid():
        return None
    values = ident.results()
    if 1 not in values:
        return None
    value = values[1]
    if value is None:
        return None
    try:
        fv = float(value)
    except Exception:
        return None
    if math.isnan(fv):
        return None
    nodata = provider.sourceNoDataValue(1)
    if nodata is not None and not math.isnan(nodata) and math.isclose(fv, nodata, rel_tol=0.0, abs_tol=1e-9):
        return None
    return fv


def _line_length(points: List[QgsPointXY]) -> float:
    total = 0.0
    for i in range(1, len(points)):
        dx = points[i].x() - points[i - 1].x()
        dy = points[i].y() - points[i - 1].y()
        total += math.hypot(dx, dy)
    return total


def _point_at_distance(points: List[QgsPointXY], distance: float) -> QgsPointXY:
    if distance <= 0:
        return QgsPointXY(points[0])
    traversed = 0.0
    for i in range(1, len(points)):
        p1 = points[i - 1]
        p2 = points[i]
        seg = math.hypot(p2.x() - p1.x(), p2.y() - p1.y())
        if traversed + seg >= distance:
            ratio = (distance - traversed) / seg if seg > 0 else 0.0
            x = p1.x() + (p2.x() - p1.x()) * ratio
            y = p1.y() + (p2.y() - p1.y()) * ratio
            return QgsPointXY(x, y)
        traversed += seg
    return QgsPointXY(points[-1])


def extract_profile_from_points(dem_layer: QgsRasterLayer, points: List[QgsPointXY], step: float) -> ProfileData:
    total_len = _line_length(points)
    if total_len <= 0:
        raise ValueError("Profile line has zero length.")

    distances = [0.0]
    d = step
    while d < total_len:
        distances.append(d)
        d += step
    if not math.isclose(distances[-1], total_len, abs_tol=1e-6):
        distances.append(total_len)

    elevations = []
    for dist in distances:
        pt = _point_at_distance(points, dist)
        val = _sample_raster_cell_value(dem_layer, pt)
        if val is None:
            raise ValueError(f"NoData encountered along profile at distance {dist:.2f} m.")
        elevations.append(val)

    return ProfileData(
        distances=distances,
        terrain_elevations=elevations,
        observer_point=points[0],
        end_point=points[-1],
    )


def compute_visibility(profile: ProfileData, observer_height: float, object_top_elev: float) -> VisibilityResult:
    obs_elev = profile.terrain_elevations[0] + observer_height
    angles = []
    for i in range(1, len(profile.distances) - 1):
        dist = profile.distances[i]
        if dist <= 0:
            angles.append(-math.inf)
        else:
            ang = math.atan2(profile.terrain_elevations[i] - obs_elev, dist)
            angles.append(ang)
    if angles:
        max_idx_local = max(range(len(angles)), key=lambda i: angles[i])
        screening_index = max_idx_local + 1
        screening_angle = angles[max_idx_local]
    else:
        screening_index = 0
        screening_angle = -math.inf

    total_dist = profile.distances[-1]
    slope_to_top = (object_top_elev - obs_elev) / total_dist if total_dist > 0 else 0.0
    clearances = []
    for dist, terr in zip(profile.distances, profile.terrain_elevations):
        los_elev = obs_elev + slope_to_top * dist
        clearances.append(los_elev - terr)

    object_base = profile.terrain_elevations[-1]
    obj_h = max(0.0, object_top_elev - object_base)
    slope_to_base = (object_base - obs_elev) / total_dist if total_dist > 0 else 0.0
    max_angle = screening_angle
    base_angle = math.atan2(object_base - obs_elev, total_dist) if total_dist > 0 else -math.pi / 2
    top_angle = math.atan2(object_top_elev - obs_elev, total_dist) if total_dist > 0 else math.pi / 2

    if obj_h <= 0:
        ratio = 0.0
    elif max_angle <= base_angle:
        ratio = 1.0
    elif max_angle >= top_angle:
        ratio = 0.0
    else:
        visible_y = obs_elev + math.tan(max_angle) * total_dist
        ratio = max(0.0, min(1.0, (object_top_elev - visible_y) / obj_h))

    return VisibilityResult(
        screening_index=screening_index,
        screening_angle=max_angle,
        line_to_object_top_clearance=clearances,
        visible_base_ratio=ratio,
    )


def dem_pixel_step(dem_layer: QgsRasterLayer) -> float:
    return min(abs(dem_layer.rasterUnitsPerPixelX()), abs(dem_layer.rasterUnitsPerPixelY()))


def feature_label(feature: QgsFeature, field_name: str, fallback: str) -> str:
    if not field_name:
        return fallback
    value = feature[field_name]
    if value is None:
        return fallback
    txt = str(value).strip()
    return txt if txt else fallback
