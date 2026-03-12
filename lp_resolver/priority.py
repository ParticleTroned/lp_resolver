# SPDX-FileCopyrightText: 2026 ParticleTroned
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

from math import isfinite
import re
from typing import Any

from .models import LightPlacerEntry

_PORTAL_STRICT_MASKS = (
    1 << 13,
    1 << 17,
)
_WORLDSPACE_COND_RE = re.compile(
    r"getinworldspace\s+([a-z0-9_]+)\s+none\s*==\s*([01])",
    re.IGNORECASE,
)


def entry_priority_sort_key(entry: LightPlacerEntry) -> tuple[int, float, float, str, str, str]:
    radius_hint = _entry_numeric_hint(entry.settings, "radius")
    fade_hint = _entry_numeric_hint(entry.settings, "fade")
    return (
        entry.source_priority,
        radius_hint,
        fade_hint,
        entry.source_mod.lower(),
        entry.source_file.lower(),
        entry.entry_id,
    )


def _normalized_token(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _is_truthy_flag_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value) != 0.0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _value_has_portal_strict(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return any((value & mask) != 0 for mask in _PORTAL_STRICT_MASKS)
    if isinstance(value, float):
        if value.is_integer():
            return _value_has_portal_strict(int(value))
        return False
    if isinstance(value, str):
        token = _normalized_token(value)
        return "portalstrict" in token
    if isinstance(value, dict):
        for key, nested in value.items():
            key_token = _normalized_token(str(key))
            if "portalstrict" in key_token and _is_truthy_flag_value(nested):
                return True
            if "flag" in key_token and _value_has_portal_strict(nested):
                return True
            if _value_has_portal_strict(nested):
                return True
        return False
    if isinstance(value, (list, tuple, set)):
        return any(_value_has_portal_strict(item) for item in value)
    return False


def _iter_numeric_key_values(value: Any):
    if isinstance(value, dict):
        for key, nested in value.items():
            key_token = _normalized_token(str(key))
            if isinstance(nested, bool):
                pass
            elif isinstance(nested, (int, float)):
                numeric = float(nested)
                if isfinite(numeric):
                    yield key_token, numeric
            yield from _iter_numeric_key_values(nested)
    elif isinstance(value, (list, tuple, set)):
        for nested in value:
            yield from _iter_numeric_key_values(nested)


def _entry_numeric_hint(settings: dict[str, Any], key_name: str) -> float:
    wanted = _normalized_token(key_name)
    best: float | None = None
    for key_token, numeric in _iter_numeric_key_values(settings):
        if key_token != wanted:
            continue
        if best is None or numeric > best:
            best = numeric
    if best is None:
        # Missing value should not outrank a valid radius/fade value.
        return float("-inf")
    return best


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


def _entry_worldspace_tokens(entry: LightPlacerEntry) -> set[str]:
    tokens: set[str] = set()
    for condition in _iter_conditions(entry.settings):
        for match in _WORLDSPACE_COND_RE.finditer(condition):
            worldspace = match.group(1).lower()
            equals_one = match.group(2) == "1"
            if equals_one and worldspace:
                tokens.add(worldspace)
    return tokens


def _has_shared_worldspace(entries: list[LightPlacerEntry]) -> bool:
    per_entry_tokens = [_entry_worldspace_tokens(entry) for entry in entries]
    if not per_entry_tokens or any(not tokens for tokens in per_entry_tokens):
        return False
    shared = set.intersection(*per_entry_tokens)
    return bool(shared)


def is_portal_strict_entry(entry: LightPlacerEntry) -> bool:
    # Normalized settings retain light/flag fields while removing only path/comment-like noise.
    return _value_has_portal_strict(entry.settings)


def choose_keep_highest_entry(
    entries: list[LightPlacerEntry],
    conflict_types: list[str] | None = None,
) -> LightPlacerEntry | None:
    if not entries:
        return None

    sorted_entries = sorted(entries, key=entry_priority_sort_key)
    types = set(conflict_types or [])

    # For divergent duplicate conflicts in the same worldspace context,
    # prefer portal-strict local/interior behavior when strict/non-strict are mixed.
    if "duplicate_divergent" in types and _has_shared_worldspace(sorted_entries):
        strict_entries = [entry for entry in sorted_entries if is_portal_strict_entry(entry)]
        if 0 < len(strict_entries) < len(sorted_entries):
            return strict_entries[-1]

    return sorted_entries[-1]
