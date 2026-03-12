# SPDX-FileCopyrightText: 2026 ParticleTroned
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from .decisions import Decision
from .engine import ScanResult
from .models import LightPlacerEntry
from .priority import choose_keep_highest_entry, entry_priority_sort_key
from .reporting import render_markdown_report

MANAGED_FILES_VERSION = 1
MANAGED_FILES_NAME = "resolver_managed_files.json"


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

    patch_mod_dir.mkdir(parents=True, exist_ok=True)

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

    warnings: list[str] = []
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

    changed_source_files: dict[str, list[LightPlacerEntry]] = {}
    for source_file, source_entries_effective in lp_entries_by_source_file_effective.items():
        original_ids = [entry.entry_id for entry in source_entries_effective]
        source_entries_all = lp_entries_by_source_file_all[source_file]
        kept_entries = [entry for entry in source_entries_all if entry.entry_id in selected_entry_ids]
        kept_ids = [entry.entry_id for entry in kept_entries]
        if kept_ids != original_ids:
            changed_source_files[source_file] = kept_entries

    managed_files_old = _load_managed_files(managed_manifest_path)
    managed_files_new: set[str] = set()
    override_files: list[Path] = []
    exported_entry_count = 0
    for source_file, kept_entries in sorted(changed_source_files.items(), key=lambda item: item[0].lower()):
        rel_path = _safe_relative_path(source_file, warnings)
        if rel_path is None:
            continue

        output_path = patch_mod_dir / rel_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_payload = [entry.full_payload for entry in kept_entries]
        output_path.write_text(json.dumps(output_payload, indent=2, sort_keys=False), encoding="utf-8")

        override_files.append(output_path)
        managed_files_new.add(rel_path.as_posix())
        exported_entry_count += len(output_payload)

    stale_removed_count = 0
    if legacy_patch_json_path.exists():
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
    report_text += f"- Selected NIF decisions: {selected_nif_count}\n"
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
