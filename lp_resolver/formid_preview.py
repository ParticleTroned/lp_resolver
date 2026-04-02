# SPDX-FileCopyrightText: 2026 ParticleTroned
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import configparser
import math
import os
import struct
import zlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .mo2 import read_enabled_mods
from .normalize import canonical_form_id, canonical_nif
from .vortex import export_vortex_enabled_mods, is_vortex_profile

_PLUGIN_SUFFIXES = (".esm", ".esp", ".esl")
_COMPRESSED_RECORD_FLAG = 0x00040000
_MODEL_SUBRECORDS = ("MODL", "MOD2", "MOD3", "MOD4", "MOD5")
_GAME_DATA_ENV_VARS = (
    "LPRESOLVER_GAME_DATA_DIR",
    "SKYRIM_DATA_DIR",
    "SKYRIMSE_DATA_DIR",
    "SKYRIM_SPECIAL_EDITION_DATA",
)


@dataclass(frozen=True)
class FormIDWorldContext:
    target_key: str
    reference_record_type: str
    reference_source_plugin: str
    position: tuple[float, float, float]
    rotation_deg: tuple[float, float, float]
    scale: float
    base_form_key: str | None
    base_model_path: str | None
    base_model_source_plugin: str | None


@dataclass(frozen=True)
class FormIDWorldResolution:
    status: str
    detail: str
    context: FormIDWorldContext | None


@dataclass(frozen=True)
class _RecordMatch:
    record_type: str
    source_plugin: str
    base_form_key: str | None = None
    position: tuple[float, float, float] | None = None
    rotation_deg: tuple[float, float, float] | None = None
    scale: float | None = None
    model_path: str | None = None


@dataclass(frozen=True)
class _EnabledModsResolution:
    entries: tuple
    issue: str | None = None


def _normalize_plugin_name(value: str) -> str:
    text = value.strip().replace("\\", "/").split("/")[-1]
    if text.lower().endswith(".ghost"):
        text = text[:-6]
    return text.lower()


def _decode_subrecord_text(payload: bytes) -> str:
    raw = payload.split(b"\x00", 1)[0]
    return raw.decode("utf-8", errors="ignore").strip()


def _split_target_key(target_key: str) -> tuple[str, int] | None:
    key = target_key.strip().lower()
    if not key.startswith("formid:"):
        return None
    parts = key.split(":")
    if len(parts) != 3:
        return None
    plugin = _normalize_plugin_name(parts[1])
    if not plugin:
        return None
    try:
        local_form_id = int(parts[2], 16)
    except ValueError:
        return None
    if local_form_id < 0:
        return None
    return (plugin, local_form_id)


def _canonical_form_id_from_raw(raw_form_id: int, plugin_name: str, masters: tuple[str, ...]) -> str:
    source_index = (raw_form_id >> 24) & 0xFF
    local_form_id = raw_form_id & 0x00FFFFFF
    if source_index < len(masters):
        source_plugin = masters[source_index]
    elif source_index == len(masters):
        source_plugin = plugin_name
    else:
        # Fallback for malformed/unexpected records.
        source_plugin = plugin_name
    return f"formid:{source_plugin}:{local_form_id:x}"


def _iter_plugin_subrecords(payload: bytes):
    pos = 0
    extended_size: int | None = None
    total = len(payload)
    while pos + 6 <= total:
        name = payload[pos : pos + 4].decode("ascii", errors="ignore")
        size = struct.unpack_from("<H", payload, pos + 4)[0]
        pos += 6
        if name == "XXXX":
            if size != 4 or pos + 4 > total:
                return
            extended_size = struct.unpack_from("<I", payload, pos)[0]
            pos += 4
            continue

        actual_size = extended_size if extended_size is not None else size
        extended_size = None
        if actual_size < 0 or pos + actual_size > total:
            return
        data = payload[pos : pos + actual_size]
        pos += actual_size
        yield name, data


def _iter_plugin_records_in_range(raw: bytes, start: int, end: int):
    pos = start
    while pos + 4 <= end:
        tag = raw[pos : pos + 4]
        if tag == b"GRUP":
            if pos + 24 > end:
                return
            group_size = struct.unpack_from("<I", raw, pos + 4)[0]
            group_end = pos + group_size
            if group_size < 24 or group_end > end:
                return
            # GRUP payload begins immediately after the 24-byte GRUP header.
            yield from _iter_plugin_records_in_range(raw, pos + 24, group_end)
            pos = group_end
            continue

        if pos + 24 > end:
            return
        record_type = tag.decode("ascii", errors="ignore")
        data_size = struct.unpack_from("<I", raw, pos + 4)[0]
        flags = struct.unpack_from("<I", raw, pos + 8)[0]
        form_id_raw = struct.unpack_from("<I", raw, pos + 12)[0]

        payload_start = pos + 24
        payload_end = payload_start + data_size
        if payload_end > end:
            return
        payload = raw[payload_start:payload_end]
        pos = payload_end

        if flags & _COMPRESSED_RECORD_FLAG:
            if len(payload) < 4:
                continue
            try:
                payload = zlib.decompress(payload[4:])
            except Exception:
                continue

        yield record_type, form_id_raw, payload


def _iter_plugin_records(raw: bytes):
    yield from _iter_plugin_records_in_range(raw, 0, len(raw))


def _find_record_in_plugin(
    plugin_path: str,
    plugin_name: str,
    target_key: str,
    mode: str,
    mtime_ns: int,
    file_size: int,
) -> _RecordMatch | None:
    # mtime_ns and file_size are intentionally part of cache key.
    _ = (mtime_ns, file_size)
    path = Path(plugin_path)
    if not path.exists() or not path.is_file():
        return None
    try:
        raw = path.read_bytes()
    except OSError:
        return None

    masters: tuple[str, ...] = tuple()
    candidate: _RecordMatch | None = None
    for record_type, form_id_raw, payload in _iter_plugin_records(raw):
        if record_type == "TES4":
            mast_entries: list[str] = []
            for name, data in _iter_plugin_subrecords(payload):
                if name == "MAST":
                    plugin = _normalize_plugin_name(_decode_subrecord_text(data))
                    if plugin:
                        mast_entries.append(plugin)
            masters = tuple(mast_entries)
            continue

        canonical_key = _canonical_form_id_from_raw(form_id_raw, plugin_name, masters)
        if canonical_key != target_key:
            continue

        if mode == "reference":
            if record_type not in {"REFR", "ACHR"}:
                continue
            base_form_key: str | None = None
            position: tuple[float, float, float] | None = None
            rotation_deg: tuple[float, float, float] | None = None
            scale: float | None = None
            for name, data in _iter_plugin_subrecords(payload):
                if name == "NAME" and len(data) >= 4:
                    base_raw = struct.unpack_from("<I", data, 0)[0]
                    base_form_key = _canonical_form_id_from_raw(base_raw, plugin_name, masters)
                elif name == "DATA" and len(data) >= 24:
                    values = struct.unpack_from("<6f", data, 0)
                    position = (float(values[0]), float(values[1]), float(values[2]))
                    rotation_deg = (float(values[3]), float(values[4]), float(values[5]))
                elif name == "XSCL" and len(data) >= 4:
                    scale = float(struct.unpack_from("<f", data, 0)[0])
            candidate = _RecordMatch(
                record_type=record_type,
                source_plugin=plugin_name,
                base_form_key=base_form_key,
                position=position,
                rotation_deg=rotation_deg,
                scale=scale,
            )
            continue

        if mode == "model":
            model_path: str | None = None
            for name, data in _iter_plugin_subrecords(payload):
                if name in _MODEL_SUBRECORDS:
                    text = _decode_subrecord_text(data)
                    if text:
                        model_path = text
                        break
            if model_path is None:
                continue
            candidate = _RecordMatch(
                record_type=record_type,
                source_plugin=plugin_name,
                model_path=model_path,
            )

    return candidate


@lru_cache(maxsize=4096)
def _find_record_in_plugin_cached(
    plugin_path: str,
    plugin_name: str,
    target_key: str,
    mode: str,
    mtime_ns: int,
    file_size: int,
) -> _RecordMatch | None:
    return _find_record_in_plugin(
        plugin_path=plugin_path,
        plugin_name=plugin_name,
        target_key=target_key,
        mode=mode,
        mtime_ns=mtime_ns,
        file_size=file_size,
    )


def _parse_plugins_txt(profile_path: Path) -> tuple[str, ...]:
    plugins_path = profile_path / "plugins.txt"
    if not plugins_path.exists():
        return tuple()
    try:
        lines = plugins_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return tuple()

    meaningful_lines = [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]
    uses_enabled_markers = any(line.startswith("*") for line in meaningful_lines)

    enabled: list[str] = []
    seen: set[str] = set()
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if uses_enabled_markers:
            if not line.startswith("*"):
                continue
            line = line[1:].strip()
        elif line.startswith("*"):
            line = line[1:].strip()
        if not line.lower().endswith(_PLUGIN_SUFFIXES) and not line.lower().endswith(".ghost"):
            continue
        plugin = _normalize_plugin_name(line)
        if not plugin or plugin in seen:
            continue
        seen.add(plugin)
        enabled.append(plugin)
    return tuple(enabled)


def _parse_loadorder_txt(profile_path: Path) -> tuple[str, ...]:
    loadorder_path = profile_path / "loadorder.txt"
    if not loadorder_path.exists():
        return tuple()
    try:
        lines = loadorder_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return tuple()
    ordered: list[str] = []
    seen: set[str] = set()
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("*"):
            line = line[1:].strip()
        plugin = _normalize_plugin_name(line)
        if not plugin or plugin in seen:
            continue
        seen.add(plugin)
        ordered.append(plugin)
    return tuple(ordered)


@lru_cache(maxsize=8)
def _active_plugin_order(profile_path: str) -> tuple[str, ...]:
    profile = Path(profile_path)
    enabled_plugins = _parse_plugins_txt(profile)
    enabled_set = set(enabled_plugins)
    ordered_plugins = _parse_loadorder_txt(profile)
    if ordered_plugins:
        if enabled_set:
            filtered = [plugin for plugin in ordered_plugins if plugin in enabled_set]
            if filtered:
                return tuple(filtered)
            return enabled_plugins
        return ordered_plugins
    return enabled_plugins


@lru_cache(maxsize=8)
def _enabled_mod_entries(profile_path: str, mods_dir: str):
    profile = Path(profile_path)
    mods = Path(mods_dir)
    if (profile / "modlist.txt").exists():
        try:
            entries = read_enabled_mods(profile, mods)
        except Exception as exc:  # noqa: BLE001
            return _EnabledModsResolution(entries=tuple(), issue=f"MO2 modlist parse failed: {exc}")
        sorted_entries = tuple(sorted(entries, key=lambda item: (item.priority, item.name.lower()), reverse=True))
        return _EnabledModsResolution(entries=sorted_entries, issue=None)

    if is_vortex_profile(profile):
        try:
            entries = export_vortex_enabled_mods(
                profile_path=profile,
                explicit_mods_dir=mods,
                export_path=profile / "vortex_modlist.txt",
                write_export_file=False,
            ).entries
        except Exception as exc:  # noqa: BLE001
            return _EnabledModsResolution(entries=tuple(), issue=f"Vortex state parse failed: {exc}")
        sorted_entries = tuple(sorted(entries, key=lambda item: (item.priority, item.name.lower()), reverse=True))
        return _EnabledModsResolution(entries=sorted_entries, issue=None)

    return _EnabledModsResolution(entries=tuple(), issue=None)


def _normalize_data_dir_candidate(path: Path) -> Path | None:
    try:
        candidate = path.expanduser().resolve()
    except OSError:
        return None
    if candidate.is_dir():
        if candidate.name.lower() == "data":
            return candidate
        data_subdir = candidate / "Data"
        if data_subdir.exists() and data_subdir.is_dir():
            return data_subdir.resolve()
    return None


def _decode_mo2_path_value(value: str) -> str:
    text = value.strip().strip('"')
    marker = "@bytearray("
    if text.lower().startswith(marker) and text.endswith(")"):
        text = text[len(marker):-1].strip()
    return text.strip().strip('"')


def _iter_env_game_data_dirs():
    for key in _GAME_DATA_ENV_VARS:
        raw = os.environ.get(key, "").strip()
        if not raw:
            continue
        for chunk in raw.split(os.pathsep):
            text = chunk.strip().strip('"')
            if not text:
                continue
            normalized = _normalize_data_dir_candidate(Path(text))
            if normalized is not None:
                yield normalized


def _iter_mo2_game_data_dirs(mods_dir: Path):
    ini_candidates = [
        mods_dir.parent / "ModOrganizer.ini",
        mods_dir / "ModOrganizer.ini",
    ]
    for ini_path in ini_candidates:
        if not ini_path.exists() or not ini_path.is_file():
            continue
        parser = configparser.ConfigParser()
        try:
            parser.read(ini_path, encoding="utf-8")
        except Exception:
            continue
        if not parser.has_section("General"):
            continue
        game_path_raw = parser.get("General", "gamePath", fallback="").strip()
        if not game_path_raw:
            game_path_raw = parser.get("General", "game_path", fallback="").strip()
        if not game_path_raw:
            continue
        decoded = _decode_mo2_path_value(game_path_raw)
        if not decoded:
            continue
        path = Path(decoded)
        if not path.is_absolute():
            path = (ini_path.parent / path).resolve()
        normalized = _normalize_data_dir_candidate(path)
        if normalized is not None:
            yield normalized


def _iter_nearby_data_dirs(profile_path: Path, mods_dir: Path):
    seeds: list[Path] = [
        mods_dir,
        mods_dir.parent,
        mods_dir.parent.parent,
        profile_path,
        profile_path.parent,
        profile_path.parent.parent,
    ]
    for seed in seeds:
        normalized = _normalize_data_dir_candidate(seed)
        if normalized is not None:
            yield normalized
        normalized_data = _normalize_data_dir_candidate(seed / "Data")
        if normalized_data is not None:
            yield normalized_data


def _iter_common_game_data_dirs():
    candidates = [
        # Windows common Steam defaults.
        Path(r"C:\Program Files (x86)\Steam\steamapps\common\Skyrim Special Edition\Data"),
        Path(r"C:\Program Files\Steam\steamapps\common\Skyrim Special Edition\Data"),
        Path(r"C:\Steam\steamapps\common\Skyrim Special Edition\Data"),
        # Linux/SteamOS common defaults.
        Path("~/.steam/steam/steamapps/common/Skyrim Special Edition/Data"),
        Path("~/.local/share/Steam/steamapps/common/Skyrim Special Edition/Data"),
    ]
    for path in candidates:
        normalized = _normalize_data_dir_candidate(path)
        if normalized is not None:
            yield normalized


@lru_cache(maxsize=32)
def _candidate_game_data_dirs(profile_path: str, mods_dir: str) -> tuple[str, ...]:
    profile = Path(profile_path)
    mods = Path(mods_dir)
    resolved: list[str] = []
    seen: set[str] = set()

    for candidate in (
        *list(_iter_env_game_data_dirs()),
        *list(_iter_mo2_game_data_dirs(mods)),
        *list(_iter_nearby_data_dirs(profile, mods)),
        *list(_iter_common_game_data_dirs()),
    ):
        key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        resolved.append(str(candidate))
    return tuple(resolved)


@lru_cache(maxsize=1024)
def _indexed_dir_files(directory_path: str, mtime_ns: int) -> tuple[tuple[str, str], ...]:
    _ = mtime_ns
    directory = Path(directory_path)
    mapping: dict[str, str] = {}
    try:
        for child in directory.iterdir():
            if not child.is_file():
                continue
            lowered = child.name.lower()
            if lowered not in mapping:
                mapping[lowered] = str(child.resolve())
    except OSError:
        return tuple()
    return tuple(sorted(mapping.items()))


def _resolve_file_case_insensitive(root: Path, filename: str) -> Path | None:
    candidate = root / filename
    if candidate.exists() and candidate.is_file():
        return candidate.resolve()

    try:
        stat = root.stat()
    except OSError:
        return None
    if not root.exists() or not root.is_dir():
        return None

    indexed = dict(_indexed_dir_files(str(root.resolve()), stat.st_mtime_ns))
    matched = indexed.get(filename.lower())
    if not matched:
        return None
    path = Path(matched)
    return path if path.exists() else None


def _find_plugin_file_in_root(root: Path, plugin_name: str) -> Path | None:
    for filename in (plugin_name, f"{plugin_name}.ghost"):
        if matched := _resolve_file_case_insensitive(root, filename):
            return matched
    return None


def _resolve_plugin_file(
    plugin_name: str,
    enabled_mods: tuple,
    data_dirs: tuple[str, ...],
) -> Path | None:
    for mod in enabled_mods:
        for root in (mod.path, mod.path / "Data"):
            if match := _find_plugin_file_in_root(root, plugin_name):
                return match
    for raw_data_dir in data_dirs:
        if match := _find_plugin_file_in_root(Path(raw_data_dir), plugin_name):
            return match
    return None


@lru_cache(maxsize=8)
def _active_plugin_sources_with_issue(profile_path: str, mods_dir: str) -> tuple[tuple[tuple[str, str], ...], str | None]:
    plugin_order = _active_plugin_order(profile_path)
    if not plugin_order:
        return (tuple(), "No plugins found in plugins.txt/loadorder.txt.")
    mods_resolution = _enabled_mod_entries(profile_path, mods_dir)
    enabled_mods = mods_resolution.entries
    data_dirs = _candidate_game_data_dirs(profile_path, mods_dir)
    resolved: list[tuple[str, str]] = []
    missing: list[str] = []
    for plugin_name in plugin_order:
        plugin_path = _resolve_plugin_file(plugin_name, enabled_mods, data_dirs)
        if plugin_path is None:
            missing.append(plugin_name)
            continue
        resolved.append((plugin_name, str(plugin_path)))
    issue_parts: list[str] = []
    if mods_resolution.issue:
        issue_parts.append(mods_resolution.issue)
    if missing:
        preview = ", ".join(missing[:6])
        suffix = "" if len(missing) <= 6 else f", +{len(missing) - 6} more"
        issue_parts.append(
            f"Missing plugin files: {len(missing)} not resolved from enabled mods or discovered Data directories ({preview}{suffix})."
        )
    if not resolved and issue_parts:
        return (tuple(), " ".join(issue_parts))
    if issue_parts:
        return (tuple(resolved), " ".join(issue_parts))
    return (tuple(resolved), None)


def clear_formid_preview_caches() -> None:
    _find_record_in_plugin_cached.cache_clear()
    _active_plugin_order.cache_clear()
    _enabled_mod_entries.cache_clear()
    _candidate_game_data_dirs.cache_clear()
    _indexed_dir_files.cache_clear()
    _active_plugin_sources_with_issue.cache_clear()


def _resolve_winning_record(
    plugin_sources: tuple[tuple[str, str], ...],
    target_key: str,
    mode: str,
) -> _RecordMatch | None:
    for plugin_name, plugin_path in reversed(plugin_sources):
        path = Path(plugin_path)
        try:
            stat = path.stat()
        except OSError:
            continue
        match = _find_record_in_plugin_cached(
            plugin_path=plugin_path,
            plugin_name=plugin_name,
            target_key=target_key,
            mode=mode,
            mtime_ns=stat.st_mtime_ns,
            file_size=stat.st_size,
        )
        if match is not None:
            return match
    return None


def resolve_formid_world_resolution(
    mods_dir: str,
    profile_path: str,
    target_key: str,
) -> FormIDWorldResolution:
    parsed = _split_target_key(target_key)
    if parsed is None:
        return FormIDWorldResolution(
            status="not_formid_target",
            detail="Target key is not a canonical FormID.",
            context=None,
        )

    raw_form_id = parsed[1]
    lookup_form_id = raw_form_id & 0x00FFFFFF
    normalized_form_id_note = ""
    if lookup_form_id != raw_form_id:
        normalized_form_id_note = (
            f" Input FormID contained load-order bits; using local record id 0x{lookup_form_id:X} for lookup."
        )

    canonical_target = canonical_form_id(
        f"0x{lookup_form_id:X}~{parsed[0]}"
    )
    if canonical_target is None:
        return FormIDWorldResolution(
            status="invalid_formid_target",
            detail="Failed to canonicalize target FormID key.",
            context=None,
        )

    plugin_sources, source_issue = _active_plugin_sources_with_issue(profile_path, mods_dir)
    source_issue_suffix = f" Source warning: {source_issue}" if source_issue else ""
    if not plugin_sources:
        return FormIDWorldResolution(
            status="no_active_plugins",
            detail=(
                "No active plugin load order could be resolved from profile plugins.txt/loadorder.txt. "
                "If base-game plugins are not discoverable, set LPRESOLVER_GAME_DATA_DIR to the game's Data folder."
                f"{normalized_form_id_note}"
                f"{source_issue_suffix}"
            ),
            context=None,
        )

    active_plugins = {plugin_name for plugin_name, _ in plugin_sources}
    if parsed[0] not in active_plugins:
        return FormIDWorldResolution(
            status="plugin_not_active",
            detail=(
                f"Target plugin '{parsed[0]}' is not active in current plugins.txt/loadorder.txt. "
                "Using LP local preview only."
                f"{normalized_form_id_note}"
                f"{source_issue_suffix}"
            ),
            context=None,
        )

    reference = _resolve_winning_record(plugin_sources, canonical_target, mode="reference")
    if reference is None:
        return FormIDWorldResolution(
            status="reference_not_found",
            detail=(
                "Winning REFR/ACHR record for this FormID was not found in active plugin order. "
                "Using LP local preview only (entries may represent different placed instances)."
                " If base-game plugins are not discoverable, set LPRESOLVER_GAME_DATA_DIR to the game's Data folder."
                f"{normalized_form_id_note}"
                f"{source_issue_suffix}"
            ),
            context=None,
        )
    if reference.position is None or reference.rotation_deg is None:
        return FormIDWorldResolution(
            status="reference_missing_data",
            detail=(
                f"Winning {reference.record_type} record is missing DATA position/rotation fields."
                f"{normalized_form_id_note}"
                f"{source_issue_suffix}"
            ),
            context=None,
        )

    base_model_path: str | None = None
    base_model_source_plugin: str | None = None
    if reference.base_form_key:
        base_record = _resolve_winning_record(plugin_sources, reference.base_form_key, mode="model")
        if base_record is not None and base_record.model_path:
            raw_model_path = base_record.model_path.replace("\\", "/").strip()
            canonical_model_path = canonical_nif(raw_model_path)
            if canonical_model_path:
                base_model_path = canonical_model_path
                base_model_source_plugin = base_record.source_plugin
            elif raw_model_path.lower().endswith(".nif"):
                base_model_path = raw_model_path.strip("/")
                base_model_source_plugin = base_record.source_plugin

    context = FormIDWorldContext(
        target_key=canonical_target,
        reference_record_type=reference.record_type,
        reference_source_plugin=reference.source_plugin,
        position=reference.position,
        rotation_deg=reference.rotation_deg,
        scale=float(reference.scale) if reference.scale is not None else 1.0,
        base_form_key=reference.base_form_key,
        base_model_path=base_model_path,
        base_model_source_plugin=base_model_source_plugin,
    )
    detail_parts = [
        f"{context.reference_record_type} from {context.reference_source_plugin}",
        f"scale={context.scale:.3f}",
    ]
    if context.base_model_path:
        detail_parts.append(f"model={context.base_model_path}")
    else:
        detail_parts.append("model=missing")
    if source_issue:
        detail_parts.append(f"source_warning={source_issue}")
    if normalized_form_id_note:
        detail_parts.append(normalized_form_id_note.strip())
    return FormIDWorldResolution(
        status="ok",
        detail=", ".join(detail_parts),
        context=context,
    )


def _rotate_point_xyz(
    point: tuple[float, float, float],
    rotation_deg: tuple[float, float, float],
) -> tuple[float, float, float]:
    x, y, z = point
    rx = math.radians(rotation_deg[0])
    ry = math.radians(rotation_deg[1])
    rz = math.radians(rotation_deg[2])

    # X rotation
    cos_x = math.cos(rx)
    sin_x = math.sin(rx)
    y, z = (y * cos_x - z * sin_x, y * sin_x + z * cos_x)

    # Y rotation
    cos_y = math.cos(ry)
    sin_y = math.sin(ry)
    x, z = (x * cos_y + z * sin_y, -x * sin_y + z * cos_y)

    # Z rotation
    cos_z = math.cos(rz)
    sin_z = math.sin(rz)
    x, y = (x * cos_z - y * sin_z, x * sin_z + y * cos_z)

    return (x, y, z)


def transform_local_points_to_world(
    points: list[tuple[float, float, float]],
    context: FormIDWorldContext,
) -> list[tuple[float, float, float]]:
    result: list[tuple[float, float, float]] = []
    sx = float(context.scale)
    for point in points:
        scaled = (point[0] * sx, point[1] * sx, point[2] * sx)
        rotated = _rotate_point_xyz(scaled, context.rotation_deg)
        world = (
            context.position[0] + rotated[0],
            context.position[1] + rotated[1],
            context.position[2] + rotated[2],
        )
        if all(math.isfinite(v) for v in world):
            result.append(world)
    return result
