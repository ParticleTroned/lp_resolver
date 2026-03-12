# SPDX-FileCopyrightText: 2026 ParticleTroned
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

from pathlib import Path

from .models import CandidateFile, ModEntry

DEFAULT_LP_GLOBS = [
    "**/LightPlacer/**/*.json",
    "**/lightplacer/**/*.json",
    "**/*light*placer*.json",
]

DEFAULT_PL_GLOBS = [
    "**/ParticleLights/**/*.json",
    "**/particlelights/**/*.json",
    "**/*particle*light*.json",
]


def _discover_for_category(mods: list[ModEntry], patterns: list[str], category: str) -> list[CandidateFile]:
    discovered: list[CandidateFile] = []
    for mod in mods:
        if not mod.path.exists() or not mod.path.is_dir():
            continue
        # MO2/Windows paths are effectively case-insensitive for our use case; collapse path-case duplicates.
        seen_rel_paths: set[str] = set()
        for pattern in patterns:
            for match in mod.path.glob(pattern):
                if not match.is_file() or match.suffix.lower() != ".json":
                    continue
                relative_path = match.relative_to(mod.path).as_posix()
                dedupe_key = relative_path.lower()
                if dedupe_key in seen_rel_paths:
                    continue
                seen_rel_paths.add(dedupe_key)
                discovered.append(
                    CandidateFile(
                        category=category,
                        mod_name=mod.name,
                        mod_priority=mod.priority,
                        relative_path=relative_path,
                        file_path=Path(match),
                    )
                )

    discovered.sort(key=lambda item: (item.mod_priority, item.mod_name.lower(), item.relative_path.lower()))
    return discovered


def discover_candidates(
    mods: list[ModEntry],
    lp_patterns: list[str] | None = None,
    pl_patterns: list[str] | None = None,
) -> tuple[list[CandidateFile], list[CandidateFile]]:
    lp = _discover_for_category(mods, lp_patterns or DEFAULT_LP_GLOBS, category="lp")
    pl = _discover_for_category(mods, pl_patterns or DEFAULT_PL_GLOBS, category="pl")
    return lp, pl


def filter_overridden_candidates(candidates: list[CandidateFile]) -> tuple[list[CandidateFile], int]:
    """
    Keep only the effective winner per virtual path (MO2 semantics):
    highest mod_priority wins for the same relative path (case-insensitive).
    """
    winners: dict[str, CandidateFile] = {}
    for candidate in candidates:
        key = candidate.relative_path.lower()
        current = winners.get(key)
        if current is None:
            winners[key] = candidate
            continue
        if candidate.mod_priority > current.mod_priority:
            winners[key] = candidate
        elif candidate.mod_priority == current.mod_priority:
            # Stable deterministic tie-breaker
            if (candidate.mod_name.lower(), candidate.file_path.as_posix().lower()) > (
                current.mod_name.lower(),
                current.file_path.as_posix().lower(),
            ):
                winners[key] = candidate

    filtered = sorted(
        winners.values(),
        key=lambda item: (item.mod_priority, item.mod_name.lower(), item.relative_path.lower()),
    )
    overridden_count = max(0, len(candidates) - len(filtered))
    return filtered, overridden_count
