import json
import tempfile
import unittest
from pathlib import Path

from lp_resolver.decisions import make_decision
from lp_resolver.engine import ScanConfig, ScanResult
from lp_resolver.models import Conflict, LightPlacerEntry
from lp_resolver.normalize import canonical_nif, normalized_settings, value_signature
from lp_resolver.patch_writer import LightIntensityPatchConfig, write_light_intensity_patch_mod, write_patch_mod


def _make_entry(
    mod_name: str,
    priority: int,
    source_file: str,
    raw_target: str,
    payload: dict,
    *,
    source_payload_index: int = 0,
) -> LightPlacerEntry:
    canonical = canonical_nif(raw_target)
    settings = normalized_settings(payload)
    return LightPlacerEntry(
        entry_id=value_signature(
            {
                "mod": mod_name,
                "priority": priority,
                "file": source_file,
                "nif": canonical,
                "settings": settings,
            }
        ),
        source_mod=mod_name,
        source_priority=priority,
        source_file=source_file,
        nif_path_raw=raw_target,
        nif_path_canonical=canonical,
        settings=settings,
        full_payload=dict(payload),
        source_payload_index=source_payload_index,
    )


def _make_report_payload(root: Path, mods_dir: Path, *, lp_entries: int, conflict_count: int) -> dict:
    return {
        "generated_at_utc": "2026-06-29T00:00:00+00:00",
        "mo2_root": str(root),
        "profile_path": str(root / "profile"),
        "mods_dir": str(mods_dir),
        "summary": {
            "enabled_mod_count": 2,
            "lp_candidate_files": 2,
            "pl_candidate_files": 0,
            "lp_overridden_files": 0,
            "pl_overridden_files": 0,
            "lp_entries": lp_entries,
            "pl_targets": 0,
            "conflict_count": conflict_count,
        },
        "issues": [],
        "conflicts": [],
    }


def _make_scan_result(
    root: Path,
    mods_dir: Path,
    lp_entries: list[LightPlacerEntry],
    *,
    conflicts: list[Conflict],
) -> ScanResult:
    return ScanResult(
        config=ScanConfig(mo2_root=root, profile_path=root / "profile", mods_dir=mods_dir),
        mo2_root=root,
        profile_path=root / "profile",
        mods_dir=mods_dir,
        mod_order_source="mo2",
        synthetic_modlist_path=None,
        vortex_state_path=None,
        enabled_mod_count=2,
        lp_candidate_files=2,
        pl_candidate_files=0,
        lp_overridden_files=0,
        pl_overridden_files=0,
        pl_json_candidate_files=0,
        pl_nif_candidate_files=0,
        pl_nif_matched_mods=0,
        lp_entries=lp_entries,
        pl_targets=[],
        issues=[],
        detected_conflicts=conflicts,
        conflicts=conflicts,
        report_payload=_make_report_payload(root, mods_dir, lp_entries=len(lp_entries), conflict_count=len(conflicts)),
    )


class PatchWriterTests(unittest.TestCase):
    def test_write_patch_mod_prunes_multi_model_payload_without_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            mods_dir = root / "mods"
            mods_dir.mkdir()

            true_file = "LightPlacer/True Light/True Light - Embers ISL.json"
            lux_file = "LightPlacer/Lux CS Patch/Lux CS - Embers ISL.json"
            true_payload = {
                "models": [
                    "clutter\\woodfires\\campfire01burning.nif",
                    "clutter\\woodfires\\campfire01landburning.nif",
                ],
                "lights": [{"points": [[0, 0, 30]], "data": {"fade": 3.5}}],
            }
            lux_payload = {
                "models": ["clutter\\woodfires\\campfire01burning.nif"],
                "lights": [{"points": [[0, 0, 42]], "data": {"fade": 9.0}}],
            }

            true_campfire = _make_entry("True Light", 1787, true_file, true_payload["models"][0], true_payload)
            true_land = _make_entry("True Light", 1787, true_file, true_payload["models"][1], true_payload)
            lux_campfire = _make_entry("Lux CS Patch", 1788, lux_file, lux_payload["models"][0], lux_payload)
            conflict = Conflict(
                nif_path_canonical=true_campfire.nif_path_canonical,
                conflict_types=["duplicate_divergent"],
                lp_entries=[true_campfire, lux_campfire],
            )
            scan_result = _make_scan_result(root, mods_dir, [true_campfire, true_land, lux_campfire], conflicts=[conflict])

            result = write_patch_mod(
                scan_result,
                {true_campfire.nif_path_canonical: make_decision(action="keep_highest_priority")},
                patch_mod_name="Patch",
            )

            output_path = result.patch_mod_dir / true_file
            payload = json.loads(output_path.read_text(encoding="utf-8"))

            self.assertEqual([path.relative_to(result.patch_mod_dir).as_posix() for path in result.override_files], [true_file])
            self.assertEqual(result.selected_entry_count, 1)
            self.assertEqual(len(payload), 1)
            self.assertEqual(payload[0]["models"], ["clutter\\woodfires\\campfire01landburning.nif"])
            self.assertFalse((result.patch_mod_dir / lux_file).exists())

    def test_write_patch_mod_preserves_unrelated_nested_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            mods_dir = root / "mods"
            mods_dir.mkdir()

            true_file = "LightPlacer/True Light/True Light - Embers ISL.json"
            lux_file = "LightPlacer/Lux CS Patch/Lux CS - Embers ISL.json"
            losing_target = "clutter\\woodfires\\campfire01burning.nif"
            winning_sibling = "clutter\\woodfires\\campfire01landburning.nif"
            true_payload = {
                "models": [losing_target, winning_sibling],
                "profile": {"lastMesh": losing_target},
                "lights": [{"points": [[0, 0, 30]], "data": {"fade": 3.5}}],
            }
            lux_payload = {
                "models": [losing_target],
                "lights": [{"points": [[0, 0, 42]], "data": {"fade": 9.0}}],
            }

            true_campfire = _make_entry("True Light", 1787, true_file, losing_target, true_payload)
            true_land = _make_entry("True Light", 1787, true_file, winning_sibling, true_payload)
            lux_campfire = _make_entry("Lux CS Patch", 1788, lux_file, losing_target, lux_payload)
            conflict = Conflict(
                nif_path_canonical=true_campfire.nif_path_canonical,
                conflict_types=["duplicate_divergent"],
                lp_entries=[true_campfire, lux_campfire],
            )
            scan_result = _make_scan_result(root, mods_dir, [true_campfire, true_land, lux_campfire], conflicts=[conflict])

            result = write_patch_mod(
                scan_result,
                {true_campfire.nif_path_canonical: make_decision(action="keep_highest_priority")},
                patch_mod_name="Patch",
            )

            payload = json.loads((result.patch_mod_dir / true_file).read_text(encoding="utf-8"))

            self.assertEqual(payload[0]["models"], [winning_sibling])
            self.assertEqual(payload[0]["profile"]["lastMesh"], losing_target)

    def test_write_light_intensity_patch_reports_logical_entry_counts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            mods_dir = root / "mods"
            mods_dir.mkdir()

            source_file = "LightPlacer/True Light/True Light - Embers ISL.json"
            payload = {
                "models": ["a.nif", "b.nif"],
                "lights": [{"points": [[0, 0, 30]], "data": {"intensity": 1.5}}],
            }
            entries = [
                _make_entry("True Light", 1, source_file, raw_target, payload)
                for raw_target in payload["models"]
            ]
            scan_result = _make_scan_result(root, mods_dir, entries, conflicts=[])

            result = write_light_intensity_patch_mod(
                scan_result,
                {},
                LightIntensityPatchConfig(scale_factor=2.0),
                patch_mod_name="ScalePatch",
            )

            output_payload = json.loads((result.patch_mod_dir / source_file).read_text(encoding="utf-8"))

            self.assertEqual(result.exported_entry_count, 2)
            self.assertEqual(result.eligible_entry_count, 2)
            self.assertEqual(result.scaled_entry_count, 2)
            self.assertEqual(len(output_payload), 1)
            self.assertEqual(output_payload[0]["models"], ["a.nif", "b.nif"])
            self.assertEqual(output_payload[0]["lights"][0]["data"]["intensity"], 3.0)


if __name__ == "__main__":
    unittest.main()
