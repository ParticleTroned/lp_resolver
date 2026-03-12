# LP Conflict Resolver

Standalone desktop and CLI tool for Mod Organizer 2 (MO2) that scans Light Placer (LP) and Particle Lights (PL) data, highlights likely lighting conflicts, and exports a patch mod.

## License

This project is licensed under the GNU General Public License v3.0 only (GPL-3.0-only).

- Full license text: [LICENSE](LICENSE)
- SPDX identifier: `GPL-3.0-only`

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GPL-3.0 license for details.

## What It Does

- Scans LP JSON entries and PL targets.
- Detects conflict types such as:
- `duplicate_exact`
- `duplicate_divergent`
- `duplicate_condition_exclusive`
- `duplicate_refinement_disjoint`
- `lp_vs_pl_overlap`
- Lets you apply decisions per conflict and export an MO2 patch mod that uses normal last-wins override behavior.

## Why It Is Useful

- Reduces manual LP/PL conflict triage in large MO2 modlists.
- Makes conflict decisions repeatable by saving/loading resolver decisions.
- Exports deterministic override JSONs that fit normal MO2 last-wins behavior.
- Supports both GUI and CLI workflows for end users and maintainers.

## Getting Started

1. Install Python 3.10+.
2. Create and activate a virtual environment.
3. Install dependencies from `requirements.txt`.
4. Run one scan in GUI mode (`python -m lp_resolver.gui`) or CLI mode (`python -m lp_resolver ...`).
5. Review conflicts, apply decisions, and export a patch mod.

See the detailed install/build/run steps in the sections below.

## Requirements

- Windows (for packaged EXE workflow)
- Python 3.10+
- Mod Organizer 2 setup with `mods/` and `profiles/`

## Install From Source

From repo root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If PowerShell blocks activation:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
```

## Run

GUI:

```powershell
python -m lp_resolver.gui
```

or:

```powershell
python -m lp_resolver --gui
```

CLI example:

```powershell
python -m lp_resolver `
  --mo2-root "C:\Path\To\MO2" `
  --profile-path "C:\Path\To\MO2\profiles\YourProfile" `
  --output-dir "dist\lp_resolver" `
  --pl-source nif `
  --verbose
```

Version:

```powershell
python -m lp_resolver.cli --version
```

## Build Windows App

Build one-folder app:

```powershell
powershell -ExecutionPolicy Bypass -File build_windows.ps1 -Clean
```

Fallback full Qt bundle (larger output):

```powershell
powershell -ExecutionPolicy Bypass -File build_windows.ps1 -Clean -FullQt
```

Output path:

- `dist\lp_resolver_app\LPConflictResolver\LPConflictResolver.exe`

Optional installer:

1. Open `LPResolver.iss` in Inno Setup.
2. Set `SourceDir` to your built app folder.
3. Compile the installer.

## User Manual

For workflow details and UI screenshots, see [USER_MANUAL.md](USER_MANUAL.md).

## Getting Help

- Open an issue in this repository for bugs, questions, or feature requests.
- Contact via GitHub: <https://github.com/ParticleTroned>
- When reporting issues, include your command/UI steps, logs, and environment details (Python version, Windows version, MO2 setup).

## Maintainers And Contributors

- Maintainer: `ParticleTroned`
- Contributions are welcome through GitHub pull requests and issues.

## GPL-3.0 Distribution Checklist

If you distribute this software (source or binaries), follow GPL-3.0 obligations. At minimum:

1. Keep copyright and license notices.
2. Include the GPL-3.0 license text (`LICENSE`) with distributions.
3. If you modify the program, keep prominent notices that you changed it and the date.
4. If you distribute binaries/object code, also provide the complete corresponding source code under GPL-3.0.
5. Do not add legal or technical restrictions that conflict with GPL-3.0 rights.
6. When required by GPL-3.0 for your distribution model, provide any needed installation information for recipients.

Practical recommendation: publish source, build scripts, and release artifacts together in the same GitHub release/repository so recipients can rebuild what you shipped.

This README is informational and not legal advice. For edge cases, review GPL-3.0 directly and consult legal counsel if needed.
