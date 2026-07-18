import json
import os
import tempfile
import unittest
from pathlib import Path

from lp_resolver.vortex import export_vortex_enabled_mods


def _state_payload(mods_dir: Path, profile_id: str, mods: list[tuple[str, str]]) -> dict:
    return {
        "persistent": {
            "profiles": {
                profile_id: {
                    "gameId": "skyrimse",
                    "name": "Test profile",
                    "modState": {
                        mod_id: {"enabled": True, "enabledTime": index + 1}
                        for index, (mod_id, _installation_path) in enumerate(mods)
                    },
                }
            },
            "mods": {
                "skyrimse": {
                    mod_id: {
                        "id": mod_id,
                        "installationPath": installation_path,
                        "attributes": {"modName": installation_path},
                    }
                    for mod_id, installation_path in mods
                }
            },
        },
        "settings": {"mods": {"installPath": {"skyrimse": str(mods_dir)}}},
    }


def _write_state(path: Path, payload: dict, *, mtime_ns: int | None = None) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")
    if mtime_ns is not None:
        os.utime(path, ns=(mtime_ns, mtime_ns))


class VortexStateTests(unittest.TestCase):
    def _layout(self, root: Path) -> tuple[Path, Path, Path]:
        profile_id = "profile-1"
        profile_path = root / "skyrimse" / "profiles" / profile_id
        mods_dir = root / "skyrimse" / "mods"
        backups_dir = root / "temp" / "state_backups_full"
        profile_path.mkdir(parents=True)
        mods_dir.mkdir(parents=True)
        backups_dir.mkdir(parents=True)
        (profile_path / "plugins.txt").write_text("", encoding="utf-8")
        return profile_path, mods_dir, backups_dir

    def test_uses_freshest_state_backup_instead_of_always_using_startup(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            profile_path, mods_dir, backups_dir = self._layout(root)
            (mods_dir / "Old Mod").mkdir()
            (mods_dir / "Current Mod").mkdir()

            startup_path = backups_dir / "startup.json"
            hourly_path = backups_dir / "hourly.json"
            _write_state(
                startup_path,
                _state_payload(mods_dir, profile_path.name, [("old", "Old Mod")]),
                mtime_ns=1_000_000_000,
            )
            _write_state(
                hourly_path,
                _state_payload(mods_dir, profile_path.name, [("current", "Current Mod")]),
                mtime_ns=2_000_000_000,
            )

            result = export_vortex_enabled_mods(profile_path, write_export_file=False)

            self.assertEqual(result.state_path, hourly_path.resolve())
            self.assertEqual([entry.name for entry in result.entries], ["Current Mod"])

    def test_falls_back_when_newer_json_is_not_a_usable_vortex_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            profile_path, mods_dir, backups_dir = self._layout(root)
            (mods_dir / "Current Mod").mkdir()

            startup_path = backups_dir / "startup.json"
            hourly_path = backups_dir / "hourly.json"
            _write_state(
                startup_path,
                _state_payload(mods_dir, profile_path.name, [("current", "Current Mod")]),
                mtime_ns=1_000_000_000,
            )
            _write_state(
                hourly_path,
                {"persistent": {"profiles": {profile_path.name: {}}}},
                mtime_ns=2_000_000_000,
            )

            result = export_vortex_enabled_mods(profile_path, write_export_file=False)

            self.assertEqual(result.state_path, startup_path.resolve())
            self.assertEqual([entry.name for entry in result.entries], ["Current Mod"])

    def test_falls_back_when_newer_state_does_not_contain_selected_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            profile_path, mods_dir, backups_dir = self._layout(root)
            (mods_dir / "Current Mod").mkdir()
            (mods_dir / "Other Mod").mkdir()

            startup_path = backups_dir / "startup.json"
            hourly_path = backups_dir / "hourly.json"
            _write_state(
                startup_path,
                _state_payload(mods_dir, profile_path.name, [("current", "Current Mod")]),
                mtime_ns=1_000_000_000,
            )
            _write_state(
                hourly_path,
                _state_payload(mods_dir, "other-profile", [("other", "Other Mod")]),
                mtime_ns=2_000_000_000,
            )

            result = export_vortex_enabled_mods(profile_path, write_export_file=False)

            self.assertEqual(result.state_path, startup_path.resolve())
            self.assertEqual([entry.name for entry in result.entries], ["Current Mod"])

    def test_skips_stale_enabled_mod_without_staging_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            profile_path, mods_dir, backups_dir = self._layout(root)
            (mods_dir / "Live Mod").mkdir()

            startup_path = backups_dir / "startup.json"
            _write_state(
                startup_path,
                _state_payload(
                    mods_dir,
                    profile_path.name,
                    [("live", "Live Mod"), ("removed", "Removed Mod")],
                ),
            )

            result = export_vortex_enabled_mods(profile_path, write_export_file=False)

            self.assertEqual([entry.name for entry in result.entries], ["Live Mod"])
            self.assertTrue(
                any(
                    issue.source_mod == "__vortex__"
                    and "Removed Mod" in issue.message
                    and "stale Vortex state" in issue.message
                    for issue in result.issues
                )
            )


if __name__ == "__main__":
    unittest.main()
