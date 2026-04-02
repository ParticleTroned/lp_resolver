# SPDX-FileCopyrightText: 2026 ParticleTroned
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

_DLL_DIR_HANDLES: list[object] = []


def _is_frozen_build() -> bool:
    return bool(getattr(sys, "frozen", False))


def _show_startup_error_dialog(message: str) -> None:
    if not _is_frozen_build() or sys.platform != "win32":
        return
    try:
        ctypes.windll.user32.MessageBoxW(None, message, "LPConflictResolver Startup Error", 0x10)
    except Exception:
        return


def _prepare_source_import_path() -> None:
    if __package__ is None or __package__ == "":
        repo_root = Path(__file__).resolve().parents[1]
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))


def _verify_frozen_qt_runtime_layout() -> None:
    if not _is_frozen_build():
        return
    exe_dir = Path(sys.executable).resolve().parent
    required_paths = [
        exe_dir / "_internal" / "PySide6" / "QtCore.pyd",
        exe_dir / "_internal" / "PySide6" / "Qt6Core.dll",
        exe_dir / "_internal" / "PySide6" / "plugins" / "platforms" / "qwindows.dll",
    ]
    missing = [str(path) for path in required_paths if not path.exists()]
    if not missing:
        return
    raise RuntimeError(
        "Packaged runtime is incomplete (missing Qt files).\n"
        "Run LPConflictResolver.exe from the extracted app folder and keep the _internal directory next to it.\n"
        f"Missing files: {', '.join(missing)}"
    )


def _configure_frozen_dll_search_paths() -> None:
    if not _is_frozen_build():
        return
    if not hasattr(os, "add_dll_directory"):
        return
    exe_dir = Path(sys.executable).resolve().parent
    candidates = [
        exe_dir / "_internal",
        exe_dir / "_internal" / "PySide6",
        exe_dir / "_internal" / "PySide6" / "plugins" / "platforms",
    ]
    for path in candidates:
        if not path.exists() or not path.is_dir():
            continue
        try:
            handle = os.add_dll_directory(str(path))
        except Exception:
            continue
        _DLL_DIR_HANDLES.append(handle)


def _load_gui_main():
    _prepare_source_import_path()
    if __package__ is None or __package__ == "":
        from lp_resolver.gui import main as gui_main
    else:
        from .gui import main as gui_main
    return gui_main


def main() -> int:
    try:
        _verify_frozen_qt_runtime_layout()
        _configure_frozen_dll_search_paths()
        gui_main = _load_gui_main()
    except Exception as exc:  # noqa: BLE001
        message = str(exc).strip() or f"{type(exc).__name__}"
        detail = f"{type(exc).__name__}: {message}"
        _show_startup_error_dialog(detail)
        print(detail, file=sys.stderr)
        return 1
    return gui_main()


if __name__ == "__main__":
    raise SystemExit(main())
