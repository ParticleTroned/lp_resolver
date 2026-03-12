# SPDX-FileCopyrightText: 2026 ParticleTroned
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import math
import struct
import zlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterator

from .mo2 import read_enabled_mods


@dataclass(frozen=True)
class MeshPreviewData:
    mesh_path: Path | None
    points: list[tuple[float, float, float]]
    status: str
    detail: str = ""


@dataclass(frozen=True)
class _BSAEntry:
    archive_path: str
    relative_path_key: str
    offset: int
    size: int
    compressed: bool


class _ByteReader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0

    def remaining(self) -> int:
        return len(self.data) - self.pos

    def read_u8(self) -> int:
        if self.remaining() < 1:
            raise ValueError("Unexpected EOF (u8)")
        value = self.data[self.pos]
        self.pos += 1
        return value

    def read_u16(self) -> int:
        if self.remaining() < 2:
            raise ValueError("Unexpected EOF (u16)")
        value = struct.unpack_from("<H", self.data, self.pos)[0]
        self.pos += 2
        return value

    def read_u32(self) -> int:
        if self.remaining() < 4:
            raise ValueError("Unexpected EOF (u32)")
        value = struct.unpack_from("<I", self.data, self.pos)[0]
        self.pos += 4
        return value

    def read_bytes(self, size: int) -> bytes:
        if size < 0 or self.remaining() < size:
            raise ValueError("Unexpected EOF (bytes)")
        start = self.pos
        self.pos += size
        return self.data[start : start + size]


def _is_valid_point(point: tuple[float, float, float], max_abs: float = 500000.0) -> bool:
    x, y, z = point
    if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(z)):
        return False
    return abs(x) <= max_abs and abs(y) <= max_abs and abs(z) <= max_abs


def _score_points(points: list[tuple[float, float, float]]) -> tuple[float, float]:
    if not points:
        return (0.0, 0.0)
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    zs = [p[2] for p in points]
    dx = max(xs) - min(xs)
    dy = max(ys) - min(ys)
    dz = max(zs) - min(zs)
    diag = math.sqrt(dx * dx + dy * dy + dz * dz)
    return (float(len(points)), diag)


def _sample_points(points: list[tuple[float, float, float]], max_points: int = 3500) -> list[tuple[float, float, float]]:
    if len(points) <= max_points:
        return points
    step = max(1, len(points) // max_points)
    sampled = points[::step]
    if len(sampled) > max_points:
        sampled = sampled[:max_points]
    return sampled


def _find_float3_runs(blob: bytes) -> list[list[tuple[float, float, float]]]:
    if len(blob) < 128:
        return []

    count_candidates: set[int] = set()
    head_limit = min(len(blob) - 4, 224)
    for off in range(0, max(0, head_limit), 2):
        n16 = struct.unpack_from("<H", blob, off)[0]
        if 16 <= n16 <= 200000:
            count_candidates.add(n16)
    for off in range(0, max(0, head_limit), 4):
        n32 = struct.unpack_from("<I", blob, off)[0]
        if 16 <= n32 <= 200000:
            count_candidates.add(n32)

    if not count_candidates:
        return []

    candidates: list[list[tuple[float, float, float]]] = []
    starts = [2, 4, 6, 8, 12, 16, 20, 24, 28, 32]
    strides = [12, 16, 20, 24, 28, 32, 36, 40, 48]
    counts = sorted(count_candidates)
    if len(counts) > 96:
        counts = counts[:48] + counts[-48:]

    for n in counts:
        for start in starts:
            for stride in strides:
                end = start + (n - 1) * stride + 12
                if end > len(blob):
                    continue
                sample_n = min(80, n)
                valid = 0
                sample_points: list[tuple[float, float, float]] = []
                for i in range(sample_n):
                    base = start + i * stride
                    point = struct.unpack_from("<fff", blob, base)
                    if _is_valid_point(point):
                        valid += 1
                        sample_points.append(point)
                if valid < int(sample_n * 0.92):
                    continue
                _, diag = _score_points(sample_points)
                if diag < 0.01:
                    continue

                points: list[tuple[float, float, float]] = []
                for i in range(n):
                    base = start + i * stride
                    point = struct.unpack_from("<fff", blob, base)
                    if _is_valid_point(point):
                        points.append(point)
                if len(points) >= 16:
                    candidates.append(_sample_points(points))

    return candidates


def _parse_nif_blocks(data: bytes) -> list[tuple[str, int, int]] | None:
    if b"File Format" not in data[:128]:
        return None

    newline = data.find(b"\n")
    if newline < 0:
        return None
    r = _ByteReader(data)
    r.pos = newline + 1

    try:
        _version = r.read_u32()
        endian = r.read_u8()
        if endian not in {0, 1}:
            return None
        _user_version = r.read_u32()
        num_blocks = r.read_u32()
        if num_blocks <= 0 or num_blocks > 250000:
            return None

        # Bethesda NIFs (Skyrim family) carry user version 2 and optional export-info strings.
        # We parse this layout first, then fall back to the simpler legacy branch.
        _user_version_2 = r.read_u32()

        def _read_block_type_section(with_export_info: bool) -> tuple[list[str], list[int], list[int]] | None:
            pos0 = r.pos
            try:
                if with_export_info:
                    # Export info: 3 short strings with u8 lengths.
                    for _ in range(3):
                        length = r.read_u8()
                        if length > 250:
                            return None
                        r.read_bytes(length)

                num_block_types = r.read_u16()
                if num_block_types <= 0 or num_block_types > 8192:
                    return None

                block_type_names: list[str] = []
                for _ in range(num_block_types):
                    name_len = r.read_u32()
                    if name_len > 4096:
                        return None
                    raw_name = r.read_bytes(name_len)
                    block_type_names.append(raw_name.decode("utf-8", errors="ignore"))

                block_type_indices = [r.read_u16() for _ in range(num_blocks)]
                block_sizes = [r.read_u32() for _ in range(num_blocks)]
                return (block_type_names, block_type_indices, block_sizes)
            except (ValueError, struct.error):
                r.pos = pos0
                return None

        parsed = _read_block_type_section(with_export_info=True)
        if parsed is None:
            parsed = _read_block_type_section(with_export_info=False)
        if parsed is None:
            return None
        block_type_names, block_type_indices, block_sizes = parsed

        num_strings = r.read_u32()
        _max_len = r.read_u32()
        if num_strings > 2_000_000:
            return None
        for _ in range(num_strings):
            s_len = r.read_u32()
            if s_len > 1_000_000:
                return None
            r.read_bytes(s_len)

        num_groups = r.read_u32()
        if num_groups > 100000:
            return None
        for _ in range(num_groups):
            group_size = r.read_u32()
            if group_size > num_blocks:
                return None
            r.read_bytes(group_size * 4)

        blocks: list[tuple[str, int, int]] = []
        cursor = r.pos
        for i in range(num_blocks):
            size = block_sizes[i]
            if cursor + size > len(data):
                return None
            type_idx = block_type_indices[i]
            if type_idx < len(block_type_names):
                type_name = block_type_names[type_idx]
            else:
                type_name = f"type_{type_idx}"
            blocks.append((type_name, cursor, size))
            cursor += size
        return blocks
    except (ValueError, struct.error):
        return None


def _extract_mesh_points_from_nif_bytes(data: bytes) -> tuple[list[tuple[float, float, float]], str]:
    blocks = _parse_nif_blocks(data)
    if not blocks:
        fallback_points = _extract_points_global_heuristic(data)
        if fallback_points:
            return (fallback_points, "global_heuristic")
        return ([], "header_parse_failed")

    preferred = [
        "BSTriShape",
        "BSSubIndexTriShape",
        "BSDynamicTriShape",
        "NiTriShapeData",
        "NiTriStripsData",
        "NiMesh",
    ]
    preferred_l = [name.lower() for name in preferred]

    candidate_blocks = []
    for type_name, start, size in blocks:
        lowered = type_name.lower()
        if any(token in lowered for token in preferred_l):
            candidate_blocks.append((type_name, start, size))
    if not candidate_blocks:
        # Fall back to all blocks if no known mesh block types were identified.
        candidate_blocks = blocks

    all_candidates: list[tuple[tuple[float, float], list[tuple[float, float, float]]]] = []
    for type_name, start, size in candidate_blocks:
        blob = data[start : start + size]
        runs = _find_float3_runs(blob)
        for points in runs:
            score = _score_points(points)
            # Require non-trivial spatial spread for visualization quality.
            if score[1] < 0.25:
                continue
            all_candidates.append((score, points))

    if not all_candidates:
        fallback_points = _extract_points_global_heuristic(data)
        if fallback_points:
            return (fallback_points, "global_heuristic")
        return ([], "no_vertex_runs")

    all_candidates.sort(key=lambda item: (item[0][0], item[0][1]), reverse=True)
    merged: list[tuple[float, float, float]] = []
    for _, points in all_candidates[:3]:
        merged.extend(points)
    if not merged:
        return ([], "no_points")

    return (_sample_points(merged), "heuristic")


def _rotation_matrix_quality(values: tuple[float, ...]) -> float | None:
    if len(values) != 9:
        return None
    if not all(math.isfinite(v) for v in values):
        return None

    rows = [
        (values[0], values[1], values[2]),
        (values[3], values[4], values[5]),
        (values[6], values[7], values[8]),
    ]
    norms: list[float] = []
    for row in rows:
        norm = math.sqrt(row[0] * row[0] + row[1] * row[1] + row[2] * row[2])
        if norm < 0.45 or norm > 2.5:
            return None
        norms.append(norm)

    def dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
        return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]

    d01 = abs(dot(rows[0], rows[1]))
    d02 = abs(dot(rows[0], rows[2]))
    d12 = abs(dot(rows[1], rows[2]))
    if max(d01, d02, d12) > 0.9:
        return None

    norm_score = sum(1.0 / (1.0 + abs(n - 1.0)) for n in norms) / 3.0
    ortho_penalty = min(1.0, (d01 + d02 + d12) / 2.4)
    return norm_score + (1.0 - ortho_penalty)


def _extract_block_bounding_radius(blob: bytes) -> tuple[float, float] | None:
    """
    Heuristic extraction for NiAVObject-style transform + bounding sphere layout:
    translation(3f) + rotation(9f) + scale(f) + collisionRef(i32) + center(3f) + radius(f)
    """
    if len(blob) < 72:
        return None

    best: tuple[float, float] | None = None  # (score, radius)
    limit = len(blob) - 72
    for off in range(0, limit + 1, 4):
        try:
            tx, ty, tz = struct.unpack_from("<fff", blob, off)
            rotation = struct.unpack_from("<fffffffff", blob, off + 12)
            scale = struct.unpack_from("<f", blob, off + 48)[0]
            collision_ref = struct.unpack_from("<i", blob, off + 52)[0]
            cx, cy, cz, radius = struct.unpack_from("<ffff", blob, off + 56)
        except struct.error:
            continue

        if not (
            math.isfinite(tx)
            and math.isfinite(ty)
            and math.isfinite(tz)
            and math.isfinite(cx)
            and math.isfinite(cy)
            and math.isfinite(cz)
            and math.isfinite(scale)
            and math.isfinite(radius)
        ):
            continue

        if radius <= 0.001 or radius > 500000.0:
            continue
        if scale <= 0.001 or scale > 100.0:
            continue
        if any(abs(v) > 500000.0 for v in (tx, ty, tz, cx, cy, cz)):
            continue
        if collision_ref < -1 or collision_ref > 1000000:
            continue

        rot_quality = _rotation_matrix_quality(rotation)
        if rot_quality is None:
            continue

        # Prefer plausible transforms and stable references.
        score = rot_quality
        if collision_ref == -1:
            score += 0.20
        score += 0.35 / (1.0 + abs(scale - 1.0))
        center_bias = abs(cx) + abs(cy) + abs(cz)
        score += 0.25 / (1.0 + center_bias * 0.05)

        if best is None or score > best[0]:
            # Use raw bounding-sphere radius (no scale multiplication) to match NIF field semantics.
            best = (score, float(radius))

    if best is None:
        return None
    return best


def _extract_nif_bounding_radius_from_bytes(data: bytes) -> tuple[float | None, str]:
    blocks = _parse_nif_blocks(data)
    candidate_blobs: list[bytes] = []
    if blocks:
        preferred_tokens = (
            "bstrishape",
            "bssubindextrishape",
            "bsdynamictrishape",
            "nitrishape",
            "nimesh",
            "nitristrips",
        )
        for type_name, start, size in blocks:
            lowered = type_name.lower()
            if any(token in lowered for token in preferred_tokens):
                candidate_blobs.append(data[start : start + size])
        if not candidate_blobs:
            # Fallback: inspect first N blocks when type tags are unexpected.
            for _type_name, start, size in blocks[:64]:
                candidate_blobs.append(data[start : start + size])
    else:
        # Header parse failed: use first part of full blob as a conservative fallback scan.
        candidate_blobs = [data[: min(len(data), 2_000_000)]]

    best: tuple[float, float] | None = None  # (score, radius)
    for blob in candidate_blobs:
        candidate = _extract_block_bounding_radius(blob)
        if candidate is None:
            continue
        if best is None or candidate[0] > best[0]:
            best = candidate

    if best is None:
        return (None, "no_bounding_sphere_radius")
    return (best[1], "nif_bounding_sphere")


def _extract_points_global_heuristic(data: bytes) -> list[tuple[float, float, float]]:
    """
    Fallback for NIF variants where block-table parsing fails.
    Scans the full file for plausible float3 streams (vertex-like runs).
    """
    size = len(data)
    if size < 1024:
        return []

    strides = (12, 16, 20, 24, 28, 32, 36, 40)
    seed_count = 20
    min_run = 48
    max_run = 7000
    candidates: list[tuple[tuple[float, float], list[tuple[float, float, float]]]] = []

    for stride in strides:
        start = 0
        while start + 12 <= size:
            # 4-byte alignment keeps scan fast and matches most float layouts.
            if start % 4 != 0:
                start += 1
                continue

            seed_points: list[tuple[float, float, float]] = []
            valid_seed = True
            for i in range(seed_count):
                off = start + i * stride
                if off + 12 > size:
                    valid_seed = False
                    break
                point = struct.unpack_from("<fff", data, off)
                if not _is_valid_point(point):
                    valid_seed = False
                    break
                seed_points.append(point)

            if not valid_seed:
                start += 4
                continue

            _, seed_diag = _score_points(seed_points)
            if seed_diag < 0.01:
                start += 4
                continue

            points: list[tuple[float, float, float]] = []
            off = start
            while off + 12 <= size and len(points) < max_run:
                point = struct.unpack_from("<fff", data, off)
                if not _is_valid_point(point):
                    break
                points.append(point)
                off += stride

            if len(points) >= min_run:
                score = _score_points(points)
                # Filter out wildly huge coordinate clouds that are usually false positives.
                if 0.1 <= score[1] <= 500000.0:
                    candidates.append((score, _sample_points(points)))
                    # Skip forward inside this run to avoid dense duplicate candidates.
                    start = max(start + 4, off - stride * 8)
                    continue

            start += 4

    if not candidates:
        return []

    candidates.sort(key=lambda item: (item[0][0], item[0][1]), reverse=True)
    merged: list[tuple[float, float, float]] = []
    for _, points in candidates[:3]:
        merged.extend(points)
    return _sample_points(merged)


def _canonical_rel_key(path: str) -> str:
    return path.replace("\\", "/").strip("/").lower()


def _iter_common_game_data_dirs() -> Iterator[Path]:
    candidates = [
        Path(r"C:\Program Files (x86)\Steam\steamapps\common\Skyrim Special Edition\Data"),
        Path(r"C:\Program Files\Steam\steamapps\common\Skyrim Special Edition\Data"),
        Path(r"C:\Steam\steamapps\common\Skyrim Special Edition\Data"),
    ]
    for path in candidates:
        if path.exists() and path.is_dir():
            yield path


def _split_rel_path(rel_key: str) -> tuple[str, str]:
    normalized = _canonical_rel_key(rel_key)
    if "/" not in normalized:
        return ("", normalized)
    folder, name = normalized.rsplit("/", 1)
    return (folder, name)


def _stem_name(file_name: str) -> str:
    if "." in file_name:
        return file_name.rsplit(".", 1)[0]
    return file_name


def _fallback_stem_bases(stem: str) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        value = value.strip().lower()
        if not value:
            return
        if value in seen:
            return
        seen.add(value)
        candidates.append(value)

    add(stem)

    if "_" in stem:
        left, right = stem.rsplit("_", 1)
        if right.isalpha() and len(right) <= 3:
            add(left)

    # strip trailing alpha suffix (e.g. foo01a -> foo01)
    trimmed = stem
    while trimmed and trimmed[-1].isalpha():
        trimmed = trimmed[:-1]
        add(trimmed)

    # strip trailing digits (e.g. foo010 -> foo01 -> foo)
    trimmed_digits = stem
    while trimmed_digits and trimmed_digits[-1].isdigit():
        trimmed_digits = trimmed_digits[:-1]
        add(trimmed_digits)

    return candidates


def _is_lz4_frame(payload: bytes) -> bool:
    return len(payload) >= 4 and payload[:4] == b"\x04\x22\x4D\x18"


def _lz4_decompress_block(block: bytes) -> bytes:
    out = bytearray()
    i = 0
    n = len(block)

    while i < n:
        token = block[i]
        i += 1

        literal_len = token >> 4
        if literal_len == 15:
            while True:
                if i >= n:
                    raise ValueError("Invalid LZ4 block (literal length overflow)")
                ext = block[i]
                i += 1
                literal_len += ext
                if ext != 255:
                    break

        if i + literal_len > n:
            raise ValueError("Invalid LZ4 block (literal overrun)")
        out.extend(block[i : i + literal_len])
        i += literal_len

        if i >= n:
            break

        if i + 2 > n:
            raise ValueError("Invalid LZ4 block (missing offset)")
        offset = block[i] | (block[i + 1] << 8)
        i += 2
        if offset <= 0 or offset > len(out):
            raise ValueError("Invalid LZ4 block (bad offset)")

        match_len = token & 0x0F
        if match_len == 15:
            while True:
                if i >= n:
                    raise ValueError("Invalid LZ4 block (match length overflow)")
                ext = block[i]
                i += 1
                match_len += ext
                if ext != 255:
                    break
        match_len += 4

        src = len(out) - offset
        for _ in range(match_len):
            out.append(out[src])
            src += 1

    return bytes(out)


def _lz4_frame_decompress(payload: bytes) -> bytes:
    if not _is_lz4_frame(payload):
        raise ValueError("Not an LZ4 frame")

    i = 4
    if len(payload) < i + 3:
        raise ValueError("Truncated LZ4 frame")
    flg = payload[i]
    i += 1
    _bd = payload[i]
    i += 1

    has_content_size = bool(flg & 0x08)
    has_block_checksum = bool(flg & 0x10)
    has_content_checksum = bool(flg & 0x04)
    has_dict_id = bool(flg & 0x01)

    if has_content_size:
        i += 8
    if has_dict_id:
        i += 4
    i += 1  # header checksum
    if i > len(payload):
        raise ValueError("Invalid LZ4 frame header")

    out = bytearray()
    while True:
        if i + 4 > len(payload):
            raise ValueError("Truncated LZ4 frame block header")
        block_size = struct.unpack_from("<I", payload, i)[0]
        i += 4
        if block_size == 0:
            break

        raw_block = bool(block_size & 0x80000000)
        block_size &= 0x7FFFFFFF
        if i + block_size > len(payload):
            raise ValueError("Truncated LZ4 frame block")
        block = payload[i : i + block_size]
        i += block_size

        if raw_block:
            out.extend(block)
        else:
            out.extend(_lz4_decompress_block(block))

        if has_block_checksum:
            i += 4
            if i > len(payload):
                raise ValueError("Truncated LZ4 frame block checksum")

    if has_content_checksum:
        i += 4
        if i > len(payload):
            raise ValueError("Truncated LZ4 frame content checksum")

    return bytes(out)


@lru_cache(maxsize=1)
def _game_bsa_paths() -> tuple[str, ...]:
    paths: list[str] = []
    for data_dir in _iter_common_game_data_dirs():
        # Meshes archives are the most relevant/likely sources.
        preferred = sorted(data_dir.glob("*Meshes*.bsa"), key=lambda p: p.name.lower())
        others = sorted(data_dir.glob("*.bsa"), key=lambda p: p.name.lower())
        seen: set[str] = set()
        for path in [*preferred, *others]:
            key = str(path.resolve()).lower()
            if key in seen:
                continue
            seen.add(key)
            paths.append(str(path.resolve()))
    return tuple(paths)


@lru_cache(maxsize=6)
def _mod_bsa_paths(profile_path: str, mods_dir: str) -> tuple[str, ...]:
    paths: list[str] = []
    for mod in reversed(_enabled_mods(profile_path, mods_dir)):
        if not mod.path.exists() or not mod.path.is_dir():
            continue
        for bsa_path in sorted(mod.path.glob("*.bsa"), key=lambda p: p.name.lower()):
            paths.append(str(bsa_path.resolve()))
    return tuple(paths)


def _bsa_archive_paths(profile_path: str, mods_dir: str) -> tuple[str, ...]:
    # Higher-priority mod archives first, then base-game archives.
    return tuple([*_mod_bsa_paths(profile_path, mods_dir), *_game_bsa_paths()])


@lru_cache(maxsize=64)
def _bsa_dir_entries(profile_path: str, mods_dir: str, folder_key: str) -> tuple[str, ...]:
    folder_prefix = folder_key.strip("/").lower()
    if folder_prefix:
        folder_prefix += "/"

    names: list[str] = []
    seen: set[str] = set()
    for archive_path in _bsa_archive_paths(profile_path, mods_dir):
        index = _bsa_index(archive_path)
        for rel in index.keys():
            if folder_prefix and not rel.startswith(folder_prefix):
                continue
            if not rel.endswith(".nif"):
                continue
            key = rel.lower()
            if key in seen:
                continue
            seen.add(key)
            names.append(rel)
    return tuple(names)


def _loose_dir_entries(profile_path: str, mods_dir: str, folder_key: str) -> tuple[str, ...]:
    folder_path_parts = [part for part in folder_key.split("/") if part]
    names: list[str] = []
    seen: set[str] = set()
    for mod in reversed(_enabled_mods(profile_path, mods_dir)):
        candidate_dir = mod.path.joinpath(*folder_path_parts)
        if not candidate_dir.exists() or not candidate_dir.is_dir():
            continue
        for nif_file in candidate_dir.glob("*.nif"):
            rel = _canonical_rel_key((Path(folder_key) / nif_file.name).as_posix())
            if rel in seen:
                continue
            seen.add(rel)
            names.append(rel)
    return tuple(names)


@lru_cache(maxsize=48)
def _bsa_index(archive_path: str) -> dict[str, _BSAEntry]:
    path = Path(archive_path)
    if not path.exists() or not path.is_file():
        return {}

    try:
        with path.open("rb") as fp:
            header = fp.read(36)
            if len(header) < 36:
                return {}
            magic, version, offset, archive_flags, folder_count, file_count, total_folder_names, total_file_names, _file_flags = struct.unpack(
                "<4s8I", header
            )
            if magic != b"BSA\x00":
                return {}
            if version not in {103, 104, 105}:
                return {}

            record_size = 24 if version >= 105 else 16
            fp.seek(offset)
            folder_records_raw = fp.read(folder_count * record_size)
            if len(folder_records_raw) < folder_count * record_size:
                return {}

            folder_file_counts: list[int] = []
            for i in range(folder_count):
                rec = folder_records_raw[i * record_size : (i + 1) * record_size]
                if version >= 105:
                    _hash, count, _unk, _foff = struct.unpack("<QIIQ", rec)
                else:
                    _hash, count, _foff = struct.unpack("<QII", rec)
                folder_file_counts.append(count)

            file_records_flat: list[tuple[str, int, int]] = []
            for count in folder_file_counts:
                name_len_raw = fp.read(1)
                if not name_len_raw:
                    return {}
                name_len = name_len_raw[0]
                folder_name = fp.read(name_len)
                if len(folder_name) < name_len:
                    return {}
                folder = folder_name.rstrip(b"\x00").decode("utf-8", errors="ignore")

                records = fp.read(count * 16)
                if len(records) < count * 16:
                    return {}
                for i in range(count):
                    record = records[i * 16 : (i + 1) * 16]
                    _hash, size_with_flags, data_offset = struct.unpack("<QII", record)
                    file_records_flat.append((folder, size_with_flags, data_offset))

            names_blob = fp.read(total_file_names)
            if len(names_blob) < total_file_names:
                return {}
            names = names_blob.split(b"\x00")
            if names and names[-1] == b"":
                names = names[:-1]
            if len(names) < len(file_records_flat):
                return {}

            archive_compressed = bool(archive_flags & 0x4)
            index: dict[str, _BSAEntry] = {}
            for i, (folder, size_with_flags, data_offset) in enumerate(file_records_flat):
                file_name = names[i].decode("utf-8", errors="ignore")
                rel = _canonical_rel_key(f"{folder}/{file_name}")
                file_flag_compressed = bool(size_with_flags & 0x40000000)
                size = size_with_flags & 0x3FFFFFFF
                is_compressed = archive_compressed ^ file_flag_compressed
                index[rel] = _BSAEntry(
                    archive_path=archive_path,
                    relative_path_key=rel,
                    offset=data_offset,
                    size=size,
                    compressed=is_compressed,
                )
            return index
    except OSError:
        return {}
    except struct.error:
        return {}


def _read_bsa_entry_bytes(entry: _BSAEntry) -> bytes | None:
    path = Path(entry.archive_path)
    if not path.exists() or not path.is_file():
        return None
    try:
        with path.open("rb") as fp:
            fp.seek(entry.offset)
            payload = fp.read(entry.size)
        if len(payload) < entry.size:
            return None
        if not entry.compressed:
            return payload
        if len(payload) < 4:
            return None
        expected_size = struct.unpack_from("<I", payload, 0)[0]
        compressed_payload = payload[4:]
        try:
            if _is_lz4_frame(compressed_payload):
                data = _lz4_frame_decompress(compressed_payload)
            else:
                data = zlib.decompress(compressed_payload)
        except Exception:
            return None
        if expected_size and len(data) != expected_size:
            # Keep data even on size mismatch; some archives may report padded sizes.
            return data
        return data
    except OSError:
        return None


@lru_cache(maxsize=1024)
def _load_nif_bytes_exact(mods_dir: str, profile_path: str, nif_path_canonical: str) -> tuple[bytes | None, str]:
    loose_path = resolve_effective_nif_path(mods_dir, profile_path, nif_path_canonical)
    if loose_path:
        path = Path(loose_path)
        try:
            return (path.read_bytes(), f"loose:{path.name}")
        except OSError:
            # Fall through to BSA lookup if loose file cannot be read.
            pass

    rel_key = _canonical_rel_key(nif_path_canonical)
    for archive_path in _bsa_archive_paths(profile_path, mods_dir):
        entry = _bsa_index(archive_path).get(rel_key)
        if entry is None:
            continue
        raw = _read_bsa_entry_bytes(entry)
        if raw is not None:
            return (raw, f"bsa:{Path(archive_path).name}")
        return (None, f"archive_read_failed:{Path(archive_path).name}")

    return (None, "missing")


def _similarity_score(target_stem: str, candidate_stem: str) -> tuple[int, int, int]:
    # Larger tuple is better.
    common_prefix = 0
    for a, b in zip(target_stem, candidate_stem):
        if a != b:
            break
        common_prefix += 1

    length_gap = abs(len(target_stem) - len(candidate_stem))
    same_initial = 1 if target_stem and candidate_stem and target_stem[0] == candidate_stem[0] else 0
    return (common_prefix, -length_gap, same_initial)


@lru_cache(maxsize=1024)
def _find_fallback_nif_key(mods_dir: str, profile_path: str, nif_path_canonical: str) -> str | None:
    rel_key = _canonical_rel_key(nif_path_canonical)
    folder, file_name = _split_rel_path(rel_key)
    target_stem = _stem_name(file_name)
    if not target_stem:
        return None

    bases = _fallback_stem_bases(target_stem)
    if not bases:
        return None

    candidates = list(_loose_dir_entries(profile_path, mods_dir, folder))
    candidates.extend(_bsa_dir_entries(profile_path, mods_dir, folder))
    if not candidates:
        return None

    # Prefer same-folder names that share meaningful base prefixes.
    best_rel = None
    best_score: tuple[int, int, int] | None = None
    for rel in candidates:
        _, cand_file = _split_rel_path(rel)
        cand_stem = _stem_name(cand_file)
        if not cand_stem:
            continue

        if not any(cand_stem.startswith(base) or base.startswith(cand_stem) for base in bases):
            continue

        score = _similarity_score(target_stem, cand_stem)
        if best_score is None or score > best_score:
            best_score = score
            best_rel = rel

    return best_rel


@lru_cache(maxsize=1024)
def _load_mesh_preview_from_bsa(
    mods_dir: str,
    profile_path: str,
    nif_path_canonical: str,
) -> MeshPreviewData:
    rel_key = _canonical_rel_key(nif_path_canonical)
    for archive_path in _bsa_archive_paths(profile_path, mods_dir):
        index = _bsa_index(archive_path)
        entry = index.get(rel_key)
        if entry is None:
            continue
        raw = _read_bsa_entry_bytes(entry)
        if raw is None:
            return MeshPreviewData(
                mesh_path=Path(archive_path),
                points=[],
                status="archive_read_failed",
                detail=f"{Path(archive_path).name} contains {nif_path_canonical} but extraction/decompression failed",
            )
        points, source = _extract_mesh_points_from_nif_bytes(raw)
        if not points:
            return MeshPreviewData(
                mesh_path=Path(archive_path),
                points=[],
                status="no_geometry",
                detail=f"{Path(archive_path).name}: extracted NIF but no preview geometry ({source})",
            )
        return MeshPreviewData(
            mesh_path=Path(archive_path),
            points=points,
            status="ok",
            detail=f"{len(points)} preview points ({source}, bsa)",
        )

    return MeshPreviewData(
        mesh_path=None,
        points=[],
        status="missing",
        detail="Mesh file not found as loose file or in indexed BSA archives",
    )


@lru_cache(maxsize=1024)
def _load_mesh_preview_exact(mods_dir: str, profile_path: str, nif_path_canonical: str) -> MeshPreviewData:
    loose_path = resolve_effective_nif_path(mods_dir, profile_path, nif_path_canonical)
    if loose_path:
        preview = load_mesh_preview(loose_path)
        if preview.status == "ok":
            return preview
        # Fall through to BSA in case loose file is malformed.
    return _load_mesh_preview_from_bsa(mods_dir, profile_path, nif_path_canonical)


@lru_cache(maxsize=6)
def _enabled_mods(profile_path: str, mods_dir: str):
    return tuple(read_enabled_mods(Path(profile_path), Path(mods_dir)))


@lru_cache(maxsize=512)
def resolve_effective_nif_path(mods_dir: str, profile_path: str, nif_path_canonical: str) -> str | None:
    target = Path(*nif_path_canonical.split("/"))
    for mod in reversed(_enabled_mods(profile_path, mods_dir)):
        mesh_path = mod.path / target
        if mesh_path.exists() and mesh_path.is_file():
            return str(mesh_path.resolve())
    return None


@lru_cache(maxsize=256)
def load_mesh_preview(mesh_path: str) -> MeshPreviewData:
    path = Path(mesh_path)
    if not path.exists() or not path.is_file():
        return MeshPreviewData(mesh_path=None, points=[], status="missing", detail="Mesh file not found")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return MeshPreviewData(mesh_path=path, points=[], status="io_error", detail=str(exc))

    points, source = _extract_mesh_points_from_nif_bytes(raw)
    if not points:
        return MeshPreviewData(
            mesh_path=path,
            points=[],
            status="no_geometry",
            detail=f"NIF parsed but no lightweight vertex cloud extracted ({source})",
        )
    return MeshPreviewData(
        mesh_path=path,
        points=points,
        status="ok",
        detail=f"{len(points)} preview points ({source})",
    )


@lru_cache(maxsize=1024)
def load_mesh_preview_for_nif(mods_dir: str, profile_path: str, nif_path_canonical: str) -> MeshPreviewData:
    preview = _load_mesh_preview_exact(mods_dir, profile_path, nif_path_canonical)
    if preview.status == "ok":
        return preview

    fallback_rel = _find_fallback_nif_key(mods_dir, profile_path, nif_path_canonical)
    if fallback_rel and _canonical_rel_key(fallback_rel) != _canonical_rel_key(nif_path_canonical):
        fallback_preview = _load_mesh_preview_exact(mods_dir, profile_path, fallback_rel)
        if fallback_preview.status == "ok":
            detail = (
                f"{fallback_preview.detail}; fallback source for missing '{nif_path_canonical}' -> '{fallback_rel}'"
            )
            return MeshPreviewData(
                mesh_path=fallback_preview.mesh_path,
                points=fallback_preview.points,
                status="ok",
                detail=detail,
            )

    return preview


@lru_cache(maxsize=1024)
def load_nif_bounding_radius_for_nif(
    mods_dir: str,
    profile_path: str,
    nif_path_canonical: str,
) -> tuple[float | None, str]:
    raw, source = _load_nif_bytes_exact(mods_dir, profile_path, nif_path_canonical)
    if raw is not None:
        radius, detail = _extract_nif_bounding_radius_from_bytes(raw)
        if radius is not None:
            return (radius, f"{detail}:{source}")

    fallback_rel = _find_fallback_nif_key(mods_dir, profile_path, nif_path_canonical)
    if fallback_rel and _canonical_rel_key(fallback_rel) != _canonical_rel_key(nif_path_canonical):
        raw_fallback, source_fallback = _load_nif_bytes_exact(mods_dir, profile_path, fallback_rel)
        if raw_fallback is not None:
            radius, detail = _extract_nif_bounding_radius_from_bytes(raw_fallback)
            if radius is not None:
                return (radius, f"{detail}:{source_fallback};fallback:{fallback_rel}")

    return (None, "no_bounding_radius")
