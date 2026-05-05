# SPDX-FileCopyrightText: 2026 ParticleTroned
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import configparser
import os
import re
from pathlib import Path

from .models import ModEntry

_MO2_PATH_SECTIONS = ("General", "Settings")


def resolve_profile_path(mo2_root: Path, profile_name: str | None, profile_path: Path | None) -> Path:
    if profile_path is not None:
        resolved = profile_path.expanduser().resolve()
    elif profile_name is not None:
        resolved = (mo2_root / "profiles" / profile_name).resolve()
    else:
        raise ValueError("Either profile_name or profile_path must be provided.")

    if not resolved.exists():
        raise FileNotFoundError(f"Profile path does not exist: {resolved}")
    if not resolved.is_dir():
        raise NotADirectoryError(f"Profile path is not a directory: {resolved}")
    return resolved


def _configured_ini_value(parser: configparser.ConfigParser, option: str) -> str | None:
    for section in _MO2_PATH_SECTIONS:
        if parser.has_option(section, option):
            configured = parser.get(section, option).strip()
            if configured:
                return configured
    return None


def _normalize_configured_path(raw_path: str, mo2_root: Path, base_directory: Path, relative_base: Path) -> Path:
    value = raw_path.strip().strip('"')
    replacements = {
        "BASE_DIR": str(base_directory),
        "MO2_ROOT": str(mo2_root),
    }

    def replace_token(match: re.Match[str]) -> str:
        token = match.group(1).upper()
        return replacements.get(token, match.group(0))

    value = re.sub(r"%([A-Za-z_][A-Za-z0-9_]*)%", replace_token, value)
    value = os.path.expandvars(value)
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = relative_base / candidate
    return candidate.resolve()


def resolve_mods_dir(mo2_root: Path, explicit_mods_dir: Path | None = None) -> Path:
    if explicit_mods_dir is not None:
        resolved = explicit_mods_dir.expanduser().resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"Mods directory does not exist: {resolved}")
        if not resolved.is_dir():
            raise NotADirectoryError(f"Mods directory is not a directory: {resolved}")
        return resolved

    ini_path = mo2_root / "ModOrganizer.ini"
    if ini_path.exists():
        parser = configparser.ConfigParser(interpolation=None)
        parser.read(ini_path, encoding="utf-8")
        base_directory_raw = _configured_ini_value(parser, "base_directory")
        base_directory = (
            _normalize_configured_path(base_directory_raw, mo2_root, mo2_root, mo2_root)
            if base_directory_raw
            else mo2_root
        )
        configured = _configured_ini_value(parser, "mod_directory")
        if configured:
            candidate = _normalize_configured_path(configured, mo2_root, base_directory, base_directory)
            if candidate.exists() and candidate.is_dir():
                return candidate
        base_mods_dir = (base_directory / "mods").resolve()
        if base_directory != mo2_root and base_mods_dir.exists() and base_mods_dir.is_dir():
            return base_mods_dir

    default_mods_dir = (mo2_root / "mods").resolve()
    if not default_mods_dir.exists():
        raise FileNotFoundError(
            f"Could not resolve mods directory; expected at {default_mods_dir} or from ModOrganizer.ini."
        )
    return default_mods_dir


def read_enabled_mods(
    profile_path: Path,
    mods_dir: Path,
) -> list[ModEntry]:
    modlist_path = profile_path / "modlist.txt"
    if not modlist_path.exists():
        raise FileNotFoundError(f"modlist.txt not found: {modlist_path}")

    lines = modlist_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    enabled_names: list[str] = []
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        marker = line[0]
        mod_name = line[1:].strip()
        if marker == "+" and mod_name:
            enabled_names.append(mod_name)

    # MO2 semantics in this resolver: top entries in modlist.txt are highest priority.
    # Internally we keep "larger priority wins" for all downstream tie-break logic.
    entries: list[ModEntry] = []
    enabled_count = len(enabled_names)
    for order_index, mod_name in enumerate(enabled_names):
        priority = enabled_count - order_index - 1
        entries.append(ModEntry(name=mod_name, priority=priority, path=mods_dir / mod_name))
    return entries
