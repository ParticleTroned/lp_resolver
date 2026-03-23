# SPDX-FileCopyrightText: 2026 ParticleTroned
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from heapq import heappop, heappush
from pathlib import Path
from typing import Any

from .models import ModEntry, ParseIssue

VORTEX_EXPORT_FILENAME = "vortex_modlist.txt"
_GAME_TOKEN_RE = re.compile(r"\{game\}|\$\{game\}|%game%", re.IGNORECASE)


@dataclass(frozen=True)
class VortexModlistResult:
    entries: list[ModEntry]
    mods_dir: Path
    export_path: Path
    profile_id: str
    profile_name: str
    game_id: str
    state_path: Path
    issues: list[ParseIssue]
    tie_breaker_description: str


@dataclass(frozen=True)
class _EnabledVortexMod:
    mod_id: str
    installation_path: str
    display_name: str
    aliases: tuple[str, ...]
    enabled_time: int | None
    install_time_epoch: int | None
    rules: list[dict[str, Any]]
    file_overrides: list[Any]
    path: Path


def is_vortex_profile(profile_path: Path) -> bool:
    return (profile_path / "plugins.txt").exists() or (profile_path / "loadorder.txt").exists()


def export_vortex_enabled_mods(
    profile_path: Path,
    explicit_mods_dir: Path | None = None,
    export_path: Path | None = None,
    write_export_file: bool = True,
) -> VortexModlistResult:
    resolved_profile = profile_path.expanduser().resolve()
    if not resolved_profile.exists():
        raise FileNotFoundError(f"Vortex profile path does not exist: {resolved_profile}")
    if not resolved_profile.is_dir():
        raise NotADirectoryError(f"Vortex profile path is not a directory: {resolved_profile}")
    if not is_vortex_profile(resolved_profile):
        raise FileNotFoundError(
            f"Vortex profile is missing plugins.txt/loadorder.txt: {resolved_profile}"
        )

    vortex_root = _resolve_vortex_root(resolved_profile)
    state, state_path = _load_vortex_state(vortex_root)
    profile_id, profile_payload = _resolve_profile_from_state(state, resolved_profile)
    game_id = str(profile_payload.get("gameId", "")).strip()
    if not game_id:
        raise ValueError(f"Could not determine gameId for Vortex profile '{profile_id}'.")

    mods_dir = _resolve_mods_dir(
        state=state,
        vortex_root=vortex_root,
        game_id=game_id,
        explicit_mods_dir=explicit_mods_dir,
    )
    enabled_mods, mod_issues = _collect_enabled_mods(state, profile_id, profile_payload, game_id, mods_dir)

    tie_breaker_description = (
        "Tie-breakers for unrelated mods: "
        "1) profile modState.enabledTime (descending, used as Vortex general-order proxy when present), "
        "2) installationPath (ascending, stable internal mod key), "
        "3) attributes.installTime (descending), "
        "4) normalized display name (ascending), "
        "5) mod id (ascending)."
    )

    ordered_mod_ids, order_issues = _order_enabled_mods(enabled_mods)
    ordered_mods = [enabled_mods[mod_id] for mod_id in ordered_mod_ids]

    target_export_path = export_path or (resolved_profile / VORTEX_EXPORT_FILENAME)
    target_export_path = target_export_path.expanduser().resolve()
    if write_export_file:
        target_export_path.parent.mkdir(parents=True, exist_ok=True)
        _write_synthetic_modlist(target_export_path, ordered_mods)

    entries: list[ModEntry] = []
    count = len(ordered_mods)
    for index, mod in enumerate(ordered_mods):
        priority = count - index - 1
        entries.append(
            ModEntry(
                name=mod.installation_path,
                priority=priority,
                path=mod.path,
            )
        )

    issues = [
        ParseIssue(
            severity="info",
            source_mod="__vortex__",
            source_file=target_export_path.name,
            message=tie_breaker_description,
        ),
        *mod_issues,
        *order_issues,
    ]

    profile_name = str(profile_payload.get("name", profile_id)).strip() or profile_id
    return VortexModlistResult(
        entries=entries,
        mods_dir=mods_dir,
        export_path=target_export_path,
        profile_id=profile_id,
        profile_name=profile_name,
        game_id=game_id,
        state_path=state_path,
        issues=issues,
        tie_breaker_description=tie_breaker_description,
    )


def _write_synthetic_modlist(path: Path, ordered_mods: list[_EnabledVortexMod]) -> None:
    lines = [f"+{mod.installation_path}" for mod in ordered_mods]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _resolve_vortex_root(profile_path: Path) -> Path:
    if profile_path.parent.name.lower() == "profiles":
        candidate = profile_path.parent.parent.parent
        if (candidate / "temp").exists():
            return candidate.resolve()

    for parent in profile_path.parents:
        if (parent / "temp").exists() and (parent / "state.v2").exists():
            return parent.resolve()

    raise FileNotFoundError(
        f"Could not locate Vortex root from profile path: {profile_path}"
    )


def _load_vortex_state(vortex_root: Path) -> tuple[dict[str, Any], Path]:
    candidates = _state_json_candidates(vortex_root)
    if not candidates:
        raise FileNotFoundError(
            f"Could not find parseable Vortex JSON state backups under: {vortex_root / 'temp'}"
        )

    errors: list[str] = []
    for candidate in candidates:
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8", errors="ignore"))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{candidate.name}: {exc}")
            continue
        if isinstance(payload, dict):
            return payload, candidate
        errors.append(f"{candidate.name}: root JSON value is not an object")

    joined = "; ".join(errors[-5:])
    raise ValueError(f"Failed to parse Vortex JSON state backup(s): {joined}")


def _state_json_candidates(vortex_root: Path) -> list[Path]:
    candidates: list[Path] = []
    for rel in (
        Path("temp") / "state_backups_full",
        Path("temp") / "state_backups",
    ):
        directory = vortex_root / rel
        if not directory.exists() or not directory.is_dir():
            continue
        for item in directory.glob("*.json"):
            if item.is_file():
                candidates.append(item.resolve())

    candidates.sort(
        key=lambda item: (
            item.name.lower() != "startup.json",
            -item.stat().st_mtime_ns,
            item.name.lower(),
        )
    )
    return candidates


def _resolve_profile_from_state(state: dict[str, Any], profile_path: Path) -> tuple[str, dict[str, Any]]:
    persistent = _as_dict(state.get("persistent"))
    profiles = _as_dict(persistent.get("profiles"))
    if not profiles:
        raise ValueError("Vortex state is missing persistent.profiles.")

    requested_profile_id = profile_path.name.strip()
    if requested_profile_id and requested_profile_id in profiles:
        payload = _as_dict(profiles.get(requested_profile_id))
        return requested_profile_id, payload

    settings = _as_dict(state.get("settings"))
    settings_profiles = _as_dict(settings.get("profiles"))
    active_profile_id = str(settings_profiles.get("activeProfileId", "")).strip()
    if active_profile_id and active_profile_id in profiles:
        payload = _as_dict(profiles.get(active_profile_id))
        return active_profile_id, payload

    first_profile_id = sorted(profiles.keys())[0]
    payload = _as_dict(profiles.get(first_profile_id))
    return first_profile_id, payload


def _normalize_identifier(value: str) -> str:
    return "".join(ch for ch in value.strip().lower() if ch.isalnum())


def _coerce_raw_install_path(value: Any) -> str | None:
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, dict):
        for key in ("path", "installPath", "value", "target"):
            nested = value.get(key)
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
    return None


def _expand_install_path_template(raw_path: str, game_id: str) -> str:
    with_game = _GAME_TOKEN_RE.sub(game_id, raw_path)
    return os.path.expandvars(with_game)


def _resolve_install_base_path(raw_path: str, vortex_root: Path, game_id: str) -> Path:
    expanded_text = _expand_install_path_template(raw_path, game_id).strip()
    candidate = Path(expanded_text).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    return (vortex_root / candidate).resolve()


def _candidate_mods_dirs(base: Path, game_id: str) -> list[Path]:
    game = game_id.strip()
    candidates: list[Path] = []

    if game:
        candidates.extend(
            [
                (base / game / "mods").resolve(),
                (base / game).resolve(),
                (base / "mods" / game).resolve(),
                (base / "mods").resolve(),
            ]
        )
    else:
        candidates.append((base / "mods").resolve())
    candidates.append(base.resolve())

    deduped: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = candidate.as_posix().lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def _state_install_path_texts(state: dict[str, Any], game_id: str) -> list[str]:
    settings = _as_dict(state.get("settings"))
    mods_settings = _as_dict(settings.get("mods"))
    install_path_value = mods_settings.get("installPath")
    normalized_game_id = _normalize_identifier(game_id)
    raw_paths: list[str] = []

    def add_raw(value: Any) -> None:
        coerced = _coerce_raw_install_path(value)
        if not coerced:
            return
        if coerced in raw_paths:
            return
        raw_paths.append(coerced)

    if isinstance(install_path_value, str):
        add_raw(install_path_value)
    elif isinstance(install_path_value, dict):
        if game_id in install_path_value:
            add_raw(install_path_value.get(game_id))
        if normalized_game_id:
            for key, value in install_path_value.items():
                if _normalize_identifier(str(key)) == normalized_game_id:
                    add_raw(value)
        for fallback_key in ("{game}", "${game}", "%game%", "default", "global"):
            if fallback_key in install_path_value:
                add_raw(install_path_value.get(fallback_key))
        for value in install_path_value.values():
            add_raw(value)

    # Fallback keys seen in some state variants.
    add_raw(mods_settings.get("installPathPattern"))
    add_raw(mods_settings.get("path"))
    add_raw(mods_settings.get("stagingPath"))

    return raw_paths


def _looks_like_vortex_root(path: Path) -> bool:
    return path.is_dir() and (path / "temp").exists() and (
        (path / "state.v2").exists() or (path / "profiles").exists()
    )


def _is_usable_mods_dir_candidate(path: Path) -> bool:
    if not path.exists() or not path.is_dir():
        return False
    if _looks_like_vortex_root(path):
        return False
    return True


def _resolve_mods_dir(
    *,
    state: dict[str, Any],
    vortex_root: Path,
    game_id: str,
    explicit_mods_dir: Path | None,
) -> Path:
    base_hints: list[tuple[str, Path]] = []

    if explicit_mods_dir is not None:
        raw_explicit = str(explicit_mods_dir).strip()
        if raw_explicit:
            base_hints.append(
                ("explicit_mods_dir", _resolve_install_base_path(raw_explicit, vortex_root, game_id))
            )

    state_install_paths = _state_install_path_texts(state, game_id)
    for index, raw_path in enumerate(state_install_paths, start=1):
        base_hints.append(
            (f"state.settings.mods.installPath[{index}]", _resolve_install_base_path(raw_path, vortex_root, game_id))
        )

    if game_id.strip():
        base_hints.append(("vortex_root/<game>/mods", (vortex_root / game_id / "mods").resolve()))
        base_hints.append(("vortex_root/<game>", (vortex_root / game_id).resolve()))

    attempted_candidates: list[tuple[str, Path]] = []
    seen_candidates: set[str] = set()
    for source, base in base_hints:
        for candidate in _candidate_mods_dirs(base, game_id):
            key = candidate.as_posix().lower()
            if key in seen_candidates:
                continue
            seen_candidates.add(key)
            attempted_candidates.append((source, candidate))
            if _is_usable_mods_dir_candidate(candidate):
                return candidate

    if not state_install_paths:
        if explicit_mods_dir is not None:
            attempted = "; ".join(
                f"{source} -> {candidate}" for source, candidate in attempted_candidates[:8]
            ) or "(none)"
            raise FileNotFoundError(
                "Could not resolve Vortex mods installPath from state.settings.mods.installPath, "
                "and the provided staging/mods path hint was not usable. "
                f"Tried: {attempted}"
            )
        raise FileNotFoundError(
            "Could not resolve Vortex mods installPath from state.settings.mods.installPath."
        )

    attempted = "; ".join(
        f"{source} -> {candidate}" for source, candidate in attempted_candidates[:8]
    ) or "(none)"
    raise FileNotFoundError(
        "Resolved Vortex mods directory does not exist or is not usable. "
        f"gameId='{game_id}'. Tried: {attempted}"
    )


def _collect_enabled_mods(
    state: dict[str, Any],
    profile_id: str,
    profile_payload: dict[str, Any],
    game_id: str,
    mods_dir: Path,
) -> tuple[dict[str, _EnabledVortexMod], list[ParseIssue]]:
    issues: list[ParseIssue] = []
    persistent = _as_dict(state.get("persistent"))
    all_mods = _as_dict(_as_dict(persistent.get("mods")).get(game_id))
    mod_state = _as_dict(profile_payload.get("modState"))

    enabled_mods: dict[str, _EnabledVortexMod] = {}
    for mod_id, raw_state in mod_state.items():
        state_payload = _as_dict(raw_state)
        if state_payload.get("enabled") is not True:
            continue

        mod_payload = _as_dict(all_mods.get(mod_id))
        if not mod_payload:
            issues.append(
                ParseIssue(
                    severity="warning",
                    source_mod="__vortex__",
                    source_file=profile_id,
                    message=f"Enabled mod '{mod_id}' is missing from persistent.mods.{game_id}; skipped.",
                )
            )
            continue

        installation_path = str(mod_payload.get("installationPath", "")).strip()
        if not installation_path:
            installation_path = str(mod_payload.get("id", "")).strip() or mod_id

        attributes = _as_dict(mod_payload.get("attributes"))
        enabled_time = _coerce_int(state_payload.get("enabledTime"))
        install_time_epoch = _parse_iso_to_epoch_ms(str(attributes.get("installTime", "")).strip())
        display_name = (
            str(attributes.get("customFileName", "")).strip()
            or str(attributes.get("logicalFileName", "")).strip()
            or str(attributes.get("modName", "")).strip()
            or installation_path
            or mod_id
        )
        aliases = tuple(
            value
            for value in {
                installation_path,
                str(mod_payload.get("id", "")).strip(),
                str(attributes.get("customFileName", "")).strip(),
                str(attributes.get("logicalFileName", "")).strip(),
                str(attributes.get("modName", "")).strip(),
                display_name,
            }
            if value
        )

        raw_rules = mod_payload.get("rules")
        rules = [rule for rule in raw_rules if isinstance(rule, dict)] if isinstance(raw_rules, list) else []

        raw_file_overrides = mod_payload.get("fileOverrides")
        file_overrides = list(raw_file_overrides) if isinstance(raw_file_overrides, list) else []

        enabled_mods[mod_id] = _EnabledVortexMod(
            mod_id=mod_id,
            installation_path=installation_path,
            display_name=display_name,
            aliases=aliases,
            enabled_time=enabled_time,
            install_time_epoch=install_time_epoch,
            rules=rules,
            file_overrides=file_overrides,
            path=mods_dir / installation_path,
        )

    per_file_override_mods = [mod.mod_id for mod in enabled_mods.values() if mod.file_overrides]
    if per_file_override_mods:
        issues.append(
            ParseIssue(
                severity="warning",
                source_mod="__vortex__",
                source_file=profile_id,
                message=(
                    "Per-file overrides detected. Exported order reflects general mod-level Vortex conflict rules only; "
                    "exact winner may differ for specific files."
                ),
            )
        )
    return enabled_mods, issues


def _order_enabled_mods(enabled_mods: dict[str, _EnabledVortexMod]) -> tuple[list[str], list[ParseIssue]]:
    if not enabled_mods:
        return [], []

    alias_index = _build_alias_index(enabled_mods)
    edges = {mod_id: set() for mod_id in enabled_mods}
    indegree = {mod_id: 0 for mod_id in enabled_mods}
    issues: list[ParseIssue] = []

    for source_id, source_mod in enabled_mods.items():
        for rule in source_mod.rules:
            rule_type = str(rule.get("type", "")).strip().lower()
            if rule_type not in {"before", "after"}:
                continue
            reference = _as_dict(rule.get("reference"))
            if not reference:
                continue

            target_id, ambiguity_warning = _resolve_reference_mod_id(reference, enabled_mods, alias_index)
            if ambiguity_warning:
                issues.append(
                    ParseIssue(
                        severity="warning",
                        source_mod="__vortex__",
                        source_file=source_mod.installation_path,
                        message=ambiguity_warning,
                    )
                )
            if target_id is None or target_id == source_id:
                continue

            if rule_type == "before":
                edge_from, edge_to = source_id, target_id
            else:
                edge_from, edge_to = target_id, source_id

            if edge_to in edges[edge_from]:
                continue
            edges[edge_from].add(edge_to)
            indegree[edge_to] += 1

    ordered_mod_ids, cycle_messages = _topological_sort(enabled_mods, edges, indegree)
    for cycle_message in cycle_messages:
        issues.append(
            ParseIssue(
                severity="warning",
                source_mod="__vortex__",
                source_file=VORTEX_EXPORT_FILENAME,
                message=cycle_message,
            )
        )
    return ordered_mod_ids, issues


def _build_alias_index(enabled_mods: dict[str, _EnabledVortexMod]) -> dict[str, list[str]]:
    alias_index: dict[str, set[str]] = {}
    for mod in enabled_mods.values():
        alias_values = {mod.mod_id, *mod.aliases}
        for alias in alias_values:
            key = _normalize_key(alias)
            if not key:
                continue
            alias_index.setdefault(key, set()).add(mod.mod_id)

    return {
        key: sorted(values, key=lambda mod_id: _mod_tie_break_key(enabled_mods[mod_id]))
        for key, values in alias_index.items()
    }


def _resolve_reference_mod_id(
    reference: dict[str, Any],
    enabled_mods: dict[str, _EnabledVortexMod],
    alias_index: dict[str, list[str]],
) -> tuple[str | None, str | None]:
    direct_keys = ("id", "idHint")
    for key in direct_keys:
        raw = reference.get(key)
        if isinstance(raw, str) and raw in enabled_mods:
            return raw, None

    candidates = [
        reference.get("id"),
        reference.get("idHint"),
        reference.get("fileExpression"),
        reference.get("logicalFileName"),
    ]
    normalized_candidates = []
    for candidate in candidates:
        if not isinstance(candidate, str):
            continue
        normalized = _normalize_key(candidate)
        if normalized:
            normalized_candidates.append((candidate, normalized))

    for raw_value, normalized_value in normalized_candidates:
        matched = alias_index.get(normalized_value, [])
        if not matched:
            continue
        if len(matched) == 1:
            return matched[0], None
        chosen = matched[0]
        warning = (
            f"Ambiguous Vortex rule reference '{raw_value}' matched {len(matched)} enabled mods; "
            f"used deterministic fallback '{enabled_mods[chosen].installation_path}'."
        )
        return chosen, warning
    return None, None


def _topological_sort(
    enabled_mods: dict[str, _EnabledVortexMod],
    edges: dict[str, set[str]],
    indegree: dict[str, int],
) -> tuple[list[str], list[str]]:
    heap: list[tuple[tuple[Any, ...], str]] = []
    for mod_id, degree in indegree.items():
        if degree == 0:
            heappush(heap, (_mod_tie_break_key(enabled_mods[mod_id]), mod_id))

    ordered: list[str] = []
    remaining = set(enabled_mods.keys())
    cycle_messages: list[str] = []

    while remaining:
        progressed = False
        while heap:
            _, mod_id = heappop(heap)
            if mod_id not in remaining:
                continue
            if indegree[mod_id] != 0:
                continue

            progressed = True
            remaining.remove(mod_id)
            ordered.append(mod_id)

            for target_id in sorted(edges[mod_id]):
                indegree[target_id] -= 1
                if indegree[target_id] == 0:
                    heappush(heap, (_mod_tie_break_key(enabled_mods[target_id]), target_id))

        if not remaining:
            break
        if progressed:
            continue

        cycle_path = _find_cycle_path(remaining, edges)
        if cycle_path:
            readable = " -> ".join(enabled_mods[mod_id].installation_path for mod_id in cycle_path)
            cycle_messages.append(
                "Cycle detected in Vortex before/after rules: "
                f"{readable}. "
                "Applied deterministic fallback to continue ordering."
            )
        else:
            cycle_messages.append(
                "Cycle detected in Vortex before/after rules. Applied deterministic fallback to continue ordering."
            )

        forced_mod_id = min(remaining, key=lambda mod_id: _mod_tie_break_key(enabled_mods[mod_id]))
        indegree[forced_mod_id] = 0
        heappush(heap, (_mod_tie_break_key(enabled_mods[forced_mod_id]), forced_mod_id))

    return ordered, cycle_messages


def _find_cycle_path(remaining: set[str], edges: dict[str, set[str]]) -> list[str] | None:
    seen_global: set[str] = set()
    for start in sorted(remaining):
        if start in seen_global:
            continue

        stack: list[tuple[str, list[str], int]] = [(start, sorted(node for node in edges[start] if node in remaining), 0)]
        path: list[str] = [start]
        path_index: dict[str, int] = {start: 0}
        seen_global.add(start)

        while stack:
            node, neighbors, offset = stack[-1]
            if offset >= len(neighbors):
                stack.pop()
                removed = path.pop()
                path_index.pop(removed, None)
                continue

            next_node = neighbors[offset]
            stack[-1] = (node, neighbors, offset + 1)

            if next_node in path_index:
                start_index = path_index[next_node]
                return [*path[start_index:], next_node]
            if next_node in seen_global:
                continue

            seen_global.add(next_node)
            path_index[next_node] = len(path)
            path.append(next_node)
            next_neighbors = sorted(neighbor for neighbor in edges[next_node] if neighbor in remaining)
            stack.append((next_node, next_neighbors, 0))
    return None


def _mod_tie_break_key(mod: _EnabledVortexMod) -> tuple[Any, ...]:
    enabled_time_rank = -(mod.enabled_time if mod.enabled_time is not None else -1)
    install_time_rank = -(mod.install_time_epoch if mod.install_time_epoch is not None else -1)
    return (
        0 if mod.enabled_time is not None else 1,
        enabled_time_rank,
        _normalize_key(mod.installation_path),
        0 if mod.install_time_epoch is not None else 1,
        install_time_rank,
        _normalize_key(mod.display_name),
        _normalize_key(mod.mod_id),
    )


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(text)
        except ValueError:
            return None
    return None


def _parse_iso_to_epoch_ms(value: str) -> int | None:
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def _normalize_key(value: str) -> str:
    return value.strip().lower()


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
