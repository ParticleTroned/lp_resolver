# SPDX-FileCopyrightText: 2026 ParticleTroned
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .engine import ScanResult
from .models import LightPlacerEntry, ParticleLightTarget
from .priority import is_portal_strict_entry

INVENTORY_WORLDSPACE_SCOPE_VALUES = {"all", "interior", "exterior"}
_WORLDSPACE_COND_RE = re.compile(
    r"getinworldspace\s+([a-z0-9_]+)\s+none\s*==\s*([01])",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class InventoryExportConfig:
    worldspace_scope: str = "all"
    portal_strict_only: bool = False
    nif_only: bool = False
    conflicts_only: bool = False


@dataclass
class InventoryExportResult:
    output_dir: Path
    json_path: Path
    target_csv_path: Path
    lp_csv_path: Path
    pl_csv_path: Path
    exported_target_count: int
    exported_lp_entry_count: int
    exported_pl_target_count: int
    filter_summary: dict[str, Any]


def _target_type_label(target_key: str) -> str:
    key = str(target_key).strip().lower()
    if key.startswith("formid:"):
        return "formid"
    if key.startswith("effectid:"):
        return "effectid"
    if key.endswith(".nif"):
        return "nif"
    return "other"


def _normalized_token(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _iter_conditions(value: Any):
    if isinstance(value, dict):
        for key, nested in value.items():
            key_token = _normalized_token(str(key))
            if key_token == "conditions" and isinstance(nested, list):
                for condition in nested:
                    if isinstance(condition, str):
                        text = condition.strip()
                        if text:
                            yield text
            yield from _iter_conditions(nested)
    elif isinstance(value, (list, tuple, set)):
        for nested in value:
            yield from _iter_conditions(nested)


def _entry_worldspace_flags(entry: LightPlacerEntry) -> tuple[bool, bool]:
    has_interior = False
    has_exterior = False
    for condition in _iter_conditions(entry.settings):
        for match in _WORLDSPACE_COND_RE.finditer(condition):
            equals_one = match.group(2) == "1"
            if equals_one:
                has_exterior = True
            else:
                has_interior = True
    return has_interior, has_exterior


def _entry_worldspace_scope_label(entry: LightPlacerEntry) -> str:
    has_interior, has_exterior = _entry_worldspace_flags(entry)
    if has_interior and has_exterior:
        return "mixed"
    if has_interior:
        return "interior"
    if has_exterior:
        return "exterior"
    return "none"


def _entry_matches_worldspace_scope(entry: LightPlacerEntry, worldspace_scope: str) -> bool:
    scope = worldspace_scope.strip().lower()
    if scope == "all":
        return True
    has_interior, has_exterior = _entry_worldspace_flags(entry)
    if scope == "interior":
        return has_interior
    if scope == "exterior":
        return has_exterior
    return True


def _normalize_worldspace_scope(value: str) -> str:
    scope = str(value or "").strip().lower()
    return scope if scope in INVENTORY_WORLDSPACE_SCOPE_VALUES else "all"


def _build_conflict_types_by_target(scan_result: ScanResult) -> dict[str, set[str]]:
    conflict_types_by_target: dict[str, set[str]] = {}
    for conflict in scan_result.detected_conflicts:
        conflict_types_by_target.setdefault(conflict.nif_path_canonical, set()).update(conflict.conflict_types)
    return conflict_types_by_target


def _filter_lp_entries(
    entries: list[LightPlacerEntry],
    *,
    worldspace_scope: str,
    portal_strict_only: bool,
    nif_only: bool,
) -> list[LightPlacerEntry]:
    filtered: list[LightPlacerEntry] = []
    for entry in entries:
        if nif_only and _target_type_label(entry.nif_path_canonical) != "nif":
            continue
        if portal_strict_only and not is_portal_strict_entry(entry):
            continue
        if not _entry_matches_worldspace_scope(entry, worldspace_scope):
            continue
        filtered.append(entry)
    return filtered


def _filter_pl_targets(
    targets: list[ParticleLightTarget],
    *,
    target_keys_hint: set[str] | None,
    nif_only: bool,
) -> list[ParticleLightTarget]:
    filtered: list[ParticleLightTarget] = []
    for target in targets:
        if nif_only and _target_type_label(target.nif_path_canonical) != "nif":
            continue
        if target_keys_hint is not None and target.nif_path_canonical not in target_keys_hint:
            continue
        filtered.append(target)
    return filtered


def _write_targets_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    columns = [
        "target_key",
        "target_type",
        "lp_entries",
        "pl_targets",
        "has_pl",
        "in_conflict",
        "conflict_types",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "target_key": row["target_key"],
                    "target_type": row["target_type"],
                    "lp_entries": row["lp_entries"],
                    "pl_targets": row["pl_targets"],
                    "has_pl": row["has_pl"],
                    "in_conflict": row["in_conflict"],
                    "conflict_types": row["conflict_types"],
                }
            )


def _write_lp_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    columns = [
        "target_key",
        "target_type",
        "source_mod",
        "source_priority",
        "source_file",
        "entry_id",
        "worldspace_scope",
        "portal_strict",
        "has_pl",
        "in_conflict",
        "conflict_types",
        "settings_json",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "target_key": row["target_key"],
                    "target_type": row["target_type"],
                    "source_mod": row["source_mod"],
                    "source_priority": row["source_priority"],
                    "source_file": row["source_file"],
                    "entry_id": row["entry_id"],
                    "worldspace_scope": row["worldspace_scope"],
                    "portal_strict": row["portal_strict"],
                    "has_pl": row["has_pl"],
                    "in_conflict": row["in_conflict"],
                    "conflict_types": row["conflict_types"],
                    "settings_json": json.dumps(row["settings"], sort_keys=True, ensure_ascii=False),
                }
            )


def _write_pl_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    columns = [
        "target_key",
        "target_type",
        "source_mod",
        "source_priority",
        "source_file",
        "source_kind",
        "in_conflict",
        "conflict_types",
        "payload_json",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "target_key": row["target_key"],
                    "target_type": row["target_type"],
                    "source_mod": row["source_mod"],
                    "source_priority": row["source_priority"],
                    "source_file": row["source_file"],
                    "source_kind": row["source_kind"],
                    "in_conflict": row["in_conflict"],
                    "conflict_types": row["conflict_types"],
                    "payload_json": json.dumps(row["payload"], sort_keys=True, ensure_ascii=False),
                }
            )


def write_inventory_reports(
    scan_result: ScanResult,
    output_dir: Path,
    *,
    config: InventoryExportConfig | None = None,
    file_prefix: str = "Results",
) -> InventoryExportResult:
    cfg = config or InventoryExportConfig()
    worldspace_scope = _normalize_worldspace_scope(cfg.worldspace_scope)
    portal_strict_only = bool(cfg.portal_strict_only)
    nif_only = bool(cfg.nif_only)
    conflicts_only = bool(cfg.conflicts_only)

    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    conflict_types_by_target = _build_conflict_types_by_target(scan_result)
    pl_target_keys_all = {target.nif_path_canonical for target in scan_result.pl_targets}
    filtered_lp_entries = _filter_lp_entries(
        scan_result.lp_entries,
        worldspace_scope=worldspace_scope,
        portal_strict_only=portal_strict_only,
        nif_only=nif_only,
    )

    # If LP-specific filters are active, PL inventory is trimmed to LP-matching target keys.
    # Otherwise it stays as full PL inventory for "all findings" audits.
    lp_scope_active = worldspace_scope != "all" or portal_strict_only
    pl_target_key_hint = {entry.nif_path_canonical for entry in filtered_lp_entries} if lp_scope_active else None
    filtered_pl_targets = _filter_pl_targets(
        scan_result.pl_targets,
        target_keys_hint=pl_target_key_hint,
        nif_only=nif_only,
    )

    pl_target_keys_filtered = {target.nif_path_canonical for target in filtered_pl_targets}

    lp_rows: list[dict[str, Any]] = []
    for entry in sorted(
        filtered_lp_entries,
        key=lambda item: (
            _target_type_label(item.nif_path_canonical),
            item.nif_path_canonical.lower(),
            item.source_priority,
            item.source_mod.lower(),
            item.source_file.lower(),
            item.entry_id,
        ),
    ):
        conflict_types = sorted(conflict_types_by_target.get(entry.nif_path_canonical, set()))
        if conflicts_only and not conflict_types:
            continue
        lp_rows.append(
            {
                "target_key": entry.nif_path_canonical,
                "target_type": _target_type_label(entry.nif_path_canonical),
                "source_mod": entry.source_mod,
                "source_priority": entry.source_priority,
                "source_file": entry.source_file,
                "entry_id": entry.entry_id,
                "worldspace_scope": _entry_worldspace_scope_label(entry),
                "portal_strict": bool(is_portal_strict_entry(entry)),
                "has_pl": entry.nif_path_canonical in pl_target_keys_all,
                "in_conflict": bool(conflict_types),
                "conflict_types": ";".join(conflict_types),
                "settings": entry.settings,
            }
        )

    pl_rows: list[dict[str, Any]] = []
    for target in sorted(
        filtered_pl_targets,
        key=lambda item: (
            _target_type_label(item.nif_path_canonical),
            item.nif_path_canonical.lower(),
            item.source_priority,
            item.source_mod.lower(),
            item.source_file.lower(),
        ),
    ):
        conflict_types = sorted(conflict_types_by_target.get(target.nif_path_canonical, set()))
        if conflicts_only and not conflict_types:
            continue
        pl_rows.append(
            {
                "target_key": target.nif_path_canonical,
                "target_type": _target_type_label(target.nif_path_canonical),
                "source_mod": target.source_mod,
                "source_priority": target.source_priority,
                "source_file": target.source_file,
                "source_kind": str(target.payload.get("kind", "particle_lights")),
                "in_conflict": bool(conflict_types),
                "conflict_types": ";".join(conflict_types),
                "payload": target.payload,
            }
        )

    lp_count_by_target: dict[str, int] = {}
    for row in lp_rows:
        key = str(row["target_key"])
        lp_count_by_target[key] = lp_count_by_target.get(key, 0) + 1

    pl_count_by_target: dict[str, int] = {}
    for row in pl_rows:
        key = str(row["target_key"])
        pl_count_by_target[key] = pl_count_by_target.get(key, 0) + 1

    target_keys = {row["target_key"] for row in lp_rows}
    target_keys.update(row["target_key"] for row in pl_rows)
    target_rows: list[dict[str, Any]] = []
    for target_key in sorted(target_keys, key=lambda item: (_target_type_label(item), item.lower())):
        conflict_types = sorted(conflict_types_by_target.get(target_key, set()))
        target_rows.append(
            {
                "target_key": target_key,
                "target_type": _target_type_label(target_key),
                "lp_entries": lp_count_by_target.get(target_key, 0),
                "pl_targets": pl_count_by_target.get(target_key, 0),
                "has_pl": target_key in pl_target_keys_filtered,
                "in_conflict": bool(conflict_types),
                "conflict_types": ";".join(conflict_types),
                "conflict_types_list": conflict_types,
            }
        )

    json_payload = {
        "version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": {
            "mo2_root": str(scan_result.mo2_root),
            "profile_path": str(scan_result.profile_path),
            "mods_dir": str(scan_result.mods_dir),
            "mod_order_source": scan_result.mod_order_source,
            "synthetic_modlist_path": (
                str(scan_result.synthetic_modlist_path) if scan_result.synthetic_modlist_path else None
            ),
            "vortex_state_path": str(scan_result.vortex_state_path) if scan_result.vortex_state_path else None,
        },
        "filters": {
            "worldspace_scope": worldspace_scope,
            "portal_strict_only": portal_strict_only,
            "nif_only": nif_only,
            "conflicts_only": conflicts_only,
        },
        "summary": {
            "lp_entries_total": len(scan_result.lp_entries),
            "pl_targets_total": len(scan_result.pl_targets),
            "lp_entries_exported": len(lp_rows),
            "pl_targets_exported": len(pl_rows),
            "targets_exported": len(target_rows),
            "targets_in_conflict_exported": sum(1 for row in target_rows if row["in_conflict"]),
        },
        "targets": [
            {
                "target_key": row["target_key"],
                "target_type": row["target_type"],
                "lp_entries": row["lp_entries"],
                "pl_targets": row["pl_targets"],
                "has_pl": row["has_pl"],
                "in_conflict": row["in_conflict"],
                "conflict_types": row["conflict_types_list"],
            }
            for row in target_rows
        ],
        "lp_entries": [
            {
                "target_key": row["target_key"],
                "target_type": row["target_type"],
                "source_mod": row["source_mod"],
                "source_priority": row["source_priority"],
                "source_file": row["source_file"],
                "entry_id": row["entry_id"],
                "worldspace_scope": row["worldspace_scope"],
                "portal_strict": row["portal_strict"],
                "has_pl": row["has_pl"],
                "in_conflict": row["in_conflict"],
                "conflict_types": row["conflict_types"].split(";") if row["conflict_types"] else [],
                "settings": row["settings"],
            }
            for row in lp_rows
        ],
        "pl_targets": [
            {
                "target_key": row["target_key"],
                "target_type": row["target_type"],
                "source_mod": row["source_mod"],
                "source_priority": row["source_priority"],
                "source_file": row["source_file"],
                "source_kind": row["source_kind"],
                "in_conflict": row["in_conflict"],
                "conflict_types": row["conflict_types"].split(";") if row["conflict_types"] else [],
                "payload": row["payload"],
            }
            for row in pl_rows
        ],
        "issues": [
            {
                "severity": issue.severity,
                "message": issue.message,
                "source_mod": issue.source_mod,
                "source_file": issue.source_file,
            }
            for issue in scan_result.issues
        ],
    }

    json_path = output_dir / f"{file_prefix}_summary.json"
    target_csv_path = output_dir / f"{file_prefix}_targets.csv"
    lp_csv_path = output_dir / f"{file_prefix}_lp_entries.csv"
    pl_csv_path = output_dir / f"{file_prefix}_pl_targets.csv"

    json_path.write_text(json.dumps(json_payload, indent=2, sort_keys=False, ensure_ascii=False), encoding="utf-8")
    _write_targets_csv(target_csv_path, target_rows)
    _write_lp_csv(lp_csv_path, lp_rows)
    _write_pl_csv(pl_csv_path, pl_rows)

    return InventoryExportResult(
        output_dir=output_dir,
        json_path=json_path,
        target_csv_path=target_csv_path,
        lp_csv_path=lp_csv_path,
        pl_csv_path=pl_csv_path,
        exported_target_count=len(target_rows),
        exported_lp_entry_count=len(lp_rows),
        exported_pl_target_count=len(pl_rows),
        filter_summary={
            "worldspace_scope": worldspace_scope,
            "portal_strict_only": portal_strict_only,
            "nif_only": nif_only,
            "conflicts_only": conflicts_only,
        },
    )
