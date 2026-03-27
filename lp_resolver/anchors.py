# SPDX-FileCopyrightText: 2026 ParticleTroned
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

from math import isfinite
from typing import Any, Mapping

LP_POINT_KEY_HINTS = ("point", "points", "offset", "position", "pos", "anchor", "location", "coord")
LP_NODE_KEY_HINTS = ("node", "nodes")


def normalize_node_name(value: str) -> str:
    return value.strip().lower()


def as_xyz(value: Any) -> tuple[float, float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return None
    try:
        return (float(value[0]), float(value[1]), float(value[2]))
    except (TypeError, ValueError):
        return None


def as_xyz_mapping(value: Any) -> tuple[float, float, float] | None:
    if not isinstance(value, dict):
        return None
    x = value.get("x", value.get("X"))
    y = value.get("y", value.get("Y"))
    z = value.get("z", value.get("Z"))
    if x is None or y is None or z is None:
        return None
    try:
        return (float(x), float(y), float(z))
    except (TypeError, ValueError):
        return None


def extract_points_from_value(value: Any) -> list[tuple[float, float, float]]:
    points: list[tuple[float, float, float]] = []
    mapping_point = as_xyz_mapping(value)
    if mapping_point is not None:
        points.append(mapping_point)
        return points
    if isinstance(value, list):
        single = as_xyz(value)
        if single is not None:
            points.append(single)
        else:
            for item in value:
                points.extend(extract_points_from_value(item))
    return points


def iter_lights_lists(value: Any):
    if isinstance(value, dict):
        for key, child in value.items():
            key_l = str(key).lower()
            if key_l in {"lights", "light"}:
                if isinstance(child, list):
                    yield child
                elif isinstance(child, dict):
                    yield [child]
            yield from iter_lights_lists(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_lights_lists(child)


def extract_nodes(value: Any) -> set[str]:
    nodes: set[str] = set()
    if isinstance(value, str):
        if value.strip():
            nodes.add(normalize_node_name(value))
        return nodes
    if not isinstance(value, list):
        return nodes
    for item in value:
        if isinstance(item, str) and item.strip():
            nodes.add(normalize_node_name(item))
    return nodes


def is_finite_point(point: tuple[float, float, float]) -> bool:
    return isfinite(point[0]) and isfinite(point[1]) and isfinite(point[2])


def sanitize_points(points: list[tuple[float, float, float]]) -> list[tuple[float, float, float]]:
    cleaned: list[tuple[float, float, float]] = []
    for point in points:
        if is_finite_point(point):
            cleaned.append((float(point[0]), float(point[1]), float(point[2])))
    return cleaned


def dedupe_points(points: list[tuple[float, float, float]]) -> list[tuple[float, float, float]]:
    result: list[tuple[float, float, float]] = []
    seen: set[tuple[float, float, float]] = set()
    for point in points:
        key = (round(point[0], 4), round(point[1], 4), round(point[2], 4))
        if key in seen:
            continue
        seen.add(key)
        result.append(point)
    return result


def to_positive_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not isfinite(number):
        return None
    if number <= 0.0:
        return None
    return number


def estimate_entry_radius_units(settings: Mapping[str, Any]) -> float | None:
    radii: list[float] = []

    def _walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                key_l = str(key).lower()
                if key_l == "radius":
                    radius = to_positive_float(child)
                    if radius is not None:
                        radii.append(radius)
                elif key_l == "size":
                    size = to_positive_float(child)
                    if size is not None:
                        # Keep compatibility with previous preview/conflict scale heuristic.
                        radii.append(size * 12.0)
                _walk(child)
            return
        if isinstance(value, list):
            for child in value:
                _walk(child)

    _walk(settings)
    if not radii:
        return None
    return sum(radii) / len(radii)


def extract_lp_anchor_points(settings: Mapping[str, Any]) -> list[tuple[float, float, float]]:
    payload = dict(settings)
    points: list[tuple[float, float, float]] = []

    for lights in iter_lights_lists(payload):
        for light in lights:
            if not isinstance(light, dict):
                continue
            points.extend(extract_points_from_value(light.get("points")))
            points.extend(extract_points_from_value(light.get("point")))
            data = light.get("data")
            if isinstance(data, dict):
                points.extend(extract_points_from_value(data.get("offset")))
                # Compatibility with non-standard LP schemas seen in the wild.
                points.extend(extract_points_from_value(data.get("position")))
                points.extend(extract_points_from_value(data.get("pos")))

    # Fallback for non-standard LP schemas where anchors are not under lights[].
    def _walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                key_l = str(key).lower()
                if any(hint in key_l for hint in LP_POINT_KEY_HINTS):
                    points.extend(extract_points_from_value(child))
                _walk(child)
            return
        if isinstance(value, list):
            for child in value:
                _walk(child)

    _walk(payload)
    return dedupe_points(sanitize_points(points))


def extract_lp_anchor_nodes(settings: Mapping[str, Any]) -> set[str]:
    payload = dict(settings)
    nodes: set[str] = set()

    for lights in iter_lights_lists(payload):
        for light in lights:
            if not isinstance(light, dict):
                continue
            nodes |= extract_nodes(light.get("nodes"))
            nodes |= extract_nodes(light.get("node"))

    # Fallback for non-standard LP schemas where nodes are outside lights[].
    def _walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                key_l = str(key).lower()
                if any(hint in key_l for hint in LP_NODE_KEY_HINTS):
                    nodes.update(extract_nodes(child))
                _walk(child)
            return
        if isinstance(value, list):
            for child in value:
                _walk(child)

    _walk(payload)
    return nodes
