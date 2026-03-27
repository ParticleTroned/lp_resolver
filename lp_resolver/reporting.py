# SPDX-FileCopyrightText: 2026 ParticleTroned
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import Conflict, ParseIssue


def _target_type_label(target_key: str) -> str:
    key = str(target_key).strip().lower()
    if key.startswith("formid:"):
        return "formid"
    if key.endswith(".nif"):
        return "nif"
    return "other"


def build_report_payload(
    *,
    mo2_root: Path,
    profile_path: Path,
    mods_dir: Path,
    enabled_mod_count: int,
    lp_candidate_files: int,
    pl_candidate_files: int,
    lp_overridden_files: int = 0,
    pl_overridden_files: int = 0,
    lp_entries: int,
    pl_targets: int,
    conflicts: list[Conflict],
    issues: list[ParseIssue],
    mod_order_source: str = "mo2",
    synthetic_modlist_path: Path | None = None,
    vortex_state_path: Path | None = None,
) -> dict[str, Any]:
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mo2_root": str(mo2_root),
        "profile_path": str(profile_path),
        "mods_dir": str(mods_dir),
        "mod_order_source": mod_order_source,
        "synthetic_modlist_path": str(synthetic_modlist_path) if synthetic_modlist_path else None,
        "vortex_state_path": str(vortex_state_path) if vortex_state_path else None,
        "summary": {
            "enabled_mod_count": enabled_mod_count,
            "lp_candidate_files": lp_candidate_files,
            "pl_candidate_files": pl_candidate_files,
            "lp_overridden_files": lp_overridden_files,
            "pl_overridden_files": pl_overridden_files,
            "lp_entries": lp_entries,
            "pl_targets": pl_targets,
            "conflict_count": len(conflicts),
        },
        "issues": [
            {
                "severity": issue.severity,
                "message": issue.message,
                "source_mod": issue.source_mod,
                "source_file": issue.source_file,
            }
            for issue in issues
        ],
        "conflicts": [
            {
                "nif_path_canonical": conflict.nif_path_canonical,
                "conflict_types": conflict.conflict_types,
                "lp_entries": [
                    {
                        "entry_id": entry.entry_id,
                        "source_mod": entry.source_mod,
                        "source_priority": entry.source_priority,
                        "source_file": entry.source_file,
                        "nif_path_raw": entry.nif_path_raw,
                        "nif_path_canonical": entry.nif_path_canonical,
                        "settings": entry.settings,
                    }
                    for entry in conflict.lp_entries
                ],
                "pl_targets": [
                    {
                        "source_mod": target.source_mod,
                        "source_priority": target.source_priority,
                        "source_file": target.source_file,
                        "nif_path_raw": target.nif_path_raw,
                        "nif_path_canonical": target.nif_path_canonical,
                    }
                    for target in conflict.pl_targets
                ],
            }
            for conflict in conflicts
        ],
    }


def render_markdown_report(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    conflicts = payload.get("conflicts", [])
    formid_conflicts = sum(
        1 for conflict in conflicts if _target_type_label(conflict.get("nif_path_canonical", "")) == "formid"
    )
    lines: list[str] = [
        "# Light Placer Conflict Report",
        "",
        f"- Generated: {payload['generated_at_utc']}",
        f"- Mod Root: `{payload['mo2_root']}`",
        f"- Profile: `{payload['profile_path']}`",
        f"- Mods Dir: `{payload['mods_dir']}`",
        f"- Mod Order Source: `{payload.get('mod_order_source', 'mo2')}`",
        "",
        "## Summary",
        f"- Enabled mods: {summary['enabled_mod_count']}",
        f"- Light Placer candidate files: {summary['lp_candidate_files']}",
        f"- Particle Lights candidate files: {summary['pl_candidate_files']}",
        f"- Overridden LP files skipped: {summary.get('lp_overridden_files', 0)}",
        f"- Overridden PL files skipped: {summary.get('pl_overridden_files', 0)}",
        f"- Normalized LP entries: {summary['lp_entries']}",
        f"- Normalized PL targets: {summary['pl_targets']}",
        f"- Conflicts: {summary['conflict_count']}",
    ]
    if formid_conflicts > 0:
        lines.append(f"- FormID-keyed conflicts: {formid_conflicts}")
        lines.append(
            "- FormID preview mode uses LP JSON local points/radius only; no mesh path is available from LP JSON."
        )
        lines.append("- LP-vs-PL overlap still requires a shared NIF target key.")
    synthetic_modlist_path = payload.get("synthetic_modlist_path")
    if synthetic_modlist_path:
        lines.append(f"- Synthetic Vortex modlist: `{synthetic_modlist_path}`")
    vortex_state_path = payload.get("vortex_state_path")
    if vortex_state_path:
        lines.append(f"- Vortex state source: `{vortex_state_path}`")

    issues = payload.get("issues", [])
    if issues:
        lines.extend(["", "## Parse Issues"])
        for issue in issues:
            lines.append(
                f"- [{issue['severity']}] `{issue['source_mod']}/{issue['source_file']}`: {issue['message']}"
            )

    if conflicts:
        lines.extend(["", "## Conflicts"])
        for conflict in conflicts:
            target_key = conflict["nif_path_canonical"]
            target_type = _target_type_label(target_key)
            lines.extend(
                [
                    "",
                    f"### `{target_key}`",
                    f"- Target type: {target_type}",
                    f"- Types: {', '.join(conflict['conflict_types'])}",
                    f"- LP candidates: {len(conflict['lp_entries'])}",
                    f"- PL overlap: {'yes' if conflict['pl_targets'] else 'no'}",
                ]
            )
            if target_type == "formid":
                lines.append("- Preview note: local LP XYZ/radius only; mesh-based preview is unavailable.")
            if conflict["lp_entries"]:
                lines.append("- LP entries:")
                for entry in conflict["lp_entries"]:
                    lines.append(
                        f"  - {entry['source_mod']} (prio {entry['source_priority']}), `{entry['source_file']}`"
                    )
            if conflict["pl_targets"]:
                lines.append("- PL targets:")
                for target in conflict["pl_targets"]:
                    lines.append(
                        f"  - {target['source_mod']} (prio {target['source_priority']}), `{target['source_file']}`"
                    )
    else:
        lines.extend(["", "## Conflicts", "- No conflicts detected."])

    return "\n".join(lines) + "\n"


def write_reports(output_dir: Path, payload: dict[str, Any], json_indent: int = 2) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "report.json"
    md_path = output_dir / "report.md"

    json_path.write_text(json.dumps(payload, indent=json_indent, sort_keys=False), encoding="utf-8")
    md_path.write_text(render_markdown_report(payload), encoding="utf-8")
    return json_path, md_path
