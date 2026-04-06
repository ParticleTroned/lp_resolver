# SPDX-FileCopyrightText: 2026 ParticleTroned
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import ctypes
import os
import struct
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


def _read_ascii_cstring(blob: bytes, offset: int, max_length: int = 260) -> str:
    if offset < 0 or offset >= len(blob):
        return ""
    end = offset
    hard_limit = min(len(blob), offset + max(1, max_length))
    while end < hard_limit and blob[end] != 0:
        end += 1
    if end <= offset:
        return ""
    try:
        return blob[offset:end].decode("ascii", errors="ignore").strip().lower()
    except Exception:
        return ""


def _pe_imported_dll_names(pe_path: Path) -> set[str]:
    try:
        blob = pe_path.read_bytes()
    except Exception:
        return set()
    if len(blob) < 0x100 or blob[:2] != b"MZ":
        return set()

    try:
        pe_offset = struct.unpack_from("<I", blob, 0x3C)[0]
        if pe_offset + 24 > len(blob) or blob[pe_offset : pe_offset + 4] != b"PE\0\0":
            return set()

        section_count = struct.unpack_from("<H", blob, pe_offset + 6)[0]
        optional_header_size = struct.unpack_from("<H", blob, pe_offset + 20)[0]
        optional_header_offset = pe_offset + 24
        if optional_header_offset + optional_header_size > len(blob):
            return set()

        magic = struct.unpack_from("<H", blob, optional_header_offset)[0]
        if magic == 0x10B:
            data_directory_offset = optional_header_offset + 96
        elif magic == 0x20B:
            data_directory_offset = optional_header_offset + 112
        else:
            return set()
        if data_directory_offset + (8 * 2) > len(blob):
            return set()

        # IMAGE_DIRECTORY_ENTRY_IMPORT (index 1)
        import_rva, import_size = struct.unpack_from("<II", blob, data_directory_offset + 8)
        if import_rva == 0 or import_size == 0:
            return set()

        section_table_offset = optional_header_offset + optional_header_size
        sections: list[tuple[int, int, int, int]] = []
        for index in range(section_count):
            offset = section_table_offset + (index * 40)
            if offset + 40 > len(blob):
                break
            virtual_size, virtual_address, raw_size, raw_ptr = struct.unpack_from("<IIII", blob, offset + 8)
            mapped_size = max(virtual_size, raw_size)
            if raw_ptr > 0 and raw_size > 0 and mapped_size > 0:
                sections.append((virtual_address, mapped_size, raw_ptr, raw_size))

        def rva_to_offset(rva: int) -> int | None:
            for virtual_address, mapped_size, raw_ptr, raw_size in sections:
                if virtual_address <= rva < virtual_address + mapped_size:
                    rel = rva - virtual_address
                    if rel < raw_size:
                        return raw_ptr + rel
                    return None
            return None

        import_table_offset = rva_to_offset(import_rva)
        if import_table_offset is None:
            return set()

        names: set[str] = set()
        descriptor_limit = max(1, min(4096, import_size // 20 + 1))
        for index in range(descriptor_limit):
            descriptor_offset = import_table_offset + (index * 20)
            if descriptor_offset + 20 > len(blob):
                break
            original_first_thunk, time_date_stamp, forwarder_chain, name_rva, first_thunk = struct.unpack_from(
                "<IIIII", blob, descriptor_offset
            )
            if (
                original_first_thunk == 0
                and time_date_stamp == 0
                and forwarder_chain == 0
                and name_rva == 0
                and first_thunk == 0
            ):
                break
            name_offset = rva_to_offset(name_rva)
            if name_offset is None:
                continue
            dll_name = _read_ascii_cstring(blob, name_offset)
            if dll_name.endswith(".dll"):
                names.add(dll_name)
        return names
    except Exception:
        return set()


def _required_qtcore_icu_dll_names(qt6core_dll: Path) -> list[str]:
    imported_dlls = _pe_imported_dll_names(qt6core_dll)
    return sorted(name for name in imported_dlls if name.startswith(("icuuc", "icuin", "icudt")))


def _dedupe_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        key = str(value)
        if key in seen:
            continue
        seen.add(key)
        unique.append(key)
    return unique


def _verify_frozen_qt_runtime_layout() -> None:
    if not _is_frozen_build():
        return
    exe_dir = Path(sys.executable).resolve().parent
    qt6core_dll = exe_dir / "_internal" / "PySide6" / "Qt6Core.dll"
    required_paths = [
        exe_dir / "_internal" / "python3.dll",
        exe_dir / "_internal" / "PySide6" / "QtCore.pyd",
        qt6core_dll,
        exe_dir / "_internal" / "PySide6" / "pyside6.abi3.dll",
        exe_dir / "_internal" / "shiboken6" / "Shiboken.pyd",
        exe_dir / "_internal" / "PySide6" / "plugins" / "platforms" / "qwindows.dll",
    ]
    missing = [str(path) for path in required_paths if not path.exists()]
    has_embedded_python = any(
        dll.name.lower().startswith("python3") and dll.suffix.lower() == ".dll"
        for dll in (exe_dir / "_internal").glob("python3*.dll")
    )
    if not has_embedded_python:
        missing.append(str(exe_dir / "_internal" / "python3*.dll"))

    for dll_name in _required_qtcore_icu_dll_names(qt6core_dll):
        if (qt6core_dll.parent / dll_name).exists():
            continue
        if (exe_dir / "_internal" / dll_name).exists():
            continue
        missing.append(str(qt6core_dll.parent / dll_name))

    missing = _dedupe_keep_order(missing)

    if not missing:
        return
    raise RuntimeError(
        "Packaged runtime is incomplete (missing bundled runtime files).\n"
        "Run LPConflictResolver.exe from the extracted app folder and keep the _internal directory next to it.\n"
        "If files disappear after install/extract, check antivirus/quarantine rules.\n"
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
