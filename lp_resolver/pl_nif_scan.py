# SPDX-FileCopyrightText: 2026 ParticleTroned
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path
import re

from .models import ModEntry, ParticleLightTarget
from .normalize import canonical_nif

DEFAULT_PL_NIF_MOD_PATTERNS = [
    "*enb*particle*light*",
    "*particle*light*enb*",
    "enb-particlelights*",
]

DEFAULT_PL_NIF_GLOBS = [
    "meshes/**/*.nif",
]

_DDS_PATH_RE = re.compile(r"([A-Za-z0-9_\-./\\ ]+\.dds)", re.IGNORECASE)


def _matches_any_pattern(value: str, patterns: list[str]) -> bool:
    lowered_value = value.lower()
    for pattern in patterns:
        if fnmatch(lowered_value, pattern.lower()):
            return True
    return False


def _extract_texture_stems_from_nif(nif_file: str) -> set[str]:
    try:
        raw = Path(nif_file).read_bytes()
    except OSError:
        return set()

    # Scan binary as latin-1 to preserve byte positions while allowing regex extraction.
    text = raw.decode("latin-1", errors="ignore")
    stems: set[str] = set()
    for match in _DDS_PATH_RE.finditer(text):
        dds_path = match.group(1).replace("\\", "/").strip().lower()
        if not dds_path.endswith(".dds"):
            continue
        stem = dds_path.rsplit("/", 1)[-1][:-4]
        if stem:
            stems.add(stem)
    return stems


def _collect_effective_particle_config_stems(mods: list[ModEntry]) -> set[str]:
    """
    Mirror MO2 winning-file behavior for ParticleLights config INIs.
    Returns effective config stems (ini file name without extension).
    """
    stems: set[str] = set()
    seen_rel: set[str] = set()

    for mod in reversed(mods):
        if not mod.path.exists() or not mod.path.is_dir():
            continue
        candidates = list(mod.path.glob("ParticleLights/*.ini"))
        candidates.extend(mod.path.glob("Data/ParticleLights/*.ini"))
        for ini in candidates:
            if not ini.is_file():
                continue
            try:
                rel = ini.relative_to(mod.path).as_posix().lower()
            except ValueError:
                rel = ini.name.lower()
            if rel in seen_rel:
                continue
            seen_rel.add(rel)
            stem = ini.stem.strip().lower()
            if stem:
                stems.add(stem)
    return stems


def discover_particle_light_nif_targets(
    mods: list[ModEntry],
    mod_name_patterns: list[str] | None = None,
    nif_globs: list[str] | None = None,
) -> tuple[list[ParticleLightTarget], int, int]:
    patterns = mod_name_patterns or DEFAULT_PL_NIF_MOD_PATTERNS
    meshes_globs = nif_globs or DEFAULT_PL_NIF_GLOBS
    valid_config_stems = _collect_effective_particle_config_stems(mods)

    targets: list[ParticleLightTarget] = []
    scanned_nif_files = 0
    matched_mods = 0

    for mod in mods:
        if not _matches_any_pattern(mod.name, patterns):
            continue
        if not mod.path.exists() or not mod.path.is_dir():
            continue

        matched_mods += 1
        seen_rel_paths: set[str] = set()
        for mesh_glob in meshes_globs:
            for nif_file in mod.path.glob(mesh_glob):
                if not nif_file.is_file() or nif_file.suffix.lower() != ".nif":
                    continue

                relative_path = nif_file.relative_to(mod.path).as_posix()
                if relative_path in seen_rel_paths:
                    continue
                seen_rel_paths.add(relative_path)
                scanned_nif_files += 1

                canonical = canonical_nif(relative_path)
                if canonical is None:
                    continue

                texture_stems = _extract_texture_stems_from_nif(str(nif_file))
                if valid_config_stems:
                    # Mirror CS 1.4.11 PL runtime intent:
                    # only treat NIFs as PL candidates when their effect texture stem
                    # has a corresponding ParticleLights config.
                    if not (texture_stems & valid_config_stems):
                        continue
                    valid_reason = "texture_config_match"
                else:
                    # If no configs are discoverable, preserve old behavior to avoid empty scans.
                    valid_reason = "no_config_filter"

                targets.append(
                    ParticleLightTarget(
                        source_mod=mod.name,
                        source_priority=mod.priority,
                        source_file=relative_path,
                        nif_path_raw=relative_path,
                        nif_path_canonical=canonical,
                        payload={
                            "kind": "enb_particle_lights_nif",
                            "nif_file": relative_path,
                            "texture_stems": sorted(texture_stems),
                            "valid_reason": valid_reason,
                        },
                    )
                )

    targets.sort(key=lambda item: (item.source_priority, item.source_mod.lower(), item.nif_path_canonical))
    return targets, scanned_nif_files, matched_mods
