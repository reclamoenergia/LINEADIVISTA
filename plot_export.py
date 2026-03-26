# -*- coding: utf-8 -*-
import math
from dataclasses import dataclass
from typing import Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .profile_logic import ProfileData, VisibilityResult


@dataclass
class ObjectSpec:
    kind: str  # obstacle | turbine
    obstacle_height: float = 0.0
    hub_height: float = 0.0
    rotor_diameter: float = 0.0


def _object_top_elevation(profile: ProfileData, obj: ObjectSpec) -> float:
    ground = profile.terrain_elevations[-1]
    if obj.kind == "turbine":
        return ground + max(0.0, obj.hub_height + (obj.rotor_diameter / 2.0))
    return ground + max(0.0, obj.obstacle_height)


def render_profile_png(
    output_path: str,
    profile: ProfileData,
    visibility: VisibilityResult,
    observer_height: float,
    observer_label: str,
    obj: ObjectSpec,
):
    width_px, height_px = 3200, 1200
    dpi = 100
    fig = plt.figure(figsize=(width_px / dpi, height_px / dpi), dpi=dpi)
    ax = fig.add_axes([0.08, 0.12, 0.88, 0.80])

    x = profile.distances
    y = profile.terrain_elevations
    observer_y = y[0] + observer_height
    end_x = x[-1]
    object_ground = y[-1]
    object_top = _object_top_elevation(profile, obj)

    x_max_content = max(end_x, _object_x_max(end_x, obj), _sight_lines_x_max(x, visibility))
    x_span = max(1.0, x_max_content)
    object_overhang = max(0.0, _object_x_max(end_x, obj) - end_x)
    x_padding = max(1.0, x_span * 0.01, object_overhang * 0.10)
    x_max_plot = x_max_content + x_padding
    x_range = x_max_plot

    ax.set_xlim(0, x_max_plot)

    target_ratio = (width_px * 0.88) / (height_px * 0.80)
    y_min_plot = 0.0
    y_max_content = max(max(y), observer_y, object_top)
    y_padding = max(1.0, (y_max_content - y_min_plot) * 0.03)
    required_y_range = x_range / target_ratio if x_range > 0 else max(1.0, y_max_content - y_min_plot)
    y_max_plot = max(y_max_content + y_padding, y_min_plot + required_y_range)
    ax.set_ylim(y_min_plot, y_max_plot)

    ax.plot(x, y, color="#1f1f1f", linewidth=2.2, label="Terrain profile", zorder=3)

    # Observer marker and label
    ax.scatter([0], [observer_y], color="#0d6efd", s=50, zorder=6)
    ax.text(0 + x_range * 0.01, observer_y + (y_max_plot - y_min_plot) * 0.02, observer_label, color="#0d6efd", fontsize=11)

    # Screening point
    si = visibility.screening_index
    if 0 <= si < len(x):
        sx, sy = x[si], y[si]
        ax.scatter([sx], [sy], color="#ff7f0e", s=35, zorder=6)
        ax.plot([0, sx], [observer_y, sy], color="#ff7f0e", linewidth=1.3, alpha=0.7, zorder=2)

    # Sight line to object top with hidden segment dashed
    clearance = visibility.line_to_object_top_clearance
    dash_from = None
    for i in range(1, len(clearance) - 1):
        if clearance[i] < 0:
            dash_from = x[i]
            break
    if dash_from is None:
        ax.plot([0, end_x], [observer_y, object_top], color="#4d4d4d", linewidth=1.2, alpha=0.7, zorder=2)
    else:
        y_dash = observer_y + ((object_top - observer_y) * (dash_from / end_x if end_x else 0))
        ax.plot([0, dash_from], [observer_y, y_dash], color="#4d4d4d", linewidth=1.2, alpha=0.7, zorder=2)
        ax.plot([dash_from, end_x], [y_dash, object_top], color="#4d4d4d", linewidth=1.2, alpha=0.9, linestyle="--", zorder=2)

    # Final object rendering with hidden part dashed
    visible_ratio = visibility.visible_base_ratio
    visible_ratio = max(0.0, min(1.0, visible_ratio))
    hidden_ratio = 1.0 - visible_ratio

    if obj.kind == "turbine":
        _draw_turbine(ax, end_x, object_ground, obj, visible_ratio)
    else:
        _draw_vertical_obstacle(ax, end_x, object_ground, object_top, visible_ratio)

    ax.set_xlabel("Distance (m)")
    ax.set_ylabel("Elevation (m)")
    ax.set_xticks(_ticks(0, x_max_plot, 500))
    ymin, ymax = ax.get_ylim()
    ax.set_yticks(_ticks(math.floor(ymin / 100) * 100, math.ceil(ymax / 100) * 100, 100))
    ax.grid(True, color="#d3d3d3", linewidth=0.6)
    ax.set_title("Orographic Profile and Visibility")

    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)


def _draw_vertical_obstacle(ax, x, base, top, visible_ratio):
    visible_start = top - (top - base) * visible_ratio
    if visible_ratio > 0:
        ax.plot([x, x], [visible_start, top], color="#c1121f", linewidth=2.4, zorder=5)
    if visible_ratio < 1:
        ax.plot([x, x], [base, visible_start], color="#c1121f", linewidth=2.4, linestyle="--", zorder=5)


def _draw_turbine(ax, x, ground, obj: ObjectSpec, visible_ratio):
    hub = ground + max(0.0, obj.hub_height)
    radius = max(0.0, obj.rotor_diameter / 2.0)
    top = hub + radius
    visible_start = top - (top - ground) * visible_ratio

    def seg(y1, y2, lw=2.2):
        low, high = min(y1, y2), max(y1, y2)
        if visible_ratio >= 1:
            ax.plot([x, x], [y1, y2], color="#c1121f", linewidth=lw, zorder=5)
            return
        if visible_ratio <= 0:
            ax.plot([x, x], [y1, y2], color="#c1121f", linewidth=lw, linestyle="--", zorder=5)
            return
        vis_low = max(low, visible_start)
        if vis_low > low:
            ax.plot([x, x], [low, vis_low], color="#c1121f", linewidth=lw, linestyle="--", zorder=5)
        if high > vis_low:
            ax.plot([x, x], [vis_low, high], color="#c1121f", linewidth=lw, zorder=5)

    # Tower, with bolder line
    seg(ground, hub, lw=3.0)

    # Three blades: one vertical up, two symmetric at +/-120 degrees
    blade_angles = [90, 210, 330]
    for ang in blade_angles:
        rad = math.radians(ang)
        dx = radius * math.cos(rad)
        dy = radius * math.sin(rad)
        x2 = x + dx
        y2 = hub + dy
        if x2 == x:
            # purely vertical blade
            seg(hub, y2, lw=1.8)
        else:
            style = "-" if visible_ratio > 0 else "--"
            ax.plot([x, x2], [hub, y2], color="#c1121f", linewidth=1.5, linestyle=style, zorder=5)


def _object_x_max(x: float, obj: ObjectSpec) -> float:
    if obj.kind != "turbine":
        return x
    radius = max(0.0, obj.rotor_diameter / 2.0)
    blade_angles = [90, 210, 330]
    blade_x = [x + radius * math.cos(math.radians(ang)) for ang in blade_angles]
    return max([x] + blade_x)


def _sight_lines_x_max(x, visibility: VisibilityResult) -> float:
    if len(x) == 0:
        return 0.0
    candidates = [x[-1]]
    si = visibility.screening_index
    if 0 <= si < len(x):
        candidates.append(x[si])
    return max(candidates)


def _ticks(start, end, step):
    if step <= 0:
        return []
    vals = []
    v = start
    count = 0
    while v <= end + 1e-9 and count < 10000:
        vals.append(v)
        v += step
        count += 1
    return vals
