#!/usr/bin/env python3
"""Build the self-contained L3 corpus: synthetic fixtures plus their verdicts.

The corpus is the input side of the L3 contract oracle: every fixture is a file
that a Python reader already accepts or rejects, so the Ghidra/QEMU harness has
something to agree with.  **No vendor bytes are read or written.**  Every
fixture is generated here from constants and the repository's own writers:

============  =====================================================  ==========
family        files                                                  reader
============  =====================================================  ==========
``cmp``       factory pair, no-op rebuild, recompressed, POI rename,  ``cmp_ind``
              truncated, 8 ``ind_mutate.py`` variants
``DRSTR``     valid tree, reordered tree, size-mismatch tree          ``drstr``
``tile``      valid X08 container, one-vertex mutation               ``tile``
``hdd_info``  reference SYS copy, base and all 89 variants of        ``hdd_info``
              ``hddinfo_variants.py`` with their verdicts
``factory``   placeholder; the real vendor pair is used only when     ``cmp_ind``
              the operator drops it into ``factory/``
============  =====================================================  ==========

The ``DRSTR`` tree is written by ``tools/drstr_ze0.build`` and the ``.cmp``
pairs by ``tools/cmpind_writer.CmpFile``; the ``hdd_info`` and ``.ind``
mutations are produced by the real tools (``hddinfo_variants.py``,
``ind_mutate.py``) run through a captured subprocess.  The tile is a minimal
X08-03-00 container (header 0x1000, level table 0x1ac, section table 0x800,
one kind-0x000a directory, one 256-aligned block holding one zlib record with a
synthetic vertex payload).  When ``tools/ze0-viewer/tools_ze0`` is installed,
the same tile is cross-checked with the vendored ``clarion_tile.read_tile`` /
``write_tile``; without it the corpus stays self-contained.

Verdicts come from the committed readers, not from this generator:

* ``cmp_ind``  -> ``tools/cmpind.py`` (``FormatError`` means REJECT);
* ``drstr``    -> ``tools/drstr.py`` plus the recursive size/identity rules of
                  ``tools/cardcheck.py`` (a card tree is not needed);
* ``hdd_info``-> ``tools/hddinfo.py`` ``classify`` against the corpus reference;
* ``tile``     -> this module's synthetic-container reader (the real tile
                  reader lives in the git-ignored vendor tree).

Usage::

    python3 tools/l3_harness/corpus.py build /tmp/l3/corpus [--json]
    python3 tools/l3_harness/corpus.py check /tmp/l3/corpus [--json]
    python3 tools/l3_harness/corpus.py --selftest

Exit codes: ``0`` ok, ``1`` validation/verdict problems, ``2`` usage error.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from l3_harness import manifest  # noqa: E402

import cmpind  # noqa: E402
import cmpind_writer  # noqa: E402
import drstr  # noqa: E402
import drstr_ze0  # noqa: E402
import hddinfo  # noqa: E402

CHUNK = 0x10000
HDD_SIZE = 72
HDD_REFERENCE = "hdd_info/reference/SYS.HDD_INFO.TXT"

#: The six CRLF-separated lines of a 72-byte ``HDD_INFO.TXT``.  Values are
#: synthetic but shape-correct: line 1 has the family digit, line 4 has the
#: ``SDC08-EVEUR`` manufacturer/destination pair the M0 model reads.
HDD_LINES = (
    b"QSD-302-100",
    b"QSD-309-101",
    b"02-110100-00",
    b"SDC08-EVEUR",
    b"11-05",
    b"470323501005",
)

#: Two 17-byte names: the same-length rename the ``poi_rename`` case needs.
POI_OLD = b"SYNTHETIC-NAME-01"
POI_NEW = b"OSM2LEAF5-NAME-01"

#: ``hddinfo_variants.py`` default matrix: 73 content + 16 permutation files.
HDD_VARIANTS = 89
#: Model-M0 outcome of that matrix on the synthetic block (EXP-M9.7).
HDD_VARIANTS_ACCEPT = 66
HDD_VARIANTS_REJECT = 23
HDD_VARIANTS_DIR = "hdd_info/variants"

#: Representative ``hddinfo_variants.py`` rejects, one per discriminator.
HDD_MISMATCHES = (
    "line1_digits_4_002.HDD_INFO.TXT",  # userdata_type 3 -> 0
    "line4_digits_3_00.HDD_INFO.TXT",   # manufacturer_id 8 -> 0
    "line4_letters_6_XXXXX.HDD_INFO.TXT",  # destination token replaced
)

#: The full ``ind_mutate.py`` matrix; every variant must be rejected.
IND_VARIANTS = (
    "size_20000",
    "size_8000",
    "count_p1",
    "count_m1",
    "off_last_m1",
    "off_last_p1",
    "off0_1",
    "off_last_0",
)

TILE_HEADER = 0x1000
TILE_TABLE = 0x1000
TILE_DIR = 0x1200
TILE_BLOCK = 0x1400
TILE_KIND = 0x000A
TILE_BODY = 8
TILE_IDENTS = (
    (0x00, "CLARION"),
    (0x40, "ZENRIN"),
    (0x80, "CLA-NAVI06-01"),
    (0xA0, "FORMAT VERSION X08-03-00"),
    (0xE0, "DATA VERSION 11/05/01/00"),
)

#: Synthetic vertices of the one background record (parcel units).
TILE_VERTICES = ((100, 200), (300, 400), (500, 600), (700, 800))


class CorpusError(RuntimeError):
    """Raised when a fixture cannot be generated as specified."""


class TileError(ValueError):
    """Raised when a synthetic tile container is malformed."""


# --------------------------------------------------------------------------
# synthetic payloads
# --------------------------------------------------------------------------


def hdd_bytes() -> bytes:
    raw = b"\r\n".join(HDD_LINES)
    if len(raw) != HDD_SIZE:
        raise CorpusError(f"HDD_INFO block is {len(raw)} bytes, want {HDD_SIZE}")
    return raw


def refer_payload() -> bytes:
    """Synthetic REFER-style page: a header area plus a named tail chunk."""
    blob = bytearray(b"\x00" * CHUNK)
    blob[0x00:0x10] = b"SYNTHETIC REFER"
    blob[0x100:0x100 + len(POI_OLD)] = POI_OLD
    for i in range(0x200, CHUNK, 0x100):
        blob[i:i + 4] = struct.pack("<I", i)
    tail = (b"page two: " + bytes(range(0x40))) * (0x4000 // 0x49 + 1)
    return bytes(blob) + tail[:0x4000]


def point_payload() -> bytes:
    """A second container with a different chunk count (3 chunks)."""
    unit = b"POINT page " + bytes(range(0x80))
    blob = (unit * ((2 * CHUNK + 0x2000) // len(unit) + 1))[: 2 * CHUNK + 0x2000]
    return blob


def tile_payload(vertices) -> bytes:
    out = bytearray(struct.pack(">H", len(vertices)))
    for x, y in vertices:
        if not (0 <= x <= 2047 and 0 <= y <= 2047):
            raise CorpusError(f"vertex {(x, y)} outside the 0..2047 bound")
        out += struct.pack(">HH", x, y)
    return bytes(out)


# --------------------------------------------------------------------------
# tile container (X08-03-00 shape, synthetic content)
# --------------------------------------------------------------------------


def _addr_of(value: int) -> int:
    return (value >> 8) * 2048 + (value & 0xFF) * 256


def _enc_addr(offset: int) -> int:
    if offset % 256:
        raise CorpusError(f"address {offset:#x} is not 256-aligned")
    return (offset // 2048) << 8 | (offset % 2048) // 256


def _pad256(size: int) -> int:
    return (size + 255) // 256 * 256


def _tile_header() -> bytearray:
    header = bytearray(b"\xff" * TILE_HEADER)
    for offset, text in TILE_IDENTS:
        raw = text.encode("utf-16-be")
        header[offset:offset + len(raw)] = raw
    header[0x160:0x164] = b"1600"

    # level table at 0x1ac: one section, one level row, one directory
    struct.pack_into(">H", header, 0x1AC, 1)
    header[0x1AE], header[0x1AF] = 1, 1
    struct.pack_into(">BBH", header, 0x1B0, 6, 0x80, 1)

    # section table at 0x800: one table entry, then the 0xffffffff sentinel
    struct.pack_into(">IH", header, 0x800, _enc_addr(TILE_TABLE), 1)
    struct.pack_into(">IH", header, 0x806, 0xFFFFFFFF, 0)
    return header


def build_tile(vertices=TILE_VERTICES) -> bytes:
    """Write the minimal X08 container around one zlib record."""
    payload = tile_payload(vertices)
    stream = zlib.compress(payload, 6)
    if len(stream) % 2:
        stream += b"\x00"
    words = len(stream) // 2
    inflated = len(payload) // 2
    if not (0 < words <= 0x10000 and 0 < inflated <= 0x10000):
        raise CorpusError("synthetic record does not fit the pair table")

    header = _tile_header()
    tag = _enc_addr(TILE_DIR)
    table = [
        10, 2,            # table word count, level-0 group offset
        8, 1,             # group length, group count
        0, 0, 0, 0,       # synthetic box (no geographic extent)
        tag >> 16, tag & 0xFFFF,
    ]

    out = bytearray(header)
    out += b"\x00" * (TILE_TABLE - len(out))
    out += struct.pack(">10H", *table)
    out += b"\x00" * (TILE_DIR - len(out))
    out += struct.pack(">HHHHHH", TILE_KIND, 0, 1, 0, 0, 0x80)
    out += struct.pack(">I", _enc_addr(TILE_BLOCK))
    out += struct.pack(">2I", words, inflated)
    out += b"\x00" * (TILE_BLOCK - len(out))
    out += stream
    out += b"\x00" * (_pad256(len(out)) - len(out))
    return bytes(out)


def _walk_table(data: bytes, offset: int, entry_len: int):
    if offset + 2 > len(data):
        raise TileError(f"table at {offset:#x} is outside the file")
    count = struct.unpack_from(">H", data, offset)[0]
    pos = offset + 2
    rows = []
    for _ in range(count):
        if pos + 2 > len(data):
            raise TileError("level table is truncated")
        section, entries = data[pos], data[pos + 1]
        pos += 2
        end = pos + entries * entry_len
        if end > len(data):
            raise TileError("level table entry runs past the file")
        rows.append((section, [data[pos + i * entry_len:pos + (i + 1) * entry_len]
                               for i in range(entries)]))
        pos = end
    return rows, pos


def read_tile(source) -> dict:
    """Read the synthetic container; raise ``TileError`` on any violation.

    This is the corpus-side ``tile`` reader.  It validates the invariants the
    generator writes (bounds, 256-byte addressing, pair table, zlib sizes,
    vertex payload); it is not a full X08-03-00 decoder.  The vendored
    ``clarion_tile`` cross-check is in :func:`vendor_tile_roundtrip`.
    """
    data = source.read_bytes() if isinstance(source, Path) else bytes(source)
    if len(data) < TILE_HEADER:
        raise TileError(f"file is {len(data)} bytes, shorter than the 0x1000 header")

    levels, _ = _walk_table(data, 0x1AC, 4)
    if not levels:
        raise TileError("no sections in the level table")

    sections = []
    pos = 0x800
    while True:
        if pos + 6 > TILE_HEADER:
            raise TileError("section table runs past 0x1000")
        tag, count = struct.unpack_from(">IH", data, pos)
        pos += 6
        if tag == 0xFFFFFFFF:
            break
        sections.append((_addr_of(tag), count))
    if len(sections) != len(levels):
        raise TileError("level table and section table disagree on the section count")

    vertices = []
    for (section_id, rows), (table_addr, dir_count) in zip(levels, sections):
        if table_addr + 2 > len(data):
            raise TileError(f"section {section_id}: table outside the file")
        words = struct.unpack_from(">H", data, table_addr)[0]
        if table_addr + 2 * words > len(data):
            raise TileError(f"section {section_id}: table words outside the file")
        table = struct.unpack_from(">%dH" % words, data, table_addr)
        seen_dirs = 0
        for index, row in enumerate(rows):
            level, _typ, declared = row[0], row[1], struct.unpack(">H", row[2:])[0]
            offset = table[1 + index]
            if offset == 0xFFFF:
                if declared:
                    raise TileError(f"level {level}: declared {declared} dirs, no group")
                continue
            if offset + 2 > words:
                raise TileError(f"level {level}: group offset outside the table")
            glen, gcnt = table[offset], table[offset + 1]
            if glen != 2 + 6 * gcnt or gcnt != declared:
                raise TileError(f"level {level}: group header {glen}/{gcnt} != {declared}")
            for k in range(gcnt):
                box = table[offset + 2 + 6 * k:offset + 8 + 6 * k]
                if len(box) != 6:
                    raise TileError(f"level {level}: group {k} runs past the table")
                tag = (box[4] << 16) | box[5]
                dir_addr = _addr_of(tag)
                if dir_addr % 256 or not TILE_HEADER <= dir_addr < len(data):
                    raise TileError(f"level {level}: directory address {dir_addr:#x} invalid")
                seen_dirs += 1
                vertices.extend(_read_dir(data, dir_addr))
        if seen_dirs != dir_count:
            raise TileError(
                f"section {section_id}: {seen_dirs} directories, table says {dir_count}"
            )
    if not vertices:
        raise TileError("no vertices in the tile")

    packed = tile_payload(vertices)
    return {
        "sections": len(sections),
        "vertices": vertices,
        "payload_sha256": hashlib.sha256(packed).hexdigest(),
    }


def _read_dir(data: bytes, offset: int) -> list:
    if offset + 12 > len(data):
        raise TileError(f"directory at {offset:#x} is truncated")
    kind, _a, slots, _y, _x, _typ = struct.unpack_from(">HHHHHH", data, offset)
    if kind != TILE_KIND:
        raise TileError(f"unsupported synthetic directory kind {kind:#06x}")
    if slots < 1:
        raise TileError("directory declares no slots")
    end = offset + 12 + slots * (4 + TILE_BODY)
    if end > len(data):
        raise TileError(f"directory at {offset:#x} runs past the file")
    vertices = []
    pos = offset + 12
    for _ in range(slots):
        tag = struct.unpack_from(">I", data, pos)[0]
        body = data[pos + 4:pos + 4 + TILE_BODY]
        pos += 4 + TILE_BODY
        if tag in (0xFFFFFFFF, 0x7FFFFFFF):
            continue
        block = _addr_of(tag)
        if block % 256 or not TILE_HEADER <= block < len(data):
            raise TileError(f"slot tag {tag:#x} does not address a block")
        words, inflated = struct.unpack(">2I", body)
        if not (0 < words <= 0x10000 and 0 < inflated <= 0x10000):
            raise TileError(f"slot pair ({words}, {inflated}) out of range")
        size = 2 * words
        if block + size > len(data):
            raise TileError("slot record runs past the file")
        stream = data[block:block + size]
        cmf, flg = stream[0], stream[1]
        if (cmf & 0x0F) != 8 or ((cmf << 8) | flg) % 31:
            raise TileError("slot record is not a zlib stream")
        try:
            plain = zlib.decompress(stream)
        except zlib.error as exc:
            raise TileError(f"slot record does not inflate: {exc}") from exc
        if len(plain) != 2 * inflated:
            raise TileError(
                f"slot record inflates to {len(plain)} bytes, pair says {2 * inflated}"
            )
        vertices.extend(_parse_vertices(plain))
    return vertices


def _parse_vertices(plain: bytes) -> list:
    if len(plain) < 2:
        raise TileError("vertex payload is shorter than its count")
    count = struct.unpack_from(">H", plain, 0)[0]
    if len(plain) != 2 + 4 * count:
        raise TileError(
            f"vertex payload is {len(plain)} bytes for {count} vertices"
        )
    out = []
    for i in range(count):
        x, y = struct.unpack_from(">HH", plain, 2 + 4 * i)
        if x > 2047 or y > 2047:
            raise TileError(f"vertex {(x, y)} outside the 0..2047 bound")
        out.append((x, y))
    return out


def vendor_tile_roundtrip(data: bytes):
    """Return True/False for the vendored reader, or None when it is absent.

    ``tools/ze0-viewer/tools_ze0`` is a git-ignored clone (``setup.sh``), so a
    clean checkout legitimately has no vendor reader.  The corpus never
    depends on it; the self-test only uses it as an extra control.
    """
    path = TOOLS_DIR / "ze0-viewer" / "tools_ze0" / "clarion_tile.py"
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("corpus_clarion_tile", path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    tile = module.read_tile(data)
    return module.write_tile(tile) == data


# --------------------------------------------------------------------------
# DRSTR001.DAT tree
# --------------------------------------------------------------------------


def _drstr_problems(data: bytes) -> list[str]:
    """Structural and size rules of ``tools/drstr.py`` + ``cardcheck.py``.

    Without a card tree the file sizes cannot be compared to disk, but the
    directory values are fully checkable: a directory entry's ``value`` must
    equal the recursive total of its children (mod 2^32).
    """
    problems: list[str] = []
    try:
        tree = drstr.parse(data)
    except ValueError as exc:
        return [f"parse: {exc}"]

    nodes = tree["nodes"]
    if not nodes:
        return ["no nodes"]

    root = nodes[0]
    if root["name"] != "/":
        problems.append(f"root name is {root['name']!r}, want '/'")
    if root["parent"] != 0:
        problems.append(f"root parent index is {root['parent']!r}, want 0 (itself)")

    table_end = tree["table_end"]
    intervals = []
    for node in nodes:
        index = node["index"]
        if node["next_index"] != index + 1:
            problems.append(
                f"node {index}: next_index {node['next_index']} != {index + 1}"
            )
        if node["parent"] is None or not (0 <= node["parent"] < len(nodes)):
            problems.append(f"node {index}: parent {node['parent']!r} out of range")
        start = node["listing_offset"]
        end = start + drstr.ENTRY_SIZE * node["entry_count"]
        if start < table_end or end > len(data):
            problems.append(
                f"node {index}: listing {start:#x}..{end:#x} outside "
                f"{table_end:#x}..{len(data):#x}"
            )
        else:
            intervals.append((start, end, index))

    intervals.sort()
    for (start_a, end_a, index_a), (start_b, _end_b, index_b) in zip(intervals, intervals[1:]):
        if start_b < end_a:
            problems.append(
                f"nodes {index_a} and {index_b}: listings overlap at {start_b:#x}"
            )

    by_name = {node["name"]: node for node in nodes[1:]}
    for node in nodes[1:]:
        parent = node["parent"]
        if parent is None or not (0 <= parent < len(nodes)):
            continue
        listed = [
            entry for entry in nodes[parent]["entries"]
            if entry["name"] == node["name"] and entry["type"] == 2
        ]
        if len(listed) != 1:
            problems.append(
                f"node {node['index']} ({node['name']!r}) is not listed exactly once "
                f"by its parent {parent}"
            )

    seen: set[str] = set()
    for node in nodes:
        for entry in node["entries"]:
            name = entry["name"]
            if not name or not all(0x20 <= ord(ch) < 0x7F for ch in name):
                problems.append(f"node {node['index']}: bad entry name {name!r}")
            if entry["type"] not in (0, 2):
                problems.append(
                    f"node {node['index']}/{name}: entry type {entry['type']} "
                    "is neither file (0) nor directory (2)"
                )
            if entry["type"] == 2:
                if name not in by_name:
                    problems.append(
                        f"node {node['index']}: directory {name!r} has no node record"
                    )
                elif name in seen:
                    problems.append(f"node {node['index']}: duplicate directory {name!r}")
                else:
                    seen.add(name)

    totals: dict[str, int] = {}

    def total(name: str, depth: int = 0) -> int:
        node = by_name[name]
        if name in totals:
            return totals[name]
        if depth > len(nodes):
            return 0
        value = 0
        for entry in node["entries"]:
            if entry["type"] == 2 and entry["name"] in by_name:
                value += total(entry["name"], depth + 1)
            else:
                value += entry["value"]
        totals[name] = value & 0xFFFFFFFF
        return totals[name]

    for node in nodes:
        for entry in node["entries"]:
            if entry["type"] == 2 and entry["name"] in by_name:
                expected = total(entry["name"])
                if entry["value"] != expected:
                    problems.append(
                        f"node {node['index']}/{entry['name']}: directory value "
                        f"{entry['value']} != recursive total {expected}"
                    )
    return problems


def build_drstr(pairs: dict[str, tuple[bytes, bytes]], tile: bytes,
                hdd: bytes) -> bytes:
    """Build ``DRSTR001.DAT`` for a staged synthetic card tree."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for stem, (cmp_bytes, ind_bytes) in pairs.items():
            target = root / "REFER001"
            target.mkdir(parents=True, exist_ok=True)
            (target / f"{stem}.cmp").write_bytes(cmp_bytes)
            (target / f"{stem}.ind").write_bytes(ind_bytes)
        (root / "MAPAL001").mkdir(parents=True, exist_ok=True)
        (root / "MAPAL001" / "B28R070R.DAT").write_bytes(tile)
        (root / "VER_INFO").mkdir(parents=True, exist_ok=True)
        (root / "VER_INFO" / "HDD_INFO.TXT").write_bytes(hdd)
        return drstr_ze0.build(root)


def _drstr_entries(data: bytes) -> list[tuple[int, int, int]]:
    tree = drstr.parse(data)
    return [
        (node["listing_offset"], node["entry_count"], node["index"])
        for node in tree["nodes"]
    ]


def reorder_drstr(data: bytes) -> bytes:
    """Reverse the entries inside every listing; offsets and sizes stay put."""
    out = bytearray(data)
    for start, count, _index in _drstr_entries(data):
        block = [bytes(out[start + i * 32:start + (i + 1) * 32]) for i in range(count)]
        for i, raw in enumerate(reversed(block)):
            out[start + i * 32:start + (i + 1) * 32] = raw
    return bytes(out)


def bump_drstr_size(data: bytes) -> bytes:
    """Add one byte to the value of the first directory entry of the root."""
    out = bytearray(data)
    tree = drstr.parse(data)
    root = tree["nodes"][0]
    for entry in root["entries"]:
        if entry["type"] == 2:
            at = root["listing_offset"] + entry["index"] * 32 + 0x1C
            value = struct.unpack_from("<I", out, at)[0]
            struct.pack_into("<I", out, at, (value + 1) & 0xFFFFFFFF)
            return bytes(out)
    raise CorpusError("root listing has no directory entry to bump")


# --------------------------------------------------------------------------
# readers -> verdicts
# --------------------------------------------------------------------------


def verdict_cmp_ind(root: Path, relative: str) -> str:
    try:
        cmpind.decode(root / relative)
    except (cmpind.FormatError, OSError, zlib.error):
        return "REJECT"
    return "ACCEPT"


def verdict_drstr(root: Path, relative: str) -> str:
    try:
        data = (root / relative).read_bytes()
    except OSError:
        return "REJECT"
    return "REJECT" if _drstr_problems(data) else "ACCEPT"


def verdict_tile(root: Path, relative: str) -> str:
    try:
        read_tile(root / relative)
    except (TileError, OSError):
        return "REJECT"
    return "ACCEPT"


def verdict_hdd_info(root: Path, relative: str) -> str:
    try:
        system = hddinfo.HddInfo.parse((root / HDD_REFERENCE).read_bytes())
        card = hddinfo.HddInfo.parse((root / relative).read_bytes())
    except (OSError, ValueError):
        return "REJECT"
    return "ACCEPT" if hddinfo.classify(system, card)["accepted"] else "REJECT"


VERDICT_FUNCTIONS = {
    "cmp_ind": verdict_cmp_ind,
    "drstr": verdict_drstr,
    "tile": verdict_tile,
    "hdd_info": verdict_hdd_info,
}


def entry_verdict(root, entry) -> str:
    func = VERDICT_FUNCTIONS.get(entry["reader"])
    if func is None:
        raise CorpusError(f"no reader for {entry['reader']!r}")
    return func(Path(root), entry["path"])


# --------------------------------------------------------------------------
# corpus construction
# --------------------------------------------------------------------------


def _write(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _run_tool(argv) -> str:
    result = subprocess.run(
        [sys.executable, *argv],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise CorpusError(
            f"{Path(argv[0]).name} exited {result.returncode}: "
            f"{(result.stderr or result.stdout).strip()}"
        )
    return result.stdout


def _cmp_pair(payload: bytes, level: int = 6) -> tuple[bytes, bytes]:
    handle = cmpind_writer.CmpFile.from_dat(payload, level=level)
    return handle.cmp_bytes(), handle.ind_bytes()


def _write_cmp_pair(root: Path, relative_dir: str, stem: str,
                    cmp_bytes: bytes, ind_bytes: bytes) -> str:
    """Write ``<stem>.cmp``/``<stem>.ind`` (stem keeps its own dots)."""
    _write(root / relative_dir / f"{stem}.cmp", cmp_bytes)
    _write(root / relative_dir / f"{stem}.ind", ind_bytes)
    return str((root / relative_dir / f"{stem}.cmp").relative_to(root))


def build_corpus(root) -> dict:
    """Write every fixture under ``root`` and return the build report."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    notes: dict[tuple[str, str], str] = {}
    specs: list[tuple[str, str, str, str | None]] = []
    skipped: list[str] = []

    hdd = hdd_bytes()
    refer = refer_payload()
    point = point_payload()
    tile = build_tile()
    edited = build_tile(((TILE_VERTICES[0][0] + 10, TILE_VERTICES[0][1]),
                         *TILE_VERTICES[1:]))

    # ---- cmp family --------------------------------------------------
    factory_cmp, factory_ind = _cmp_pair(refer)
    path = _write_cmp_pair(root, "cmp/factory", "ADDRE001.DAT",
                           factory_cmp, factory_ind)
    specs.append(("factory", "cmp_ind", path, None))
    notes[("factory", path)] = "synthetic .cmp/.ind pair; always accepted"

    point_cmp, point_ind = _cmp_pair(point)
    noop = cmpind_writer.CmpFile.from_files(
        _write(root / "cmp" / "noop-rebuild" / "POINT001.DAT.cmp", point_cmp),
        _write(root / "cmp" / "noop-rebuild" / "POINT001.DAT.ind", point_ind),
    )
    if noop.cmp_bytes() != point_cmp or noop.ind_bytes() != point_ind:
        raise CorpusError("preserve round-trip is not byte-identical")
    path = "cmp/noop-rebuild/POINT001.DAT.cmp"
    specs.append(("noop_rebuild", "cmp_ind", path, None))
    notes[("noop_rebuild", path)] = (
        "CmpFile.from_files -> ind_bytes rebuild; container identity"
    )

    rec_cmp, rec_ind = _cmp_pair(refer, level=1)
    path = _write_cmp_pair(root, "cmp/recompressed", "ADDRE001.DAT", rec_cmp, rec_ind)
    specs.append(("recompressed", "cmp_ind", path, None))
    notes[("recompressed", path)] = (
        "same payload deflated at level 1: different bytes, same decode"
    )

    renamed = cmpind_writer.CmpFile.from_files(
        _write(root / "cmp/poi-rename" / "ADDRE001.DAT.cmp", factory_cmp),
        _write(root / "cmp/poi-rename" / "ADDRE001.DAT.ind", factory_ind),
    )
    plain = renamed.decode()
    if plain.count(POI_OLD) != 1:
        raise CorpusError(f"want exactly one {POI_OLD!r} in the factory payload")
    renamed.replace_chunk(0, plain.replace(POI_OLD, POI_NEW)[:CHUNK])
    renamed.check()
    renamed.write(root / "cmp" / "poi-rename", "ADDRE001.DAT")
    path = "cmp/poi-rename/ADDRE001.DAT.cmp"
    specs.append(("poi_rename", "cmp_ind", path, None))
    notes[("poi_rename", path)] = (
        f"{len(POI_OLD)}-byte rename {POI_OLD.decode()} -> {POI_NEW.decode()}"
    )

    path = _write_cmp_pair(root, "cmp/truncated", "ADDRE001.DAT",
                           factory_cmp[:-37], factory_ind)
    specs.append(("truncated_cmp", "cmp_ind", path, None))
    notes[("truncated_cmp", path)] = (
        "37 bytes cut from the .cmp; the .ind still declares the old size"
    )

    with tempfile.TemporaryDirectory() as tmp:
        source_ind = _write(Path(tmp) / "ADDRE001.DAT.ind", factory_ind)
        mutated = Path(tmp) / "out"
        _run_tool([str(TOOLS_DIR / "ind_mutate.py"), "--ind", str(source_ind),
                   "--out", str(mutated)])
        for variant in IND_VARIANTS:
            ind_path = mutated / f"{variant}.ind"
            if not ind_path.is_file():
                raise CorpusError(f"ind_mutate.py did not write {ind_path.name}")
            path = _write_cmp_pair(
                root, f"cmp/corrupt-ind/{variant}", "ADDRE001.DAT",
                factory_cmp, ind_path.read_bytes(),
            )
            specs.append(("corrupt_ind", "cmp_ind", path, None))
            notes[("corrupt_ind", path)] = f"ind_mutate.py variant {variant}"

    # ---- DRSTR family ------------------------------------------------
    tree = build_drstr({"ADDRE001.DAT": (factory_cmp, factory_ind),
                        "POINT001.DAT": (point_cmp, point_ind)}, tile, hdd)
    path = str(_write(root / "drstr" / "DRSTR001.DAT", tree).relative_to(root))
    specs.append(("drstr_factory", "drstr", path, None))
    notes[("drstr_factory", path)] = (
        "root + 3 directories, 4 files; values are the recursive totals"
    )

    path = str(_write(root / "drstr" / "DRSTR001.reordered.DAT",
                      reorder_drstr(tree)).relative_to(root))
    specs.append(("drstr_factory", "drstr", path, None))
    notes[("drstr_factory", path)] = (
        "same tree with every listing in reverse order; order is not part of "
        "the contract"
    )

    path = str(_write(root / "drstr" / "DRSTR001.size-mismatch.DAT",
                      bump_drstr_size(tree)).relative_to(root))
    specs.append(("drstr_size_mismatch", "drstr", path, None))
    notes[("drstr_size_mismatch", path)] = (
        "root directory value for MAPAL001 is one byte larger than its subtree"
    )

    # ---- tile family -------------------------------------------------
    path = str(_write(root / "tile" / "B28R070R.DAT", tile).relative_to(root))
    specs.append(("tile_factory", "tile", path, None))
    notes[("tile_factory", path)] = (
        "minimal X08-03-00 container, one zlib record with 4 vertices"
    )

    path = str(_write(root / "tile" / "B28R070R.edited.DAT", edited).relative_to(root))
    specs.append(("tile_edited", "tile", path, None))
    notes[("tile_edited", path)] = "same container, first vertex x 100 -> 110"

    # ---- hdd_info family ---------------------------------------------
    _write(root / HDD_REFERENCE, hdd)
    path = str(_write(root / "hdd_info" / "factory" / "HDD_INFO.TXT",
                      hdd).relative_to(root))
    specs.append(("hdd_info_factory", "hdd_info", path, None))
    notes[("hdd_info_factory", path)] = (
        "72-byte block, identical to the corpus reference"
    )

    with tempfile.TemporaryDirectory() as tmp:
        base = _write(Path(tmp) / "HDD_INFO.TXT", hdd)
        mutated = Path(tmp) / "out"
        # Default matrix: 73 content variants + 16 permutations = 89 files.
        _run_tool([str(TOOLS_DIR / "hddinfo_variants.py"), str(base),
                   str(mutated), "--sweep", "0-5"])
        variants = sorted(mutated.glob("*.HDD_INFO.TXT"))
        if len(variants) != HDD_VARIANTS:
            raise CorpusError(
                f"hddinfo_variants.py wrote {len(variants)} variants, "
                f"want {HDD_VARIANTS}"
            )
        for variant in variants:
            name = variant.name
            data = variant.read_bytes()
            if len(data) != HDD_SIZE:
                raise CorpusError(f"{name} changed length to {len(data)}")
            path = str(_write(root / HDD_VARIANTS_DIR / name, data)
                       .relative_to(root))
            # The M0 model is the reader, so its verdict decides the case:
            # a variant the model still accepts exercises the accept path.
            case = (
                "hdd_info_mismatch"
                if verdict_hdd_info(root, path) == "REJECT"
                else "hdd_info_factory"
            )
            specs.append((case, "hdd_info", path, None))
            notes[(case, path)] = (
                f"hddinfo_variants.py {name}; "
                + ("model M0 rejects the map code" if case == "hdd_info_mismatch"
                   else "map code unchanged, model M0 still accepts")
            )

    # ---- factory placeholder -----------------------------------------
    placeholder = root / "factory" / "README.txt"
    _write(placeholder, (
        "Optional factory slot for the L3 corpus.\n"
        "\n"
        "No vendor bytes are generated by tools/l3_harness/corpus.py.  To add\n"
        "the real acceptance baseline, copy an unmodified REFER001 pair here:\n"
        "\n"
        "    factory/ADDRE001.DAT.cmp\n"
        "    factory/ADDRE001.DAT.ind\n"
        "\n"
        "`corpus.py build DIR` then adds one `factory:cmp_ind` manifest entry;\n"
        "with the pair absent the case is reported as skipped.\n"
    ).encode("ascii"))
    vendor_pair = (root / "factory" / "ADDRE001.DAT.cmp",
                   root / "factory" / "ADDRE001.DAT.ind")
    if all(p.is_file() for p in vendor_pair):
        path = "factory/ADDRE001.DAT.cmp"
        specs.append(("factory", "cmp_ind", path, None))
        notes[("factory", path)] = (
            "vendor-provided factory pair dropped into factory/ (not generated)"
        )
    else:
        skipped.append(
            "factory: no vendor ADDRE001.DAT.cmp/.ind in factory/ "
            "(no vendor bytes are generated)"
        )

    # ---- manifest ----------------------------------------------------
    doc = manifest.build(root, specs)
    for entry in doc["corpus"]:
        note = notes.get((entry["case"], entry["path"]))
        if note:
            entry["notes"] = note
    doc["notes"] = (
        "synthetic L3 corpus generated by tools/l3_harness/corpus.py; no vendor "
        "bytes. Hashes are what this build produced (zlib output is "
        "implementation-dependent), so rebuild rather than transplant."
    )
    problems = manifest.validate(doc, root=root)
    if problems:
        raise CorpusError("; ".join(problems))

    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    _write(root / "README.txt", _readme().encode("ascii"))

    case_counts: dict[str, int] = {}
    for entry in doc["corpus"]:
        case_counts[entry["case"]] = case_counts.get(entry["case"], 0) + 1
    return {
        "root": str(root),
        "manifest": str(manifest_path),
        "entries": len(doc["corpus"]),
        "cases": dict(sorted(case_counts.items())),
        "skipped": skipped,
        "result": "BUILT",
        "document": doc,
    }


def _readme() -> str:
    return """L3 synthetic corpus
===================

Generated by tools/l3_harness/corpus.py.  Every byte here is synthetic; no
vendor firmware or map data was read or written.  manifest.json is the
contract: path, size, SHA-256, reader, case and the verdict that reader must
produce (schema osm2leaf.l3.manifest/v1, validator tools/l3_harness/manifest.py).

Layout

    cmp/factory/            .cmp/.ind container, baseline accept
    cmp/noop-rebuild/       preserve round-trip of a second container
    cmp/recompressed/       same payload, level-1 zlib streams
    cmp/poi-rename/         17-byte POI rename, offsets unchanged
    cmp/truncated/          .cmp cut by 37 bytes, .ind untouched
    cmp/corrupt-ind/        one directory per ind_mutate.py variant
    drstr/                  DRSTR001.DAT: valid, reordered, size mismatch
    tile/                   minimal X08 container: valid, one vertex moved
    hdd_info/               reference SYS copy, base copy and the 89
                            hddinfo_variants.py variants with verdicts
    factory/                placeholder for an operator-supplied vendor pair

Rebuild after any change to a writer, and never copy manifest.json between
machines: zlib output depends on the implementation, so the hashes describe
this build.  `corpus.py check DIR` re-validates the manifest and re-runs every
Python reader.
"""


# --------------------------------------------------------------------------
# checking
# --------------------------------------------------------------------------


def check_corpus(root) -> dict:
    root = Path(root)
    manifest_path = root / "manifest.json"
    problems: list[str] = []
    try:
        doc = manifest.load(manifest_path)
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "root": str(root),
            "manifest": str(manifest_path),
            "entries": 0,
            "problems": [f"cannot read {manifest_path}: {exc}"],
            "verdicts": [],
            "result": "FAIL",
        }

    problems.extend(manifest.validate(doc, root=root))

    verdicts = []
    for entry in doc.get("corpus", []):
        try:
            actual = entry_verdict(root, entry)
        except CorpusError as exc:
            problems.append(f"{entry.get('id', '?')}: {exc}")
            continue
        verdicts.append(
            {
                "id": entry.get("id"),
                "case": entry.get("case"),
                "reader": entry.get("reader"),
                "path": entry.get("path"),
                "expected": entry.get("expected"),
                "actual": actual,
            }
        )
        if actual != entry.get("expected"):
            problems.append(
                f"{entry.get('id', '?')}: reader {entry.get('reader')} gave "
                f"{actual}, manifest expects {entry.get('expected')}"
            )

    return {
        "root": str(root),
        "manifest": str(manifest_path),
        "entries": len(doc.get("corpus", [])),
        "problems": problems,
        "verdicts": verdicts,
        "result": "PASS" if not problems else "FAIL",
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _print_build(report: dict, as_json: bool) -> None:
    if as_json:
        payload = {k: v for k, v in report.items() if k != "document"}
        print(json.dumps(payload, indent=2))
        return
    print(f"corpus    {report['root']}")
    print(f"manifest  {report['manifest']} ({report['entries']} entries)")
    for case, count in report["cases"].items():
        print(f"  {case:<20} {count}")
    for note in report["skipped"]:
        print(f"  skipped: {note}")
    print(f"RESULT: {report['result']} ({report['entries']} entries)")


def _print_check(report: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(report, indent=2))
        return
    for problem in report["problems"]:
        print(f"FAIL {problem}")
    if report["problems"]:
        print(f"RESULT: FAIL ({len(report['problems'])} problem(s))")
    else:
        print(f"RESULT: PASS ({report['entries']} entries re-read)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build or check the synthetic L3 corpus"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    build_cmd = sub.add_parser("build", help="generate a corpus directory")
    build_cmd.add_argument("directory")
    build_cmd.add_argument("--json", action="store_true")

    check_cmd = sub.add_parser("check", help="validate and re-read a corpus")
    check_cmd.add_argument("directory")
    check_cmd.add_argument("--json", action="store_true")

    sub.add_parser("selftest", help="run the corpus self-test")
    return parser


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["--selftest"]:
        argv = ["selftest"]

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "selftest":
        return run_selftest()

    try:
        if args.command == "build":
            report = build_corpus(args.directory)
            _print_build(report, args.json)
            return 0
        report = check_corpus(args.directory)
        _print_check(report, args.json)
        return 0 if report["result"] == "PASS" else 1
    except (CorpusError, manifest.ManifestError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


# --------------------------------------------------------------------------
# self-test
# --------------------------------------------------------------------------

CHECKS: list[tuple[str, callable]] = []


def check(name):
    def register(func):
        CHECKS.append((name, func))
        return func

    return register


def _build(tmp, name="corpus") -> tuple[Path, dict]:
    root = Path(tmp) / name
    report = build_corpus(root)
    return root, report


@check("build: every non-factory case is present")
def test_build_cases(tmp):
    root, report = _build(tmp)
    doc = report["document"]
    assert not manifest.validate(doc, root=root), manifest.validate(doc, root=root)
    cases = {entry["case"] for entry in doc["corpus"]}
    expected = set(manifest.CASES) - {"factory"}
    missing = expected - cases
    assert not missing, f"cases missing from the manifest: {sorted(missing)}"
    vendor = [e for e in doc["corpus"] if e["path"].startswith("factory/")]
    assert not vendor, f"vendor factory pair must be skipped: {vendor}"
    assert report["skipped"], "the skipped factory placeholder must be reported"
    assert (root / "manifest.json").is_file()
    assert (root / "factory" / "README.txt").is_file()


@check("build: deterministic across two runs")
def test_build_deterministic(tmp):
    first, _ = _build(tmp, "one")
    second, _ = _build(tmp, "two")
    a = json.loads((first / "manifest.json").read_text())
    b = json.loads((second / "manifest.json").read_text())
    assert a == b, "two builds produced different manifests"


@check("build: factory placeholder is used when the pair exists")
def test_build_factory(tmp):
    root, report = _build(tmp)
    pair = first_pair(root)
    (root / "factory").mkdir(parents=True, exist_ok=True)
    (root / "factory" / "ADDRE001.DAT.cmp").write_bytes(pair[0])
    (root / "factory" / "ADDRE001.DAT.ind").write_bytes(pair[1])
    report = build_corpus(root)
    assert not report["skipped"], report["skipped"]
    entries = [
        e for e in report["document"]["corpus"]
        if e["case"] == "factory" and e["path"].startswith("factory/")
    ]
    assert len(entries) == 1, entries
    assert entries[0]["path"] == "factory/ADDRE001.DAT.cmp"
    assert entries[0]["expected"] == "ACCEPT"
    assert verdict_cmp_ind(root, entries[0]["path"]) == "ACCEPT"


def first_pair(root: Path) -> tuple[bytes, bytes]:
    base = root / "cmp" / "factory"
    return (
        (base / "ADDRE001.DAT.cmp").read_bytes(),
        (base / "ADDRE001.DAT.ind").read_bytes(),
    )


@check("readers: every expected verdict is reproduced")
def test_verdicts(tmp):
    root, report = _build(tmp)
    doc = report["document"]
    seen = {}
    for entry in doc["corpus"]:
        actual = entry_verdict(root, entry)
        assert actual == entry["expected"], (
            f"{entry['id']}: {entry['reader']} gave {actual}, "
            f"expected {entry['expected']}"
        )
        seen.setdefault(entry["reader"], set()).add(actual)
    # The manifest schema has no rejecting ``tile`` case, so require every
    # verdict the case table allows for a reader rather than both literals.
    allowed = {
        reader: {
            spec["verdict"]
            for spec in manifest.CASES.values()
            if reader in spec["readers"]
        }
        for reader in manifest.READERS
    }
    for reader, verdicts in seen.items():
        assert allowed[reader] <= verdicts, (
            f"{reader} covered {verdicts}, cases allow {allowed[reader]}"
        )
    assert set(seen) == {"cmp_ind", "drstr", "tile", "hdd_info"}, sorted(seen)


@check("readers: hdd_info discriminates line 1 and line 4")
def test_hdd_info_discriminators(tmp):
    root, _ = _build(tmp)
    system = hddinfo.HddInfo.parse((root / HDD_REFERENCE).read_bytes())
    base = hddinfo.HddInfo.parse((root / "hdd_info/factory/HDD_INFO.TXT").read_bytes())
    result = hddinfo.classify(system, base)
    assert result["accepted"]
    causes = set()
    for name in HDD_MISMATCHES:
        record = hddinfo.HddInfo.parse(
            (root / HDD_VARIANTS_DIR / name).read_bytes()
        )
        verdict = hddinfo.classify(system, record)
        assert not verdict["accepted"], name
        for reason in verdict["reasons"]:
            causes.add(reason.split(":")[0])
    assert causes == {"manufacturer_id", "userdata_type", "destination_id"}, causes


@check("readers: the full hddinfo_variants.py matrix is in the manifest")
def test_hdd_matrix(tmp):
    root, report = _build(tmp)
    entries = [
        e for e in report["document"]["corpus"]
        if e["reader"] == "hdd_info" and e["path"].startswith(HDD_VARIANTS_DIR + "/")
    ]
    assert len(entries) == HDD_VARIANTS, len(entries)
    accepted = sum(1 for e in entries if e["expected"] == "ACCEPT")
    rejected = sum(1 for e in entries if e["expected"] == "REJECT")
    assert (accepted, rejected) == (HDD_VARIANTS_ACCEPT, HDD_VARIANTS_REJECT), (
        accepted,
        rejected,
    )
    for entry in entries:
        assert entry_verdict(root, entry) == entry["expected"], entry["path"]


@check("tile: the edit moves exactly one vertex")
def test_tile_edit(tmp):
    root, _ = _build(tmp)
    before = read_tile(root / "tile" / "B28R070R.DAT")["vertices"]
    after = read_tile(root / "tile" / "B28R070R.edited.DAT")["vertices"]
    assert len(before) == len(after) == len(TILE_VERTICES)
    diff = [(a, b) for a, b in zip(before, after) if a != b]
    assert diff == [((100, 200), (110, 200))], diff
    assert verdict_tile(root, "tile/B28R070R.edited.DAT") == "ACCEPT"


@check("tile: corrupt containers are rejected")
def test_tile_negatives(tmp):
    root, _ = _build(tmp)
    data = (root / "tile" / "B28R070R.DAT").read_bytes()

    broken = bytearray(data)
    broken[TILE_BLOCK + 4] ^= 0xFF
    assert _rejects(read_tile, bytes(broken)), "corrupt zlib byte accepted"

    broken = bytearray(data)
    struct.pack_into(">I", broken, TILE_DIR + 12, 0)  # slot tag -> 0
    assert _rejects(read_tile, bytes(broken)), "slot tag 0 accepted"

    broken = bytearray(data)
    struct.pack_into(">I", broken, TILE_DIR + 16, 0xFFFF)  # pair word count
    assert _rejects(read_tile, bytes(broken)), "wrong pair word count accepted"

    broken = bytearray(data)
    struct.pack_into(">I", broken, TILE_DIR + 20, 1)  # inflated word count
    assert _rejects(read_tile, bytes(broken)), "wrong inflated size accepted"

    words = struct.unpack_from(">I", data, TILE_DIR + 16)[0]
    record_end = TILE_BLOCK + 2 * words
    assert record_end <= len(data), "synthetic record runs past the padded file"
    # The 256-byte padding after the record is not data; cut inside the record.
    assert _rejects(read_tile, data[:record_end - 1]), "truncated record accepted"
    assert _rejects(read_tile, data[:TILE_HEADER]), "header-only tile accepted"
    assert _rejects(read_tile, b""), "empty tile accepted"


def _rejects(func, *args) -> bool:
    try:
        func(*args)
    except (TileError, CorpusError, OSError):
        return True
    return False


@check("drstr: ordering is free, sentinel and sizes are not")
def test_drstr_controls(tmp):
    root, _ = _build(tmp)
    tree = (root / "drstr" / "DRSTR001.DAT").read_bytes()
    reordered = (root / "drstr" / "DRSTR001.reordered.DAT").read_bytes()
    mismatched = (root / "drstr" / "DRSTR001.size-mismatch.DAT").read_bytes()

    assert _drstr_problems(tree) == [], _drstr_problems(tree)
    assert _drstr_problems(reordered) == [], _drstr_problems(reordered)

    def names(data):
        parsed = drstr.parse(data)
        return {
            (node["index"], tuple(sorted(e["name"] for e in node["entries"])))
            for node in parsed["nodes"]
        }

    assert names(tree) == names(reordered), "reordering changed the entry sets"
    assert _drstr_problems(mismatched), "size mismatch was accepted"

    sentinel = bytearray(tree)
    sentinel[0:2] = b"X\x00"  # root name no longer "/"
    assert _drstr_problems(bytes(sentinel)), "broken root sentinel accepted"

    orphan = bytearray(tree)
    struct.pack_into("<H", orphan, drstr.NODE_SIZE + 0x16, 0)  # parent_plus_1 = 0
    assert _drstr_problems(bytes(orphan)), "orphan node accepted"

    assert verdict_drstr(root, "drstr/DRSTR001.reordered.DAT") == "ACCEPT"
    assert verdict_drstr(root, "drstr/DRSTR001.size-mismatch.DAT") == "REJECT"


@check("cmp: every ind_mutate.py variant is rejected")
def test_ind_variants(tmp):
    root, _ = _build(tmp)
    for variant in IND_VARIANTS:
        path = root / "cmp" / "corrupt-ind" / variant / "ADDRE001.DAT.cmp"
        try:
            cmpind.decode(path)
        except cmpind.FormatError:
            continue
        raise AssertionError(f"{variant} was accepted")


@check("check: PASS, then FAIL on a manifest or fixture change")
def test_check_roundtrip(tmp):
    root, _ = _build(tmp)
    report = check_corpus(root)
    assert report["result"] == "PASS", report["problems"]
    assert report["entries"] == len(report["verdicts"])

    doc = json.loads((root / "manifest.json").read_text())
    doc["corpus"][0]["sha256"] = "0" * 64
    (root / "manifest.json").write_text(json.dumps(doc, indent=2))
    report = check_corpus(root)
    assert report["result"] == "FAIL"
    assert any("sha256 mismatch" in p for p in report["problems"]), report["problems"]

    # restore the manifest, then break the data instead
    root, _ = _build(tmp, "again")
    target = root / "tile" / "B28R070R.DAT"
    data = bytearray(target.read_bytes())
    data[TILE_BLOCK + 4] ^= 0xFF
    target.write_bytes(bytes(data))
    report = check_corpus(root)
    assert report["result"] == "FAIL"
    assert any("tile" in p for p in report["problems"]), report["problems"]


@check("check: vendor reader cross-check when it is installed")
def test_vendor_tile(tmp):
    root, _ = _build(tmp)
    state = vendor_tile_roundtrip((root / "tile" / "B28R070R.DAT").read_bytes())
    if state is None:
        print("     (tools/ze0-viewer/tools_ze0 absent: vendor cross-check skipped)")
        return
    assert state, "the vendored clarion_tile did not round-trip the corpus tile"
    assert vendor_tile_roundtrip(
        (root / "tile" / "B28R070R.edited.DAT").read_bytes()
    ), "the vendored clarion_tile did not round-trip the edited tile"


def run_selftest() -> int:
    failures = 0
    for name, func in CHECKS:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                func(tmp)
            except Exception as exc:  # noqa: BLE001 - report, do not abort
                failures += 1
                print(f"FAIL {name}: {exc}")
                import traceback

                if __import__("os").environ.get("L3_SELFTEST_VERBOSE"):
                    traceback.print_exc()
            else:
                print(f"ok   {name}")
    print()
    if failures:
        print(f"corpus selftest: FAILED ({failures}/{len(CHECKS)} checks)")
        return 1
    print(f"corpus selftest: OK ({len(CHECKS)} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
