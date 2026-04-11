# SPDX-FileCopyrightText: 2026 ParticleTroned
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

from html import escape
import json
import sys
from math import dist, isfinite
from pathlib import Path
from typing import Any

from . import __version__
from .anchors import (
    dedupe_points as _dedupe_points,
    estimate_entry_radius_units as _estimate_entry_radius_units,
    extract_lp_anchor_nodes as _extract_lp_anchor_nodes,
    extract_lp_anchor_points as _extract_lp_anchor_points,
    iter_lights_lists as _iter_lights_lists,
    sanitize_points as _sanitize_points,
    to_positive_float as _to_positive_float,
)
from .decisions import Decision, apply_decisions, load_decisions, make_decision, save_decisions
from .engine import ScanConfig, ScanResult, run_scan
from .formid_preview import (
    FormIDWorldResolution,
    clear_formid_preview_caches,
    resolve_formid_world_resolution,
    transform_local_points_to_world,
)
from .inventory_writer import InventoryExportConfig, InventoryExportResult, write_inventory_reports
from .models import Conflict
from .nif_preview import load_mesh_preview_for_nif, load_nif_bounding_radius_for_nif, load_nif_node_positions_for_nif
from .patch_writer import LightIntensityPatchConfig, write_light_intensity_patch_mod, write_patch_mod
from .priority import choose_keep_highest_entry, entry_priority_sort_key

try:
    from PySide6.QtCore import QItemSelectionModel, QObject, QPointF, QSettings, Qt, QThread, QUrl, Signal, Slot
    from PySide6.QtGui import QColor, QDesktopServices, QGuiApplication, QPainter, QPainterPath, QPalette, QPen, QTextOption
    from PySide6.QtWidgets import (
        QAbstractItemView,
        QApplication,
        QCheckBox,
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QFileDialog,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMenu,
        QMessageBox,
        QPushButton,
        QProxyStyle,
        QHeaderView,
        QSizePolicy,
        QSplitter,
        QStyle,
        QTableWidget,
        QTableWidgetItem,
        QTextEdit,
        QVBoxLayout,
        QWidget,
        QWidgetAction,
        QSlider,
    )
except Exception as exc:  # noqa: BLE001
    detail = f"{type(exc).__name__}: {exc}"
    if getattr(sys, "frozen", False):
        raise RuntimeError(
            "PySide6/Qt runtime could not be loaded from the packaged app. "
            "Ensure the full extracted app folder is present (including _internal\\PySide6 and plugins\\platforms) "
            "and run LPConflictResolver.exe from that folder. "
            f"Details: {detail}"
        ) from exc
    raise RuntimeError(
        "PySide6 is required for GUI mode. Install with: pip install pyside6. "
        f"Details: {detail}"
    ) from exc


_UI_THEME_COLORS: dict[str, dict[str, str]] = {
    "light": {
        "widget_bg": "#eef2f7",
        "widget_text": "#1f2a37",
        "main_bg": "#e8edf5",
        "group_border": "#c7d2e3",
        "group_bg": "#f7f9fc",
        "group_title_text": "#1f3a5f",
        "input_bg": "#ffffff",
        "input_border": "#b9c7db",
        "selection_bg": "#2d6cdf",
        "selection_text": "#ffffff",
        "combo_drop_border": "#b9c7db",
        "combo_drop_bg": "#e3ebf9",
        "button_bg": "#2d6cdf",
        "button_text": "#ffffff",
        "button_border": "#2458b4",
        "button_hover_bg": "#3b7bf2",
        "button_pressed_bg": "#244f9c",
        "button_disabled_bg": "#9fb4d8",
        "button_disabled_text": "#eef3fb",
        "header_bg": "#dde7f5",
        "header_text": "#1f2a37",
        "header_border": "#c4d0e4",
        "table_grid": "#d3dceb",
        "table_alt_bg": "#f5f8fd",
        "checkbox_text": "#1f2a37",
        "splitter_marker": "#1b2d45",
        "splitter_track": "#d0dbec",
        "splitter_hover": "#bccae0",
        "splitter_pressed": "#aabbd7",
        "tooltip_bg": "#1f2a37",
        "tooltip_text": "#f8fafc",
        "tooltip_border": "#4b5f7a",
        "note_text": "#4b5f7a",
        "scan_button_bg": "#2f8a3b",
        "scan_button_border": "#236a2d",
        "scan_button_hover_bg": "#389e46",
        "scan_button_pressed_bg": "#256f30",
        "status_idle_bg": "#fff3c4",
        "status_idle_border": "#d5b54a",
        "status_idle_text": "#5d4700",
        "status_running_bg": "#d5e8ff",
        "status_running_border": "#6f9cd3",
        "status_running_text": "#17395f",
        "status_success_bg": "#d7f1dd",
        "status_success_border": "#4f9b63",
        "status_success_text": "#1f5d30",
        "status_error_bg": "#f8d6d6",
        "status_error_border": "#c36a6a",
        "status_error_text": "#7a1f1f",
    },
    "dark": {
        "widget_bg": "#1d242e",
        "widget_text": "#e8eff9",
        "main_bg": "#161c24",
        "group_border": "#46556d",
        "group_bg": "#242d39",
        "group_title_text": "#dbe7f8",
        "input_bg": "#1a2029",
        "input_border": "#55657f",
        "selection_bg": "#4a86e8",
        "selection_text": "#ffffff",
        "combo_drop_border": "#55657f",
        "combo_drop_bg": "#2b3748",
        "button_bg": "#3f7ee0",
        "button_text": "#ffffff",
        "button_border": "#2f64b2",
        "button_hover_bg": "#4d8ded",
        "button_pressed_bg": "#2f64b2",
        "button_disabled_bg": "#52647f",
        "button_disabled_text": "#d1dceb",
        "header_bg": "#2a3444",
        "header_text": "#e8eff9",
        "header_border": "#55657f",
        "table_grid": "#3d4b61",
        "table_alt_bg": "#212b37",
        "checkbox_text": "#e8eff9",
        "splitter_marker": "#d8e5f8",
        "splitter_track": "#44556e",
        "splitter_hover": "#56698a",
        "splitter_pressed": "#6d84ab",
        "tooltip_bg": "#0f141b",
        "tooltip_text": "#f8fafc",
        "tooltip_border": "#7188aa",
        "note_text": "#adc2df",
        "scan_button_bg": "#3f9f54",
        "scan_button_border": "#2f7a40",
        "scan_button_hover_bg": "#4cb764",
        "scan_button_pressed_bg": "#348547",
        "status_idle_bg": "#655200",
        "status_idle_border": "#c2a63f",
        "status_idle_text": "#ffeaa8",
        "status_running_bg": "#1b3d62",
        "status_running_border": "#6f9cd3",
        "status_running_text": "#d5e9ff",
        "status_success_bg": "#1f4a2b",
        "status_success_border": "#63ad76",
        "status_success_text": "#c4f1d0",
        "status_error_bg": "#5a2424",
        "status_error_border": "#c98787",
        "status_error_text": "#ffd8d8",
    },
}

_UI_STYLESHEET_TEMPLATE = """
QWidget {
    background-color: @widget_bg@;
    color: @widget_text@;
    font-size: 13px;
}
QMainWindow {
    background-color: @main_bg@;
}
QGroupBox {
    border: 1px solid @group_border@;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 8px;
    background-color: @group_bg@;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: @group_title_text@;
}
QLineEdit, QTextEdit, QComboBox, QListWidget, QTableWidget {
    background-color: @input_bg@;
    border: 1px solid @input_border@;
    border-radius: 4px;
    selection-background-color: @selection_bg@;
    selection-color: @selection_text@;
}
QComboBox {
    padding-right: 26px;
}
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 22px;
    border-left: 1px solid @combo_drop_border@;
    background-color: @combo_drop_bg@;
    border-top-right-radius: 4px;
    border-bottom-right-radius: 4px;
}
QComboBox::down-arrow {
    image: none;
    width: 0px;
    height: 0px;
}
QComboBox QAbstractItemView {
    background-color: @input_bg@;
    border: 1px solid @input_border@;
    selection-background-color: @selection_bg@;
    selection-color: @selection_text@;
}
QPushButton {
    background-color: @button_bg@;
    color: @button_text@;
    border: 1px solid @button_border@;
    border-radius: 5px;
    padding: 4px 10px;
}
QPushButton:hover {
    background-color: @button_hover_bg@;
}
QPushButton:pressed {
    background-color: @button_pressed_bg@;
}
QPushButton:disabled {
    background-color: @button_disabled_bg@;
    color: @button_disabled_text@;
}
QPushButton#scanActionButton {
    background-color: @scan_button_bg@;
    border: 1px solid @scan_button_border@;
    font-weight: 700;
}
QPushButton#scanActionButton:hover {
    background-color: @scan_button_hover_bg@;
}
QPushButton#scanActionButton:pressed {
    background-color: @scan_button_pressed_bg@;
}
QHeaderView::section {
    background-color: @header_bg@;
    color: @header_text@;
    border: 1px solid @header_border@;
    padding: 4px;
    font-weight: 600;
}
QTableWidget {
    gridline-color: @table_grid@;
    alternate-background-color: @table_alt_bg@;
}
QCheckBox {
    spacing: 6px;
    color: @checkbox_text@;
}
QCheckBox::indicator {
    width: 14px;
    height: 14px;
}
QSplitter::handle {
    background-color: @splitter_track@;
    border: 1px solid @splitter_track@;
    border-radius: 2px;
}
QSplitter::handle:hover {
    background-color: @splitter_hover@;
    border: 1px solid @splitter_hover@;
}
QSplitter::handle:pressed {
    background-color: @splitter_pressed@;
    border: 1px solid @splitter_pressed@;
}
QSplitter::handle:horizontal {
    width: 10px;
    margin: 0px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 @splitter_track@, stop:0.43 @splitter_track@,
                                stop:0.5 @splitter_marker@, stop:0.57 @splitter_track@, stop:1 @splitter_track@);
}
QSplitter::handle:vertical {
    height: 10px;
    margin: 0px;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 @splitter_track@, stop:0.43 @splitter_track@,
                                stop:0.5 @splitter_marker@, stop:0.57 @splitter_track@, stop:1 @splitter_track@);
}
QToolTip {
    background-color: @tooltip_bg@;
    color: @tooltip_text@;
    border: 1px solid @tooltip_border@;
}
QLabel#lightScaleNoteLabel {
    color: @note_text@;
    font-size: 12px;
}
QLabel#scanSummaryStatusLabel {
    font-size: 13px;
    font-weight: 700;
    border-radius: 4px;
    padding: 3px 8px;
}
QLabel#scanSummaryStatusLabel[scanState="idle"] {
    background-color: @status_idle_bg@;
    border: 1px solid @status_idle_border@;
    color: @status_idle_text@;
}
QLabel#scanSummaryStatusLabel[scanState="running"] {
    background-color: @status_running_bg@;
    border: 1px solid @status_running_border@;
    color: @status_running_text@;
}
QLabel#scanSummaryStatusLabel[scanState="success"] {
    background-color: @status_success_bg@;
    border: 1px solid @status_success_border@;
    color: @status_success_text@;
}
QLabel#scanSummaryStatusLabel[scanState="error"] {
    background-color: @status_error_bg@;
    border: 1px solid @status_error_border@;
    color: @status_error_text@;
}
"""

_UI_STYLESHEET_CACHE: dict[str, str] = {}


def _normalize_theme_mode(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"auto", "light", "dark"}:
        return normalized
    return "auto"


def _system_prefers_dark_theme() -> bool:
    app = QGuiApplication.instance()
    if app is None:
        return False

    try:
        hints = app.styleHints()
        color_scheme_fn = getattr(hints, "colorScheme", None)
        if callable(color_scheme_fn):
            scheme = color_scheme_fn()
            color_scheme_enum = getattr(Qt, "ColorScheme", None)
            if color_scheme_enum is not None:
                if scheme == color_scheme_enum.Dark:
                    return True
                if scheme == color_scheme_enum.Light:
                    return False
    except Exception:  # noqa: BLE001
        pass

    return app.palette().color(QPalette.ColorRole.Window).lightness() < 128


def _resolve_theme_variant(theme_mode: str | None) -> str:
    mode = _normalize_theme_mode(theme_mode)
    if mode == "light":
        return "light"
    if mode == "dark":
        return "dark"
    return "dark" if _system_prefers_dark_theme() else "light"


def _build_ui_stylesheet(theme_variant: str) -> str:
    colors = _UI_THEME_COLORS.get(theme_variant, _UI_THEME_COLORS["light"])
    stylesheet = _UI_STYLESHEET_TEMPLATE
    for name, value in colors.items():
        stylesheet = stylesheet.replace(f"@{name}@", value)
    return stylesheet


def _stylesheet_for_theme_variant(theme_variant: str) -> str:
    key = theme_variant if theme_variant in _UI_THEME_COLORS else "light"
    cached = _UI_STYLESHEET_CACHE.get(key)
    if cached is not None:
        return cached
    built = _build_ui_stylesheet(key)
    _UI_STYLESHEET_CACHE[key] = built
    return built


class _TooltipDelayProxyStyle(QProxyStyle):
    """Adds a tooltip wake-up delay and quickly exits tooltip mode between widgets."""

    def __init__(self, base_style=None, wakeup_delay_ms: int = 650, fall_asleep_delay_ms: int = 0) -> None:
        super().__init__(base_style)
        self._wakeup_delay_ms = max(0, int(wakeup_delay_ms))
        # Keep wake-up and fall-asleep independent. Forcing fall-asleep >= wake-up
        # keeps Qt in "hot" tooltip mode and causes immediate follow-up tooltips.
        self._fall_asleep_delay_ms = max(0, int(fall_asleep_delay_ms))
        self._wakeup_hint = getattr(QStyle, "SH_ToolTip_WakeUpDelay", None)
        self._fall_asleep_hint = getattr(QStyle, "SH_ToolTip_FallAsleepDelay", None)

    def styleHint(self, hint, option=None, widget=None, returnData=None) -> int:  # type: ignore[override]
        if self._wakeup_hint is not None and hint == self._wakeup_hint:
            return self._wakeup_delay_ms
        if self._fall_asleep_hint is not None and hint == self._fall_asleep_hint:
            return self._fall_asleep_delay_ms
        return super().styleHint(hint, option, widget, returnData)


def _as_xyz(value: Any) -> tuple[float, float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return None
    try:
        return (float(value[0]), float(value[1]), float(value[2]))
    except (TypeError, ValueError):
        return None


def _as_xyz_mapping(value: Any) -> tuple[float, float, float] | None:
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


def _extract_points_from_value(value: Any) -> list[tuple[float, float, float]]:
    points: list[tuple[float, float, float]] = []
    mapping_point = _as_xyz_mapping(value)
    if mapping_point is not None:
        points.append(mapping_point)
        return points
    if isinstance(value, list):
        single = _as_xyz(value)
        if single is not None:
            points.append(single)
        else:
            for item in value:
                points.extend(_extract_points_from_value(item))
    return points


def _is_formid_target(value: str) -> bool:
    return value.strip().lower().startswith("formid:")


def _is_nif_target(value: str) -> bool:
    return value.strip().lower().endswith(".nif")


def _normalized_node_lookup_key(value: str) -> str:
    return "".join(ch for ch in value.strip().lower() if ch.isalnum() or ch == "_")


def _node_lookup_aliases(value: str) -> set[str]:
    raw = value.strip().lower()
    if not raw:
        return set()

    aliases: set[str] = set()
    compact = _normalized_node_lookup_key(raw)
    if compact:
        aliases.add(compact)

    token: list[str] = []
    for ch in raw:
        if ch.isalnum() or ch == "_":
            token.append(ch)
            continue
        if token:
            aliases.add("".join(token))
            token = []
    if token:
        aliases.add("".join(token))
    return aliases


def _compact_value_text(value: Any, max_len: int = 120) -> str:
    if value is None:
        return "(none)"
    if isinstance(value, (dict, list, tuple)):
        text = json.dumps(value, ensure_ascii=True, sort_keys=True)
    else:
        text = str(value)
    if len(text) <= max_len:
        return text
    head_len = max(16, max_len - 14)
    tail_len = min(10, max(0, len(text) - head_len))
    return f"{text[:head_len]}...{text[-tail_len:] if tail_len else ''}"


def _lookup_case_insensitive(mapping: dict[str, Any], key: str) -> Any:
    if key in mapping:
        return mapping[key]
    key_l = key.lower()
    for raw_key, raw_value in mapping.items():
        if str(raw_key).lower() == key_l:
            return raw_value
    return None


def _extract_lp_light_value_summaries(settings: dict[str, Any]) -> list[str]:
    summaries: list[str] = []
    seen: set[str] = set()
    preferred_keys = ("light", "fade", "cutoff", "size", "radius", "flags", "color")
    skip_keys = {"data", "point", "points", "node", "nodes", "nif", "mesh", "model", "path"}

    for lights in _iter_lights_lists(settings):
        for light in lights:
            if not isinstance(light, dict):
                continue
            data = light.get("data")
            data_map = data if isinstance(data, dict) else {}
            parts: list[str] = []
            used_keys: set[str] = set()
            for key in preferred_keys:
                raw_value = _lookup_case_insensitive(data_map, key)
                if raw_value is None:
                    raw_value = _lookup_case_insensitive(light, key)
                if raw_value is None:
                    continue
                used_keys.add(key.lower())
                parts.append(f"{key}={_compact_value_text(raw_value)}")

            # Fallback: when preferred keys are missing, include any scalar-ish fields from
            # data/light blocks so values are still visible for non-standard LP schemas.
            if not parts:
                for source in (data_map, light):
                    for raw_key, raw_value in sorted(source.items(), key=lambda item: str(item[0]).lower()):
                        key_l = str(raw_key).lower()
                        if key_l in skip_keys or key_l in used_keys:
                            continue
                        if raw_value is None:
                            continue
                        parts.append(f"{raw_key}={_compact_value_text(raw_value, max_len=72)}")
                        if len(parts) >= 8:
                            break
                    if len(parts) >= 8:
                        break
            if not parts:
                continue
            summary = ", ".join(parts)
            if summary in seen:
                continue
            seen.add(summary)
            summaries.append(summary)
    return summaries


_PL_POINT_KEY_HINTS = ("point", "points", "offset", "position", "pos", "anchor", "location", "coord")
_PL_NODE_KEY_HINTS = ("node", "nodes")

def _extract_pl_anchor_points(payload: dict[str, Any]) -> list[tuple[float, float, float]]:
    points: list[tuple[float, float, float]] = []

    def _walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                key_l = str(key).lower()
                if any(hint in key_l for hint in _PL_POINT_KEY_HINTS):
                    points.extend(_extract_points_from_value(child))
                _walk(child)
            return
        if isinstance(value, list):
            for child in value:
                _walk(child)

    _walk(payload)
    return _dedupe_points(_sanitize_points(points))


def _extract_pl_anchor_nodes(payload: dict[str, Any]) -> set[str]:
    nodes: set[str] = set()

    def _add_nodes(raw: Any) -> None:
        if isinstance(raw, str):
            text = raw.strip().lower()
            if text:
                nodes.add(text)
            return
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, str):
                    text = item.strip().lower()
                    if text:
                        nodes.add(text)

    def _walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                key_l = str(key).lower()
                if any(hint in key_l for hint in _PL_NODE_KEY_HINTS):
                    _add_nodes(child)
                _walk(child)
            return
        if isinstance(value, list):
            for child in value:
                _walk(child)

    _walk(payload)
    return nodes


def _estimate_pl_radius_units(payload: dict[str, Any]) -> float | None:
    radii: list[float] = []

    def _walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                key_l = str(key).lower()
                if key_l == "radius":
                    radius = _to_positive_float(child)
                    if radius is not None:
                        radii.append(radius)
                elif key_l == "size":
                    size = _to_positive_float(child)
                    if size is not None:
                        radii.append(size * 12.0)
                _walk(child)
            return
        if isinstance(value, list):
            for child in value:
                _walk(child)

    _walk(payload)
    if not radii:
        return None
    return sum(radii) / len(radii)


def _centroid(points: list[tuple[float, float, float]]) -> tuple[float, float, float] | None:
    finite_points = _sanitize_points(points)
    if not finite_points:
        return None
    count = float(len(finite_points))
    return (
        sum(point[0] for point in finite_points) / count,
        sum(point[1] for point in finite_points) / count,
        sum(point[2] for point in finite_points) / count,
    )


def _estimate_mesh_radius_units(points: list[tuple[float, float, float]]) -> float | None:
    finite_points = _sanitize_points(points)
    if not finite_points:
        return None
    xs = [point[0] for point in finite_points]
    ys = [point[1] for point in finite_points]
    zs = [point[2] for point in finite_points]
    dx = max(xs) - min(xs)
    dy = max(ys) - min(ys)
    dz = max(zs) - min(zs)
    # Use half-diagonal as a stable, conservative preview radius.
    radius = 0.5 * (dx * dx + dy * dy + dz * dz) ** 0.5
    return radius if radius > 0.0 else None


class DropDownComboBox(QComboBox):
    """Combo box with a palette-aware down-triangle indicator."""

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        role = QPalette.ColorRole.Highlight if self.isEnabled() else QPalette.ColorRole.Mid
        painter.setBrush(self.palette().color(role))

        rect = self.rect()
        center_x = rect.right() - 11
        center_y = rect.center().y() + 1
        half_width = 6
        height = 5
        painter.drawPolygon(
            [
                QPointF(center_x - half_width, center_y - height),
                QPointF(center_x + half_width, center_y - height),
                QPointF(center_x, center_y + height),
            ]
        )
        painter.end()


class AnchorPreviewWidget(QWidget):
    _RADIUS_SCALE_MIN_SPAN_UNITS = 300.0
    _PALETTE = [
        QColor("#e74c3c"),
        QColor("#3498db"),
        QColor("#2ecc71"),
        QColor("#f39c12"),
        QColor("#9b59b6"),
        QColor("#1abc9c"),
        QColor("#e67e22"),
        QColor("#95a5a6"),
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._series: list[dict[str, Any]] = []
        self._mesh_points: list[tuple[float, float, float]] = []
        self._mesh_status_text = "Mesh cloud: not loaded"
        self.setMinimumHeight(110)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setToolTip(
            "Visual preview of LP and PL anchor points.\n"
            "Left plot: X/Y (top view), right plot: X/Z (side view).\n"
            "Each color corresponds to one entry/target.\n"
            "Legend tags: [LP] = Light Placer entry, [PL] = Particle Light target.\n"
            "Bold legend text marks the currently selected winner entry/target.\n"
            "Radius halos use one shared XY/XZ scale derived from current anchor view.\n"
            "Very large halos are proportionally downscaled for readability while preserving ratios.\n"
            "Axis ranges prioritize anchor points when available (mesh overlay does not force range flattening).\n"
            "For PL from ENB NIF scans, coordinates may be centroid estimates.\n"
            "When anchors overlap at the same spot, one marker is split into multiple colors."
        )

    def set_anchor_series(self, series: list[dict[str, Any]]) -> None:
        sanitized: list[dict[str, Any]] = []
        for item in series:
            copied = dict(item)
            raw_points = copied.get("points", [])
            if isinstance(raw_points, list):
                copied["points"] = _sanitize_points(raw_points)
            sanitized.append(copied)
        self._series = sanitized
        self.update()

    def clear_anchor_series(self) -> None:
        self._series = []
        self.update()

    def set_mesh_points(self, points: list[tuple[float, float, float]]) -> None:
        clean_points = _sanitize_points(points)
        self._mesh_points = clean_points
        if clean_points:
            self._mesh_status_text = f"Mesh cloud: {len(clean_points)} pts"
        else:
            self._mesh_status_text = "Mesh cloud: no points"
        self.update()

    def clear_mesh_points(self) -> None:
        self._mesh_points = []
        self._mesh_status_text = "Mesh cloud: not loaded"
        self.update()

    def set_mesh_status_text(self, text: str) -> None:
        self._mesh_status_text = text.strip() if text.strip() else "Mesh cloud: status unknown"
        self.update()

    @staticmethod
    def _map(value: float, vmin: float, vmax: float, out_min: float, out_max: float) -> float:
        if abs(vmax - vmin) < 1e-6:
            return (out_min + out_max) * 0.5
        t = (value - vmin) / (vmax - vmin)
        return out_min + t * (out_max - out_min)

    @staticmethod
    def _plot_content_bounds(rect) -> tuple[float, float, float, float]:
        left = rect.left() + 8
        right = rect.right() - 8
        top = rect.top() + 24
        bottom = rect.bottom() - 8
        return (left, right, top, bottom)

    @classmethod
    def _px_per_unit_for_plot(
        cls,
        rect,
        x_range: tuple[float, float],
        y_range: tuple[float, float],
    ) -> float:
        left, right, top, bottom = cls._plot_content_bounds(rect)
        span_x = max(1e-6, x_range[1] - x_range[0])
        span_y = max(1e-6, y_range[1] - y_range[0])
        return min((right - left) / span_x, (bottom - top) / span_y)

    def _draw_plot(
        self,
        painter: QPainter,
        rect,
        title: str,
        x_range: tuple[float, float],
        y_range: tuple[float, float],
        use_z_axis: bool,
        radius_px_per_unit: float | None = None,
    ) -> None:
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(self.palette().mid().color()))
        painter.drawRect(rect)
        painter.setPen(self.palette().text().color())
        painter.drawText(rect.adjusted(6, 4, -6, -4), Qt.AlignLeft | Qt.AlignTop, title)

        left, right, top, bottom = self._plot_content_bounds(rect)
        if right - left < 2 or bottom - top < 2:
            return
        content_rect = rect.adjusted(1, 24, -1, -1)

        xmin, xmax = x_range
        ymin, ymax = y_range

        painter.save()
        painter.setClipRect(content_rect)
        if xmin <= 0 <= xmax:
            x0 = self._map(0.0, xmin, xmax, left, right)
            painter.setPen(QPen(self.palette().mid().color(), 1, Qt.DotLine))
            painter.drawLine(int(x0), top, int(x0), bottom)
        if ymin <= 0 <= ymax:
            y0 = self._map(0.0, ymin, ymax, bottom, top)
            painter.setPen(QPen(self.palette().mid().color(), 1, Qt.DotLine))
            painter.drawLine(left, int(y0), right, int(y0))

        if self._mesh_points:
            mesh_proj = [(point[0], point[2] if use_z_axis else point[1]) for point in self._mesh_points]
            hull = self._convex_hull(mesh_proj)
            if len(hull) >= 3:
                path = QPainterPath()
                hx0, hy0 = hull[0]
                path.moveTo(
                    QPointF(
                        self._map(hx0, xmin, xmax, left, right),
                        self._map(hy0, ymin, ymax, bottom, top),
                    )
                )
                for hx, hy in hull[1:]:
                    path.lineTo(
                        QPointF(
                            self._map(hx, xmin, xmax, left, right),
                            self._map(hy, ymin, ymax, bottom, top),
                        )
                    )
                path.closeSubpath()
                painter.setPen(QPen(QColor(75, 75, 75, 180), 1.2))
                painter.setBrush(QColor(130, 130, 130, 58))
                painter.drawPath(path)
            else:
                # Fallback rectangle if hull could not be derived.
                px = [point[0] for point in mesh_proj]
                py = [point[1] for point in mesh_proj]
                if px and py:
                    x0 = self._map(min(px), xmin, xmax, left, right)
                    x1 = self._map(max(px), xmin, xmax, left, right)
                    y0 = self._map(min(py), ymin, ymax, bottom, top)
                    y1 = self._map(max(py), ymin, ymax, bottom, top)
                    painter.setPen(QPen(QColor(75, 75, 75, 180), 1.2))
                    painter.setBrush(QColor(130, 130, 130, 58))
                    painter.drawRect(int(min(x0, x1)), int(min(y0, y1)), int(abs(x1 - x0)), int(abs(y1 - y0)))
        else:
            painter.setPen(QPen(self.palette().mid().color()))
            painter.drawText(
                rect.adjusted(6, 22, -6, -6),
                Qt.AlignLeft | Qt.AlignBottom,
                self._mesh_status_text,
            )

        # Cluster by world-space point key so overlap/split markers stay consistent
        # across XY and XZ projections.
        clusters: dict[tuple[float, float, float], list[tuple[int, float, float, float]]] = {}
        for i, series in enumerate(self._series):
            points = series.get("points", [])
            raw_radius_units = series.get("radius_units")
            try:
                radius_units = float(raw_radius_units or 0.0)
            except (TypeError, ValueError):
                radius_units = 0.0
            if not isfinite(radius_units) or radius_units <= 0.0:
                radius_units = 0.0
            for point in points:
                x_raw = self._map(point[0], xmin, xmax, left, right)
                axis_value = point[2] if use_z_axis else point[1]
                y_raw = self._map(axis_value, ymin, ymax, bottom, top)
                if not isfinite(x_raw) or not isfinite(y_raw):
                    continue
                bucket = (round(point[0], 1), round(point[1], 1), round(point[2], 1))
                clusters.setdefault(bucket, []).append((i, x_raw, y_raw, radius_units))

        for samples in clusters.values():
            if not samples:
                continue
            cx = sum(sample[1] for sample in samples) / len(samples)
            cy = sum(sample[2] for sample in samples) / len(samples)
            series_indices = sorted({sample[0] for sample in samples})
            halo_sizes: list[float] = []
            for series_index, x_raw, y_raw, radius_units in samples:
                halo_px = self._radius_units_to_px(radius_units, xmin, xmax, ymin, ymax, left, right, top, bottom)
                if radius_px_per_unit is not None and radius_units > 0.0:
                    halo_px = radius_units * radius_px_per_unit
                if not isfinite(halo_px) or halo_px <= 0.0:
                    continue
                # Cap halo draw size to prevent extreme payload values from destabilizing paint.
                halo_cap = max(16.0, max(right - left, bottom - top) * 6.0)
                halo_px = min(halo_px, halo_cap)
                color = QColor(self._PALETTE[series_index % len(self._PALETTE)])
                fill = QColor(color)
                fill.setAlpha(35)
                edge = QColor(color)
                edge.setAlpha(120)
                painter.setPen(QPen(edge, 1))
                painter.setBrush(fill)
                painter.drawEllipse(int(x_raw - halo_px), int(y_raw - halo_px), int(halo_px * 2.0), int(halo_px * 2.0))
                halo_sizes.append(halo_px)

            marker_radius = 5
            if halo_sizes:
                marker_radius = int(max(2.0, min(8.0, max(halo_sizes) * 0.18)))
            radius = marker_radius
            diameter = radius * 2
            rect_x = int(cx) - radius
            rect_y = int(cy) - radius

            if len(series_indices) == 1:
                color = self._PALETTE[series_indices[0] % len(self._PALETTE)]
                painter.setPen(QPen(Qt.white, 1))
                painter.setBrush(color)
                painter.drawEllipse(rect_x, rect_y, diameter, diameter)
                continue

            painter.setPen(Qt.NoPen)
            total = len(series_indices)
            start = 0
            for idx, series_index in enumerate(series_indices):
                color = self._PALETTE[series_index % len(self._PALETTE)]
                painter.setBrush(color)
                if idx == total - 1:
                    span = 360 * 16 - start
                else:
                    span = int(round((360.0 / total) * 16.0))
                painter.drawPie(rect_x, rect_y, diameter, diameter, start, span)
                start += span

            painter.setPen(QPen(Qt.white, 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(rect_x, rect_y, diameter, diameter)
        painter.restore()

    @staticmethod
    def _cross(o: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    @classmethod
    def _convex_hull(cls, points: list[tuple[float, float]]) -> list[tuple[float, float]]:
        unique = sorted(set(points))
        if len(unique) <= 1:
            return unique
        lower: list[tuple[float, float]] = []
        for point in unique:
            while len(lower) >= 2 and cls._cross(lower[-2], lower[-1], point) <= 0:
                lower.pop()
            lower.append(point)
        upper: list[tuple[float, float]] = []
        for point in reversed(unique):
            while len(upper) >= 2 and cls._cross(upper[-2], upper[-1], point) <= 0:
                upper.pop()
            upper.append(point)
        return lower[:-1] + upper[:-1]

    @staticmethod
    def _radius_units_to_px(
        radius_units: float,
        xmin: float,
        xmax: float,
        ymin: float,
        ymax: float,
        left: float,
        right: float,
        top: float,
        bottom: float,
        radius_px_per_unit: float | None = None,
    ) -> float:
        if not isfinite(radius_units) or radius_units <= 0.0:
            return 0.0
        if radius_px_per_unit is not None and radius_px_per_unit > 0.0:
            radius_px = radius_units * radius_px_per_unit
            return radius_px if isfinite(radius_px) and radius_px > 0.0 else 0.0
        span_x = max(1e-6, xmax - xmin)
        span_y = max(1e-6, ymax - ymin)
        px_per_unit = min((right - left) / span_x, (bottom - top) / span_y)
        # True scale: preview radius uses the same unit->pixel mapping for LP and PL.
        # No artificial compression/clamp, so radius ratios remain accurate.
        radius_px = radius_units * px_per_unit
        return radius_px if isfinite(radius_px) and radius_px > 0.0 else 0.0

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        outer = self.rect().adjusted(4, 4, -4, -4)
        painter.fillRect(outer, self.palette().base())
        painter.setPen(QPen(self.palette().mid().color()))
        painter.drawRect(outer)

        if not self._series and not self._mesh_points:
            painter.setPen(self.palette().text().color())
            painter.drawText(outer, Qt.AlignCenter, "No LP/PL anchor points to preview for this conflict.")
            return

        all_points = [point for series in self._series for point in series.get("points", [])]
        all_ref_points = [*all_points, *self._mesh_points]
        if not all_ref_points:
            painter.setPen(self.palette().text().color())
            painter.drawText(
                outer,
                Qt.AlignCenter,
                "No numeric points/offsets found.\n"
                "This conflict uses node-only anchors, so geometric preview is limited.",
            )
            return

        # Keep plot geometry anchor-focused while preserving enough mesh extent to
        # make silhouette context visible.
        anchor_points = all_points if all_points else all_ref_points
        anchor_xs = [point[0] for point in anchor_points]
        anchor_ys = [point[1] for point in anchor_points]
        anchor_zs = [point[2] for point in anchor_points]

        def _expand(vmin: float, vmax: float, *, min_span: float = 0.0) -> tuple[float, float]:
            if abs(vmax - vmin) < 1e-6:
                vmin, vmax = (vmin - 1.0, vmax + 1.0)
            else:
                pad = (vmax - vmin) * 0.12
                vmin, vmax = (vmin - pad, vmax + pad)
            span = max(0.0, vmax - vmin)
            if min_span > 0.0 and span < min_span:
                center = 0.5 * (vmin + vmax)
                half = 0.5 * min_span
                return (center - half, center + half)
            return (vmin, vmax)

        def _blend_anchor_mesh_range(
            anchor_range: tuple[float, float],
            mesh_range: tuple[float, float] | None,
            *,
            max_zoom_factor: float = 6.0,
        ) -> tuple[float, float]:
            if mesh_range is None:
                return anchor_range
            a0, a1 = anchor_range
            m0, m1 = mesh_range
            union0 = min(a0, m0)
            union1 = max(a1, m1)
            anchor_span = max(1e-6, a1 - a0)
            union_span = max(1e-6, union1 - union0)
            if union_span <= anchor_span * max_zoom_factor:
                return (union0, union1)
            center = 0.5 * (a0 + a1)
            half = 0.5 * anchor_span * max_zoom_factor
            return (center - half, center + half)

        def _expand_for_pixel_margin(
            value_range: tuple[float, float],
            pixel_margin: float,
            pixel_span: float,
        ) -> tuple[float, float]:
            if pixel_margin <= 0.0 or pixel_span <= 1e-6:
                return value_range
            vmin, vmax = value_range
            span = max(1e-6, vmax - vmin)
            unit_margin = span * (pixel_margin / pixel_span)
            return (vmin - unit_margin, vmax + unit_margin)

        x_range = _expand(min(anchor_xs), max(anchor_xs))
        y_range = _expand(min(anchor_ys), max(anchor_ys))
        z_range = _expand(min(anchor_zs), max(anchor_zs))

        if all_points and self._mesh_points:
            mesh_xs = [point[0] for point in self._mesh_points]
            mesh_ys = [point[1] for point in self._mesh_points]
            mesh_zs = [point[2] for point in self._mesh_points]
            mesh_x_range = _expand(min(mesh_xs), max(mesh_xs))
            mesh_y_range = _expand(min(mesh_ys), max(mesh_ys))
            mesh_z_range = _expand(min(mesh_zs), max(mesh_zs))
            x_range = _blend_anchor_mesh_range(x_range, mesh_x_range, max_zoom_factor=6.0)
            y_range = _blend_anchor_mesh_range(y_range, mesh_y_range, max_zoom_factor=6.0)
            z_range = _blend_anchor_mesh_range(z_range, mesh_z_range, max_zoom_factor=6.0)

        legend_row_h = 18
        legend_items = len(self._series) + (1 if self._mesh_points else 0)
        max_legend_rows = max(1, int((outer.height() - 64) / legend_row_h))
        visible_legend_rows = min(legend_items, max_legend_rows)
        legend_height = 24 + legend_row_h * max(1, visible_legend_rows)
        plots_rect = outer.adjusted(6, 6, -6, -legend_height)
        gap = 8
        left_plot = plots_rect.adjusted(0, 0, -(plots_rect.width() // 2 + gap // 2), 0)
        right_plot = plots_rect.adjusted(plots_rect.width() // 2 + gap // 2, 0, 0, 0)

        # Derive radius scale from current anchor-focused view so overlap and radius
        # are both readable; keep one shared scale for XY/XZ consistency.
        left_l, left_r, _, _ = self._plot_content_bounds(left_plot)
        right_l, right_r, _, _ = self._plot_content_bounds(right_plot)
        left_w = max(1.0, left_r - left_l)
        right_w = max(1.0, right_r - right_l)
        _, _, left_t, left_b = self._plot_content_bounds(left_plot)
        _, _, right_t, right_b = self._plot_content_bounds(right_plot)
        left_h = max(1.0, left_b - left_t)
        right_h = max(1.0, right_b - right_t)

        max_radius_units = 0.0
        for series in self._series:
            raw_radius_units = series.get("radius_units")
            try:
                radius_units = float(raw_radius_units or 0.0)
            except (TypeError, ValueError):
                radius_units = 0.0
            if not isfinite(radius_units) or radius_units <= 0.0:
                radius_units = 0.0
            if radius_units > max_radius_units:
                max_radius_units = radius_units

        px_per_unit_xy = self._px_per_unit_for_plot(left_plot, x_range, y_range)
        px_per_unit_xz = self._px_per_unit_for_plot(right_plot, x_range, z_range)
        shared_radius_px_per_unit = min(px_per_unit_xy, px_per_unit_xz)

        # Adaptive readability cap: preserve relative radius ratios but avoid a single
        # very large light obscuring all anchors.
        if max_radius_units > 0.0:
            raw_max_halo_px = max_radius_units * shared_radius_px_per_unit
            max_readable_halo_px = max(12.0, min(left_w, right_w, left_h, right_h) * 0.42)
            if isfinite(raw_max_halo_px) and raw_max_halo_px > max_readable_halo_px:
                shared_radius_px_per_unit *= max_readable_halo_px / raw_max_halo_px

        # Keep points/halos inside the view area: expand world ranges by the on-screen
        # halo radius so markers are not clipped at plot boundaries.
        if max_radius_units > 0.0:
            max_halo_px = max_radius_units * shared_radius_px_per_unit
            if not isfinite(max_halo_px) or max_halo_px <= 0.0:
                max_halo_px = 0.0
            # Include marker diameter + small safety margin.
            pixel_margin = max_halo_px + 8.0

            # Prevent halo margin expansion from overwhelming axis representation.
            x_margin_px = min(pixel_margin, min(left_w, right_w) * 0.22)
            y_margin_px = min(pixel_margin, left_h * 0.22)
            z_margin_px = min(pixel_margin, right_h * 0.22)

            x_range = _expand_for_pixel_margin(
                x_range,
                x_margin_px,
                min(left_w, right_w),
            )
            y_range = _expand_for_pixel_margin(y_range, y_margin_px, left_h)
            z_range = _expand_for_pixel_margin(z_range, z_margin_px, right_h)

        self._draw_plot(
            painter,
            left_plot,
            "Top View (X/Y)",
            x_range,
            y_range,
            use_z_axis=False,
            radius_px_per_unit=shared_radius_px_per_unit,
        )
        self._draw_plot(
            painter,
            right_plot,
            "Side View (X/Z)",
            x_range,
            z_range,
            use_z_axis=True,
            radius_px_per_unit=shared_radius_px_per_unit,
        )

        legend_top = outer.bottom() - legend_height + 8
        text_x = outer.left() + 10
        legend_entries: list[tuple[QColor, str, bool]] = []
        if self._mesh_points:
            legend_entries.append((QColor(65, 65, 65), f"Mesh silhouette ({len(self._mesh_points)} pts)", False))

        for i, series in enumerate(self._series):
            color = self._PALETTE[i % len(self._PALETTE)]
            kind = str(series.get("kind", "LP")).upper()
            localized = str(series.get("localized", ""))
            radius_source = str(series.get("radius_source", ""))
            label = series.get("label", f"Entry {i + 1}")
            points_count = len(series.get("points", []))
            meta = ""
            if kind == "PL" and localized == "centroid":
                meta = " | centroid-est"
            if kind == "PL" and radius_source == "nif_bounding_sphere":
                meta += " | radius-nif"
            elif kind == "PL" and radius_source == "mesh_bounds":
                meta += " | radius-est"
            if bool(series.get("winner")):
                meta += " | winner"
            legend_entries.append((color, f"{i + 1}. [{kind}] {label} ({points_count} pts){meta}", bool(series.get("winner"))))

        hidden_count = max(0, len(legend_entries) - visible_legend_rows)
        if hidden_count > 0 and visible_legend_rows > 0:
            shown_entries = legend_entries[: max(0, visible_legend_rows - 1)]
            shown_entries.append((QColor(120, 120, 120), f"... +{hidden_count} more entries", False))
        else:
            shown_entries = legend_entries

        base_font = painter.font()
        for row, (swatch, text, is_winner) in enumerate(shown_entries):
            painter.setBrush(swatch)
            painter.setPen(QPen(swatch))
            painter.drawRect(text_x, legend_top + row * legend_row_h + 2, 10, 10)
            winner_font = painter.font()
            winner_font.setBold(bool(is_winner))
            painter.setFont(winner_font)
            if is_winner:
                plot_bg_lightness = self.palette().color(QPalette.ColorRole.Base).lightness()
                winner_color = QColor(0, 0, 0) if plot_bg_lightness >= 128 else QColor(255, 255, 255)
                painter.setPen(winner_color)
            else:
                painter.setPen(self.palette().text().color())
            painter.drawText(text_x + 16, legend_top + row * legend_row_h + 12, text)
        painter.setFont(base_font)


class ScanWorker(QObject):
    finished = Signal(int, object)
    failed = Signal(int, str)

    def __init__(self, config: ScanConfig, scan_id: int) -> None:
        super().__init__()
        self.config = config
        self.scan_id = scan_id

    @Slot()
    def run(self) -> None:
        try:
            result = run_scan(self.config, write_output_reports=True)
            self.finished.emit(self.scan_id, result)
        except Exception as exc:  # noqa: BLE001
            message = str(exc).strip()
            if not message:
                message = type(exc).__name__
            elif not message.lower().startswith(type(exc).__name__.lower()):
                message = f"{type(exc).__name__}: {message}"
            self.failed.emit(self.scan_id, message)


class FormIDResolutionWorker(QObject):
    finished = Signal(int, str, object)
    failed = Signal(int, str, str)

    def __init__(self, mods_dir: str, profile_path: str, target_key: str, request_id: int) -> None:
        super().__init__()
        self.mods_dir = mods_dir
        self.profile_path = profile_path
        self.target_key = target_key
        self.request_id = request_id

    @Slot()
    def run(self) -> None:
        try:
            result = resolve_formid_world_resolution(
                self.mods_dir,
                self.profile_path,
                self.target_key,
            )
            self.finished.emit(self.request_id, self.target_key, result)
        except Exception as exc:  # noqa: BLE001
            message = str(exc).strip()
            if not message:
                message = type(exc).__name__
            elif not message.lower().startswith(type(exc).__name__.lower()):
                message = f"{type(exc).__name__}: {message}"
            self.failed.emit(self.request_id, self.target_key, message)


class MainWindow(QMainWindow):
    _DUPLICATE_CONFLICT_TYPES: set[str] = {
        "duplicate_exact",
        "duplicate_divergent",
        "duplicate_condition_exclusive",
        "duplicate_refinement_disjoint",
    }

    _TYPE_LABELS: dict[str, str] = {
        "lp_vs_pl_overlap": "Overlap",
        "duplicate_exact": "Exact Duplicates",
        "duplicate_divergent": "Divergent Duplicates",
        "duplicate_condition_exclusive": "Worldspace Splits",
        "duplicate_refinement_disjoint": "Refinements",
    }

    _TYPE_HELP: dict[str, str] = {
        "lp_vs_pl_overlap": (
            "LP and PL both target the same key (usually a NIF). Potential stacked lighting overhead and overbright results."
        ),
        "duplicate_exact": (
            "Multiple LP entries with effectively identical settings. Usually redundant overhead without quality gain."
        ),
        "duplicate_divergent": (
            "Multiple LP entries target overlapping anchors but with different settings. High risk of stacked intensity and extra light cost."
        ),
        "duplicate_condition_exclusive": (
            "Overlapping LP anchors with divergent settings, but worldspace conditions are mutually exclusive "
            "(for example interior vs exterior variants). Usually not simultaneous stacking."
        ),
        "duplicate_refinement_disjoint": (
            "Multiple LP entries use different/disjoint anchors. Often refinement coverage, not true stacking overhead."
        ),
    }

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"Placed Lights and Particle Lights Conflict Resolver v{__version__}")
        self.resize(1800, 1000)
        # Keep usable on 1080p/768p non-fullscreen desktops without clipping lower panes.
        self.setMinimumSize(920, 560)
        self._splitter_sizes_initialized = False
        self._window_geometry_initialized = False

        self.scan_result: ScanResult | None = None
        self.decisions: dict[str, Decision] = {}
        self._entry_selection_by_nif: dict[str, list[str]] = {}
        self._conflict_by_nif: dict[str, Conflict] = {}
        self._worker_thread: QThread | None = None
        self._worker: ScanWorker | None = None
        self._formid_worker_thread: QThread | None = None
        self._formid_worker: FormIDResolutionWorker | None = None
        self._formid_request_seq = 0
        self._formid_request_inflight_target: str | None = None
        self._formid_request_pending_target: str | None = None
        self._active_scan_id = 0
        self._scan_in_progress = False
        self._auto_rescan_requested = False
        self._updating_conflicts_table = False
        self._is_closing = False
        self._system_theme_signal_connected = False
        self._conflict_min_widths = [72, 64, 72, 32, 32, 72]
        self._light_scale_menu: QMenu | None = None
        self._formid_world_resolution_cache: dict[str, FormIDWorldResolution] = {}
        self._inventory_scope = "all"
        self._inventory_portal_strict_only = False
        self._inventory_nif_only = False
        self._inventory_conflicts_only = False

        self._build_ui()
        self._connect_system_theme_notifications()
        self._load_persistent_paths()

    def _build_ui(self) -> None:
        root = QWidget(self)
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        controls = self._build_controls_group()
        self.controls_group = controls
        self.summary_label = QLabel("No scan run yet.")
        self.summary_label.setWordWrap(True)
        self.summary_label.setObjectName("scanSummaryStatusLabel")
        self._set_scan_summary_state("No scan run yet.", "idle")

        conflicts_panel = self._build_conflicts_panel()
        details_panel = self._build_details_panel()
        scan_panel = QWidget()
        self.scan_panel = scan_panel
        scan_layout = QVBoxLayout(scan_panel)
        scan_layout.setContentsMargins(0, 0, 0, 0)
        scan_layout.setSpacing(8)
        scan_layout.addWidget(controls)
        scan_layout.addWidget(self.summary_label)

        conflicts_panel.setMinimumWidth(180)
        details_panel.setMinimumWidth(220)
        controls.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.summary_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        scan_panel.setMinimumWidth(0)
        scan_panel.setMinimumHeight(self._compute_scan_panel_min_height())
        scan_panel.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        conflicts_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        details_panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        self.left_splitter = QSplitter(Qt.Vertical)
        self.left_splitter.setChildrenCollapsible(False)
        self.left_splitter.setHandleWidth(10)
        self.left_splitter.setToolTip("Drag this divider to resize Scan/Output and Conflicts panels.")
        self.left_splitter.addWidget(scan_panel)
        self.left_splitter.addWidget(conflicts_panel)
        self.left_splitter.setStretchFactor(0, 0)
        self.left_splitter.setStretchFactor(1, 1)
        self.left_splitter.setSizes([210, 790])
        self.left_splitter.splitterMoved.connect(self._on_left_splitter_moved)
        self.left_splitter.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        self.left_splitter.handle(1).setCursor(Qt.SizeVerCursor)

        self.content_splitter = QSplitter(Qt.Horizontal)
        self.content_splitter.setChildrenCollapsible(False)
        self.content_splitter.setHandleWidth(10)
        self.content_splitter.setToolTip("Drag this divider to resize left and right main panels.")
        self.content_splitter.addWidget(self.left_splitter)
        self.content_splitter.addWidget(details_panel)
        self.content_splitter.setStretchFactor(0, 1)
        self.content_splitter.setStretchFactor(1, 1)
        self.content_splitter.setCollapsible(0, False)
        self.content_splitter.setCollapsible(1, False)
        self.content_splitter.setSizes([1080, 720])
        self.content_splitter.splitterMoved.connect(self._on_content_splitter_moved)
        self.content_splitter.handle(1).setCursor(Qt.SizeHorCursor)

        layout.addWidget(self.content_splitter)
        self._set_scan_dependent_controls_enabled(False)

    def _set_scan_summary_state(self, text: str, state: str) -> None:
        self.summary_label.setText(text)
        if hasattr(self, "scan_panel"):
            self._update_summary_label_height()
            self.scan_panel.setMinimumHeight(self._compute_scan_panel_min_height())
        state_name = state if state in {"idle", "running", "success", "error"} else "idle"
        if str(self.summary_label.property("scanState") or "") == state_name:
            return
        self.summary_label.setProperty("scanState", state_name)
        style = self.summary_label.style()
        style.unpolish(self.summary_label)
        style.polish(self.summary_label)
        self.summary_label.update()

    def _set_scan_dependent_controls_enabled(self, enabled: bool) -> None:
        state = bool(enabled) and not self._scan_in_progress and not self._is_closing
        for name in (
            "load_decisions_btn",
            "save_decisions_btn",
            "export_patch_btn",
            "inventory_export_btn",
            "clear_all_decisions_btn",
            "apply_overlap_disable_btn",
            "apply_highest_duplicates_btn",
            "action_combo",
            "entry_list",
            "apply_btn",
            "clear_btn",
        ):
            widget = getattr(self, name, None)
            if widget is not None:
                widget.setEnabled(state)
        if hasattr(self, "conflicts_table"):
            self.conflicts_table.setEnabled(state)

    def _update_summary_label_height(self) -> None:
        if not hasattr(self, "scan_panel"):
            return
        scan_layout = self.scan_panel.layout()
        if scan_layout is None:
            return
        margins = scan_layout.contentsMargins()
        summary_width = max(220, self.scan_panel.width() - margins.left() - margins.right())
        label_margins = self.summary_label.contentsMargins()
        single_line_height = (
            self.summary_label.fontMetrics().lineSpacing()
            + label_margins.top()
            + label_margins.bottom()
            + 4
        )
        required_height = self.summary_label.heightForWidth(summary_width)
        if required_height <= 0:
            required_height = single_line_height
        required_height = max(single_line_height, required_height)
        self.summary_label.setMinimumHeight(required_height)
        self.summary_label.setMaximumHeight(required_height)
        self.summary_label.updateGeometry()

    def _mark_as_dropdown(self, combo: QComboBox) -> None:
        tip = combo.toolTip().strip()
        suffix = "Drop-down menu."
        if suffix in tip:
            return
        combo.setToolTip(f"{tip}\n{suffix}" if tip else suffix)
        combo.setEditable(False)

    def _fit_combo_to_current_text(self, combo: QComboBox, extra_padding_px: int = 36) -> None:
        text_width = combo.fontMetrics().horizontalAdvance(combo.currentText())
        target_width = max(90, text_width + extra_padding_px)
        combo.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        combo.view().setTextElideMode(Qt.ElideNone)
        combo.setMinimumWidth(target_width)
        combo.setMaximumWidth(target_width)

    def _build_light_scale_menu(self) -> None:
        self._light_scale_menu = QMenu(self)
        menu_host = QWidget(self._light_scale_menu)
        menu_layout = QVBoxLayout(menu_host)
        menu_layout.setContentsMargins(10, 10, 10, 10)
        menu_layout.setSpacing(6)

        self.light_scale_enabled_cb = QCheckBox("Enable Separate Intensity Patch (Experimental)")
        self.light_scale_enabled_cb.setChecked(False)
        self.light_scale_enabled_cb.setToolTip(
            "When enabled, Export Patch writes a second patch mod after conflict export.\n"
            "That second mod scales light intensity in effective winner LP JSON files."
        )
        menu_layout.addWidget(self.light_scale_enabled_cb)

        slider_row = QHBoxLayout()
        slider_row.setContentsMargins(0, 0, 0, 0)
        slider_row.setSpacing(8)
        slider_row.addWidget(QLabel("Scale"))
        self.light_scale_slider = QSlider(Qt.Horizontal)
        self.light_scale_slider.setRange(50, 200)
        self.light_scale_slider.setSingleStep(1)
        self.light_scale_slider.setPageStep(5)
        self.light_scale_slider.setValue(100)
        self.light_scale_slider.setToolTip(
            "Scale factor for intensity-like LP fields.\n"
            "Range 0.50 to 2.00 (1.00 keeps original values)."
        )
        slider_row.addWidget(self.light_scale_slider, 1)
        self.light_scale_value_label = QLabel("1.00x")
        self.light_scale_value_label.setMinimumWidth(54)
        slider_row.addWidget(self.light_scale_value_label)
        menu_layout.addLayout(slider_row)

        scope_row = QHBoxLayout()
        scope_row.setContentsMargins(0, 0, 0, 0)
        scope_row.setSpacing(8)
        scope_row.addWidget(QLabel("Scope"))
        self.light_scale_scope_combo = DropDownComboBox()
        self.light_scale_scope_combo.addItem("All Entries", "all")
        self.light_scale_scope_combo.addItem("Interior Only", "interior")
        self.light_scale_scope_combo.addItem("Exterior Only", "exterior")
        self.light_scale_scope_combo.setToolTip(
            "Optional filter before scaling:\n"
            "- All Entries: no worldspace filter\n"
            "- Interior/Exterior: match `GetInWorldspace ... == 0/1` conditions"
        )
        self._mark_as_dropdown(self.light_scale_scope_combo)
        scope_row.addWidget(self.light_scale_scope_combo, 1)
        menu_layout.addLayout(scope_row)

        self.light_scale_portal_strict_cb = QCheckBox("PortalStrict only")
        self.light_scale_portal_strict_cb.setToolTip(
            "Apply scaling only to LP entries detected as PortalStrict.\n"
            "Can be combined with Interior/Exterior scope."
        )
        menu_layout.addWidget(self.light_scale_portal_strict_cb)

        note = QLabel(
            "Second patch name: <Patch Mod Name>_LightIntensityPatch\n"
            "Place it after your conflict patch and other LP JSON providers."
        )
        note.setWordWrap(True)
        note.setObjectName("lightScaleNoteLabel")
        menu_layout.addWidget(note)

        action = QWidgetAction(self._light_scale_menu)
        action.setDefaultWidget(menu_host)
        self._light_scale_menu.addAction(action)
        self._light_scale_menu.setToolTipsVisible(True)
        self._light_scale_menu.setMinimumWidth(360)

        self.light_scale_enabled_cb.toggled.connect(self._on_light_scale_options_changed)
        self.light_scale_slider.valueChanged.connect(self._on_light_scale_slider_changed)
        self.light_scale_scope_combo.currentIndexChanged.connect(self._on_light_scale_options_changed)
        self.light_scale_portal_strict_cb.toggled.connect(self._on_light_scale_options_changed)
        self._set_light_scale_controls_enabled(False)
        self._refresh_light_scale_button()

    def _show_light_scale_menu(self) -> None:
        if self._light_scale_menu is None:
            return
        anchor = self.light_scale_menu_btn.mapToGlobal(self.light_scale_menu_btn.rect().bottomLeft())
        self._light_scale_menu.popup(anchor)

    def _inventory_export_config(self) -> InventoryExportConfig:
        return InventoryExportConfig(
            worldspace_scope=self._inventory_scope,
            portal_strict_only=self._inventory_portal_strict_only,
            nif_only=self._inventory_nif_only,
            conflicts_only=self._inventory_conflicts_only,
        )

    def _show_inventory_filter_dialog(self) -> bool:
        dialog = QDialog(self)
        dialog.setWindowTitle("Export Results")
        dialog.setModal(True)
        dialog.setMinimumWidth(440)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        header = QLabel(
            "Select export-result filters. Scope applies to LP entries and PL rows by matching target keys."
        )
        header.setWordWrap(True)
        layout.addWidget(header)

        scope_row = QHBoxLayout()
        scope_row.setContentsMargins(0, 0, 0, 0)
        scope_row.setSpacing(8)
        scope_row.addWidget(QLabel("Scope"))
        scope_combo = DropDownComboBox()
        scope_combo.addItem("All", "all")
        scope_combo.addItem("Interior", "interior")
        scope_combo.addItem("Exterior", "exterior")
        scope_combo.addItem("Unscoped", "unscoped")
        scope_combo.setToolTip(
            "LP worldspace scope filter.\n"
            "- All: include all LP entries.\n"
            "- Interior/Exterior: prefer explicit `GetInWorldspace ... == 0/1` conditions.\n"
            "- If explicit scope is missing, a filename/path hint pass is used "
            "(e.g. tokens like Interior/Exterior/ISL).\n"
            "- Unscoped: include entries with no explicit/inferred worldspace scope."
        )
        self._mark_as_dropdown(scope_combo)
        scope_index = scope_combo.findData(self._inventory_scope)
        if scope_index < 0:
            scope_index = scope_combo.findData("all")
        if scope_index >= 0:
            scope_combo.setCurrentIndex(scope_index)
        scope_row.addWidget(scope_combo, 1)
        layout.addLayout(scope_row)

        portal_strict_cb = QCheckBox("PortalStrict (LP only)")
        portal_strict_cb.setChecked(self._inventory_portal_strict_only)
        portal_strict_cb.setToolTip(
            "Include only LP entries detected as PortalStrict.\n"
            "This filter applies to LP entries only."
        )
        layout.addWidget(portal_strict_cb)

        nif_only_cb = QCheckBox("NIF targets only (LP + PL)")
        nif_only_cb.setChecked(self._inventory_nif_only)
        nif_only_cb.setToolTip(
            "Include only NIF target keys.\n"
            "When enabled, FormID/EffectID targets are excluded."
        )
        layout.addWidget(nif_only_cb)

        conflicts_only_cb = QCheckBox("Conflicts only")
        conflicts_only_cb.setChecked(self._inventory_conflicts_only)
        conflicts_only_cb.setToolTip(
            "Include only rows whose target key is currently detected as a conflict.\n"
            "Non-conflicting LP/PL findings are excluded."
        )
        layout.addWidget(conflicts_only_cb)

        note = QLabel(
            "Output files:\n"
            "- Results_summary.json\n"
            "- Results_targets.csv\n"
            "- Results_lp_entries.csv\n"
            "- Results_pl_targets.csv"
        )
        note.setWordWrap(True)
        note.setObjectName("lightScaleNoteLabel")
        layout.addWidget(note)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.Accepted:
            return False

        self._inventory_scope = str(scope_combo.currentData() or "all")
        self._inventory_portal_strict_only = portal_strict_cb.isChecked()
        self._inventory_nif_only = nif_only_cb.isChecked()
        self._inventory_conflicts_only = conflicts_only_cb.isChecked()
        self._save_persistent_paths()
        return True

    def _light_scale_factor(self) -> float:
        return float(self.light_scale_slider.value()) / 100.0

    def _set_light_scale_controls_enabled(self, enabled: bool) -> None:
        self.light_scale_slider.setEnabled(enabled)
        self.light_scale_scope_combo.setEnabled(enabled)
        self.light_scale_portal_strict_cb.setEnabled(enabled)
        self.light_scale_value_label.setEnabled(enabled)

    def _refresh_light_scale_button(self) -> None:
        enabled = self.light_scale_enabled_cb.isChecked()
        factor = self._light_scale_factor()
        self.light_scale_value_label.setText(f"{factor:.2f}x")
        self._set_light_scale_controls_enabled(enabled)
        if enabled:
            self.light_scale_menu_btn.setText(f"Light Scale ({factor:.2f}x)")
        else:
            self.light_scale_menu_btn.setText("Light Scale")

    def _on_light_scale_slider_changed(self, _value: int) -> None:
        self._refresh_light_scale_button()
        self._save_persistent_paths()

    def _on_light_scale_options_changed(self, *_args) -> None:
        self._refresh_light_scale_button()
        self._save_persistent_paths()

    def _on_formid_preview_options_changed(self, *_args) -> None:
        self._save_persistent_paths()
        if not self.formid_preview_enabled_cb.isChecked():
            self._formid_request_pending_target = None
        if self.scan_result is not None:
            self.on_conflict_selection_changed()

    def _on_conflict_visibility_options_changed(self, *_args) -> None:
        self._save_persistent_paths()
        if self.scan_result is None:
            return
        selected_nifs = self._selected_nif_paths()
        self._populate_conflicts_table(preserve_nif_paths=selected_nifs)
        self._set_scan_summary_state(self._build_scan_summary_text(self.scan_result), "success")

    def _on_scan_filter_toggle_requires_rescan(self, checked: bool) -> None:
        # These filters are baked into ScanConfig/run_scan, so enabling them
        # needs a fresh scan result rather than local table re-filtering.
        if not checked:
            return
        if self._is_closing:
            return
        thread = self._worker_thread
        if self._scan_in_progress or (thread is not None and thread.isRunning()):
            self._auto_rescan_requested = True
            return
        if self.scan_result is None:
            return
        if self._scan_filters_match_last_result():
            return
        self.start_scan()

    def _connect_system_theme_notifications(self) -> None:
        if self._system_theme_signal_connected:
            return
        app = QGuiApplication.instance()
        if app is None:
            return
        color_scheme_changed = getattr(app.styleHints(), "colorSchemeChanged", None)
        if color_scheme_changed is None:
            return
        try:
            color_scheme_changed.connect(self._on_system_color_scheme_changed)
            self._system_theme_signal_connected = True
        except Exception:  # noqa: BLE001
            return

    def _theme_mode(self) -> str:
        if hasattr(self, "theme_mode_combo"):
            return _normalize_theme_mode(str(self.theme_mode_combo.currentData() or "auto"))
        return "auto"

    def _apply_theme_stylesheet(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        theme_variant = _resolve_theme_variant(self._theme_mode())
        current_variant = str(app.property("_lp_theme_variant") or "")
        if current_variant == theme_variant:
            return
        app.setStyleSheet(_stylesheet_for_theme_variant(theme_variant))
        app.setProperty("_lp_theme_variant", theme_variant)

    def _on_theme_mode_changed(self, *_args) -> None:
        self._fit_combo_to_current_text(self.theme_mode_combo, extra_padding_px=48)
        self._apply_theme_stylesheet()
        self._save_persistent_paths()

    def _on_system_color_scheme_changed(self, *_args) -> None:
        if self._theme_mode() == "auto":
            self._apply_theme_stylesheet()

    def _light_scale_config(self) -> LightIntensityPatchConfig:
        return LightIntensityPatchConfig(
            scale_factor=self._light_scale_factor(),
            worldspace_scope=str(self.light_scale_scope_combo.currentData() or "all"),
            portal_strict_only=self.light_scale_portal_strict_cb.isChecked(),
        )

    def _application_base_dir(self) -> Path:
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve().parent
        return Path(__file__).resolve().parents[1]

    def _settings(self) -> QSettings:
        return QSettings("ParticleTroned", "LPConflictResolver")

    def _load_persistent_paths(self) -> None:
        settings = self._settings()
        mo2_root = settings.value("paths/mo2_root", "", str).strip()
        profile_path = settings.value("paths/profile_path", "", str).strip()
        output_dir = settings.value("paths/output_dir", "", str).strip()
        patch_name = settings.value("paths/patch_name", "", str).strip()
        light_scale_enabled = bool(settings.value("light_scale/enabled", False, bool))
        light_scale_slider_value = int(settings.value("light_scale/slider_value", 100, int))
        light_scale_scope = settings.value("light_scale/scope", "all", str).strip().lower()
        light_scale_portal_strict_only = bool(settings.value("light_scale/portal_strict_only", False, bool))
        inventory_scope = settings.value("inventory/scope", "all", str).strip().lower()
        inventory_portal_strict_only = bool(settings.value("inventory/portal_strict_only", False, bool))
        inventory_nif_only = bool(
            settings.value(
                "inventory/nif_only",
                settings.value("inventory/nifs_with_pl_only", False, bool),
                bool,
            )
        )
        inventory_conflicts_only = bool(settings.value("inventory/conflicts_only", False, bool))
        formid_preview_enabled = bool(settings.value("preview/formid_world_enabled", True, bool))
        hide_unresolved_formid_local = bool(
            settings.value("filters/hide_unresolved_formid_local_duplicates", True, bool)
        )
        theme_mode = _normalize_theme_mode(settings.value("ui/theme_mode", "auto", str))

        if mo2_root:
            self.mo2_root_edit.setText(mo2_root)
        if profile_path:
            self.profile_path_edit.setText(profile_path)
        if output_dir:
            self.output_dir_edit.setText(output_dir)
        if patch_name:
            self.patch_name_edit.setText(patch_name)
        self.light_scale_enabled_cb.setChecked(light_scale_enabled)
        self.light_scale_slider.setValue(max(50, min(200, light_scale_slider_value)))
        scope_index = self.light_scale_scope_combo.findData(light_scale_scope)
        if scope_index < 0:
            scope_index = self.light_scale_scope_combo.findData("all")
        if scope_index >= 0:
            self.light_scale_scope_combo.setCurrentIndex(scope_index)
        self.light_scale_portal_strict_cb.setChecked(light_scale_portal_strict_only)
        if inventory_scope not in {"all", "interior", "exterior", "unscoped"}:
            inventory_scope = "all"
        self._inventory_scope = inventory_scope
        self._inventory_portal_strict_only = inventory_portal_strict_only
        self._inventory_nif_only = inventory_nif_only
        self._inventory_conflicts_only = inventory_conflicts_only
        self.formid_preview_enabled_cb.setChecked(formid_preview_enabled)
        self.hide_unresolved_formid_local_duplicates_cb.setChecked(hide_unresolved_formid_local)
        theme_index = self.theme_mode_combo.findData(theme_mode)
        if theme_index < 0:
            theme_index = self.theme_mode_combo.findData("auto")
        previous_block_state = self.theme_mode_combo.blockSignals(True)
        if theme_index >= 0:
            self.theme_mode_combo.setCurrentIndex(theme_index)
        self.theme_mode_combo.blockSignals(previous_block_state)
        self._fit_combo_to_current_text(self.theme_mode_combo, extra_padding_px=48)
        self._refresh_light_scale_button()
        self._apply_theme_stylesheet()

        self._ensure_output_dir_exists(self._resolve_output_dir_text(self.output_dir_edit.text().strip()))

    def _save_persistent_paths(self) -> None:
        settings = self._settings()
        settings.setValue("paths/mo2_root", self.mo2_root_edit.text().strip())
        settings.setValue("paths/profile_path", self.profile_path_edit.text().strip())
        settings.setValue("paths/output_dir", self.output_dir_edit.text().strip())
        settings.setValue("paths/patch_name", self.patch_name_edit.text().strip())
        if hasattr(self, "light_scale_enabled_cb"):
            settings.setValue("light_scale/enabled", self.light_scale_enabled_cb.isChecked())
            settings.setValue("light_scale/slider_value", int(self.light_scale_slider.value()))
            settings.setValue("light_scale/scope", str(self.light_scale_scope_combo.currentData() or "all"))
            settings.setValue("light_scale/portal_strict_only", self.light_scale_portal_strict_cb.isChecked())
        settings.setValue("inventory/scope", self._inventory_scope)
        settings.setValue("inventory/portal_strict_only", self._inventory_portal_strict_only)
        settings.setValue("inventory/nif_only", self._inventory_nif_only)
        settings.setValue("inventory/conflicts_only", self._inventory_conflicts_only)
        if hasattr(self, "formid_preview_enabled_cb"):
            settings.setValue("preview/formid_world_enabled", self.formid_preview_enabled_cb.isChecked())
        if hasattr(self, "hide_unresolved_formid_local_duplicates_cb"):
            settings.setValue(
                "filters/hide_unresolved_formid_local_duplicates",
                self.hide_unresolved_formid_local_duplicates_cb.isChecked(),
            )
        if hasattr(self, "theme_mode_combo"):
            settings.setValue("ui/theme_mode", self._theme_mode())
        settings.sync()

    def _resolve_output_dir_text(self, output_dir_text: str) -> Path:
        candidate = Path(output_dir_text).expanduser()
        if candidate.is_absolute():
            return candidate
        return self._application_base_dir() / candidate

    def _ensure_output_dir_exists(self, output_dir: Path) -> str | None:
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:  # noqa: BLE001
            return str(exc)
        if not output_dir.is_dir():
            return "Path exists but is not a directory."
        return None

    @staticmethod
    def _error_detail_line(error_text: str) -> str:
        lines = [line.strip() for line in str(error_text).splitlines() if line.strip()]
        if not lines:
            return "No additional details available."
        for line in reversed(lines):
            lowered = line.lower()
            if lowered.startswith("traceback"):
                continue
            if line.startswith('File "'):
                continue
            return line
        return lines[-1]

    def _format_scan_error_message(self, error_text: str) -> str:
        detail = self._error_detail_line(error_text)
        lowered = detail.lower()

        if "modlist.txt" in lowered:
            return (
                "Profile Path must point to either:\n"
                "- an MO2 profile folder containing modlist.txt, or\n"
                "- a Vortex profile folder containing plugins.txt/loadorder.txt.\n\n"
                "How to fix:\n"
                "1. For MO2: open MO2 once with this profile so modlist.txt exists.\n"
                "2. For Vortex: use the profile folder under Vortex\\<game>\\profiles\\<ProfileId>.\n"
                "3. Scan again.\n\n"
                f"Details: {detail}"
            )

        if "profile path does not exist" in lowered or "profile path is not a directory" in lowered:
            return (
                "The selected Profile Path is invalid.\n\n"
                "How to fix:\n"
                "1. Set Profile Path to an existing MO2 or Vortex profile folder.\n"
                "2. Make sure the folder belongs to the profile you want to scan.\n"
                "3. Scan again.\n\n"
                f"Details: {detail}"
            )

        if "mods directory does not exist" in lowered or "could not resolve mods directory" in lowered:
            return (
                "The mods directory could not be resolved from your setup.\n\n"
                "How to fix:\n"
                "1. MO2: set MO2 Root to your Mod Organizer 2 folder.\n"
                "2. Vortex: set MO2 Root to your Vortex staging mods folder (or ensure Vortex state has installPath).\n"
                "3. Retry scan.\n\n"
                f"Details: {detail}"
            )

        if "permission" in lowered or "access is denied" in lowered:
            return (
                "The resolver does not have permission to read or write one of the required paths.\n\n"
                "How to fix:\n"
                "1. Close MO2 and Explorer windows that might lock files.\n"
                "2. Choose an Output Dir you can write to.\n"
                "3. Retry the scan.\n\n"
                f"Details: {detail}"
            )

        return (
            "Scan failed.\n\n"
            "How to fix:\n"
            "1. Verify path inputs are correct.\n"
            "2. Ensure the selected profile folder matches MO2 or Vortex format.\n"
            "3. Retry scan.\n\n"
            f"Details: {detail}"
        )

    def _format_ui_error_message(self, context: str, error_text: str) -> str:
        detail = self._error_detail_line(error_text)
        return (
            f"{context}\n\n"
            "How to fix:\n"
            "1. Try the action again.\n"
            "2. If it repeats, restart LP Resolver.\n"
            "3. If it still repeats, report it on GitHub with the detail below.\n\n"
            f"Details: {detail}"
        )

    def _format_file_io_error_message(self, context: str, error_text: str) -> str:
        detail = self._error_detail_line(error_text)
        return (
            f"{context}\n\n"
            "How to fix:\n"
            "1. Check that the selected file/folder exists.\n"
            "2. Check that you have read/write permission.\n"
            "3. Retry the action.\n\n"
            f"Details: {detail}"
        )

    def _build_controls_group(self) -> QWidget:
        group = QGroupBox("Scan And Output")
        group.setToolTip(
            "Configure scan inputs and export output.\n"
            "Paths should point to your MO2 or Vortex setup and desired report location."
        )
        grid = QGridLayout(group)
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 0)

        self.mo2_root_edit = QLineEdit("")
        self.mo2_root_edit.setPlaceholderText("C:\\Path\\To\\MO2  (or E:\\modding\\vortex)")
        self.mo2_root_edit.setToolTip(
            "For MO2: root folder containing 'mods/' and 'profiles/'.\n"
            "For Vortex: staging mods folder (for example E:\\modding\\vortex).\n"
            "Example MO2: C:\\Path\\To\\MO2"
        )
        self.profile_path_edit = QLineEdit("")
        self.profile_path_edit.setPlaceholderText("MO2\\profiles\\<Profile>  or  Vortex\\<game>\\profiles\\<id>")
        self.profile_path_edit.setToolTip(
            "Exact profile folder to scan.\n"
            "MO2 example: C:\\Path\\To\\MO2\\profiles\\YourProfile\n"
            "Vortex example: C:\\Users\\<user>\\AppData\\Roaming\\Vortex\\skyrimse\\profiles\\<ProfileId>"
        )
        self.output_dir_edit = QLineEdit("output")
        self.output_dir_edit.setToolTip(
            "Where report.json/report.md are written.\n"
            "Also used as default location for resolver_decisions.json.\n"
            "Relative paths are resolved under the LP Conflict Resolver folder.\n"
            "Default: output"
        )
        self._ensure_output_dir_exists(self._resolve_output_dir_text(self.output_dir_edit.text().strip()))
        self.patch_name_edit = QLineEdit("LP_ConflictPatch")
        self.patch_name_edit.setToolTip(
            "Name of exported patch mod folder under MO2 mods/.\n"
            "Used on export, not during scan."
        )
        self.light_scale_menu_btn = QPushButton("Light Scale")
        self.light_scale_menu_btn.setToolTip(
            "Configure optional post-resolution light intensity scaling.\n"
            "This opens a compact drop-down menu with slider and filters."
        )
        self.light_scale_menu_btn.clicked.connect(self._show_light_scale_menu)
        self._build_light_scale_menu()
        self.mo2_root_edit.editingFinished.connect(self._save_persistent_paths)
        self.profile_path_edit.editingFinished.connect(self._save_persistent_paths)
        self.output_dir_edit.editingFinished.connect(self._save_persistent_paths)
        self.patch_name_edit.editingFinished.connect(self._save_persistent_paths)

        self.pl_source_combo = DropDownComboBox()
        self.pl_source_combo.addItem("NIF (ENB Particle Lights)", "nif")
        self.pl_source_combo.addItem("JSON", "json")
        self.pl_source_combo.addItem("Both", "both")
        both_index = self.pl_source_combo.findData("both")
        if both_index >= 0:
            self.pl_source_combo.setCurrentIndex(both_index)
        self.pl_source_combo.setToolTip(
            "Choose light source for LP-vs-PL overlap checks:\n"
            "- NIF: scan ENB Particle Lights mesh targets (recommended)\n"
            "- JSON: scan JSON-defined PL targets\n"
            "- Both: combine both sources"
        )
        self._mark_as_dropdown(self.pl_source_combo)

        self.only_overlap_cb = QCheckBox("Overlap Only")
        self.only_overlap_cb.setToolTip(
            "Show only LP-vs-PL overlaps.\n"
            "Hides LP-only duplicate conflicts.\n"
            "Enabling this toggle auto-starts a rescan (when a scan result exists)."
        )
        self.ignore_duplicate_exact_cb = QCheckBox("Ignore Exact Duplicates")
        self.ignore_duplicate_exact_cb.setToolTip(
            "Hide exact duplicate LP entries (same effective settings).\n"
            "Useful when you only want to review divergent conflicts.\n"
            "Enabling this toggle auto-starts a rescan (when a scan result exists)."
        )
        self.cross_mod_duplicates_cb = QCheckBox("Cross-Mod Duplicates")
        self.cross_mod_duplicates_cb.setToolTip(
            "Keep LP duplicate conflict types only when entries come from different mods.\n"
            "Same-mod duplicates are filtered out.\n"
            "Enabling this toggle auto-starts a rescan (when a scan result exists)."
        )
        self.include_overridden_files_cb = QCheckBox("Include Overridden")
        self.include_overridden_files_cb.setChecked(False)
        self.include_overridden_files_cb.setToolTip(
            "Include JSON files that are overridden at the same virtual path by higher-priority mods.\n"
            "Off (recommended): scan only effective MO2 winners.\n"
            "Enabling this toggle auto-starts a rescan (when a scan result exists)."
        )
        self.include_refinements_cb = QCheckBox("Include Refinements")
        self.include_refinements_cb.setChecked(False)
        self.include_refinements_cb.setToolTip(
            "Include 'duplicate_refinement_disjoint' in results.\n"
            "Off (recommended): focus on likely stacking conflicts only.\n"
            "Enabling this toggle auto-starts a rescan (when a scan result exists)."
        )
        self.include_worldspace_divergent_cb = QCheckBox("Include Worldspace Splits")
        self.include_worldspace_divergent_cb.setChecked(False)
        self.include_worldspace_divergent_cb.setToolTip(
            "Include 'duplicate_condition_exclusive' entries.\n"
            "These are overlapping anchors with mutually exclusive worldspace conditions\n"
            "(for example interior vs exterior variants), so they usually do not stack simultaneously.\n"
            "Enabling this toggle auto-starts a rescan (when a scan result exists)."
        )
        self.only_overlap_cb.toggled.connect(self._on_scan_filter_toggle_requires_rescan)
        self.ignore_duplicate_exact_cb.toggled.connect(self._on_scan_filter_toggle_requires_rescan)
        self.cross_mod_duplicates_cb.toggled.connect(self._on_scan_filter_toggle_requires_rescan)
        self.include_overridden_files_cb.toggled.connect(self._on_scan_filter_toggle_requires_rescan)
        self.include_refinements_cb.toggled.connect(self._on_scan_filter_toggle_requires_rescan)
        self.include_worldspace_divergent_cb.toggled.connect(self._on_scan_filter_toggle_requires_rescan)
        self.formid_preview_enabled_cb = QCheckBox("FormID LP Preview")
        self.formid_preview_enabled_cb.setChecked(True)
        self.formid_preview_enabled_cb.setToolTip(
            "Enable world-space preview for FormID LP targets.\n"
            "When on, the resolver reads active plugins, resolves winning REFR/ACHR reference records,\n"
            "and transforms LP local points with world position/rotation/scale."
        )
        self.formid_preview_enabled_cb.toggled.connect(self._on_formid_preview_options_changed)
        self.hide_unresolved_formid_local_duplicates_cb = QCheckBox("Hide Unresolved FormID Local-Only Duplicates")
        self.hide_unresolved_formid_local_duplicates_cb.setChecked(True)
        self.hide_unresolved_formid_local_duplicates_cb.setToolTip(
            "Hide FormID duplicate conflicts where winning REFR/ACHR world transform cannot be resolved.\n"
            "These entries are local-only overlap estimates and can represent different placed instances."
        )
        self.hide_unresolved_formid_local_duplicates_cb.toggled.connect(self._on_conflict_visibility_options_changed)
        self.theme_mode_combo = DropDownComboBox()
        self.theme_mode_combo.addItem("Auto", "auto")
        self.theme_mode_combo.addItem("Light", "light")
        self.theme_mode_combo.addItem("Dark", "dark")
        self.theme_mode_combo.setToolTip(
            "UI theme mode:\n"
            "- Auto: follow desktop light/dark preference\n"
            "- Light: force light theme\n"
            "- Dark: force dark theme"
        )
        self._mark_as_dropdown(self.theme_mode_combo)
        self._fit_combo_to_current_text(self.theme_mode_combo, extra_padding_px=48)
        self.theme_mode_combo.currentIndexChanged.connect(self._on_theme_mode_changed)

        browse_mo2_btn = QPushButton("Browse")
        browse_profile_btn = QPushButton("Browse")
        browse_output_btn = QPushButton("Browse")
        browse_mo2_btn.setToolTip("Browse to MO2 root folder or Vortex staging mods folder.")
        browse_profile_btn.setToolTip("Browse to profile path folder.")
        browse_output_btn.setToolTip("Browse to report output folder.")
        browse_mo2_btn.clicked.connect(lambda: self._browse_directory(self.mo2_root_edit))
        browse_profile_btn.clicked.connect(lambda: self._browse_directory(self.profile_path_edit))
        browse_output_btn.clicked.connect(lambda: self._browse_directory(self.output_dir_edit))

        self.scan_btn = QPushButton("Scan")
        self.scan_btn.setObjectName("scanActionButton")
        self.scan_btn.setToolTip(
            "Run scan using current settings.\n"
            "Updates conflicts table and summary."
        )
        self.scan_btn.clicked.connect(self.start_scan)

        self.load_decisions_btn = QPushButton("Load Decisions")
        self.save_decisions_btn = QPushButton("Save Decisions")
        self.export_patch_btn = QPushButton("Export Patch")
        self.clear_all_decisions_btn = QPushButton("Clear All Decisions")
        self.load_decisions_btn.setToolTip("Load resolver decisions from JSON.")
        self.clear_all_decisions_btn.setToolTip("Remove all currently stored decisions from this session.")
        self.save_decisions_btn.setToolTip("Save current decisions to JSON.")
        self.export_patch_btn.setToolTip(
            "Generate patch mod JSON from current decisions.\n"
            "Writes overrides at original LightPlacer source paths under MO2 mods/<PatchName>/\n"
            "so MO2 last-wins behavior applies.\n"
            "If Light Scale is enabled, export also writes a second patch mod:\n"
            "<PatchName>_LightIntensityPatch (place it after the first patch).\n"
            "For Vortex profiles, writes to the Vortex mods staging folder under <PatchName>/\n"
            "(for example E:\\modding\\vortex\\<PatchName> or E:\\modding\\vortex\\<game>\\<PatchName>).\n"
            "Vortex: ensure this patch mod has higher deployment/conflict priority than all other\n"
            "mods that provide LightPlacer JSON files, so the patch files win."
        )
        self.load_decisions_btn.clicked.connect(self.load_decisions_from_disk)
        self.save_decisions_btn.clicked.connect(self.save_decisions_to_disk)
        self.export_patch_btn.clicked.connect(self.export_patch_mod)
        self.clear_all_decisions_btn.clicked.connect(self.clear_all_decisions)
        self.inventory_export_btn = QPushButton("Export Results")
        self.inventory_export_btn.setEnabled(False)
        self.inventory_export_btn.setToolTip(
            "Export detailed scan results as CSV + JSON.\n"
            "Enabled after the first successful scan.\n"
            "Click to open filter window (Interior/Exterior, PortalStrict, NIF only)."
        )
        self.inventory_export_btn.clicked.connect(self.export_inventory_reports)

        self.apply_overlap_disable_btn = QPushButton("Disable LP for PL overlaps")
        self.apply_overlap_disable_btn.clicked.connect(self.apply_disable_for_all_overlaps)
        self.apply_highest_duplicates_btn = QPushButton("Keep Highest For All Duplicates")
        self.apply_highest_duplicates_btn.clicked.connect(self.apply_keep_highest_for_all_duplicates)
        self.apply_overlap_disable_btn.setToolTip(
            "Bulk action: for every Light Placer versus Particle Lights overlap conflict, "
            "disable Light Placer entries in the exported patch."
        )
        self.apply_highest_duplicates_btn.setToolTip(
            "Bulk action: set decision 'keep_highest_priority' for duplicate conflicts.\n"
            "Winner criteria (deterministic):\n"
            "1) MO2 position (source_priority; larger wins)\n"
            "2) For divergent duplicates with same worldspace context, PortalStrict preferred\n"
            "3) Larger radius\n"
            "4) Higher fade\n"
            "5) source_mod\n"
            "6) source_file\n"
            "7) entry_id\n"
            "Vortex note: Keep Highest currently cannot determine priority order reliably from Vortex lists.\n"
            "For Vortex profiles, review results manually before exporting.\n"
            "Use with care: avoid this when duplicates are intentional refinements,\n"
            "worldspace-split variants, or hand-tuned multi-light compositions."
        )

        mods_root_label = QLabel("MO2 Root/Vortex mod staging folder")
        mods_root_label.setWordWrap(True)
        grid.addWidget(mods_root_label, 0, 0)
        grid.addWidget(self.mo2_root_edit, 0, 1)
        grid.addWidget(browse_mo2_btn, 0, 2)
        grid.addWidget(QLabel("Profile Path"), 1, 0)
        grid.addWidget(self.profile_path_edit, 1, 1)
        grid.addWidget(browse_profile_btn, 1, 2)
        grid.addWidget(QLabel("Output Dir"), 2, 0)
        grid.addWidget(self.output_dir_edit, 2, 1)
        grid.addWidget(browse_output_btn, 2, 2)
        grid.addWidget(QLabel("Patch Mod Name"), 3, 0)
        grid.addWidget(self.patch_name_edit, 3, 1)
        grid.addWidget(self.light_scale_menu_btn, 3, 2)
        grid.addWidget(QLabel("Light Source"), 4, 0)
        grid.addWidget(self.pl_source_combo, 4, 1)
        grid.addWidget(self.inventory_export_btn, 4, 2)

        filter_row_primary = QHBoxLayout()
        filter_row_primary.addWidget(self.only_overlap_cb)
        filter_row_primary.addWidget(self.include_refinements_cb)
        filter_row_primary.addWidget(self.include_worldspace_divergent_cb)
        filter_row_primary.addSpacing(12)
        filter_row_primary.addWidget(self.cross_mod_duplicates_cb)
        filter_row_primary.addWidget(self.ignore_duplicate_exact_cb)
        filter_row_primary.addStretch(1)
        grid.addLayout(filter_row_primary, 5, 0, 1, 2)

        theme_cell = QVBoxLayout()
        theme_cell.setContentsMargins(0, 0, 0, 0)
        theme_cell.setSpacing(2)
        theme_cell.addWidget(QLabel("Theme"))
        theme_cell.addWidget(self.theme_mode_combo)
        grid.addLayout(theme_cell, 5, 2, 1, 1, Qt.AlignRight)

        filter_row_secondary = QHBoxLayout()
        filter_row_secondary.addWidget(self.include_overridden_files_cb)
        filter_row_secondary.addWidget(self.formid_preview_enabled_cb)
        filter_row_secondary.addWidget(self.hide_unresolved_formid_local_duplicates_cb)
        filter_row_secondary.addStretch(1)
        grid.addLayout(filter_row_secondary, 6, 0, 1, 3)

        for btn in (
            self.scan_btn,
            self.load_decisions_btn,
            self.save_decisions_btn,
            self.export_patch_btn,
            self.inventory_export_btn,
            self.clear_all_decisions_btn,
            self.apply_overlap_disable_btn,
            self.apply_highest_duplicates_btn,
        ):
            btn.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)

        button_row_primary = QHBoxLayout()
        button_row_primary.setSpacing(6)
        button_row_primary.addWidget(self.scan_btn)
        button_row_primary.addWidget(self.load_decisions_btn)
        button_row_primary.addWidget(self.save_decisions_btn)
        button_row_primary.addWidget(self.export_patch_btn)
        button_row_primary.addWidget(self.clear_all_decisions_btn)
        button_row_primary.addWidget(self.apply_overlap_disable_btn)
        button_row_primary.addWidget(self.apply_highest_duplicates_btn)
        button_row_primary.addStretch(1)
        grid.addLayout(button_row_primary, 7, 0, 1, 3)

        return group

    def _build_conflicts_panel(self) -> QWidget:
        box = QGroupBox("Conflicts")
        box.setToolTip(
            "Filtered conflict list.\n"
            "Select one or more rows to inspect source JSON files and apply decisions.\n"
            "Use Shift/Ctrl for multi-select."
        )
        layout = QVBoxLayout(box)

        self.conflicts_table = QTableWidget(0, 6)
        self.conflicts_table.setHorizontalHeaderLabels(["Target", "Types", "LP JSON", "LP #", "PL #", "Decision"])
        self.conflicts_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.conflicts_table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.conflicts_table.itemSelectionChanged.connect(self.on_conflict_selection_changed)
        self.conflicts_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.conflicts_table.customContextMenuRequested.connect(self._show_conflicts_context_menu)
        self.conflicts_table.setSortingEnabled(True)
        self.conflicts_table.setAlternatingRowColors(True)
        self.conflicts_table.setWordWrap(False)
        self.conflicts_table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.conflicts_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.conflicts_table.setToolTip(
            "Columns:\n"
            "- Target: canonical NIF path or normalized FormID key\n"
            "- Types: detected conflict types (hover value for meaning/overhead)\n"
            "- LP JSON: contributing LightPlacer files\n"
            "- LP # / PL #: candidate counts\n"
            "- Decision: current resolver action\n"
            "Right-click a row to open contributing source folder(s) in Explorer."
        )

        header = self.conflicts_table.horizontalHeader()
        header.setMinimumSectionSize(28)
        header.setSectionResizeMode(0, QHeaderView.Interactive)  # Target
        header.setSectionResizeMode(1, QHeaderView.Interactive)  # Types
        header.setSectionResizeMode(2, QHeaderView.Interactive)  # LP Mods
        header.setSectionResizeMode(3, QHeaderView.Interactive)  # LP #
        header.setSectionResizeMode(4, QHeaderView.Interactive)  # PL #
        header.setSectionResizeMode(5, QHeaderView.Interactive)  # Decision
        self.conflicts_table.setColumnWidth(0, 640)
        self.conflicts_table.setColumnWidth(1, 200)
        self.conflicts_table.setColumnWidth(2, 520)
        self.conflicts_table.setColumnWidth(3, 66)
        self.conflicts_table.setColumnWidth(4, 66)
        self.conflicts_table.setColumnWidth(5, 140)
        header.setStretchLastSection(False)

        layout.addWidget(self.conflicts_table)
        return box

    def _build_details_panel(self) -> QWidget:
        box = QGroupBox("Details And Decisions")
        box.setToolTip(
            "Inspect selected conflict and choose resolution action."
        )
        layout = QVBoxLayout(box)

        self.details_decision_widget = QWidget()
        decision_top_grid = QGridLayout()
        decision_top_grid.setContentsMargins(0, 0, 0, 0)
        decision_top_grid.setHorizontalSpacing(6)
        decision_top_grid.setVerticalSpacing(4)

        action_label = QLabel("Action")
        entry_label = QLabel("LP Entries")
        self.action_combo = DropDownComboBox()
        self.action_combo.addItem("Ignore", "ignore")
        self.action_combo.addItem("Keep Highest", "keep_highest_priority")
        self.action_combo.addItem("Choose Entries", "choose_entry")
        self.action_combo.addItem("Disable LP", "disable_lp")
        self.action_combo.setToolTip(
            "Resolution action for selected conflict:\n"
            "- Ignore: leave unchanged\n"
            "- Keep Highest: keep one LP entry by deterministic priority order:\n"
            "  1) source_priority (MO2; larger wins)\n"
            "  2) For divergent duplicates with same worldspace context, PortalStrict preferred\n"
            "  3) larger radius\n"
            "  4) higher fade\n"
            "  5) source_mod\n"
            "  6) source_file\n"
            "  7) entry_id\n"
            "- Choose Entries: keep selected LP entries (multi-select)\n"
            "- Disable LP: export no LP entries for this target key\n"
            "Note: Keep Highest is not quality-aware; it only follows priority/tie-break order.\n"
            "Vortex note: Keep Highest currently cannot determine priority order reliably from Vortex lists.\n"
            "For Vortex profiles, review results manually before exporting.\n"
            "Anchor Preview legend: winner entry/target is shown in bold text."
        )
        self._mark_as_dropdown(self.action_combo)
        self.action_combo.currentTextChanged.connect(lambda _: self._fit_combo_to_current_text(self.action_combo))
        self._fit_combo_to_current_text(self.action_combo)

        self.entry_list = QListWidget()
        self.entry_list.setToolTip(
            "LP entries used when action is 'Choose Entries'.\n"
            "Use Ctrl/Shift or drag to select multiple entries to keep."
        )
        self.entry_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.entry_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.entry_list.setMinimumWidth(220)
        self.entry_list.setMinimumHeight(48)
        self.entry_list.setMaximumHeight(48)
        self.entry_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.entry_list.itemSelectionChanged.connect(self._on_entry_selection_changed)

        self.apply_btn = QPushButton("Apply To Selected")
        self.clear_btn = QPushButton("Clear Decision")
        self.apply_btn.setToolTip("Apply current action (and selected LP entries, if needed) to selected conflict.")
        self.clear_btn.setToolTip("Remove stored decision for selected conflict.")
        self.apply_btn.clicked.connect(self.apply_decision_to_selected)
        self.clear_btn.clicked.connect(self.clear_decision_for_selected)
        self.apply_btn.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.clear_btn.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)

        decision_top_grid.addWidget(action_label, 0, 0)
        decision_top_grid.addWidget(self.action_combo, 0, 1)
        decision_top_grid.addWidget(entry_label, 1, 0, 1, 2)
        decision_top_grid.addWidget(self.entry_list, 2, 0, 1, 2)
        decision_top_grid.setColumnStretch(0, 0)
        decision_top_grid.setColumnStretch(1, 1)

        decision_buttons_row = QHBoxLayout()
        decision_buttons_row.setContentsMargins(0, 0, 0, 0)
        decision_buttons_row.setSpacing(8)
        decision_buttons_row.addStretch(1)
        decision_buttons_row.addWidget(self.apply_btn)
        decision_buttons_row.addWidget(self.clear_btn)

        decision_layout = QVBoxLayout(self.details_decision_widget)
        decision_layout.setContentsMargins(0, 0, 0, 0)
        decision_layout.setSpacing(6)
        decision_layout.addLayout(decision_top_grid)
        decision_layout.addLayout(decision_buttons_row)
        self.details_decision_widget.setMinimumHeight(0)
        self.details_decision_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)

        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setLineWrapMode(QTextEdit.WidgetWidth)
        self.detail_text.setWordWrapMode(QTextOption.WrapAnywhere)
        self.detail_text.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.detail_text.setToolTip(
            "Detailed conflict breakdown:\n"
            "- LP/PL source files\n"
            "- LP entry payload/settings\n"
            "- IDs used for export decisions"
        )

        preview_group = QGroupBox("Anchor Preview")
        preview_group.setToolTip(
            "Visual LP anchor debug:\n"
            "- Gray shape: lightweight 2D mesh silhouette from NIF data\n"
            "- Left: X/Y top view\n"
            "- Right: X/Z side view\n"
            "- Colored circles: LP/PL anchors, radius drawn to true relative scale from LP/PL radius values.\n"
            "- Bold legend text marks the winner selected by current decision.\n"
            "- PL targets without explicit points use mesh centroid as coarse estimate.\n"
            "Use this to verify likely overlap vs disjoint refinement."
        )
        preview_layout = QVBoxLayout(preview_group)
        preview_layout.setContentsMargins(6, 6, 6, 6)
        preview_layout.setSpacing(4)
        self.anchor_preview = AnchorPreviewWidget()
        self.anchor_summary_label = QLabel("Select a conflict to preview LP anchor placement.")
        self.anchor_summary_label.setWordWrap(True)
        self.anchor_summary_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.mesh_status_label = QLabel("Mesh: not loaded")
        self.mesh_status_label.setWordWrap(True)
        self.mesh_status_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.anchor_points_text = QTextEdit()
        self.anchor_points_text.setReadOnly(True)
        self.anchor_points_text.setLineWrapMode(QTextEdit.WidgetWidth)
        self.anchor_points_text.setWordWrapMode(QTextOption.WrapAnywhere)
        self.anchor_points_text.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.anchor_points_text.setMinimumHeight(64)
        self.anchor_points_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.anchor_points_text.setToolTip(
            "Parsed LP anchor points/nodes per entry.\n"
            "Use this to confirm if entries target the same anchor coordinates."
        )
        preview_layout.addWidget(self.anchor_preview, 1)
        preview_layout.addWidget(self.anchor_summary_label)
        preview_layout.addWidget(self.mesh_status_label)
        preview_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        details_text_splitter = QSplitter(Qt.Vertical)
        details_text_splitter.setChildrenCollapsible(False)
        details_text_splitter.setHandleWidth(10)
        details_text_splitter.setToolTip("Drag this divider to resize Anchor Points and Details text panes.")
        details_text_splitter.addWidget(self.anchor_points_text)
        details_text_splitter.addWidget(self.detail_text)
        details_text_splitter.setStretchFactor(0, 0)
        details_text_splitter.setStretchFactor(1, 1)
        details_text_splitter.setSizes([150, 380])
        details_text_splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        details_text_splitter.handle(1).setCursor(Qt.SizeVerCursor)

        preview_and_text_splitter = QSplitter(Qt.Vertical)
        preview_and_text_splitter.setChildrenCollapsible(False)
        preview_and_text_splitter.setHandleWidth(10)
        preview_and_text_splitter.setToolTip("Drag this divider to resize Anchor Preview vs lower text panes.")
        preview_and_text_splitter.addWidget(preview_group)
        preview_and_text_splitter.addWidget(details_text_splitter)
        preview_and_text_splitter.setStretchFactor(0, 1)
        preview_and_text_splitter.setStretchFactor(1, 1)
        preview_and_text_splitter.setSizes([320, 420])
        preview_and_text_splitter.handle(1).setCursor(Qt.SizeVerCursor)

        layout.addWidget(self.details_decision_widget)
        layout.addWidget(preview_and_text_splitter, 1)
        self._update_entry_list_height()
        return box

    def _browse_directory(self, target_edit: QLineEdit) -> None:
        initial = target_edit.text().strip() or "."
        selected = QFileDialog.getExistingDirectory(self, "Select Directory", initial)
        if selected:
            target_edit.setText(selected)

    def _build_scan_config(self) -> ScanConfig:
        output_dir_text = self.output_dir_edit.text().strip()
        return ScanConfig(
            mo2_root=Path(self.mo2_root_edit.text().strip()),
            profile_path=Path(self.profile_path_edit.text().strip()),
            output_dir=self._resolve_output_dir_text(output_dir_text),
            pl_source=self.pl_source_combo.currentData(),
            only_overlap=self.only_overlap_cb.isChecked(),
            ignore_duplicate_exact=self.ignore_duplicate_exact_cb.isChecked(),
            cross_mod_lp_duplicates_only=self.cross_mod_duplicates_cb.isChecked(),
            include_refinements=self.include_refinements_cb.isChecked(),
            include_worldspace_divergent=self.include_worldspace_divergent_cb.isChecked(),
            include_overridden_files=self.include_overridden_files_cb.isChecked(),
        )

    def _scan_filter_signature(self) -> tuple[str, bool, bool, bool, bool, bool, bool]:
        return (
            str(self.pl_source_combo.currentData() or "nif"),
            self.only_overlap_cb.isChecked(),
            self.ignore_duplicate_exact_cb.isChecked(),
            self.cross_mod_duplicates_cb.isChecked(),
            self.include_refinements_cb.isChecked(),
            self.include_worldspace_divergent_cb.isChecked(),
            self.include_overridden_files_cb.isChecked(),
        )

    def _scan_result_filter_signature(
        self,
        result: ScanResult | None,
    ) -> tuple[str, bool, bool, bool, bool, bool, bool] | None:
        if result is None:
            return None
        cfg = result.config
        return (
            str(cfg.pl_source or "nif"),
            bool(cfg.only_overlap),
            bool(cfg.ignore_duplicate_exact),
            bool(cfg.cross_mod_lp_duplicates_only),
            bool(cfg.include_refinements),
            bool(cfg.include_worldspace_divergent),
            bool(cfg.include_overridden_files),
        )

    def _scan_filters_match_last_result(self) -> bool:
        previous = self._scan_result_filter_signature(self.scan_result)
        if previous is None:
            return False
        return self._scan_filter_signature() == previous

    def _build_scan_summary_text(self, result: ScanResult) -> str:
        visible_conflicts = len(self._conflict_by_nif)
        hidden_conflicts = max(0, len(result.conflicts) - visible_conflicts)
        summary = (
            "Enabled mods: {0} | LP files: {1} | PL candidates: {2} | LP entries: {3} | PL targets: {4} | "
            "Conflicts(raw/filtered/visible): {5}/{6}/{7}".format(
                result.enabled_mod_count,
                result.lp_candidate_files,
                result.pl_candidate_files,
                len(result.lp_entries),
                len(result.pl_targets),
                len(result.detected_conflicts),
                len(result.conflicts),
                visible_conflicts,
            )
        )
        summary += f" | Order source: {result.mod_order_source}"
        if hidden_conflicts > 0 and self.hide_unresolved_formid_local_duplicates_cb.isChecked():
            summary += f" | Hidden unresolved FormID local-only duplicates: {hidden_conflicts}"
        if not result.config.include_overridden_files:
            summary += f" | Overridden skipped LP/PL: {result.lp_overridden_files}/{result.pl_overridden_files}"
        if result.synthetic_modlist_path is not None:
            summary += f" | Synthetic list: {result.synthetic_modlist_path}"
        return summary

    def _validate_scan_inputs(self) -> ScanConfig | None:
        config = self._build_scan_config()
        errors: list[str] = []

        mo2_root_text = self.mo2_root_edit.text().strip()
        profile_path_text = self.profile_path_edit.text().strip()
        output_dir_text = self.output_dir_edit.text().strip()
        profile_dir = config.profile_path
        profile_is_vortex = profile_dir.exists() and profile_dir.is_dir() and (
            (profile_dir / "plugins.txt").exists() or (profile_dir / "loadorder.txt").exists()
        )

        if not mo2_root_text and not profile_is_vortex:
            errors.append("MO2 Root/Vortex mod staging folder is required for MO2 profiles.")
        elif mo2_root_text and (not config.mo2_root.exists() or not config.mo2_root.is_dir()):
            errors.append(f"MO2 Root/Vortex mod staging folder does not exist or is not a folder: {config.mo2_root}")

        if not profile_path_text:
            errors.append("Profile Path is required.")
        elif not config.profile_path.exists() or not config.profile_path.is_dir():
            errors.append(f"Profile Path does not exist or is not a folder: {config.profile_path}")
        elif not (
            (config.profile_path / "modlist.txt").exists()
            or (config.profile_path / "plugins.txt").exists()
            or (config.profile_path / "loadorder.txt").exists()
        ):
            errors.append(
                "Profile Path must contain modlist.txt (MO2) or plugins.txt/loadorder.txt (Vortex).\n"
                "Tip: for MO2 open the profile once so modlist.txt is generated."
            )

        if not output_dir_text:
            errors.append("Output Dir is required.")
        else:
            output_dir_error = self._ensure_output_dir_exists(config.output_dir)
            if output_dir_error:
                errors.append(f"Output Dir is not writable: {config.output_dir} ({output_dir_error})")

        if errors:
            QMessageBox.warning(self, "Invalid Scan Paths", "\n".join(errors))
            return None
        return config

    def start_scan(self) -> None:
        if self._scan_in_progress:
            return
        if self._worker_thread is not None and self._worker_thread.isRunning():
            return
        config = self._validate_scan_inputs()
        if config is None:
            return
        self._active_scan_id += 1
        scan_id = self._active_scan_id
        clear_formid_preview_caches()
        self._formid_request_seq += 1
        self._formid_request_pending_target = None
        self._formid_request_inflight_target = None
        self._scan_in_progress = True
        self.scan_btn.setEnabled(False)
        self._set_scan_dependent_controls_enabled(False)
        self.scan_result = None
        self._formid_world_resolution_cache = {}
        self._set_scan_summary_state("Scanning...", "running")
        self.detail_text.setPlainText("")
        self._entry_selection_by_nif = {}
        self._conflict_by_nif = {}
        self.anchor_preview.clear_anchor_series()
        self.anchor_preview.clear_mesh_points()
        self.anchor_preview.set_mesh_status_text("Mesh cloud: not loaded")
        self.anchor_summary_label.setText("Select a conflict to preview LP anchor placement.")
        self.mesh_status_label.setText("Mesh: not loaded")
        self.anchor_points_text.clear()
        self.conflicts_table.blockSignals(True)
        self.conflicts_table.setRowCount(0)
        self.conflicts_table.blockSignals(False)
        self.entry_list.clear()
        self._update_entry_list_height()
        worker = ScanWorker(config, scan_id)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self.on_scan_finished)
        worker.failed.connect(self.on_scan_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(self._on_scan_thread_finished)
        thread.finished.connect(thread.deleteLater)

        self._worker_thread = thread
        self._worker = worker
        thread.start()

    @Slot(int, object)
    def on_scan_finished(self, scan_id: int, result: object) -> None:
        if scan_id != self._active_scan_id or self._is_closing:
            return
        try:
            if not isinstance(result, ScanResult):
                self._set_scan_summary_state("Scan failed: invalid result type", "error")
                return

            self.scan_result = result
            self.decisions = {}
            self._entry_selection_by_nif = {}
            self._load_default_decisions_if_present()

            self._populate_conflicts_table()
            self._set_scan_summary_state(self._build_scan_summary_text(result), "success")
            self._set_scan_dependent_controls_enabled(True)
        except Exception as exc:  # noqa: BLE001
            self._set_scan_summary_state("Scan finished, but UI update failed.", "error")
            self._set_scan_dependent_controls_enabled(False)
            QMessageBox.critical(
                self,
                "UI Error",
                self._format_ui_error_message(
                    "Scan finished, but the results view could not be refreshed.",
                    str(exc),
                ),
            )

    @Slot(int, str)
    def on_scan_failed(self, scan_id: int, error_text: str) -> None:
        if scan_id != self._active_scan_id or self._is_closing:
            return
        try:
            self._set_scan_summary_state("Scan failed.", "error")
            self.anchor_preview.clear_anchor_series()
            self.anchor_preview.clear_mesh_points()
            self.anchor_preview.set_mesh_status_text("Mesh cloud: not loaded")
            self.anchor_summary_label.setText("Scan failed. No preview available.")
            self.mesh_status_label.setText("Mesh: not loaded")
            self.anchor_points_text.clear()
            self._set_scan_dependent_controls_enabled(False)
            QMessageBox.critical(self, "Scan Failed", self._format_scan_error_message(error_text))
        except Exception:  # noqa: BLE001
            self._set_scan_summary_state("Scan failed (UI update error).", "error")
            self._set_scan_dependent_controls_enabled(False)

    @Slot()
    def _on_scan_thread_finished(self) -> None:
        self._worker = None
        self._worker_thread = None
        self._scan_in_progress = False
        if self._auto_rescan_requested and not self._is_closing:
            self._auto_rescan_requested = False
            if not self._scan_filters_match_last_result():
                self.start_scan()
                if self._scan_in_progress:
                    return
        if not self._is_closing:
            self.scan_btn.setEnabled(True)
            self._set_scan_dependent_controls_enabled(self.scan_result is not None)

    def closeEvent(self, event) -> None:
        self._is_closing = True
        self.scan_btn.setEnabled(False)
        thread = self._worker_thread
        if thread is not None and thread.isRunning():
            thread.quit()
            # Avoid leaving an active worker thread during shutdown.
            if not thread.wait(30000):
                QMessageBox.warning(
                    self,
                    "Scan In Progress",
                    "A scan is still running. Please wait for it to finish, then close again.",
                )
                self._is_closing = False
                self.scan_btn.setEnabled(not self._scan_in_progress)
                self._set_scan_dependent_controls_enabled(self.scan_result is not None)
                event.ignore()
                return
        formid_thread = self._formid_worker_thread
        if formid_thread is not None and formid_thread.isRunning():
            formid_thread.quit()
            if not formid_thread.wait(30000):
                QMessageBox.warning(
                    self,
                    "FormID Preview Busy",
                    "FormID world preview is still resolving. Please wait for it to finish, then close again.",
                )
                self._is_closing = False
                self.scan_btn.setEnabled(not self._scan_in_progress)
                self._set_scan_dependent_controls_enabled(self.scan_result is not None)
                event.ignore()
                return
        self._save_persistent_paths()
        super().closeEvent(event)

    def _selected_nif_paths(self) -> list[str]:
        selected_rows: set[int] = set()
        selection_model = self.conflicts_table.selectionModel()
        if selection_model is not None:
            for index in selection_model.selectedRows(0):
                selected_rows.add(index.row())
        if not selected_rows:
            for item in self.conflicts_table.selectedItems():
                selected_rows.add(item.row())

        nif_paths: list[str] = []
        for row in sorted(selected_rows):
            nif_item = self.conflicts_table.item(row, 0)
            if nif_item is None:
                continue
            nif_path = nif_item.data(Qt.UserRole)
            if isinstance(nif_path, str) and nif_path:
                nif_paths.append(nif_path)
        return nif_paths

    def _selected_nif_path(self) -> str | None:
        selected_paths = self._selected_nif_paths()
        return selected_paths[0] if selected_paths else None

    def _restore_conflict_selection(self, nif_path: str | None) -> bool:
        if nif_path is None:
            return False
        return self._restore_conflict_selections([nif_path])

    def _restore_conflict_selections(self, nif_paths: list[str] | None) -> bool:
        if not nif_paths:
            return False
        wanted = {path for path in nif_paths if isinstance(path, str) and path}
        if not wanted:
            return False

        selection_model = self.conflicts_table.selectionModel()
        if selection_model is None:
            return False

        selection_model.clearSelection()
        first_index = None
        first_item = None
        for row in range(self.conflicts_table.rowCount()):
            nif_item = self.conflicts_table.item(row, 0)
            if nif_item is None:
                continue
            value = nif_item.data(Qt.UserRole)
            if value not in wanted:
                continue
            model_index = self.conflicts_table.model().index(row, 0)
            selection_model.select(model_index, QItemSelectionModel.Select | QItemSelectionModel.Rows)
            if first_index is None:
                first_index = model_index
                first_item = nif_item

        if first_index is None:
            return False

        selection_model.setCurrentIndex(first_index, QItemSelectionModel.NoUpdate)
        if first_item is not None:
            self.conflicts_table.scrollToItem(first_item, QAbstractItemView.PositionAtCenter)
        return True

    def _populate_conflicts_table(
        self,
        preserve_nif_path: str | None = None,
        preserve_nif_paths: list[str] | None = None,
    ) -> bool:
        if preserve_nif_paths is None:
            if preserve_nif_path is not None:
                preserve_nif_paths = [preserve_nif_path]
            else:
                preserve_nif_paths = self._selected_nif_paths()
        restored = False
        should_refresh_selection = False
        self._updating_conflicts_table = True
        sorting_was_enabled = self.conflicts_table.isSortingEnabled()
        signals_were_blocked = self.conflicts_table.blockSignals(True)
        updates_were_enabled = self.conflicts_table.updatesEnabled()
        self.conflicts_table.setUpdatesEnabled(False)
        self.conflicts_table.setSortingEnabled(False)
        try:
            self.conflicts_table.setRowCount(0)
            self._conflict_by_nif = {}
            if self.scan_result is None:
                return False

            visible_conflicts = self._visible_conflicts()
            for row, conflict in enumerate(visible_conflicts):
                self._conflict_by_nif[conflict.nif_path_canonical] = conflict
                self.conflicts_table.insertRow(row)
                lp_json_summary = self._summarize_lp_json_sources(conflict)
                decision = self.decisions.get(conflict.nif_path_canonical)
                decision_label = ""
                if decision is not None:
                    if decision.action == "choose_entry":
                        selected_count = len(decision.entry_ids)
                        if selected_count <= 0 and decision.entry_id:
                            selected_count = 1
                        if selected_count > 1:
                            decision_label = f"choose_entry ({selected_count})"
                        else:
                            decision_label = "choose_entry"
                    else:
                        decision_label = decision.action
                values = [
                    conflict.nif_path_canonical,
                    self._format_conflict_types(conflict.conflict_types),
                    lp_json_summary,
                    str(len(conflict.lp_entries)),
                    str(len(conflict.pl_targets)),
                    decision_label,
                ]
                for col, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    if col in {3, 4}:
                        item.setTextAlignment(Qt.AlignCenter)
                    if col == 0:
                        item.setData(Qt.UserRole, conflict.nif_path_canonical)
                    if col == 1:
                        item.setToolTip(self._conflict_types_tooltip(conflict.conflict_types))
                    if col == 2:
                        item.setToolTip(self._full_lp_json_sources_text(conflict))
                    self.conflicts_table.setItem(row, col, item)

            self._compact_conflicts_columns()
            restored = self._restore_conflict_selections(preserve_nif_paths)
            should_refresh_selection = restored
            if not restored and self.conflicts_table.rowCount() > 0:
                self.conflicts_table.setCurrentCell(0, 0)
                self.conflicts_table.selectRow(0)
                first_item = self.conflicts_table.item(0, 0)
                if first_item is not None:
                    self.conflicts_table.scrollToItem(first_item, QAbstractItemView.PositionAtCenter)
                    should_refresh_selection = True
            return restored
        finally:
            self.conflicts_table.setSortingEnabled(sorting_was_enabled)
            self.conflicts_table.setUpdatesEnabled(updates_were_enabled)
            self.conflicts_table.blockSignals(signals_were_blocked)
            self._updating_conflicts_table = False
            if should_refresh_selection:
                self.on_conflict_selection_changed()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._window_geometry_initialized:
            self._window_geometry_initialized = True
            self._fit_window_to_available_geometry()
        if self._splitter_sizes_initialized:
            return
        self._splitter_sizes_initialized = True
        self._update_summary_label_height()
        self.scan_panel.setMinimumHeight(self._compute_scan_panel_min_height())
        total_width = max(1, self.content_splitter.size().width())
        left_target = max(360, min(int(total_width * 0.60), total_width - 300))
        self.content_splitter.setSizes([left_target, max(1, total_width - left_target)])
        total_height = max(1, self.left_splitter.size().height())
        scan_min = max(self.scan_panel.minimumHeight(), self.scan_panel.minimumSizeHint().height())
        scan_target = max(scan_min, min(scan_min + 96, int(total_height * 0.36)))
        self.left_splitter.setSizes([scan_target, max(1, total_height - scan_target)])
        self._compact_conflicts_columns()
        self._compact_details_controls()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_summary_label_height()
        self.scan_panel.setMinimumHeight(self._compute_scan_panel_min_height())
        self._compact_conflicts_columns()
        self._compact_details_controls()

    def _on_content_splitter_moved(self, _pos: int, _index: int) -> None:
        self._update_summary_label_height()
        self.scan_panel.setMinimumHeight(self._compute_scan_panel_min_height())
        self._compact_conflicts_columns()
        self._compact_details_controls()

    def _on_left_splitter_moved(self, _pos: int, _index: int) -> None:
        self._update_summary_label_height()
        self.scan_panel.setMinimumHeight(self._compute_scan_panel_min_height())
        self._compact_conflicts_columns()

    def _compute_scan_panel_min_height(self) -> int:
        scan_layout = self.scan_panel.layout()
        if scan_layout is None:
            return 170
        margins = scan_layout.contentsMargins()
        controls_h = self.controls_group.sizeHint().height()
        summary_width = max(220, self.scan_panel.width() - margins.left() - margins.right())
        wrapped_summary_h = self.summary_label.heightForWidth(summary_width)
        label_margins = self.summary_label.contentsMargins()
        single_line_summary_h = (
            self.summary_label.fontMetrics().lineSpacing()
            + label_margins.top()
            + label_margins.bottom()
            + 4
        )
        if wrapped_summary_h <= 0:
            wrapped_summary_h = single_line_summary_h
        summary_h = max(single_line_summary_h, wrapped_summary_h)
        spacing = max(0, scan_layout.spacing())
        minimum = controls_h + single_line_summary_h + spacing + margins.top() + margins.bottom() + 6
        desired = controls_h + summary_h + spacing + margins.top() + margins.bottom() + 6
        # Keep controls visible and allow summary to grow only when wrapping requires it.
        return max(minimum, min(420, desired))

    def _fit_window_to_available_geometry(self) -> None:
        if self.isMaximized() or self.isFullScreen():
            return
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        margin = 8
        max_w = max(640, available.width() - margin * 2)
        max_h = max(480, available.height() - margin * 2)

        target_w = min(max(self.minimumWidth(), self.width()), max_w)
        target_h = min(max(self.minimumHeight(), self.height()), max_h)
        if target_w != self.width() or target_h != self.height():
            self.resize(target_w, target_h)

        frame = self.frameGeometry()
        x = frame.left()
        y = frame.top()

        if frame.right() > available.right() - margin:
            x -= frame.right() - (available.right() - margin)
        if frame.left() < available.left() + margin:
            x = available.left() + margin

        if frame.bottom() > available.bottom() - margin:
            y -= frame.bottom() - (available.bottom() - margin)
        if frame.top() < available.top() + margin:
            y = available.top() + margin

        if x != frame.left() or y != frame.top():
            self.move(int(x), int(y))

    def _compact_conflicts_columns(self) -> None:
        if self.conflicts_table.columnCount() != 6:
            return

        available = self.conflicts_table.viewport().width() - 8
        if available <= 0:
            return

        widths = [self.conflicts_table.columnWidth(i) for i in range(6)]
        mins = self._conflict_min_widths
        total = sum(widths)
        if total == available:
            return

        # Fill free space by expanding long-text columns first, so no right-side gap remains.
        if total < available:
            extra = available - total
            weights = [0.53, 0.12, 0.29, 0.00, 0.00, 0.06]  # NIF, Types, LP JSON, LP#, PL#, Decision
            new_widths = widths[:]
            allocated = 0
            for i, weight in enumerate(weights):
                delta = int(extra * weight)
                new_widths[i] += delta
                allocated += delta

            remainder = extra - allocated
            grow_order = [0, 2, 1, 5]
            idx = 0
            while remainder > 0:
                col = grow_order[idx % len(grow_order)]
                new_widths[col] += 1
                remainder -= 1
                idx += 1

            for i, width in enumerate(new_widths):
                self.conflicts_table.setColumnWidth(i, width)
            return

        new_widths = widths[:]
        reduce_needed = total - available
        flex = [max(0, new_widths[i] - mins[i]) for i in range(6)]
        flex_total = sum(flex)

        if flex_total > 0:
            for i in range(6):
                if flex[i] <= 0:
                    continue
                delta = int(round(reduce_needed * (flex[i] / flex_total)))
                new_widths[i] = max(mins[i], new_widths[i] - delta)

            overflow = sum(new_widths) - available
            if overflow > 0:
                for i in sorted(range(6), key=lambda idx: new_widths[idx] - mins[idx], reverse=True):
                    spare = max(0, new_widths[i] - mins[i])
                    if spare <= 0:
                        continue
                    cut = min(spare, overflow)
                    new_widths[i] -= cut
                    overflow -= cut
                    if overflow <= 0:
                        break
        else:
            # Keep true minimum widths and let horizontal scrolling handle overflow.
            new_widths = mins[:]

        for i, width in enumerate(new_widths):
            self.conflicts_table.setColumnWidth(i, width)

    def _entry_list_row_height(self) -> int:
        if self.entry_list.count() > 0:
            row_h = self.entry_list.sizeHintForRow(0)
            if row_h > 0:
                return row_h
        return max(20, self.entry_list.fontMetrics().height() + 8)

    def _update_entry_list_height(self) -> None:
        row_h = self._entry_list_row_height()
        row_spacing = max(0, self.entry_list.spacing())
        row_block_h = max(1, row_h + row_spacing)

        count = max(1, self.entry_list.count())
        # Keep the decision header compact while still allowing bigger lists to expand naturally.
        # This caps LP list growth to a portion of window height so lower panes remain usable.
        window_height = max(480, self.height())
        max_rows_by_window = max(3, int((window_height * 0.34) / row_block_h))
        visible_rows = min(count, max_rows_by_window)

        frame = (self.entry_list.frameWidth() * 2) + 4
        rows_height = (visible_rows * row_h) + (max(0, visible_rows - 1) * row_spacing)
        viewport_width = self.entry_list.viewport().width()
        widest_item = self.entry_list.sizeHintForColumn(0)
        needs_h_scroll = (
            self.entry_list.count() > 0
            and self.entry_list.horizontalScrollBarPolicy() != Qt.ScrollBarAlwaysOff
            and (viewport_width <= 0 or widest_item > viewport_width)
        )
        scrollbar_height = self.entry_list.horizontalScrollBar().sizeHint().height() if needs_h_scroll else 0
        target_height = frame + rows_height + scrollbar_height + 2

        min_height = frame + row_h + scrollbar_height + 2
        target_height = max(min_height, target_height)

        self.entry_list.setMinimumHeight(target_height)
        self.entry_list.setMaximumHeight(target_height)
        self.details_decision_widget.updateGeometry()

    def _compact_details_controls(self) -> None:
        width = self.details_decision_widget.width()
        compact = width < 560
        very_compact = width < 440

        self.apply_btn.setText("Apply" if compact else "Apply To Selected")
        self.clear_btn.setText("Clear" if compact else "Clear Decision")

        if very_compact:
            self.action_combo.setMinimumContentsLength(7)
            min_floor = 92
        elif compact:
            self.action_combo.setMinimumContentsLength(8)
            min_floor = 118
        else:
            self.action_combo.setMinimumContentsLength(8)
            min_floor = 150

        action_w = max(self.action_combo.minimumWidth(), self.action_combo.width())
        fm = self.fontMetrics()
        reserve = action_w + fm.horizontalAdvance("Action") + 40
        entry_target = max(min_floor, width - reserve)
        self.entry_list.setMinimumWidth(entry_target)
        self._update_entry_list_height()

    def _selected_conflict(self) -> Conflict | None:
        selected = self.conflicts_table.selectedItems()
        if not selected:
            return None
        row = selected[0].row()
        nif_item = self.conflicts_table.item(row, 0)
        if nif_item is None:
            return None
        nif_path = nif_item.data(Qt.UserRole)
        if not isinstance(nif_path, str):
            return None
        return self._conflict_by_nif.get(nif_path)

    def _selected_conflicts(self) -> list[Conflict]:
        selected_conflicts: list[Conflict] = []
        for nif_path in self._selected_nif_paths():
            conflict = self._conflict_by_nif.get(nif_path)
            if conflict is not None:
                selected_conflicts.append(conflict)
        return selected_conflicts

    @Slot(object)
    def _show_conflicts_context_menu(self, position) -> None:
        if self._scan_in_progress or self._is_closing:
            return

        row = self.conflicts_table.rowAt(position.y())
        if row < 0:
            return

        row_item = self.conflicts_table.item(row, 0)
        if row_item is not None and not row_item.isSelected():
            self.conflicts_table.selectRow(row)

        conflicts = self._selected_conflicts()
        folders = self._conflict_source_folders(conflicts)
        menu = QMenu(self)
        if len(folders) <= 1:
            label = "Open Source Folder In Explorer"
        else:
            label = f"Open {len(folders)} Source Folders In Explorer"
        open_action = menu.addAction(label)
        open_action.setEnabled(bool(folders))

        chosen_action = menu.exec(self.conflicts_table.viewport().mapToGlobal(position))
        if chosen_action == open_action:
            self._open_conflict_source_folders(folders)

    def _conflict_source_folders(self, conflicts: list[Conflict]) -> list[Path]:
        if self.scan_result is None:
            return []

        mods_dir = self.scan_result.mods_dir
        source_files: list[Path] = []
        seen_sources: set[tuple[str, str]] = set()

        for conflict in conflicts:
            for entry in conflict.lp_entries:
                key = (entry.source_mod, entry.source_file)
                if key in seen_sources:
                    continue
                seen_sources.add(key)
                source_files.append(mods_dir / entry.source_mod / Path(entry.source_file))
            for target in conflict.pl_targets:
                key = (target.source_mod, target.source_file)
                if key in seen_sources:
                    continue
                seen_sources.add(key)
                source_files.append(mods_dir / target.source_mod / Path(target.source_file))

        folders: list[Path] = []
        seen_folders: set[Path] = set()
        for source_file in source_files:
            folder = source_file.parent
            if not folder.exists():
                existing_parent = folder
                while not existing_parent.exists() and existing_parent != existing_parent.parent:
                    existing_parent = existing_parent.parent
                if existing_parent.exists():
                    folder = existing_parent
            folder = folder.resolve()
            if folder in seen_folders:
                continue
            seen_folders.add(folder)
            folders.append(folder)

        return folders

    def _open_conflict_source_folders(self, folders: list[Path]) -> None:
        if not folders:
            QMessageBox.information(
                self,
                "Open Source Folder",
                "No source folders were found for the selected conflict.",
            )
            return

        if len(folders) > 8:
            answer = QMessageBox.question(
                self,
                "Open Source Folders",
                f"This will open {len(folders)} folders in Explorer. Continue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return

        failed: list[str] = []
        for folder in folders:
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))):
                failed.append(str(folder))

        if failed:
            preview = "\n".join(failed[:6])
            suffix = "" if len(failed) <= 6 else f"\n...and {len(failed) - 6} more."
            QMessageBox.warning(
                self,
                "Open Source Folder",
                f"Could not open these folders:\n{preview}{suffix}",
            )

    def _selected_entry_ids(self) -> list[str]:
        selected_ids: list[str] = []
        seen: set[str] = set()
        for item in self.entry_list.selectedItems():
            entry_id = item.data(Qt.UserRole)
            if not isinstance(entry_id, str) or not entry_id or entry_id in seen:
                continue
            seen.add(entry_id)
            selected_ids.append(entry_id)
        return selected_ids

    def _restore_entry_selection(self, entry_ids: list[str] | None) -> bool:
        if not entry_ids:
            return False
        wanted = {entry_id for entry_id in entry_ids if isinstance(entry_id, str) and entry_id}
        if not wanted:
            return False

        first_item: QListWidgetItem | None = None
        for row in range(self.entry_list.count()):
            item = self.entry_list.item(row)
            if item is None:
                continue
            entry_id = item.data(Qt.UserRole)
            selected = isinstance(entry_id, str) and entry_id in wanted
            item.setSelected(selected)
            if selected and first_item is None:
                first_item = item

        if first_item is not None:
            self.entry_list.scrollToItem(first_item, QAbstractItemView.PositionAtCenter)
            return True
        return False

    def _on_entry_selection_changed(self) -> None:
        conflict = self._selected_conflict()
        if conflict is None:
            return
        selected_entry_ids = self._selected_entry_ids()
        if selected_entry_ids:
            self._entry_selection_by_nif[conflict.nif_path_canonical] = selected_entry_ids
        else:
            self._entry_selection_by_nif.pop(conflict.nif_path_canonical, None)

    def _queue_formid_world_resolution(self, target_key: str) -> None:
        if not _is_formid_target(target_key):
            return
        if self.scan_result is None:
            return
        if target_key in self._formid_world_resolution_cache:
            return
        if self._formid_request_inflight_target == target_key:
            return
        # Keep only the most recent requested target to avoid long background queues.
        self._formid_request_pending_target = target_key
        self._start_next_formid_resolution_request()

    def _start_next_formid_resolution_request(self) -> None:
        if self.scan_result is None or self._is_closing:
            return
        if self._formid_worker_thread is not None and self._formid_worker_thread.isRunning():
            return
        target_key = self._formid_request_pending_target
        self._formid_request_pending_target = None
        if target_key in self._formid_world_resolution_cache:
            return
        if not target_key:
            return

        self._formid_request_seq += 1
        request_id = self._formid_request_seq
        worker = FormIDResolutionWorker(
            str(self.scan_result.mods_dir),
            str(self.scan_result.profile_path),
            target_key,
            request_id,
        )
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self.on_formid_resolution_finished)
        worker.failed.connect(self.on_formid_resolution_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(self._on_formid_resolution_thread_finished)
        thread.finished.connect(thread.deleteLater)

        self._formid_request_inflight_target = target_key
        self._formid_worker = worker
        self._formid_worker_thread = thread
        thread.start()

    @Slot(int, str, object)
    def on_formid_resolution_finished(self, request_id: int, target_key: str, result: object) -> None:
        if self._is_closing:
            return
        if request_id != self._formid_request_seq:
            return

        if isinstance(result, FormIDWorldResolution):
            resolution = result
        else:
            resolution = FormIDWorldResolution(
                status="error",
                detail="Unexpected FormID resolver result payload.",
                context=None,
            )
        self._apply_formid_resolution_result(target_key, resolution)

    @Slot(int, str, str)
    def on_formid_resolution_failed(self, request_id: int, target_key: str, error_text: str) -> None:
        if self._is_closing:
            return
        if request_id != self._formid_request_seq:
            return

        resolution = FormIDWorldResolution(
            status="error",
            detail=self._error_detail_line(error_text),
            context=None,
        )
        self._apply_formid_resolution_result(target_key, resolution)

    def _apply_formid_resolution_result(self, target_key: str, resolution: FormIDWorldResolution) -> None:
        self._formid_world_resolution_cache[target_key] = resolution
        self._formid_request_inflight_target = None

        if self.scan_result is not None and self.hide_unresolved_formid_local_duplicates_cb.isChecked():
            selected_nifs = self._selected_nif_paths()
            self._populate_conflicts_table(preserve_nif_paths=selected_nifs)
            self._set_scan_summary_state(self._build_scan_summary_text(self.scan_result), "success")

        selected = self._selected_conflict()
        if (
            selected is not None
            and selected.nif_path_canonical == target_key
            and self.formid_preview_enabled_cb.isChecked()
            and not self._scan_in_progress
            and not self._updating_conflicts_table
        ):
            self.on_conflict_selection_changed()

    @Slot()
    def _on_formid_resolution_thread_finished(self) -> None:
        self._formid_worker = None
        self._formid_worker_thread = None
        self._formid_request_inflight_target = None
        self._start_next_formid_resolution_request()

    def _is_duplicate_only_conflict(self, conflict: Conflict) -> bool:
        types = set(conflict.conflict_types)
        return bool(types & self._DUPLICATE_CONFLICT_TYPES) and "lp_vs_pl_overlap" not in types

    def _is_unresolved_formid_local_duplicate_conflict(self, conflict: Conflict) -> bool:
        if not _is_formid_target(conflict.nif_path_canonical):
            return False
        if not self._is_duplicate_only_conflict(conflict):
            return False
        resolution = self._formid_world_resolution_cache.get(conflict.nif_path_canonical)
        if resolution is None:
            return False
        return resolution.status != "ok"

    def _visible_conflicts(self) -> list[Conflict]:
        if self.scan_result is None:
            return []
        if not self.hide_unresolved_formid_local_duplicates_cb.isChecked():
            return list(self.scan_result.conflicts)
        return [
            conflict
            for conflict in self.scan_result.conflicts
            if not self._is_unresolved_formid_local_duplicate_conflict(conflict)
        ]

    def _resolve_formid_world_resolution_for_conflict(
        self,
        conflict: Conflict,
    ) -> tuple[FormIDWorldResolution | None, str]:
        if not _is_formid_target(conflict.nif_path_canonical):
            return (None, "")
        if not self.formid_preview_enabled_cb.isChecked():
            return (None, "FormID world preview: disabled (using LP JSON local points).")
        if self.scan_result is None:
            return (None, "FormID world preview: unavailable (no scan result).")

        resolution = self._formid_world_resolution_cache.get(conflict.nif_path_canonical)
        if resolution is None:
            self._queue_formid_world_resolution(conflict.nif_path_canonical)
            return (None, "FormID world preview: resolving winning REFR/ACHR in background (local preview shown).")
        if resolution.status == "ok":
            return (resolution, f"FormID world preview: active ({resolution.detail}).")
        return (resolution, f"FormID world preview: {resolution.status} ({resolution.detail}).")

    def on_conflict_selection_changed(self) -> None:
        if self._scan_in_progress or self._updating_conflicts_table or self._is_closing:
            return
        try:
            conflict = self._selected_conflict()
            self.entry_list.blockSignals(True)
            self.entry_list.clear()
            self._update_entry_list_height()
            if conflict is None:
                self.entry_list.blockSignals(False)
                self.detail_text.setPlainText("")
                self.anchor_preview.clear_anchor_series()
                self.anchor_preview.clear_mesh_points()
                self.anchor_preview.set_mesh_status_text("Mesh cloud: not loaded")
                self.anchor_summary_label.setText("Select a conflict to preview LP anchor placement.")
                self.mesh_status_label.setText("Mesh: not loaded")
                self.anchor_points_text.clear()
                return

            for entry in conflict.lp_entries:
                label = f"{entry.source_mod} | prio {entry.source_priority} | {entry.source_file} | {entry.entry_id[:10]}"
                item = QListWidgetItem(label)
                item.setData(Qt.UserRole, entry.entry_id)
                item.setToolTip(f"{entry.source_mod} | {entry.source_file} | {entry.entry_id}")
                self.entry_list.addItem(item)
            self._update_entry_list_height()

            decision = self.decisions.get(conflict.nif_path_canonical)
            selected_entry_ids: list[str] = []
            if decision is not None:
                index = self.action_combo.findData(decision.action)
                if index >= 0:
                    self.action_combo.setCurrentIndex(index)
                if decision.action == "choose_entry":
                    selected_entry_ids = list(decision.entry_ids)
                    if not selected_entry_ids and decision.entry_id:
                        selected_entry_ids = [decision.entry_id]

            if not selected_entry_ids:
                selected_entry_ids = self._entry_selection_by_nif.get(conflict.nif_path_canonical, [])

            restored = self._restore_entry_selection(selected_entry_ids)
            if not restored and self.entry_list.count() > 0:
                first_item = self.entry_list.item(0)
                if first_item is not None:
                    first_item.setSelected(True)
                    self.entry_list.scrollToItem(first_item, QAbstractItemView.PositionAtCenter)

            self.entry_list.blockSignals(False)
            self._on_entry_selection_changed()

            self.detail_text.setHtml(self._render_conflict_detail_html(conflict))
            formid_resolution, formid_status = self._resolve_formid_world_resolution_for_conflict(conflict)
            mesh_points: list[tuple[float, float, float]] = []
            if self._requires_mesh_preview_for_conflict(conflict):
                mesh_status, mesh_points = self._load_mesh_preview_for_conflict(
                    conflict,
                    formid_resolution=formid_resolution,
                )
            else:
                mesh_status = "skipped (not needed for this conflict)"
                self.anchor_preview.clear_mesh_points()
                self.anchor_preview.set_mesh_status_text("Mesh cloud: skipped (fast preview)")
            nif_radius_hint: float | None = None
            if self._requires_nif_radius_hint_for_conflict(conflict):
                nif_radius_hint, _nif_radius_detail = self._load_nif_radius_hint_for_conflict(conflict)
            node_anchor_points, node_anchor_status = self._load_nif_node_anchor_points_for_conflict(
                conflict,
                formid_resolution=formid_resolution,
            )
            self.anchor_preview.set_anchor_series(
                self._build_preview_anchor_series(
                    conflict,
                    mesh_points,
                    nif_radius_hint,
                    decision,
                    node_anchor_points=node_anchor_points,
                    formid_resolution=formid_resolution,
                )
            )
            lp_summary = self._build_anchor_overlap_summary(
                conflict,
                node_anchor_points=node_anchor_points,
                formid_resolution=formid_resolution,
            )
            pl_summary = self._build_pl_localization_summary(conflict, mesh_points)
            projection_note = self._build_projection_note(
                conflict,
                mesh_points,
                node_anchor_points=node_anchor_points,
                formid_resolution=formid_resolution,
            )
            self.anchor_summary_label.setText(f"{lp_summary} {pl_summary} {projection_note}".strip())
            mesh_text = f"Mesh: {mesh_status}"
            if formid_status:
                mesh_text += f"\n{formid_status}"
            if node_anchor_status:
                mesh_text += f"\n{node_anchor_status}"
            self.mesh_status_label.setText(mesh_text)
            self.anchor_points_text.setPlainText(
                self._build_anchor_points_text(
                    conflict,
                    mesh_points,
                    nif_radius_hint,
                    node_anchor_points=node_anchor_points,
                    formid_resolution=formid_resolution,
                )
            )
        except Exception as exc:  # noqa: BLE001
            self.entry_list.blockSignals(False)
            QMessageBox.critical(
                self,
                "UI Error",
                self._format_ui_error_message(
                    "The conflict details panel could not be updated for the selected row.",
                    str(exc),
                ),
            )

    @staticmethod
    def _normalize_snapshot_value(value: Any) -> str:
        if value is None:
            return "(none)"
        if isinstance(value, (dict, list, tuple)):
            return json.dumps(value, ensure_ascii=True, sort_keys=True)
        return str(value)

    def _lp_light_block_maps(self, settings: dict[str, Any]) -> list[dict[str, str]]:
        blocks: list[dict[str, str]] = []
        for lights in _iter_lights_lists(settings):
            for light in lights:
                if not isinstance(light, dict):
                    continue
                block: dict[str, str] = {}

                data = light.get("data")
                if isinstance(data, dict):
                    for key in sorted(data.keys(), key=lambda item: str(item).lower()):
                        block[f"data.{key}"] = self._normalize_snapshot_value(data.get(key))
                elif data is not None:
                    block["data"] = self._normalize_snapshot_value(data)

                for key in sorted(light.keys(), key=lambda item: str(item).lower()):
                    if key == "data":
                        continue
                    block[str(key)] = self._normalize_snapshot_value(light.get(key))

                if block:
                    blocks.append(block)

        blocks.sort(key=lambda block: json.dumps(block, ensure_ascii=True, sort_keys=True))
        return blocks

    def _format_lp_block_summary(
        self,
        block: dict[str, str],
        *,
        diff_fields: set[tuple[int, str]] | None = None,
        block_index: int | None = None,
        html: bool = False,
    ) -> str:
        keys = sorted(block.keys(), key=lambda item: item.lower())
        if not keys:
            return "(no light fields)"

        parts: list[str] = []
        for key in keys:
            segment_plain = f"{key}={block[key]}"
            if html:
                segment = escape(segment_plain)
                if diff_fields and block_index is not None and (block_index, key) in diff_fields:
                    segment = f"<b>{segment}</b>"
            else:
                segment = segment_plain
            parts.append(segment)
        return " | ".join(parts)

    def _collect_divergence_snapshot(
        self,
        conflict: Conflict,
    ) -> tuple[list[dict[str, Any]], set[tuple[int, str]], set[int]]:
        if "duplicate_divergent" not in conflict.conflict_types:
            return ([], set(), set())
        if len(conflict.lp_entries) < 2:
            return ([], set(), set())

        snapshots: list[dict[str, Any]] = []
        for entry in conflict.lp_entries:
            snapshots.append(
                {
                    "source": f"{entry.source_mod}/{self._short_name(entry.source_file)}",
                    "entry_id_short": entry.entry_id[:8],
                    "blocks": self._lp_light_block_maps(entry.settings),
                }
            )

        max_block_count = max((len(snapshot["blocks"]) for snapshot in snapshots), default=0)
        differing_fields: set[tuple[int, str]] = set()
        missing_block_indices: set[int] = set()

        for block_index in range(max_block_count):
            keys: set[str] = set()
            block_missing_for_any = False

            for snapshot in snapshots:
                blocks = snapshot["blocks"]
                if block_index >= len(blocks):
                    block_missing_for_any = True
                    continue
                keys.update(blocks[block_index].keys())

            if block_missing_for_any:
                missing_block_indices.add(block_index)

            for key in sorted(keys):
                values: set[str] = set()
                for snapshot in snapshots:
                    blocks = snapshot["blocks"]
                    if block_index >= len(blocks):
                        values.add("(missing-block)")
                    else:
                        values.add(blocks[block_index].get(key, "(missing-field)"))
                if len(values) > 1:
                    differing_fields.add((block_index, key))

        return (snapshots, differing_fields, missing_block_indices)

    def _build_divergence_snapshot_lines(self, conflict: Conflict) -> list[str]:
        snapshots, _diff_fields, missing_block_indices = self._collect_divergence_snapshot(conflict)
        if not snapshots:
            return []

        lines: list[str] = [
            "",
            "Divergence Snapshot (all LP light blocks):",
        ]

        max_block_count = max((len(snapshot["blocks"]) for snapshot in snapshots), default=0)
        if max_block_count <= 0:
            lines.append("- No LP light blocks found to compare.")
            return lines

        for snapshot in snapshots:
            source = snapshot["source"]
            entry_id_short = snapshot["entry_id_short"]
            blocks: list[dict[str, str]] = snapshot["blocks"]
            lines.append(f"- {source} [{entry_id_short}]")
            for block_index in range(max_block_count):
                if block_index >= len(blocks):
                    if block_index in missing_block_indices:
                        lines.append(f"  block[{block_index + 1}]: (missing)")
                    continue
                lines.append(
                    f"  block[{block_index + 1}]: {self._format_lp_block_summary(blocks[block_index])}"
                )
        return lines

    def _build_divergence_snapshot_html_lines(self, conflict: Conflict) -> list[str]:
        snapshots, diff_fields, missing_block_indices = self._collect_divergence_snapshot(conflict)
        if not snapshots:
            return []

        rendered: list[str] = [
            escape(""),
            escape("Divergence Snapshot (all LP light blocks, differing fields in bold):"),
        ]

        max_block_count = max((len(snapshot["blocks"]) for snapshot in snapshots), default=0)
        if max_block_count <= 0:
            rendered.append(escape("- No LP light blocks found to compare."))
            return rendered

        for snapshot in snapshots:
            source = snapshot["source"]
            entry_id_short = snapshot["entry_id_short"]
            blocks: list[dict[str, str]] = snapshot["blocks"]
            rendered.append(escape(f"- {source} [{entry_id_short}]"))
            for block_index in range(max_block_count):
                if block_index >= len(blocks):
                    if block_index in missing_block_indices:
                        rendered.append(f"  <b>{escape(f'block[{block_index + 1}]: (missing)')}</b>")
                    continue
                summary = self._format_lp_block_summary(
                    blocks[block_index],
                    diff_fields=diff_fields,
                    block_index=block_index,
                    html=True,
                )
                rendered.append(f"  block[{block_index + 1}]: {summary}")
        return rendered

    def _render_conflict_detail(self, conflict: Conflict) -> str:
        lp_json_sources = sorted(
            {
                (entry.source_mod, entry.source_file)
                for entry in conflict.lp_entries
            },
            key=lambda item: (item[0].lower(), item[1].lower()),
        )
        pl_sources = sorted(
            {
                (target.source_mod, target.source_file)
                for target in conflict.pl_targets
            },
            key=lambda item: (item[0].lower(), item[1].lower()),
        )

        lines = [
            f"Target: {conflict.nif_path_canonical}",
            f"Types: {self._format_conflict_types(conflict.conflict_types)}",
            f"LP entries: {len(conflict.lp_entries)} | PL targets: {len(conflict.pl_targets)}",
            "",
            "Type Notes:",
        ]
        for conflict_type in conflict.conflict_types:
            lines.append(
                f"- {self._type_label(conflict_type)}: {self._TYPE_HELP.get(conflict_type, 'No description available.')}"
            )
        lines.extend(self._build_divergence_snapshot_lines(conflict))

        lines.extend([
            "",
            "LP Source JSON Files:",
        ])
        if lp_json_sources:
            for source_mod, source_file in lp_json_sources:
                lines.append(f"- {source_mod} | {source_file}")
        else:
            lines.append("- (none)")

        lines.extend([
            "",
            "PL Source Files:",
        ])
        if pl_sources:
            for source_mod, source_file in pl_sources:
                lines.append(f"- {source_mod} | {source_file}")
        else:
            lines.append("- (none)")

        lines.extend([
            "",
            "LP Entries:",
        ])
        for entry in conflict.lp_entries:
            lines.append(f"- {entry.source_mod} (prio {entry.source_priority})")
            lines.append(f"  source_json: {entry.source_file}")
            lines.append(f"  entry_id: {entry.entry_id}")
            lines.append(f"  settings: {json.dumps(entry.settings, ensure_ascii=True)}")
        lines.append("")
        lines.append("PL Targets:")
        for target in conflict.pl_targets:
            lines.append(f"- {target.source_mod} (prio {target.source_priority})")
            lines.append(f"  source_file: {target.source_file}")
        return "\n".join(lines)

    def _render_conflict_detail_html(self, conflict: Conflict) -> str:
        lp_json_sources = sorted(
            {
                (entry.source_mod, entry.source_file)
                for entry in conflict.lp_entries
            },
            key=lambda item: (item[0].lower(), item[1].lower()),
        )
        pl_sources = sorted(
            {
                (target.source_mod, target.source_file)
                for target in conflict.pl_targets
            },
            key=lambda item: (item[0].lower(), item[1].lower()),
        )

        html_lines: list[str] = []

        def add_plain(line: str = "") -> None:
            html_lines.append(escape(line))

        add_plain(f"Target: {conflict.nif_path_canonical}")
        add_plain(f"Types: {self._format_conflict_types(conflict.conflict_types)}")
        add_plain(f"LP entries: {len(conflict.lp_entries)} | PL targets: {len(conflict.pl_targets)}")
        add_plain("")
        add_plain("Type Notes:")
        for conflict_type in conflict.conflict_types:
            add_plain(
                f"- {self._type_label(conflict_type)}: {self._TYPE_HELP.get(conflict_type, 'No description available.')}"
            )

        html_lines.extend(self._build_divergence_snapshot_html_lines(conflict))

        add_plain("")
        add_plain("LP Source JSON Files:")
        if lp_json_sources:
            for source_mod, source_file in lp_json_sources:
                add_plain(f"- {source_mod} | {source_file}")
        else:
            add_plain("- (none)")

        add_plain("")
        add_plain("PL Source Files:")
        if pl_sources:
            for source_mod, source_file in pl_sources:
                add_plain(f"- {source_mod} | {source_file}")
        else:
            add_plain("- (none)")

        add_plain("")
        add_plain("LP Entries:")
        for entry in conflict.lp_entries:
            add_plain(f"- {entry.source_mod} (prio {entry.source_priority})")
            add_plain(f"  source_json: {entry.source_file}")
            add_plain(f"  entry_id: {entry.entry_id}")
            add_plain(f"  settings: {json.dumps(entry.settings, ensure_ascii=True)}")

        add_plain("")
        add_plain("PL Targets:")
        for target in conflict.pl_targets:
            add_plain(f"- {target.source_mod} (prio {target.source_priority})")
            add_plain(f"  source_file: {target.source_file}")

        body = "\n".join(html_lines)
        return (
            "<pre style=\"white-space: pre-wrap; "
            "overflow-wrap: anywhere; "
            "word-break: break-word; "
            "font-family: Consolas, 'Courier New', monospace; "
            "font-size: 12px; margin: 0;\">"
            f"{body}</pre>"
        )

    @staticmethod
    def _short_name(path: str) -> str:
        normalized = path.replace("\\", "/")
        return normalized.rsplit("/", 1)[-1]

    @staticmethod
    def _resolve_node_anchor_points(
        nodes: set[str],
        node_anchor_points: dict[str, tuple[float, float, float]] | None,
    ) -> list[tuple[float, float, float]]:
        if not nodes or not node_anchor_points:
            return []
        resolved = [node_anchor_points[node] for node in sorted(nodes) if node in node_anchor_points]
        return _dedupe_points(_sanitize_points(resolved))

    @staticmethod
    def _world_context_from_formid_resolution(
        formid_resolution: FormIDWorldResolution | None,
    ):
        if formid_resolution and formid_resolution.status == "ok":
            return formid_resolution.context
        return None

    def _build_anchor_series(
        self,
        conflict: Conflict,
        node_anchor_points: dict[str, tuple[float, float, float]] | None = None,
        formid_resolution: FormIDWorldResolution | None = None,
    ) -> list[dict[str, Any]]:
        target_is_formid = _is_formid_target(conflict.nif_path_canonical)
        world_context = self._world_context_from_formid_resolution(formid_resolution)
        distinct_targets = {
            entry.nif_path_canonical.strip().lower()
            for entry in conflict.lp_entries
            if isinstance(entry.nif_path_canonical, str) and entry.nif_path_canonical.strip()
        }
        suppress_points = target_is_formid and len(distinct_targets) > 1
        series: list[dict[str, Any]] = []
        for idx, entry in enumerate(conflict.lp_entries):
            points = _extract_lp_anchor_points(entry.settings)
            nodes = _extract_lp_anchor_nodes(entry.settings)
            point_source = "json" if points else "none"
            if suppress_points:
                points = []
                point_source = "mixed_formid_targets"
            elif target_is_formid and world_context is not None and points:
                points = transform_local_points_to_world(points, world_context)
                point_source = "formid_world"
            elif not points and nodes:
                node_points = self._resolve_node_anchor_points(nodes, node_anchor_points)
                if node_points:
                    points = node_points
                    point_source = "formid_node_world" if target_is_formid else "nif_node"
                elif target_is_formid and world_context is not None:
                    point_source = "node_only_formid_world_unresolved"
                elif target_is_formid:
                    point_source = "node_only_formid"
            radius_units = _estimate_entry_radius_units(entry.settings)
            label = f"{self._short_name(entry.source_file)} [{entry.entry_id[:8]}]"
            series.append(
                {
                    "index": idx,
                    "kind": "LP",
                    "entry_id": entry.entry_id,
                    "label": label,
                    "points": points,
                    "nodes": nodes,
                    "point_source": point_source,
                    "radius_units": radius_units,
                    "winner": False,
                }
            )
        return series

    def _build_preview_anchor_series(
        self,
        conflict: Conflict,
        mesh_points: list[tuple[float, float, float]] | None = None,
        nif_radius_hint: float | None = None,
        decision: Decision | None = None,
        node_anchor_points: dict[str, tuple[float, float, float]] | None = None,
        formid_resolution: FormIDWorldResolution | None = None,
    ) -> list[dict[str, Any]]:
        series = self._build_anchor_series(
            conflict,
            node_anchor_points=node_anchor_points,
            formid_resolution=formid_resolution,
        )
        mesh_center = _centroid(mesh_points or [])
        mesh_radius = _estimate_mesh_radius_units(mesh_points or [])
        winner_entry_ids: set[str] = set()
        pl_wins = False
        if decision is not None:
            if decision.action == "disable_lp" and conflict.pl_targets:
                pl_wins = True
            elif decision.action in {"keep_highest_priority", "choose_entry"} and conflict.lp_entries:
                sorted_entries = sorted(
                    conflict.lp_entries,
                    key=entry_priority_sort_key,
                )
                highest = choose_keep_highest_entry(conflict.lp_entries, conflict_types=conflict.conflict_types)
                if highest is None:
                    highest = sorted_entries[-1]
                if decision.action == "choose_entry":
                    selected_ids = list(decision.entry_ids)
                    if not selected_ids and decision.entry_id:
                        selected_ids = [decision.entry_id]
                    if selected_ids:
                        selected_ids_set = set(selected_ids)
                        for entry in sorted_entries:
                            if entry.entry_id in selected_ids_set:
                                winner_entry_ids.add(entry.entry_id)
                    if not winner_entry_ids:
                        winner_entry_ids.add(highest.entry_id)
                else:
                    winner_entry_ids.add(highest.entry_id)

        if winner_entry_ids:
            for lp_series in series:
                lp_series["winner"] = str(lp_series.get("entry_id")) in winner_entry_ids

        for target in conflict.pl_targets:
            points = _extract_pl_anchor_points(target.payload)
            nodes = _extract_pl_anchor_nodes(target.payload)
            radius_units = _estimate_pl_radius_units(target.payload)
            radius_source = "payload" if radius_units is not None else "none"
            approximated = False
            if not points and mesh_center is not None:
                # ENB PL NIF source does not carry explicit anchor points; use centroid as a coarse proxy.
                points = [mesh_center]
                approximated = True
            if radius_units is None and str(target.payload.get("kind", "")).lower() == "enb_particle_lights_nif":
                if nif_radius_hint is not None:
                    radius_units = nif_radius_hint
                    radius_source = "nif_bounding_sphere"
                elif mesh_radius is not None:
                    radius_units = mesh_radius
                    radius_source = "mesh_bounds"
            label = f"PL {self._short_name(target.source_file)}"
            if approximated:
                label += " [centroid]"
            series.append(
                {
                    "index": len(series),
                    "kind": "PL",
                    "localized": "centroid" if approximated else ("explicit" if points else "none"),
                    "radius_source": radius_source,
                    "label": label,
                    "points": points,
                    "nodes": nodes,
                    "radius_units": radius_units,
                    "winner": pl_wins,
                }
            )
        return series

    def _load_mesh_preview_for_conflict(
        self,
        conflict: Conflict,
        *,
        formid_resolution: FormIDWorldResolution | None = None,
    ) -> tuple[str, list[tuple[float, float, float]]]:
        if self.scan_result is None:
            self.anchor_preview.clear_mesh_points()
            status = "preview unavailable (no scan result)"
            self.anchor_preview.set_mesh_status_text(f"Mesh cloud: {status}")
            return status, []

        if not _is_nif_target(conflict.nif_path_canonical):
            world_context = self._world_context_from_formid_resolution(formid_resolution)
            if world_context and world_context.base_model_path:
                preview = load_mesh_preview_for_nif(
                    str(self.scan_result.mods_dir),
                    str(self.scan_result.profile_path),
                    world_context.base_model_path,
                )
                world_points = transform_local_points_to_world(preview.points, world_context)
                self.anchor_preview.set_mesh_points(world_points)
                if preview.status == "ok":
                    status = (
                        f"{world_context.base_model_path} | {preview.detail} | "
                        "transformed with winning REFR/ACHR world transform"
                    )
                    self.anchor_preview.set_mesh_status_text(f"Mesh cloud: {len(world_points)} pts (formid world)")
                    return status, world_points
                status = (
                    f"{world_context.base_model_path} | {preview.status}: {preview.detail} | "
                    "formid world preview"
                )
                self.anchor_preview.set_mesh_status_text(f"Mesh cloud: {preview.status} (formid world)")
                return status, world_points

            self.anchor_preview.clear_mesh_points()
            status = "preview unavailable (LP JSON FormID targets do not include mesh path data)"
            self.anchor_preview.set_mesh_status_text("Mesh cloud: n/a (no mesh information in LP JSON)")
            return status, []

        preview = load_mesh_preview_for_nif(
            str(self.scan_result.mods_dir),
            str(self.scan_result.profile_path),
            conflict.nif_path_canonical,
        )
        self.anchor_preview.set_mesh_points(preview.points)
        if preview.status == "ok":
            source_name = preview.mesh_path.name if preview.mesh_path else "resolved source"
            status = f"{source_name} | {preview.detail}"
            self.anchor_preview.set_mesh_status_text(f"Mesh cloud: {len(preview.points)} pts")
            return status, preview.points
        source_name = preview.mesh_path.name if preview.mesh_path else conflict.nif_path_canonical
        status = f"{source_name} | {preview.status}: {preview.detail}"
        self.anchor_preview.set_mesh_status_text(f"Mesh cloud: {preview.status}")
        return status, preview.points

    def _load_nif_radius_hint_for_conflict(self, conflict: Conflict) -> tuple[float | None, str]:
        if self.scan_result is None:
            return (None, "no_scan_result")
        if not _is_nif_target(conflict.nif_path_canonical):
            return (None, "not_a_nif_target")
        return load_nif_bounding_radius_for_nif(
            str(self.scan_result.mods_dir),
            str(self.scan_result.profile_path),
            conflict.nif_path_canonical,
        )

    def _load_nif_node_anchor_points_for_conflict(
        self,
        conflict: Conflict,
        *,
        formid_resolution: FormIDWorldResolution | None = None,
    ) -> tuple[dict[str, tuple[float, float, float]], str]:
        requested_nodes = sorted(
            {
                node
                for entry in conflict.lp_entries
                for node in _extract_lp_anchor_nodes(entry.settings)
            }
        )
        if not requested_nodes:
            return ({}, "")
        if self.scan_result is None:
            return ({}, "NIF node anchors: unavailable (no scan result).")

        detail = ""
        status_prefix = "NIF node anchors"
        node_positions: dict[str, tuple[float, float, float]] = {}
        if _is_nif_target(conflict.nif_path_canonical):
            node_positions, detail = load_nif_node_positions_for_nif(
                str(self.scan_result.mods_dir),
                str(self.scan_result.profile_path),
                conflict.nif_path_canonical,
            )
            status_prefix = "NIF node anchors"
        else:
            world_context = self._world_context_from_formid_resolution(formid_resolution)
            if world_context is None:
                return ({}, "FormID node anchors: unavailable (world preview inactive or unresolved).")
            if not world_context.base_model_path:
                return ({}, "FormID node anchors: unavailable (base model path not resolved).")
            model_positions, detail = load_nif_node_positions_for_nif(
                str(self.scan_result.mods_dir),
                str(self.scan_result.profile_path),
                world_context.base_model_path,
            )
            node_positions = {
                name: transformed[0]
                for name, point in model_positions.items()
                if (transformed := transform_local_points_to_world([point], world_context))
            }
            status_prefix = "FormID node anchors"

        if not node_positions:
            return ({}, f"{status_prefix}: resolved 0/{len(requested_nodes)} ({detail}).")

        canonical: dict[str, tuple[float, float, float]] = {}
        alias_map: dict[str, tuple[float, float, float]] = {}
        for raw_name, point in node_positions.items():
            name = raw_name.strip().lower()
            if not name:
                continue
            canonical.setdefault(name, point)
            for alias in _node_lookup_aliases(name):
                alias_map.setdefault(alias, point)

        resolved: dict[str, tuple[float, float, float]] = {}
        unresolved: list[str] = []
        for node in requested_nodes:
            point = canonical.get(node)
            if point is None:
                for alias in _node_lookup_aliases(node):
                    point = alias_map.get(alias)
                    if point is not None:
                        break
            if point is None:
                unresolved.append(node)
                continue
            resolved[node] = point

        status = f"{status_prefix}: resolved {len(resolved)}/{len(requested_nodes)} ({detail})."
        if unresolved:
            preview = ", ".join(unresolved[:4])
            if len(unresolved) > 4:
                preview += f", +{len(unresolved) - 4} more"
            status += f" Missing: {preview}."
        return (resolved, status)

    def _build_anchor_overlap_summary(
        self,
        conflict: Conflict,
        threshold: float = 14.0,
        node_anchor_points: dict[str, tuple[float, float, float]] | None = None,
        formid_resolution: FormIDWorldResolution | None = None,
    ) -> str:
        world_context = self._world_context_from_formid_resolution(formid_resolution)
        series = self._build_anchor_series(
            conflict,
            node_anchor_points=node_anchor_points,
            formid_resolution=formid_resolution,
        )
        if len(series) < 2:
            return "Need at least two LP entries to evaluate overlap."

        pairs_with_points = 0
        distance_overlap_pairs = 0
        radius_overlap_pairs = 0
        radius_capable_pairs = 0
        min_pair_distance: float | None = None

        for i in range(len(series)):
            left_points = series[i]["points"]
            left_radius_raw = series[i].get("radius_units")
            try:
                left_radius = float(left_radius_raw)
            except (TypeError, ValueError):
                left_radius = 0.0
            if not isfinite(left_radius) or left_radius <= 0.0:
                left_radius = 0.0

            for j in range(i + 1, len(series)):
                right_points = series[j]["points"]
                right_radius_raw = series[j].get("radius_units")
                try:
                    right_radius = float(right_radius_raw)
                except (TypeError, ValueError):
                    right_radius = 0.0
                if not isfinite(right_radius) or right_radius <= 0.0:
                    right_radius = 0.0

                if not left_points or not right_points:
                    continue
                pairs_with_points += 1
                local_min = min(dist(lp, rp) for lp in left_points for rp in right_points)
                min_pair_distance = local_min if min_pair_distance is None else min(min_pair_distance, local_min)
                if local_min <= threshold:
                    distance_overlap_pairs += 1
                    continue
                if left_radius > 0.0 and right_radius > 0.0:
                    radius_capable_pairs += 1
                    if local_min <= (left_radius + right_radius):
                        radius_overlap_pairs += 1

        if pairs_with_points > 0:
            overlapping_pairs = distance_overlap_pairs + radius_overlap_pairs
            min_text = "n/a" if min_pair_distance is None else f"{min_pair_distance:.2f}"
            if _is_formid_target(conflict.nif_path_canonical) and world_context is None:
                if overlapping_pairs > 0:
                    return (
                        f"Uncertain (local-only FormID): {overlapping_pairs}/{pairs_with_points} LP entry pairs overlap "
                        f"in local coordinates (fixed<= {threshold:.1f} or radius-aware). "
                        "World placement could not be resolved from winning REFR/ACHR records. "
                        "Same-JSON LP entries are still treated as separate placements."
                    )
                return (
                    f"Uncertain (local-only FormID): 0/{pairs_with_points} LP entry pairs overlap in local coordinates. "
                    "World placement could not be resolved from winning REFR/ACHR records. "
                    "Same-JSON LP entries are still treated as separate placements."
                )
            if overlapping_pairs > 0:
                criteria_hits: list[str] = []
                if distance_overlap_pairs > 0:
                    criteria_hits.append(f"fixed<= {threshold:.1f}: {distance_overlap_pairs}")
                if radius_overlap_pairs > 0:
                    criteria_hits.append(f"radius-aware: {radius_overlap_pairs}")
                criteria_text = " | ".join(criteria_hits) if criteria_hits else "n/a"
                return (
                    f"Likely stacking{' (world-space)' if world_context else ''}: "
                    f"{overlapping_pairs}/{pairs_with_points} LP entry pairs overlap "
                    f"(fixed<= {threshold:.1f} or radius-aware). "
                    f"Hits: {criteria_text}. Minimum pair distance: {min_text}."
                )
            if radius_capable_pairs > 0:
                return (
                    f"Likely disjoint refinement: 0/{pairs_with_points} LP entry pairs satisfy "
                    f"fixed<= {threshold:.1f} or radius-aware overlap. Minimum pair distance: {min_text}."
                )
            return (
                f"Likely disjoint refinement: 0/{pairs_with_points} LP entry pairs are within {threshold:.1f}. "
                f"Minimum pair distance: {min_text}."
            )

        if _is_formid_target(conflict.nif_path_canonical):
            if world_context is not None:
                return (
                    "No numeric world-space XYZ points available for overlap preview. "
                    "Entries are node-only or missing point/offset fields for this FormID target."
                )
            return (
                "No numeric local XYZ points available for overlap preview. "
                "Entries are node-only or missing point/offset fields for this FormID target."
            )

        node_pairs = 0
        overlapping_node_pairs = 0
        for i in range(len(series)):
            left_nodes = series[i]["nodes"]
            for j in range(i + 1, len(series)):
                right_nodes = series[j]["nodes"]
                if not left_nodes or not right_nodes:
                    continue
                node_pairs += 1
                if left_nodes & right_nodes:
                    overlapping_node_pairs += 1

        if node_pairs > 0:
            if overlapping_node_pairs > 0:
                return (
                    f"Node-based overlap risk: {overlapping_node_pairs}/{node_pairs} pairs share anchor node names "
                    "(no numeric point/offset data available)."
                )
            return "Likely refinement split: node anchors are disjoint and no numeric point/offset data was found."

        point_entries = sum(1 for item in series if item.get("points"))
        node_entries = sum(1 for item in series if item.get("nodes"))
        if point_entries > 0 and node_entries > 0:
            return (
                "Mixed LP anchor styles detected (point-based and node-based entries). "
                "Direct geometric overlap confidence is limited."
            )

        return "No comparable point or node anchors found in LP payloads."

    def _build_pl_localization_summary(
        self,
        conflict: Conflict,
        mesh_points: list[tuple[float, float, float]] | None = None,
    ) -> str:
        if not conflict.pl_targets:
            return ""

        explicit = 0
        centroid_estimated = 0
        mesh_center = _centroid(mesh_points or [])
        for target in conflict.pl_targets:
            points = _extract_pl_anchor_points(target.payload)
            if points:
                explicit += 1
            elif mesh_center is not None:
                centroid_estimated += 1

        total = len(conflict.pl_targets)
        unresolved = max(0, total - explicit - centroid_estimated)
        parts = [f"PL localized: explicit {explicit}/{total}"]
        if centroid_estimated > 0:
            parts.append(f"centroid-estimated {centroid_estimated}/{total}")
        if unresolved > 0:
            parts.append(f"unlocalized {unresolved}/{total}")
        return " | ".join(parts) + "."

    def _build_projection_note(
        self,
        conflict: Conflict,
        mesh_points: list[tuple[float, float, float]] | None = None,
        node_anchor_points: dict[str, tuple[float, float, float]] | None = None,
        formid_resolution: FormIDWorldResolution | None = None,
    ) -> str:
        target_is_formid = _is_formid_target(conflict.nif_path_canonical)
        world_context = self._world_context_from_formid_resolution(formid_resolution)
        if target_is_formid:
            distinct_targets = {
                entry.nif_path_canonical.strip().lower()
                for entry in conflict.lp_entries
                if isinstance(entry.nif_path_canonical, str) and entry.nif_path_canonical.strip()
            }
            if len(distinct_targets) > 1:
                return "Projection note: mixed FormID targets; XYZ preview is intentionally disabled."

        points: list[tuple[float, float, float]] = []
        for entry in conflict.lp_entries:
            entry_points = _extract_lp_anchor_points(entry.settings)
            if target_is_formid and world_context is not None and entry_points:
                entry_points = transform_local_points_to_world(entry_points, world_context)
            if not entry_points:
                entry_nodes = _extract_lp_anchor_nodes(entry.settings)
                entry_points = self._resolve_node_anchor_points(entry_nodes, node_anchor_points)
            points.extend(entry_points)

        mesh_center = _centroid(mesh_points or [])
        for target in conflict.pl_targets:
            target_points = _extract_pl_anchor_points(target.payload)
            if target_points:
                points.extend(target_points)
            elif mesh_center is not None:
                points.append(mesh_center)

        if target_is_formid and len(points) < 2:
            if world_context is not None:
                return (
                    "Projection note: FormID world preview has insufficient numeric XYZ points; "
                    "node-only entries cannot be projected without base model/node transform data."
                )
            return (
                "Projection note: FormID local preview has insufficient numeric XYZ points; "
                "node-only entries cannot be projected without mesh/node transform data."
            )

        if len(points) < 2:
            return ""

        ys = [point[1] for point in points]
        zs = [point[2] for point in points]
        spread_y = max(ys) - min(ys)
        spread_z = max(zs) - min(zs)
        if spread_y <= 8.0 and spread_z <= 8.0:
            return "Projection note: Y and Z anchor spread are both small, so XY/XZ can look similar."
        return ""

    def _build_anchor_points_text(
        self,
        conflict: Conflict,
        mesh_points: list[tuple[float, float, float]] | None = None,
        nif_radius_hint: float | None = None,
        node_anchor_points: dict[str, tuple[float, float, float]] | None = None,
        formid_resolution: FormIDWorldResolution | None = None,
    ) -> str:
        lines: list[str] = []
        target_is_formid = _is_formid_target(conflict.nif_path_canonical)
        world_context = self._world_context_from_formid_resolution(formid_resolution)
        distinct_targets = {
            entry.nif_path_canonical.strip().lower()
            for entry in conflict.lp_entries
            if isinstance(entry.nif_path_canonical, str) and entry.nif_path_canonical.strip()
        }
        suppress_points = target_is_formid and len(distinct_targets) > 1
        if target_is_formid:
            if world_context is not None:
                lines.append("FormID world preview mode:")
                lines.append("- LP local points are transformed with winning REFR/ACHR DATA+XSCL")
                lines.append("- base object model/node context is used when resolvable")
                lines.append("- LP JSON itself does not include mesh information")
            else:
                lines.append("FormID local preview mode:")
                lines.append("- using LP JSON local points/radius only")
                lines.append("- mesh information is not available in LP JSON")
            lines.append("- same-source LP JSON entries are additive unless conditions make them mutually exclusive")
            if suppress_points:
                lines.append("- XYZ drawing disabled because LP entries map to different FormID targets in this group")
            lines.append("")
        for idx, entry in enumerate(conflict.lp_entries, start=1):
            local_points = _extract_lp_anchor_points(entry.settings)
            points = local_points
            nodes = sorted(_extract_lp_anchor_nodes(entry.settings))
            points_from_nodes = False
            if suppress_points:
                points = []
            elif target_is_formid and world_context is not None and points:
                points = transform_local_points_to_world(points, world_context)
            elif not points and nodes:
                node_points = self._resolve_node_anchor_points(set(nodes), node_anchor_points)
                if node_points:
                    points = node_points
                    points_from_nodes = True
            radius_units = _estimate_entry_radius_units(entry.settings)
            light_value_summaries = _extract_lp_light_value_summaries(entry.settings)
            label = f"{idx}. {self._short_name(entry.source_file)} [{entry.entry_id[:8]}]"
            lines.append(label)
            if radius_units is not None:
                lines.append(f"   preview_radius: {radius_units:.2f}")
            else:
                lines.append("   preview_radius: (unknown)")
            if points:
                formatted_points = ", ".join(f"({p[0]:.1f}, {p[1]:.1f}, {p[2]:.1f})" for p in points[:12])
                if len(points) > 12:
                    formatted_points += f", +{len(points) - 12} more"
                if target_is_formid and world_context is not None and local_points and not points_from_nodes:
                    formatted_local_points = ", ".join(
                        f"({p[0]:.1f}, {p[1]:.1f}, {p[2]:.1f})"
                        for p in local_points[:12]
                    )
                    if len(local_points) > 12:
                        formatted_local_points += f", +{len(local_points) - 12} more"
                    lines.append(f"   points_local: {formatted_local_points}")
                    lines.append(f"   points_world: {formatted_points} (transformed)")
                elif points_from_nodes and target_is_formid:
                    lines.append(f"   points: {formatted_points} (resolved from base model node transform)")
                elif points_from_nodes:
                    lines.append(f"   points: {formatted_points} (resolved from NIF node transform)")
                else:
                    lines.append(f"   points: {formatted_points}")
            else:
                if target_is_formid and nodes:
                    if world_context is not None:
                        lines.append("   points: (unavailable - node-only entry and base model node transform unresolved)")
                    else:
                        lines.append("   points: (unavailable - node-only entry for FormID target)")
                elif suppress_points:
                    lines.append("   points: (suppressed - mixed FormID targets)")
                else:
                    lines.append("   points: (none)")

            if nodes:
                formatted_nodes = ", ".join(nodes[:8])
                if len(nodes) > 8:
                    formatted_nodes += f", +{len(nodes) - 8} more"
                lines.append(f"   nodes: {formatted_nodes}")
            else:
                lines.append("   nodes: (none)")

            if light_value_summaries:
                lines.append(f"   values: {light_value_summaries[0]}")
                if len(light_value_summaries) > 1:
                    lines.append(f"   values+: {light_value_summaries[1]}")
                    if len(light_value_summaries) > 2:
                        lines.append(f"   values_more: +{len(light_value_summaries) - 2}")
            else:
                lines.append("   values: (none)")

        lines.extend(self._build_divergence_snapshot_lines(conflict))

        if conflict.pl_targets:
            lines.append("")
            lines.append("PL Targets:")
            mesh_center = _centroid(mesh_points or [])
            mesh_radius = _estimate_mesh_radius_units(mesh_points or [])
            for idx, target in enumerate(conflict.pl_targets, start=1):
                points = _extract_pl_anchor_points(target.payload)
                nodes = sorted(_extract_pl_anchor_nodes(target.payload))
                radius_units = _estimate_pl_radius_units(target.payload)
                radius_source = "payload" if radius_units is not None else "none"
                approximated = False
                if not points and mesh_center is not None:
                    points = [mesh_center]
                    approximated = True
                if radius_units is None and str(target.payload.get("kind", "")).lower() == "enb_particle_lights_nif":
                    if nif_radius_hint is not None:
                        radius_units = nif_radius_hint
                        radius_source = "nif_bounding_sphere"
                    elif mesh_radius is not None:
                        radius_units = mesh_radius
                        radius_source = "mesh_bounds"

                lines.append(
                    f"{idx}. {target.source_mod} - {self._short_name(target.source_file)}"
                )
                if radius_units is not None:
                    if radius_source == "nif_bounding_sphere":
                        lines.append(f"   preview_radius: {radius_units:.2f} (nif-bounding-sphere)")
                    elif radius_source == "mesh_bounds":
                        lines.append(f"   preview_radius: {radius_units:.2f} (mesh-bounds estimate)")
                    else:
                        lines.append(f"   preview_radius: {radius_units:.2f}")
                else:
                    lines.append("   preview_radius: (unknown)")
                if points:
                    formatted_points = ", ".join(f"({p[0]:.1f}, {p[1]:.1f}, {p[2]:.1f})" for p in points[:12])
                    if len(points) > 12:
                        formatted_points += f", +{len(points) - 12} more"
                    if approximated:
                        lines.append(f"   points: {formatted_points} (mesh-centroid estimate)")
                    else:
                        lines.append(f"   points: {formatted_points}")
                else:
                    lines.append("   points: (none)")
                if nodes:
                    formatted_nodes = ", ".join(nodes[:8])
                    if len(nodes) > 8:
                        formatted_nodes += f", +{len(nodes) - 8} more"
                    lines.append(f"   nodes: {formatted_nodes}")
                else:
                    lines.append("   nodes: (none)")

        if not lines:
            return "No LP entries for selected conflict."
        return "\n".join(lines)

    def _conflict_types_tooltip(self, conflict_types: list[str]) -> str:
        lines = ["Conflict type meaning:"]
        for conflict_type in conflict_types:
            lines.append(
                f"- {self._type_label(conflict_type)}: {self._TYPE_HELP.get(conflict_type, 'No description available.')}"
            )
        return "\n".join(lines)

    def _type_label(self, conflict_type: str) -> str:
        return self._TYPE_LABELS.get(conflict_type, conflict_type)

    def _format_conflict_types(self, conflict_types: list[str]) -> str:
        return ", ".join(self._type_label(conflict_type) for conflict_type in conflict_types)

    def _summarize_lp_json_sources(self, conflict: Conflict) -> str:
        labels: list[str] = []
        seen: set[tuple[str, str]] = set()
        for entry in conflict.lp_entries:
            key = (entry.source_mod, entry.source_file)
            if key in seen:
                continue
            seen.add(key)
            labels.append(f"{entry.source_mod}/{self._short_name(entry.source_file)}")

        if not labels:
            return "-"
        if len(labels) <= 2:
            return "; ".join(labels)
        return f"{labels[0]}; {labels[1]}; +{len(labels) - 2} more"

    def _full_lp_json_sources_text(self, conflict: Conflict) -> str:
        rows: list[str] = []
        seen: set[tuple[str, str]] = set()
        for entry in sorted(conflict.lp_entries, key=lambda e: (e.source_mod.lower(), e.source_file.lower())):
            key = (entry.source_mod, entry.source_file)
            if key in seen:
                continue
            seen.add(key)
            rows.append(f"{entry.source_mod} | {entry.source_file}")
        return "\n".join(rows) if rows else "(none)"

    def apply_decision_to_selected(self) -> None:
        conflicts = self._selected_conflicts()
        if not conflicts:
            return

        action = self.action_combo.currentData()
        selected_entry_ids: list[str] = []
        if action == "choose_entry":
            if len(conflicts) != 1:
                QMessageBox.warning(
                    self,
                    "Decision",
                    "'Choose Entries' can only be applied to one selected conflict at a time.",
                )
                return
            selected_entry_ids = self._selected_entry_ids()
            if not selected_entry_ids:
                QMessageBox.warning(self, "Decision", "Select one or more LP entries for 'Choose Entries'.")
                return

        selected_nifs = [conflict.nif_path_canonical for conflict in conflicts]
        if len(conflicts) == 1 and selected_entry_ids:
            self._entry_selection_by_nif[selected_nifs[0]] = list(selected_entry_ids)

        for conflict in conflicts:
            self.decisions[conflict.nif_path_canonical] = make_decision(
                action=action,
                entry_ids=selected_entry_ids if action == "choose_entry" else None,
            )

        self._populate_conflicts_table(preserve_nif_paths=selected_nifs)

    def clear_decision_for_selected(self) -> None:
        conflicts = self._selected_conflicts()
        if not conflicts:
            return

        selected_nifs = [conflict.nif_path_canonical for conflict in conflicts]
        for conflict in conflicts:
            self.decisions.pop(conflict.nif_path_canonical, None)

        self._populate_conflicts_table(preserve_nif_paths=selected_nifs)

    def clear_all_decisions(self) -> None:
        if not self.decisions:
            QMessageBox.information(self, "Clear All Decisions", "No decisions to clear.")
            return

        answer = QMessageBox.question(
            self,
            "Clear All Decisions",
            f"Remove all decisions ({len(self.decisions)}) from the current session?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        preserve_nif_paths = self._selected_nif_paths()
        self.decisions.clear()
        self._populate_conflicts_table(preserve_nif_paths=preserve_nif_paths)
        QMessageBox.information(self, "Clear All Decisions", "All decisions were cleared.")

    def apply_disable_for_all_overlaps(self) -> None:
        if self.scan_result is None:
            return
        for conflict in self.scan_result.conflicts:
            if "lp_vs_pl_overlap" in conflict.conflict_types:
                self.decisions[conflict.nif_path_canonical] = make_decision(action="disable_lp")
        self._populate_conflicts_table()
        QMessageBox.information(self, "Decisions", "Applied disable_lp to all overlap conflicts.")

    def apply_keep_highest_for_all_duplicates(self) -> None:
        if self.scan_result is None:
            return
        for conflict in self.scan_result.conflicts:
            if "duplicate_exact" in conflict.conflict_types or "duplicate_divergent" in conflict.conflict_types:
                self.decisions[conflict.nif_path_canonical] = make_decision(action="keep_highest_priority")
        self._populate_conflicts_table()
        QMessageBox.information(self, "Decisions", "Applied keep_highest_priority to all duplicate conflicts.")

    def _default_decisions_path(self) -> Path:
        return self._resolve_output_dir_text(self.output_dir_edit.text().strip()) / "resolver_decisions.json"

    def _load_default_decisions_if_present(self) -> None:
        if self.scan_result is None:
            return
        decisions_path = self._default_decisions_path()
        if not decisions_path.exists():
            return
        try:
            decisions = load_decisions(decisions_path)
            applied, stale = apply_decisions(self.scan_result.conflicts, decisions)
            self.decisions = applied
            if stale:
                current_state = str(self.summary_label.property("scanState") or "success")
                self._set_scan_summary_state(
                    self.summary_label.text() + f" | Stale decisions skipped: {len(stale)}",
                    current_state,
                )
        except Exception as exc:  # noqa: BLE001
            current_state = str(self.summary_label.property("scanState") or "error")
            self._set_scan_summary_state(
                self.summary_label.text() + " | Default decisions load failed.",
                current_state,
            )
            QMessageBox.warning(
                self,
                "Load Decisions",
                self._format_file_io_error_message(
                    "Found resolver_decisions.json but could not load it. The scan results are still available.",
                    str(exc),
                ),
            )

    def load_decisions_from_disk(self) -> None:
        if self.scan_result is None:
            QMessageBox.warning(self, "Load Decisions", "Run scan first.")
            return
        default_path = str(self._default_decisions_path())
        selected_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Decisions",
            default_path,
            "JSON Files (*.json);;All Files (*.*)",
        )
        if not selected_path:
            return

        try:
            decisions = load_decisions(Path(selected_path))
            applied, stale = apply_decisions(self.scan_result.conflicts, decisions)
            self.decisions = applied
            self._populate_conflicts_table()
            message = f"Loaded decisions: {len(applied)}"
            if stale:
                message += f" | Stale skipped: {len(stale)}"
            QMessageBox.information(self, "Load Decisions", message)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(
                self,
                "Load Decisions",
                self._format_file_io_error_message(
                    "Could not load the selected decisions file.",
                    str(exc),
                ),
            )

    def save_decisions_to_disk(self) -> None:
        default_path = str(self._default_decisions_path())
        selected_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Decisions",
            default_path,
            "JSON Files (*.json);;All Files (*.*)",
        )
        if not selected_path:
            return
        try:
            save_decisions(Path(selected_path), self.decisions)
            self._save_persistent_paths()
            QMessageBox.information(self, "Save Decisions", f"Saved {len(self.decisions)} decisions.")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(
                self,
                "Save Decisions",
                self._format_file_io_error_message(
                    "Could not save decisions to the selected file.",
                    str(exc),
                ),
            )

    def _requires_mesh_preview_for_conflict(self, conflict: Conflict) -> bool:
        # Mesh loading is one of the most expensive per-selection operations.
        # For LP-only conflicts we can render anchors from LP points/nodes directly.
        if not conflict.pl_targets:
            return False
        for target in conflict.pl_targets:
            points = _extract_pl_anchor_points(target.payload)
            if not points:
                return True
        return False

    def _requires_nif_radius_hint_for_conflict(self, conflict: Conflict) -> bool:
        if not _is_nif_target(conflict.nif_path_canonical):
            return False
        for target in conflict.pl_targets:
            if _estimate_pl_radius_units(target.payload) is not None:
                continue
            kind = str(target.payload.get("kind", "")).strip().lower()
            if kind == "enb_particle_lights_nif":
                return True
        return False

    def _export_patch_outputs(self, patch_name: str):
        result = write_patch_mod(self.scan_result, self.decisions, patch_mod_name=patch_name)
        light_scale_result = None
        if self.light_scale_enabled_cb.isChecked():
            light_scale_patch_name = f"{patch_name}_LightIntensityPatch"
            try:
                light_scale_result = write_light_intensity_patch_mod(
                    self.scan_result,
                    self.decisions,
                    self._light_scale_config(),
                    patch_mod_name=light_scale_patch_name,
                )
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(
                    "Conflict patch was exported, but light intensity patch export failed.\n\n"
                    f"Conflict patch dir: {result.patch_mod_dir}\n\n"
                    f"Details: {exc}"
                ) from exc
        return result, light_scale_result

    def _export_inventory_outputs(self) -> InventoryExportResult:
        output_dir = self._resolve_output_dir_text(self.output_dir_edit.text().strip())
        output_dir_error = self._ensure_output_dir_exists(output_dir)
        if output_dir_error:
            raise RuntimeError(f"Output Dir is not writable: {output_dir} ({output_dir_error})")
        return write_inventory_reports(
            self.scan_result,
            output_dir,
            config=self._inventory_export_config(),
            file_prefix="Results",
        )

    def export_inventory_reports(self) -> None:
        if self.scan_result is None:
            QMessageBox.warning(self, "Export Results", "Run scan first.")
            return
        if not self._show_inventory_filter_dialog():
            return
        try:
            result = self._export_inventory_outputs()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(
                self,
                "Export Results",
                self._format_file_io_error_message(
                    "Result export failed.",
                    str(exc),
                ),
            )
            return

        filters = result.filter_summary
        worldspace_scope = str(filters.get("worldspace_scope") or "all")
        scoped_total = int(filters.get("worldspace_scoped_lp_entries") or 0)
        scoped_interior = int(filters.get("worldspace_interior_only_lp_entries") or 0)
        scoped_exterior = int(filters.get("worldspace_exterior_only_lp_entries") or 0)
        scoped_mixed = int(filters.get("worldspace_mixed_lp_entries") or 0)
        scoped_unscoped = int(filters.get("worldspace_unscoped_lp_entries") or 0)
        explicit_interior = int(filters.get("worldspace_explicit_interior_only_lp_entries") or 0)
        explicit_exterior = int(filters.get("worldspace_explicit_exterior_only_lp_entries") or 0)
        explicit_mixed = int(filters.get("worldspace_explicit_mixed_lp_entries") or 0)
        inferred_interior = int(filters.get("worldspace_inferred_interior_only_lp_entries") or 0)
        inferred_exterior = int(filters.get("worldspace_inferred_exterior_only_lp_entries") or 0)
        inferred_mixed = int(filters.get("worldspace_inferred_mixed_lp_entries") or 0)
        lp_stage_total = int(filters.get("lp_stage_total") or 0)
        lp_stage_after_scope = int(filters.get("lp_stage_after_scope") or 0)
        lp_stage_after_scope_nif = int(filters.get("lp_stage_after_scope_nif") or 0)
        lp_stage_after_scope_nif_portal = int(filters.get("lp_stage_after_scope_nif_portal") or 0)
        worldspace_note = ""
        if worldspace_scope in {"interior", "exterior", "unscoped"} and result.exported_lp_entry_count == 0:
            if lp_stage_after_scope == 0:
                if scoped_total == 0:
                    worldspace_note = (
                        "\n\nScope note: no LP entries in this scan expose "
                        "`GetInWorldspace ... == 0/1` conditions.\n"
                        "Interior/Exterior scope filters can therefore return 0 rows."
                    )
                else:
                    worldspace_note = (
                        "\n\nScope note: no LP entries matched the selected scope "
                        "(after explicit + filename/path scope inference)."
                    )
            elif lp_stage_after_scope_nif == 0:
                worldspace_note = (
                    "\n\nScope note: scope-matching LP entries exist, but `NIF targets only` "
                    "removed all of them."
                )
            elif lp_stage_after_scope_nif_portal == 0:
                worldspace_note = (
                    "\n\nScope note: scope-matching LP entries exist, but `PortalStrict only` "
                    "removed all remaining rows."
                )
            elif bool(filters.get("conflicts_only")):
                worldspace_note = (
                    "\n\nScope note: rows remained after scope/NIF/PortalStrict filtering, "
                    "but `Conflicts only` removed them."
                )
        QMessageBox.information(
            self,
            "Export Results",
            (
                "Result export written to:\n"
                f"{result.output_dir}\n\n"
                f"JSON: {result.json_path}\n"
                f"Targets CSV: {result.target_csv_path}\n"
                f"LP Entries CSV: {result.lp_csv_path}\n"
                f"PL Targets CSV: {result.pl_csv_path}\n\n"
                f"Targets exported: {result.exported_target_count}\n"
                f"LP entries exported: {result.exported_lp_entry_count}\n"
                f"PL targets exported: {result.exported_pl_target_count}\n"
                f"Filters: scope={filters.get('worldspace_scope')}, "
                f"portalStrictOnly={filters.get('portal_strict_only')}, "
                f"nifOnly={filters.get('nif_only')}, "
                f"conflictsOnly={filters.get('conflicts_only')}\n"
                f"LP worldspace coverage: scoped={scoped_total} "
                f"(interior={scoped_interior}, exterior={scoped_exterior}, mixed={scoped_mixed}), "
                f"unscoped={scoped_unscoped}\n"
                f"scope-source split: explicit(i/e/m)={explicit_interior}/{explicit_exterior}/{explicit_mixed}, "
                f"inferred(i/e/m)={inferred_interior}/{inferred_exterior}/{inferred_mixed}\n"
                f"LP filter stages: total={lp_stage_total} -> scope={lp_stage_after_scope} "
                f"-> scope+nif={lp_stage_after_scope_nif} "
                f"-> scope+nif+portal={lp_stage_after_scope_nif_portal} "
                f"-> exported={result.exported_lp_entry_count}"
                f"{worldspace_note}"
            ),
        )

    def export_patch_mod(self) -> None:
        if self.scan_result is None:
            QMessageBox.warning(self, "Export Patch", "Run scan first.")
            return
        patch_name = self.patch_name_edit.text().strip() or "LP_ConflictPatch"
        try:
            result, light_scale_result = self._export_patch_outputs(patch_name)
        except Exception as exc:  # noqa: BLE001
            message_text = str(exc).strip()
            if message_text.startswith("Conflict patch was exported, but light intensity patch export failed."):
                QMessageBox.critical(self, "Export Patch", message_text)
                return
            QMessageBox.critical(
                self,
                "Export Patch",
                self._format_file_io_error_message(
                    "Patch export failed.",
                    str(exc),
                ),
            )
            return

        message = (
            f"Conflict patch written to:\n{result.patch_mod_dir}\n\n"
            f"Selected target decisions: {result.selected_nif_count}\n"
            f"Overridden source JSON files: {len(result.override_files)}\n"
            f"Exported LP entries: {result.selected_entry_count}\n"
            f"Stale overrides removed: {result.stale_removed_count}\n"
            f"Warnings: {len(result.warnings)}"
        )
        if light_scale_result is not None:
            message += (
                "\n\n"
                f"Light intensity patch written to:\n{light_scale_result.patch_mod_dir}\n\n"
                f"Scale factor: {self._light_scale_factor():.2f}\n"
                f"Worldspace scope: {self.light_scale_scope_combo.currentData()}\n"
                f"PortalStrict only: {self.light_scale_portal_strict_cb.isChecked()}\n"
                f"Winner source JSON files exported: {len(light_scale_result.override_files)}\n"
                f"Exported LP entries: {light_scale_result.exported_entry_count}\n"
                f"Filter-matching LP entries: {light_scale_result.eligible_entry_count}\n"
                f"LP entries with scaled values: {light_scale_result.scaled_entry_count}\n"
                f"Numeric intensity values scaled: {light_scale_result.scaled_value_count}\n"
                f"Stale overrides removed: {light_scale_result.stale_removed_count}\n"
                f"Warnings: {len(light_scale_result.warnings)}\n\n"
                "Load-order note: place this light intensity patch after the conflict patch."
            )
        QMessageBox.information(self, "Export Patch", message)


def main() -> int:
    app = QApplication([])
    app.setApplicationName("Placed Lights and Particle Lights Conflict Resolver")
    app.setStyle(_TooltipDelayProxyStyle(app.style()))
    startup_theme_mode = _normalize_theme_mode(QSettings("ParticleTroned", "LPConflictResolver").value("ui/theme_mode", "auto", str))
    startup_theme_variant = _resolve_theme_variant(startup_theme_mode)
    app.setStyleSheet(_stylesheet_for_theme_variant(startup_theme_variant))
    app.setProperty("_lp_theme_variant", startup_theme_variant)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

