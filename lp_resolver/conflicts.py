# SPDX-FileCopyrightText: 2026 ParticleTroned
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from math import dist
import re
from typing import Any

from .anchors import estimate_entry_radius_units, extract_lp_anchor_nodes, extract_lp_anchor_points, iter_lights_lists as _iter_lights_lists
from .models import Conflict, LightPlacerEntry, ParticleLightTarget
from .normalize import value_signature

_POINT_OVERLAP_EPSILON = 14.0
_WORLDSPACE_COND_RE = re.compile(
    r"getinworldspace\s+([a-z0-9_]+)\s+none\s*==\s*([01])",
    re.IGNORECASE,
)


@dataclass
class _PlacementSignature:
    nodes: set[str]
    points: list[tuple[float, float, float]]
    radius_units: float | None


def _extract_conditions(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    conditions: list[str] = []
    for item in value:
        if isinstance(item, str):
            text = item.strip()
            if text:
                conditions.append(text)
    return conditions


def _extract_placement_signature(settings: dict[str, Any]) -> _PlacementSignature:
    return _PlacementSignature(
        nodes=extract_lp_anchor_nodes(settings),
        points=extract_lp_anchor_points(settings),
        radius_units=estimate_entry_radius_units(settings),
    )


def _extract_worldspace_condition_tokens(settings: dict[str, Any]) -> set[tuple[str, bool]]:
    tokens: set[tuple[str, bool]] = set()
    for lights in _iter_lights_lists(settings):
        for light in lights:
            if not isinstance(light, dict):
                continue
            data = light.get("data")
            if not isinstance(data, dict):
                continue
            for condition in _extract_conditions(data.get("conditions")):
                for match in _WORLDSPACE_COND_RE.finditer(condition):
                    worldspace = match.group(1).lower()
                    equals_one = match.group(2) == "1"
                    tokens.add((worldspace, equals_one))
    return tokens


def _min_point_distance(
    lhs: list[tuple[float, float, float]],
    rhs: list[tuple[float, float, float]],
) -> float | None:
    if not lhs or not rhs:
        return None
    return min(dist(left, right) for left in lhs for right in rhs)


def _entries_overlap(lhs: LightPlacerEntry, rhs: LightPlacerEntry) -> bool:
    lhs_sig = _extract_placement_signature(lhs.settings)
    rhs_sig = _extract_placement_signature(rhs.settings)

    # If both define concrete points/offsets, treat near points as stacking.
    if lhs_sig.points and rhs_sig.points:
        min_distance = _min_point_distance(lhs_sig.points, rhs_sig.points)
        if min_distance is not None and min_distance <= _POINT_OVERLAP_EPSILON:
            return True

        # Radius-aware rule: catch overlaps where points are farther apart than
        # fixed epsilon but effective light radii still intersect.
        left_radius = lhs_sig.radius_units
        right_radius = rhs_sig.radius_units
        if (
            min_distance is not None
            and left_radius is not None
            and right_radius is not None
            and min_distance <= (left_radius + right_radius)
        ):
            return True

    lhs_has_points = bool(lhs_sig.points)
    rhs_has_points = bool(rhs_sig.points)

    # Fallback for node-only definitions (no explicit points): same node implies stacking risk.
    if not lhs_has_points and not rhs_has_points:
        return bool(lhs_sig.nodes & rhs_sig.nodes)

    # Hybrid fallback when one side lacks points but both have node anchors.
    if lhs_sig.nodes and rhs_sig.nodes and (lhs_sig.nodes & rhs_sig.nodes):
        return True

    return False


def _entries_condition_exclusive(lhs: LightPlacerEntry, rhs: LightPlacerEntry) -> bool:
    lhs_tokens = _extract_worldspace_condition_tokens(lhs.settings)
    rhs_tokens = _extract_worldspace_condition_tokens(rhs.settings)
    if not lhs_tokens or not rhs_tokens:
        return False

    rhs_by_worldspace: dict[str, set[bool]] = defaultdict(set)
    for worldspace, state in rhs_tokens:
        rhs_by_worldspace[worldspace].add(state)

    for worldspace, lhs_state in lhs_tokens:
        rhs_states = rhs_by_worldspace.get(worldspace)
        if not rhs_states:
            continue
        if (not lhs_state) in rhs_states and lhs_state not in rhs_states:
            return True
    return False


def _divergent_overlap_summary(entries: list[LightPlacerEntry]) -> tuple[bool, bool]:
    if len(entries) < 2:
        return (False, False)

    # Compare only across different setting signatures.
    by_signature: dict[str, list[LightPlacerEntry]] = defaultdict(list)
    for entry in entries:
        by_signature[value_signature(entry.settings)].append(entry)

    signatures = list(by_signature.keys())
    if len(signatures) < 2:
        return (False, False)

    has_nonexclusive_overlap = False
    has_exclusive_overlap = False

    for i in range(len(signatures)):
        for j in range(i + 1, len(signatures)):
            for lhs in by_signature[signatures[i]]:
                for rhs in by_signature[signatures[j]]:
                    if _entries_overlap(lhs, rhs):
                        if _entries_condition_exclusive(lhs, rhs):
                            has_exclusive_overlap = True
                        else:
                            has_nonexclusive_overlap = True
    return (has_nonexclusive_overlap, has_exclusive_overlap)


def detect_conflicts(lp_entries: list[LightPlacerEntry], pl_targets: list[ParticleLightTarget]) -> list[Conflict]:
    lp_by_nif: dict[str, list[LightPlacerEntry]] = defaultdict(list)
    pl_by_nif: dict[str, list[ParticleLightTarget]] = defaultdict(list)

    for entry in lp_entries:
        lp_by_nif[entry.nif_path_canonical].append(entry)
    for target in pl_targets:
        pl_by_nif[target.nif_path_canonical].append(target)

    conflicts: list[Conflict] = []
    all_nifs = sorted(set(lp_by_nif.keys()) | set(pl_by_nif.keys()))
    for nif in all_nifs:
        lp_candidates = sorted(
            lp_by_nif.get(nif, []),
            key=lambda item: (item.source_priority, item.source_mod.lower(), item.source_file.lower(), item.entry_id),
        )
        pl_candidates = sorted(
            pl_by_nif.get(nif, []),
            key=lambda item: (item.source_priority, item.source_mod.lower(), item.source_file.lower()),
        )

        conflict_types: list[str] = []
        if len(lp_candidates) > 1:
            sigs = {value_signature(entry.settings) for entry in lp_candidates}
            if len(sigs) == 1:
                conflict_types.append("duplicate_exact")
            else:
                has_nonexclusive_overlap, has_exclusive_overlap = _divergent_overlap_summary(lp_candidates)
                if has_nonexclusive_overlap:
                    conflict_types.append("duplicate_divergent")
                elif has_exclusive_overlap:
                    conflict_types.append("duplicate_condition_exclusive")
                else:
                    # Divergent LP entries exist, but placement anchors are disjoint:
                    # treat these as refinements/variants, not stacking by default.
                    conflict_types.append("duplicate_refinement_disjoint")
        if lp_candidates and pl_candidates:
            conflict_types.append("lp_vs_pl_overlap")

        if conflict_types:
            conflicts.append(
                Conflict(
                    nif_path_canonical=nif,
                    conflict_types=conflict_types,
                    lp_entries=lp_candidates,
                    pl_targets=pl_candidates,
                )
            )
    return conflicts


def filter_conflicts(
    conflicts: list[Conflict],
    *,
    only_overlap: bool = False,
    ignore_duplicate_exact: bool = False,
    cross_mod_lp_duplicates_only: bool = False,
    include_refinements: bool = False,
    include_condition_exclusive: bool = False,
) -> list[Conflict]:
    filtered: list[Conflict] = []
    duplicate_types = {"duplicate_exact", "duplicate_divergent", "duplicate_condition_exclusive"}
    for conflict in conflicts:
        conflict_types = [
            conflict_type
            for conflict_type in conflict.conflict_types
            if not (ignore_duplicate_exact and conflict_type == "duplicate_exact")
        ]
        if not include_condition_exclusive:
            conflict_types = [
                conflict_type
                for conflict_type in conflict_types
                if conflict_type != "duplicate_condition_exclusive"
            ]
        if not include_refinements:
            conflict_types = [
                conflict_type
                for conflict_type in conflict_types
                if conflict_type != "duplicate_refinement_disjoint"
            ]

        if cross_mod_lp_duplicates_only:
            source_mods = {entry.source_mod for entry in conflict.lp_entries}
            has_cross_mod_duplicates = len(source_mods) > 1
            if not has_cross_mod_duplicates:
                conflict_types = [conflict_type for conflict_type in conflict_types if conflict_type not in duplicate_types]

        if only_overlap and "lp_vs_pl_overlap" not in conflict_types:
            continue
        if not conflict_types:
            continue

        filtered.append(
            Conflict(
                nif_path_canonical=conflict.nif_path_canonical,
                conflict_types=conflict_types,
                lp_entries=conflict.lp_entries,
                pl_targets=conflict.pl_targets,
            )
        )
    return filtered
