# SPDX-FileCopyrightText: 2026 ParticleTroned
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
from pathlib import Path, PurePosixPath
from typing import Any

from .decisions import Decision
from .engine import ScanResult
from .models import LightPlacerEntry
from .normalize import value_signature
from .priority import choose_keep_highest_entry, entry_priority_sort_key, is_portal_strict_entry
from .reporting import render_markdown_report
from .worldspace_conditions import iter_get_in_worldspace_states

MANAGED_FILES_VERSION = 1
MANAGED_FILES_NAME = "resolver_managed_files.json"
LIGHT_SCALE_MANAGED_FILES_NAME = "resolver_light_scale_managed_files.json"
LIGHT_INTENSITY_SCOPE_VALUES = {"all", "interior", "exterior"}
_INTENSITY_KEY_EXACT = {"light", "intensity", "brightness"}
_INTENSITY_KEY_CONTAINS = ("intensity", "brightness")
_TARGET_KEY_PREFIXES = (
    "nif",
    "mesh",
    "model",
    "path",
    "file",
    "formid",
    "visualeffect",
    "effectshader",
    "magiceffect",
    "artobject",
    "mgef",
)


@dataclass
class PatchWriteResult:
    patch_mod_dir: Path
    patch_json_path: Path | None
    override_files: list[Path]
    managed_manifest_path: Path
    decisions_path: Path
    report_path: Path
    selected_nif_count: int
    selected_entry_count: int
    stale_removed_count: int
    warnings: list[str]


@dataclass(frozen=True)
class LightIntensityPatchConfig:
    scale_factor: float = 1.0
    worldspace_scope: str = "all"
    portal_strict_only: bool = False


@dataclass
class LightIntensityPatchWriteResult:
    patch_mod_dir: Path
    override_files: list[Path]
    managed_manifest_path: Path
    report_path: Path
    selected_nif_count: int
    source_json_file_count: int
    exported_entry_count: int
    eligible_entry_count: int
    scaled_entry_count: int
    scaled_value_count: int
    stale_removed_count: int
    warnings: list[str]


@dataclass
class _PayloadGroup:
    source_payload_index: int
    payload: dict[str, Any]
    entries: list[LightPlacerEntry]


@dataclass
class _SelectedPayload:
    payload: dict[str, Any]
    selected_entries: list[LightPlacerEntry]


def _target_text_variants(value: str) -> set[str]:
    stripped = value.strip()
    if not stripped:
        return set()

    slash_normalized = stripped.replace("\\", "/")
    backslash_normalized = stripped.replace("/", "\\")
    variants = {
        stripped,
        slash_normalized,
        backslash_normalized,
        stripped.lower(),
        slash_normalized.lower(),
        backslash_normalized.lower(),
    }
    return {variant for variant in variants if variant}


def _entry_target_values(entries: list[LightPlacerEntry]) -> set[str]:
    values: set[str] = set()
    for entry in entries:
        values.update(_target_text_variants(entry.nif_path_raw))
    return values


def _target_key_hint(key: object) -> bool:
    key_token = _normalized_token(str(key))
    return any(key_token.startswith(prefix) for prefix in _TARGET_KEY_PREFIXES)


def _target_match_state(value: str, all_target_values: set[str], kept_target_values: set[str]) -> bool | None:
    variants = _target_text_variants(value)
    if variants.isdisjoint(all_target_values):
        return None
    return not variants.isdisjoint(kept_target_values)


def _prune_unselected_targets(
    value: Any,
    *,
    all_target_values: set[str],
    kept_target_values: set[str],
    target_context: bool = False,
    list_context: bool = False,
) -> tuple[Any, bool]:
    if isinstance(value, dict):
        pruned: dict[str, Any] = {}
        for key, child in value.items():
            child_context = target_context or _target_key_hint(key)
            pruned_child, keep_child = _prune_unselected_targets(
                child,
                all_target_values=all_target_values,
                kept_target_values=kept_target_values,
                target_context=child_context,
                list_context=False,
            )
            if keep_child:
                pruned[key] = pruned_child
        return pruned, True

    if isinstance(value, list):
        pruned_list: list[Any] = []
        for child in value:
            pruned_child, keep_child = _prune_unselected_targets(
                child,
                all_target_values=all_target_values,
                kept_target_values=kept_target_values,
                target_context=target_context,
                list_context=True,
            )
            if keep_child:
                pruned_list.append(pruned_child)
        return pruned_list, True

    if isinstance(value, str):
        match_state = _target_match_state(value, all_target_values, kept_target_values)
        if match_state is False and (target_context or (list_context and ".nif" in value.lower())):
            return None, False
        return value, True

    return value, True


def _payload_group_key(entry: LightPlacerEntry) -> tuple[str, int, int, str]:
    return (
        entry.source_mod,
        entry.source_priority,
        entry.source_payload_index,
        value_signature(entry.full_payload),
    )


def _group_entries_by_source_payload(entries: list[LightPlacerEntry]) -> list[_PayloadGroup]:
    groups: list[_PayloadGroup] = []
    groups_by_key: dict[tuple[str, int, int, str], _PayloadGroup] = {}
    for entry in entries:
        key = _payload_group_key(entry)
        group = groups_by_key.get(key)
        if group is None:
            group = _PayloadGroup(
                source_payload_index=entry.source_payload_index,
                payload=entry.full_payload,
                entries=[],
            )
            groups_by_key[key] = group
            groups.append(group)
        group.entries.append(entry)
    return groups


def _payload_for_selected_entries(
    *,
    source_file: str,
    group: _PayloadGroup,
    selected_entry_ids: set[str],
    warnings: list[str],
) -> _SelectedPayload | None:
    selected_entries = [entry for entry in group.entries if entry.entry_id in selected_entry_ids]
    if not selected_entries:
        return None

    payload = copy.deepcopy(group.payload)
    if len(selected_entries) == len(group.entries):
        return _SelectedPayload(payload=payload, selected_entries=selected_entries)

    all_target_values = _entry_target_values(group.entries)
    kept_target_values = _entry_target_values(selected_entries)
    if not kept_target_values:
        return None

    pruned_payload, keep_payload = _prune_unselected_targets(
        payload,
        all_target_values=all_target_values,
        kept_target_values=kept_target_values,
    )
    if not keep_payload or not isinstance(pruned_payload, dict):
        warnings.append(
            f"{source_file}: could not rebuild payload {group.source_payload_index} after target pruning."
        )
        return None
    return _SelectedPayload(payload=pruned_payload, selected_entries=selected_entries)


def _build_selected_source_payloads(
    *,
    source_file: str,
    source_entries: list[LightPlacerEntry],
    selected_entry_ids: set[str],
    warnings: list[str],
) -> list[_SelectedPayload]:
    selected_payloads: list[_SelectedPayload] = []
    for group in _group_entries_by_source_payload(source_entries):
        selected_payload = _payload_for_selected_entries(
            source_file=source_file,
            group=group,
            selected_entry_ids=selected_entry_ids,
            warnings=warnings,
        )
        if selected_payload is not None:
            selected_payloads.append(selected_payload)
    return selected_payloads


def _selected_payload_entry_count(selected_payloads: list[_SelectedPayload]) -> int:
    return sum(len(selected_payload.selected_entries) for selected_payload in selected_payloads)


def _select_entry_for_decision(
    entries: list[LightPlacerEntry],
    decision: Decision,
    warnings: list[str],
    nif_path: str,
    conflict_types: list[str] | None = None,
) -> list[LightPlacerEntry]:
    if not entries:
        return []
    sorted_entries = sorted(
        entries,
        key=entry_priority_sort_key,
    )
    highest_priority_entry = choose_keep_highest_entry(entries, conflict_types=conflict_types)
    if highest_priority_entry is None:
        return []

    if decision.action == "disable_lp":
        return []
    if decision.action == "ignore":
        return list(entries)
    if decision.action == "keep_highest_priority":
        return [highest_priority_entry]
    if decision.action == "choose_entry":
        requested_ids = list(decision.entry_ids)
        if not requested_ids and decision.entry_id:
            requested_ids = [decision.entry_id]
        if requested_ids:
            requested_set = set(requested_ids)
            chosen_entries = [entry for entry in sorted_entries if entry.entry_id in requested_set]
            if chosen_entries:
                missing_ids = [entry_id for entry_id in requested_ids if entry_id not in {entry.entry_id for entry in chosen_entries}]
                if missing_ids:
                    warnings.append(
                        f"{nif_path}: choose_entry skipped missing entry_ids {missing_ids}, kept matched entries."
                    )
                return chosen_entries
            warnings.append(
                f"{nif_path}: choose_entry could not find any requested entry_ids {requested_ids}, used highest priority."
            )
        else:
            warnings.append(f"{nif_path}: choose_entry had no entry_ids, used highest priority.")
        return [highest_priority_entry]

    warnings.append(f"{nif_path}: unknown decision action '{decision.action}', no changes applied.")
    return list(entries)


def _build_entry_selection_state(
    scan_result: ScanResult,
    decisions: dict[str, Decision],
    warnings: list[str],
) -> tuple[dict[str, list[LightPlacerEntry]], dict[str, list[LightPlacerEntry]], set[str], int]:
    lp_entries_by_nif: dict[str, list[LightPlacerEntry]] = {}
    conflict_types_by_nif: dict[str, set[str]] = {}
    lp_entries_by_source_file_all: dict[str, list[LightPlacerEntry]] = {}
    for entry in scan_result.lp_entries:
        lp_entries_by_nif.setdefault(entry.nif_path_canonical, []).append(entry)
        lp_entries_by_source_file_all.setdefault(entry.source_file, []).append(entry)
    for conflict in scan_result.detected_conflicts:
        conflict_types_by_nif.setdefault(conflict.nif_path_canonical, set()).update(conflict.conflict_types)
    for conflict in scan_result.conflicts:
        conflict_types_by_nif.setdefault(conflict.nif_path_canonical, set()).update(conflict.conflict_types)

    winning_priority_by_source_file: dict[str, int] = {}
    for source_file, entries in lp_entries_by_source_file_all.items():
        winning_priority_by_source_file[source_file] = max(entry.source_priority for entry in entries)

    lp_entries_by_source_file_effective: dict[str, list[LightPlacerEntry]] = {}
    for source_file, entries in lp_entries_by_source_file_all.items():
        winning_priority = winning_priority_by_source_file[source_file]
        lp_entries_by_source_file_effective[source_file] = [
            entry for entry in entries if entry.source_priority == winning_priority
        ]

    selected_entry_ids = {
        entry.entry_id
        for entries in lp_entries_by_source_file_effective.values()
        for entry in entries
    }
    selected_nif_count = 0
    for nif_path, decision in sorted(decisions.items()):
        entries = lp_entries_by_nif.get(nif_path, [])
        if decision.action == "ignore":
            continue

        selected_nif_count += 1
        if not entries:
            warnings.append(f"{nif_path}: decision '{decision.action}' had no matching LP entries in current scan.")
            continue

        conflict_types = sorted(conflict_types_by_nif.get(nif_path, set()))
        chosen_entries = _select_entry_for_decision(
            entries,
            decision,
            warnings,
            nif_path,
            conflict_types=conflict_types,
        )
        for entry in entries:
            selected_entry_ids.discard(entry.entry_id)
        for entry in chosen_entries:
            selected_entry_ids.add(entry.entry_id)

    return lp_entries_by_source_file_all, lp_entries_by_source_file_effective, selected_entry_ids, selected_nif_count


def _normalize_rel_path(relative_path: str) -> str:
    return relative_path.replace("\\", "/")


def _safe_relative_path(relative_path: str, warnings: list[str]) -> Path | None:
    normalized = _normalize_rel_path(relative_path).strip().lstrip("/")
    posix_path = PurePosixPath(normalized)
    if posix_path.is_absolute() or any(part in {"", ".."} for part in posix_path.parts):
        warnings.append(f"Skipped unsafe source path '{relative_path}' while exporting override patch.")
        return None
    return Path(*posix_path.parts)


def _cleanup_empty_dirs(start_dir: Path, stop_dir: Path) -> None:
    current = start_dir
    while current != stop_dir:
        if not current.exists() or any(current.iterdir()):
            break
        current.rmdir()
        current = current.parent


def _load_managed_files(manifest_path: Path) -> set[str]:
    if not manifest_path.exists():
        return set()

    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return set()

    if not isinstance(payload, dict):
        return set()
    if int(payload.get("version", 0)) != MANAGED_FILES_VERSION:
        return set()

    raw_files = payload.get("managed_override_files")
    if not isinstance(raw_files, list):
        return set()

    files: set[str] = set()
    for value in raw_files:
        if isinstance(value, str) and value.strip():
            files.add(_normalize_rel_path(value))
    return files


def _write_managed_files(manifest_path: Path, patch_mod_name: str, managed_files: set[str]) -> None:
    payload = {
        "version": MANAGED_FILES_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "patch_mod_name": patch_mod_name,
        "managed_override_files": sorted(managed_files),
    }
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")


def _write_override_files(
    *,
    patch_mod_dir: Path,
    patch_mod_name: str,
    managed_manifest_path: Path,
    source_payloads: dict[str, list[dict[str, Any]]],
    warnings: list[str],
    legacy_patch_json_path: Path | None = None,
) -> tuple[list[Path], int, int]:
    patch_mod_dir.mkdir(parents=True, exist_ok=True)
    (patch_mod_dir / "meshes").mkdir(exist_ok=True)

    managed_files_old = _load_managed_files(managed_manifest_path)
    managed_files_new: set[str] = set()
    override_files: list[Path] = []
    exported_entry_count = 0
    for source_file, output_payload in sorted(source_payloads.items(), key=lambda item: item[0].lower()):
        rel_path = _safe_relative_path(source_file, warnings)
        if rel_path is None:
            continue

        output_path = patch_mod_dir / rel_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(output_payload, indent=2, sort_keys=False), encoding="utf-8")

        override_files.append(output_path)
        managed_files_new.add(rel_path.as_posix())
        exported_entry_count += len(output_payload)

    stale_removed_count = 0
    if legacy_patch_json_path is not None and legacy_patch_json_path.exists():
        try:
            legacy_patch_json_path.unlink()
            _cleanup_empty_dirs(legacy_patch_json_path.parent, patch_mod_dir)
            stale_removed_count += 1
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Failed to remove legacy resolved patch '{legacy_patch_json_path}': {exc}")

    stale_files = sorted(managed_files_old - managed_files_new)
    for stale_rel_path in stale_files:
        stale_path = patch_mod_dir / Path(*PurePosixPath(stale_rel_path).parts)
        try:
            if stale_path.exists():
                stale_path.unlink()
                _cleanup_empty_dirs(stale_path.parent, patch_mod_dir)
                stale_removed_count += 1
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Failed to remove stale override '{stale_rel_path}': {exc}")

    _write_managed_files(managed_manifest_path, patch_mod_name, managed_files_new)
    return override_files, exported_entry_count, stale_removed_count


def _normalized_token(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _entry_matches_worldspace_scope(entry: LightPlacerEntry, worldspace_scope: str) -> bool:
    scope = worldspace_scope.strip().lower()
    if scope == "all":
        return True

    has_interior = False
    has_exterior = False
    for is_exterior in iter_get_in_worldspace_states(entry.settings):
        if is_exterior:
            has_exterior = True
        else:
            has_interior = True

    if scope == "interior":
        return has_interior
    if scope == "exterior":
        return has_exterior
    return True


def _entry_matches_light_scale_filters(
    entry: LightPlacerEntry,
    *,
    worldspace_scope: str,
    portal_strict_only: bool,
) -> bool:
    if portal_strict_only and not is_portal_strict_entry(entry):
        return False
    return _entry_matches_worldspace_scope(entry, worldspace_scope)


def _is_intensity_key(token: str) -> bool:
    if token in _INTENSITY_KEY_EXACT:
        return True
    return any(fragment in token for fragment in _INTENSITY_KEY_CONTAINS)


def _scale_numeric_value(value: Any, scale_factor: float) -> tuple[Any, bool]:
    if isinstance(value, bool):
        return value, False
    if isinstance(value, int):
        scaled = float(value) * scale_factor
        if not isfinite(scaled):
            return value, False
        scaled = round(scaled, 6)
        if scaled == -0.0:
            scaled = 0.0
        rounded_int = int(round(scaled))
        if abs(scaled - rounded_int) <= 1e-6:
            return rounded_int, True
        return scaled, True
    if isinstance(value, float):
        if not isfinite(value):
            return value, False
        scaled = round(value * scale_factor, 6)
        if scaled == -0.0:
            scaled = 0.0
        return scaled, True
    return value, False


def _scale_intensity_fields_in_place(value: Any, scale_factor: float) -> int:
    scaled_values = 0
    if isinstance(value, dict):
        for key, child in value.items():
            key_token = _normalized_token(str(key))
            if _is_intensity_key(key_token):
                scaled_child, did_scale = _scale_numeric_value(child, scale_factor)
                if did_scale:
                    value[key] = scaled_child
                    scaled_values += 1
                    continue
            scaled_values += _scale_intensity_fields_in_place(child, scale_factor)
    elif isinstance(value, list):
        for child in value:
            scaled_values += _scale_intensity_fields_in_place(child, scale_factor)
    return scaled_values


def _validate_light_intensity_patch_config(config: LightIntensityPatchConfig) -> tuple[float, str]:
    try:
        scale_factor = float(config.scale_factor)
    except (TypeError, ValueError) as exc:
        raise ValueError("scale_factor must be a numeric value.") from exc
    if not isfinite(scale_factor) or scale_factor <= 0.0:
        raise ValueError("scale_factor must be a finite number greater than zero.")

    worldspace_scope = str(config.worldspace_scope).strip().lower()
    if worldspace_scope not in LIGHT_INTENSITY_SCOPE_VALUES:
        expected = ", ".join(sorted(LIGHT_INTENSITY_SCOPE_VALUES))
        raise ValueError(f"worldspace_scope must be one of: {expected}")

    return scale_factor, worldspace_scope


def write_patch_mod(
    scan_result: ScanResult,
    decisions: dict[str, Decision],
    patch_mod_name: str = "LP_ConflictPatch",
) -> PatchWriteResult:
    patch_mod_dir = scan_result.mods_dir / patch_mod_name
    legacy_patch_json_path = patch_mod_dir / "LightPlacer" / patch_mod_name / "resolved.json"
    managed_manifest_path = patch_mod_dir / MANAGED_FILES_NAME
    decisions_path = patch_mod_dir / "resolver_decisions.json"
    report_path = patch_mod_dir / "resolver_report.md"

    warnings: list[str] = []
    (
        lp_entries_by_source_file_all,
        lp_entries_by_source_file_effective,
        selected_entry_ids,
        selected_nif_count,
    ) = _build_entry_selection_state(scan_result, decisions, warnings)

    changed_source_payloads: dict[str, list[dict[str, Any]]] = {}
    exported_entry_count = 0
    for source_file, source_entries_effective in lp_entries_by_source_file_effective.items():
        original_ids = [entry.entry_id for entry in source_entries_effective]
        source_entries_all = lp_entries_by_source_file_all[source_file]
        kept_entries = [entry for entry in source_entries_all if entry.entry_id in selected_entry_ids]
        kept_ids = [entry.entry_id for entry in kept_entries]
        if kept_ids != original_ids:
            selected_payloads = _build_selected_source_payloads(
                source_file=source_file,
                source_entries=source_entries_all,
                selected_entry_ids=selected_entry_ids,
                warnings=warnings,
            )
            changed_source_payloads[source_file] = [item.payload for item in selected_payloads]
            exported_entry_count += _selected_payload_entry_count(selected_payloads)

    override_files, _exported_payload_count, stale_removed_count = _write_override_files(
        patch_mod_dir=patch_mod_dir,
        patch_mod_name=patch_mod_name,
        managed_manifest_path=managed_manifest_path,
        source_payloads=changed_source_payloads,
        warnings=warnings,
        legacy_patch_json_path=legacy_patch_json_path,
    )

    decisions_payload = {
        "version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "patch_mod_name": patch_mod_name,
        "decisions": {
            nif_path: {
                "action": decision.action,
                "entry_id": decision.entry_id,
                "entry_ids": decision.entry_ids,
                "note": decision.note,
                "updated_at_utc": decision.updated_at_utc,
            }
            for nif_path, decision in sorted(decisions.items())
        },
    }
    decisions_path.write_text(json.dumps(decisions_payload, indent=2, sort_keys=False), encoding="utf-8")

    report_text = render_markdown_report(scan_result.report_payload)
    report_text += "\n## Patch Export\n"
    report_text += f"- Patch mod dir: `{patch_mod_dir}`\n"
    report_text += "- Export mode: `override_source_files` (MO2 last-wins)\n"
    report_text += f"- Selected target decisions: {selected_nif_count}\n"
    report_text += f"- Exported LP entries: {exported_entry_count}\n"
    report_text += f"- Remaining LP entries after decisions: {len(selected_entry_ids)}\n"
    report_text += f"- Overridden source JSON files: {len(override_files)}\n"
    report_text += f"- Stale overrides removed: {stale_removed_count}\n"
    if warnings:
        report_text += "- Warnings:\n"
        for warning in warnings:
            report_text += f"  - {warning}\n"
    report_path.write_text(report_text, encoding="utf-8")

    return PatchWriteResult(
        patch_mod_dir=patch_mod_dir,
        patch_json_path=override_files[0] if override_files else None,
        override_files=override_files,
        managed_manifest_path=managed_manifest_path,
        decisions_path=decisions_path,
        report_path=report_path,
        selected_nif_count=selected_nif_count,
        selected_entry_count=exported_entry_count,
        stale_removed_count=stale_removed_count,
        warnings=warnings,
    )


def write_light_intensity_patch_mod(
    scan_result: ScanResult,
    decisions: dict[str, Decision],
    config: LightIntensityPatchConfig,
    patch_mod_name: str = "LP_LightIntensityPatch",
) -> LightIntensityPatchWriteResult:
    scale_factor, worldspace_scope = _validate_light_intensity_patch_config(config)

    patch_mod_dir = scan_result.mods_dir / patch_mod_name
    managed_manifest_path = patch_mod_dir / LIGHT_SCALE_MANAGED_FILES_NAME
    report_path = patch_mod_dir / "resolver_light_scale_report.md"

    warnings: list[str] = []
    (
        lp_entries_by_source_file_all,
        lp_entries_by_source_file_effective,
        selected_entry_ids,
        selected_nif_count,
    ) = _build_entry_selection_state(scan_result, decisions, warnings)

    scaled_payloads_by_source_file: dict[str, list[dict[str, Any]]] = {}
    exported_entry_count = 0
    eligible_entry_count = 0
    scaled_entry_count = 0
    scaled_value_count = 0
    for source_file in lp_entries_by_source_file_effective:
        source_entries_all = lp_entries_by_source_file_all[source_file]
        output_payload: list[dict[str, Any]] = []
        selected_payloads = _build_selected_source_payloads(
            source_file=source_file,
            source_entries=source_entries_all,
            selected_entry_ids=selected_entry_ids,
            warnings=warnings,
        )
        exported_entry_count += _selected_payload_entry_count(selected_payloads)
        for selected_payload in selected_payloads:
            eligible_entries = [
                entry
                for entry in selected_payload.selected_entries
                if _entry_matches_light_scale_filters(
                    entry,
                    worldspace_scope=worldspace_scope,
                    portal_strict_only=config.portal_strict_only,
                )
            ]
            eligible_entry_count += len(eligible_entries)
            if eligible_entries:
                scaled_values_for_entry = _scale_intensity_fields_in_place(selected_payload.payload, scale_factor)
                if scaled_values_for_entry > 0:
                    scaled_entry_count += len(eligible_entries)
                    scaled_value_count += scaled_values_for_entry
            output_payload.append(selected_payload.payload)
        scaled_payloads_by_source_file[source_file] = output_payload

    override_files, _exported_payload_count, stale_removed_count = _write_override_files(
        patch_mod_dir=patch_mod_dir,
        patch_mod_name=patch_mod_name,
        managed_manifest_path=managed_manifest_path,
        source_payloads=scaled_payloads_by_source_file,
        warnings=warnings,
    )

    report_text = render_markdown_report(scan_result.report_payload)
    report_text += "\n## Light Intensity Patch Export\n"
    report_text += f"- Patch mod dir: `{patch_mod_dir}`\n"
    report_text += "- Export mode: `override_source_files_all_effective_winners`\n"
    report_text += f"- Scale factor: {scale_factor:.2f}\n"
    report_text += f"- Worldspace filter: `{worldspace_scope}`\n"
    report_text += f"- PortalStrict only: `{str(bool(config.portal_strict_only)).lower()}`\n"
    report_text += f"- Selected target decisions applied: {selected_nif_count}\n"
    report_text += f"- Effective winner source JSON files considered: {len(lp_entries_by_source_file_effective)}\n"
    report_text += f"- Overridden source JSON files exported: {len(override_files)}\n"
    report_text += f"- Exported LP entries: {exported_entry_count}\n"
    report_text += f"- Filter-matching LP entries: {eligible_entry_count}\n"
    report_text += f"- LP entries with scaled values: {scaled_entry_count}\n"
    report_text += f"- Numeric intensity values scaled: {scaled_value_count}\n"
    report_text += f"- Remaining LP entries after decisions: {len(selected_entry_ids)}\n"
    report_text += f"- Stale overrides removed: {stale_removed_count}\n"
    report_text += (
        "- Interior/Exterior matching uses `GetInWorldspace ... == 0/1` conditions in LP settings.\n"
    )
    if warnings:
        report_text += "- Warnings:\n"
        for warning in warnings:
            report_text += f"  - {warning}\n"
    report_path.write_text(report_text, encoding="utf-8")

    return LightIntensityPatchWriteResult(
        patch_mod_dir=patch_mod_dir,
        override_files=override_files,
        managed_manifest_path=managed_manifest_path,
        report_path=report_path,
        selected_nif_count=selected_nif_count,
        source_json_file_count=len(lp_entries_by_source_file_effective),
        exported_entry_count=exported_entry_count,
        eligible_entry_count=eligible_entry_count,
        scaled_entry_count=scaled_entry_count,
        scaled_value_count=scaled_value_count,
        stale_removed_count=stale_removed_count,
        warnings=warnings,
    )
