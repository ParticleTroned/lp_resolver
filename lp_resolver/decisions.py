# SPDX-FileCopyrightText: 2026 ParticleTroned
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .models import Conflict

DECISIONS_VERSION = 1
VALID_ACTIONS = {"ignore", "keep_highest_priority", "choose_entry", "disable_lp"}


@dataclass
class Decision:
    action: str
    entry_id: str | None = None
    entry_ids: list[str] = field(default_factory=list)
    note: str = ""
    updated_at_utc: str = ""


def _normalize_entry_ids(raw_entry_ids: object) -> list[str]:
    if not isinstance(raw_entry_ids, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for value in raw_entry_ids:
        entry_id = str(value).strip() if value is not None else ""
        if not entry_id or entry_id in seen:
            continue
        seen.add(entry_id)
        normalized.append(entry_id)
    return normalized


def _decision_from_dict(raw: dict) -> Decision | None:
    action = str(raw.get("action", "")).strip()
    if action not in VALID_ACTIONS:
        return None
    legacy_entry_id = raw.get("entry_id")
    entry_id: str | None = None
    if legacy_entry_id is not None:
        entry_id = str(legacy_entry_id).strip() or None
    entry_ids = _normalize_entry_ids(raw.get("entry_ids"))
    if entry_id and entry_id not in entry_ids:
        entry_ids.insert(0, entry_id)
    if entry_ids:
        entry_id = entry_ids[0]
    note = str(raw.get("note", ""))
    updated_at_utc = str(raw.get("updated_at_utc", ""))
    return Decision(action=action, entry_id=entry_id, entry_ids=entry_ids, note=note, updated_at_utc=updated_at_utc)


def load_decisions(path: Path) -> dict[str, Decision]:
    if not path.exists():
        return {}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}

    if not isinstance(payload, dict):
        return {}
    if int(payload.get("version", 0)) != DECISIONS_VERSION:
        return {}

    decisions_payload = payload.get("decisions", {})
    if not isinstance(decisions_payload, dict):
        return {}

    decisions: dict[str, Decision] = {}
    for nif_path, raw_decision in decisions_payload.items():
        if not isinstance(raw_decision, dict):
            continue
        decision = _decision_from_dict(raw_decision)
        if decision is None:
            continue
        decisions[str(nif_path)] = decision
    return decisions


def save_decisions(path: Path, decisions: dict[str, Decision]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": DECISIONS_VERSION,
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "decisions": {nif_path: asdict(decision) for nif_path, decision in sorted(decisions.items())},
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")


def apply_decisions(conflicts: list[Conflict], decisions: dict[str, Decision]) -> tuple[dict[str, Decision], list[str]]:
    available_nifs = {conflict.nif_path_canonical for conflict in conflicts}
    applied: dict[str, Decision] = {}
    stale: list[str] = []
    for nif_path, decision in decisions.items():
        if nif_path in available_nifs:
            applied[nif_path] = decision
        else:
            stale.append(nif_path)
    return applied, sorted(stale)


def make_decision(
    action: str,
    entry_id: str | None = None,
    entry_ids: list[str] | None = None,
    note: str = "",
) -> Decision:
    if action not in VALID_ACTIONS:
        raise ValueError(f"Invalid decision action: {action}")
    normalized_entry_ids = _normalize_entry_ids(entry_ids or [])
    normalized_entry_id = str(entry_id).strip() if entry_id is not None else ""
    normalized_entry_id = normalized_entry_id or None
    if normalized_entry_id and normalized_entry_id not in normalized_entry_ids:
        normalized_entry_ids.insert(0, normalized_entry_id)
    if normalized_entry_ids:
        normalized_entry_id = normalized_entry_ids[0]
    return Decision(
        action=action,
        entry_id=normalized_entry_id,
        entry_ids=normalized_entry_ids,
        note=note,
        updated_at_utc=datetime.now(timezone.utc).isoformat(),
    )
