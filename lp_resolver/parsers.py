# SPDX-FileCopyrightText: 2026 ParticleTroned
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from .models import CandidateFile, LightPlacerEntry, ParseIssue, ParticleLightTarget
from .normalize import canonical_form_id, canonical_nif, normalized_settings, value_signature

_NIF_KEY_HINTS = ("nif", "mesh", "model", "path", "file")
_FORM_ID_KEY_HINTS = ("formid", "formids", "form_id", "form_ids")
_EFFECT_ID_KEY_HINTS = (
    "visualeffects",
    "visual_effects",
    "visualeffect",
    "visual_effect",
    "effectshader",
    "effectshaders",
    "effect_shader",
    "effect_shaders",
    "magiceffect",
    "magiceffects",
    "magic_effect",
    "magic_effects",
    "artobject",
    "artobjects",
    "art_object",
    "art_objects",
    "mgef",
)
_LP_FIELD_HINTS = ("radius", "intensity", "brightness", "color", "falloff", "fade", "flicker", "shadow")
_LP_STRUCT_HINTS = ("lights", "points", "data", "flags", "light")
_PL_FIELD_HINTS = ("particle", "billboard", "effectshader", "effect_shader", "vertexcolor", "vertex_color")


def _normalized_rel_path(relative_path: str) -> str:
    return relative_path.replace("\\", "/").lower()


def _path_suggests_light_placer(relative_path: str) -> bool:
    rel_path = _normalized_rel_path(relative_path)
    return "lightplacer/" in rel_path or "light placer" in rel_path or "light_placer" in rel_path


def _path_suggests_particle_lights(relative_path: str) -> bool:
    rel_path = _normalized_rel_path(relative_path)
    return (
        "particlelights/" in rel_path
        or "particle_lights/" in rel_path
        or ("particle" in rel_path and "light" in rel_path)
        or "communityshaders/lights/" in rel_path
    )


def _load_json(file_path: Path) -> Any:
    with file_path.open("r", encoding="utf-8", errors="ignore") as handle:
        return json.load(handle)


def _iter_dict_nodes(value: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _iter_dict_nodes(child)
        return
    if isinstance(value, list):
        for child in value:
            yield from _iter_dict_nodes(child)


def _extract_direct_nif_candidates(node: Mapping[str, Any]) -> set[str]:
    candidates: set[str] = set()
    for key, value in node.items():
        key_l = str(key).lower()
        if isinstance(value, str):
            value_l = value.lower()
            if ".nif" in value_l:
                candidates.add(value)
            elif any(hint in key_l for hint in _NIF_KEY_HINTS) and value.endswith(".nif"):
                candidates.add(value)
            continue

        if isinstance(value, list) and any(hint in key_l for hint in _NIF_KEY_HINTS):
            for item in value:
                if isinstance(item, str) and ".nif" in item.lower():
                    candidates.add(item)
            continue

        if isinstance(value, dict) and any(hint in key_l for hint in _NIF_KEY_HINTS):
            for nested_value in value.values():
                if isinstance(nested_value, str) and ".nif" in nested_value.lower():
                    candidates.add(nested_value)
    return candidates


def _extract_direct_form_id_candidates(node: Mapping[str, Any]) -> set[str]:
    candidates: set[str] = set()
    for key, value in node.items():
        key_l = str(key).lower()
        if not any(hint in key_l for hint in _FORM_ID_KEY_HINTS):
            continue

        if isinstance(value, str):
            candidates.add(value)
            continue

        if isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    candidates.add(item)
            continue

        if isinstance(value, dict):
            for nested_value in value.values():
                if isinstance(nested_value, str):
                    candidates.add(nested_value)
    return candidates


def _extract_direct_effect_id_candidates(node: Mapping[str, Any]) -> set[str]:
    candidates: set[str] = set()
    for key, value in node.items():
        key_l = str(key).lower()
        if not any(hint in key_l for hint in _EFFECT_ID_KEY_HINTS):
            continue
        if isinstance(value, str):
            text = value.strip()
            if text:
                candidates.add(text)
            continue
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    text = item.strip()
                    if text:
                        candidates.add(text)
            continue
        if isinstance(value, dict):
            for nested_value in value.values():
                if isinstance(nested_value, str):
                    text = nested_value.strip()
                    if text:
                        candidates.add(text)
    return candidates


def _canonical_effect_id(effect_id: str | None) -> str | None:
    if not effect_id:
        return None
    text = effect_id.strip()
    if not text:
        return None
    if any(ch in text for ch in ("\\", "/")):
        return None
    lowered = text.lower()
    if lowered.endswith(".nif"):
        return None
    return f"effectid:{lowered}"


def _fallback_effect_id_from_form_id_candidate(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    # Keep strict FormID validation for canonical `0x...~plugin` values.
    if "~" in text:
        return None
    # Only promote clearly symbolic IDs (EditorID-like strings), not numeric typos.
    if not any(ch.isalpha() for ch in text):
        return None
    return _canonical_effect_id(text)


def _looks_like_light_payload(node: Mapping[str, Any]) -> bool:
    for key in node.keys():
        key_l = str(key).lower()
        if any(hint in key_l for hint in _LP_FIELD_HINTS):
            return True
    return False


def _has_any_key_hint(node: Mapping[str, Any], hints: tuple[str, ...]) -> bool:
    for key in node.keys():
        key_l = str(key).lower()
        if any(hint in key_l for hint in hints):
            return True
    return False


def _node_looks_like_light_placer(node: Mapping[str, Any]) -> bool:
    if _has_any_key_hint(node, _LP_STRUCT_HINTS):
        return True
    return _looks_like_light_payload(node)


def _node_looks_like_particle_lights(node: Mapping[str, Any]) -> bool:
    return _has_any_key_hint(node, _PL_FIELD_HINTS)


def _root_has_light_placer_hints(root: Any) -> bool:
    for node in _iter_dict_nodes(root):
        if _node_looks_like_light_placer(node):
            return True
    return False


def _root_has_particle_hints(root: Any) -> bool:
    for node in _iter_dict_nodes(root):
        if _node_looks_like_particle_lights(node):
            return True
    return False


class LightPlacerAdapter:
    name = "light_placer"

    def can_parse(self, candidate: CandidateFile) -> bool:
        return candidate.file_path.suffix.lower() == ".json"

    def extract_entries(self, candidate: CandidateFile) -> tuple[list[LightPlacerEntry], list[ParseIssue]]:
        entries: list[LightPlacerEntry] = []
        issues: list[ParseIssue] = []
        if not self.can_parse(candidate):
            return entries, issues

        likely_lp_path = _path_suggests_light_placer(candidate.relative_path)
        try:
            root = _load_json(candidate.file_path)
        except Exception as exc:  # noqa: BLE001
            if likely_lp_path:
                issues.append(
                    ParseIssue(
                        severity="warn",
                        message=f"JSON parse failed: {exc}",
                        source_file=candidate.relative_path,
                        source_mod=candidate.mod_name,
                    )
                )
            return entries, issues

        root_has_lp_hints = _root_has_light_placer_hints(root)
        if not likely_lp_path and not root_has_lp_hints:
            return entries, issues

        seen: set[tuple[str, str]] = set()
        formid_editorid_fallbacks: set[str] = set()
        for node in _iter_dict_nodes(root):
            nif_candidates = _extract_direct_nif_candidates(node)
            form_id_candidates = _extract_direct_form_id_candidates(node)
            effect_id_candidates = _extract_direct_effect_id_candidates(node)
            if not nif_candidates and not form_id_candidates and not effect_id_candidates:
                continue
            if not _node_looks_like_light_placer(node) and not likely_lp_path:
                continue

            settings = normalized_settings(dict(node))
            for raw_path in sorted(nif_candidates):
                canonical = canonical_nif(raw_path)
                if canonical is None:
                    issues.append(
                        ParseIssue(
                            severity="warn",
                            message=f"Invalid NIF path '{raw_path}'",
                            source_file=candidate.relative_path,
                            source_mod=candidate.mod_name,
                        )
                    )
                    continue

                sig = value_signature(settings)
                dedupe_key = (canonical, sig)
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)

                entry_id = value_signature(
                    {
                        "mod": candidate.mod_name,
                        "priority": candidate.mod_priority,
                        "file": candidate.relative_path,
                        "nif": canonical,
                        "settings": settings,
                    }
                )
                entries.append(
                    LightPlacerEntry(
                        entry_id=entry_id,
                        source_mod=candidate.mod_name,
                        source_priority=candidate.mod_priority,
                        source_file=candidate.relative_path,
                        nif_path_raw=raw_path,
                        nif_path_canonical=canonical,
                        settings=settings,
                        full_payload=dict(node),
                    )
                )

            for raw_form_id in sorted(form_id_candidates):
                canonical = canonical_form_id(raw_form_id)
                if canonical is None:
                    fallback = _fallback_effect_id_from_form_id_candidate(raw_form_id)
                    if fallback is None:
                        issues.append(
                            ParseIssue(
                                severity="warn",
                                message=f"Invalid FormID target '{raw_form_id}'",
                                source_file=candidate.relative_path,
                                source_mod=candidate.mod_name,
                            )
                        )
                        continue
                    canonical = fallback
                    formid_editorid_fallbacks.add(raw_form_id.strip())

                sig = value_signature(settings)
                dedupe_key = (canonical, sig)
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)

                entry_id = value_signature(
                    {
                        "mod": candidate.mod_name,
                        "priority": candidate.mod_priority,
                        "file": candidate.relative_path,
                        "nif": canonical,
                        "settings": settings,
                    }
                )
                entries.append(
                    LightPlacerEntry(
                        entry_id=entry_id,
                        source_mod=candidate.mod_name,
                        source_priority=candidate.mod_priority,
                        source_file=candidate.relative_path,
                        nif_path_raw=raw_form_id,
                        nif_path_canonical=canonical,
                        settings=settings,
                        full_payload=dict(node),
                    )
                )

            for raw_effect_id in sorted(effect_id_candidates):
                canonical = _canonical_effect_id(raw_effect_id)
                if canonical is None:
                    continue

                sig = value_signature(settings)
                dedupe_key = (canonical, sig)
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)

                entry_id = value_signature(
                    {
                        "mod": candidate.mod_name,
                        "priority": candidate.mod_priority,
                        "file": candidate.relative_path,
                        "nif": canonical,
                        "settings": settings,
                    }
                )
                entries.append(
                    LightPlacerEntry(
                        entry_id=entry_id,
                        source_mod=candidate.mod_name,
                        source_priority=candidate.mod_priority,
                        source_file=candidate.relative_path,
                        nif_path_raw=raw_effect_id,
                        nif_path_canonical=canonical,
                        settings=settings,
                        full_payload=dict(node),
                    )
                )

        if formid_editorid_fallbacks:
            preview_values = sorted(value for value in formid_editorid_fallbacks if value)
            preview_text = ", ".join(preview_values[:4])
            if len(preview_values) > 4:
                preview_text += f", +{len(preview_values) - 4} more"
            issues.append(
                ParseIssue(
                    severity="info",
                    message=(
                        "Detected symbolic values under formID/formIDs and treated them as effect-ID targets "
                        f"(compatibility fallback): {preview_text}"
                    ),
                    source_file=candidate.relative_path,
                    source_mod=candidate.mod_name,
                )
            )

        if likely_lp_path and not entries:
            if root_has_lp_hints:
                message = (
                    "No extractable LP targets found. Supported LP target key families are "
                    "NIF path fields (nif/mesh/model/path/file), FormID fields (formID/formIDs), "
                    "and effect-ID fields (visualEffects/effectShaders/magicEffects/artObjects/mgef)."
                )
            else:
                message = "No Light Placer-like keys found in JSON payload (missing lights/points/data-like structure)."
            issues.append(
                ParseIssue(
                    severity="info",
                    message=message,
                    source_file=candidate.relative_path,
                    source_mod=candidate.mod_name,
                )
            )
        return entries, issues

    def build_output(self, entries: list[LightPlacerEntry]) -> list[dict[str, Any]]:
        return [entry.full_payload for entry in entries]


class ParticleLightsAdapter:
    name = "particle_lights"

    def can_parse(self, candidate: CandidateFile) -> bool:
        return candidate.file_path.suffix.lower() == ".json"

    def extract_entries(self, candidate: CandidateFile) -> tuple[list[ParticleLightTarget], list[ParseIssue]]:
        targets: list[ParticleLightTarget] = []
        issues: list[ParseIssue] = []
        if not self.can_parse(candidate):
            return targets, issues

        likely_pl_path = _path_suggests_particle_lights(candidate.relative_path)
        path_is_lightplacer = _path_suggests_light_placer(candidate.relative_path)
        try:
            root = _load_json(candidate.file_path)
        except Exception as exc:  # noqa: BLE001
            if likely_pl_path:
                issues.append(
                    ParseIssue(
                        severity="warn",
                        message=f"JSON parse failed: {exc}",
                        source_file=candidate.relative_path,
                        source_mod=candidate.mod_name,
                    )
                )
            return targets, issues

        root_has_pl_hints = _root_has_particle_hints(root)
        if path_is_lightplacer and not root_has_pl_hints:
            # Avoid treating LightPlacer JSON as Particle Lights based on generic nif fields.
            return targets, issues
        if not likely_pl_path and not root_has_pl_hints:
            return targets, issues

        seen: set[tuple[str, str]] = set()
        for node in _iter_dict_nodes(root):
            if not _node_looks_like_particle_lights(node):
                continue
            nif_candidates = _extract_direct_nif_candidates(node)
            if not nif_candidates:
                continue
            payload_signature = value_signature(node)
            for raw_path in sorted(nif_candidates):
                canonical = canonical_nif(raw_path)
                if canonical is None:
                    issues.append(
                        ParseIssue(
                            severity="warn",
                            message=f"Invalid NIF path '{raw_path}'",
                            source_file=candidate.relative_path,
                            source_mod=candidate.mod_name,
                        )
                    )
                    continue

                dedupe_key = (canonical, payload_signature)
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)

                targets.append(
                    ParticleLightTarget(
                        source_mod=candidate.mod_name,
                        source_priority=candidate.mod_priority,
                        source_file=candidate.relative_path,
                        nif_path_raw=raw_path,
                        nif_path_canonical=canonical,
                        payload=dict(node),
                    )
                )
        return targets, issues

    def build_output(self, targets: list[ParticleLightTarget]) -> list[dict[str, Any]]:
        return [target.payload for target in targets]


def parse_light_placer_files(candidates: list[CandidateFile]) -> tuple[list[LightPlacerEntry], list[ParseIssue]]:
    adapter = LightPlacerAdapter()
    entries: list[LightPlacerEntry] = []
    issues: list[ParseIssue] = []
    for candidate in candidates:
        parsed_entries, parsed_issues = adapter.extract_entries(candidate)
        entries.extend(parsed_entries)
        issues.extend(parsed_issues)
    return entries, issues


def parse_particle_light_files(candidates: list[CandidateFile]) -> tuple[list[ParticleLightTarget], list[ParseIssue]]:
    adapter = ParticleLightsAdapter()
    targets: list[ParticleLightTarget] = []
    issues: list[ParseIssue] = []
    for candidate in candidates:
        parsed_targets, parsed_issues = adapter.extract_entries(candidate)
        targets.extend(parsed_targets)
        issues.extend(parsed_issues)
    return targets, issues
