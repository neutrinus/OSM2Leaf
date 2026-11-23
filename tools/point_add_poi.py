#!/usr/bin/env python3
"""Place one new POI (name + position) into a factory POINT pair (M5.82).

Unlike ``point_move_poi`` (M5.63), which edits an existing record and an
existing leaf inside one copy-A cell, this tool *adds* a 15,470th name record,
a spatial-tree leaf and a name-search index key to a copy of the EU 2011
``POINT010`` pair.  Every structure is reached through the same locator the
firmware reader uses; no offset is guessed and no byte is hand-patched.

The three writes are deliberately local:

* the name page grows by one record, so the 1000-page chain is relocated to
  the end of the ``.DAT`` (M4.47: the firmware page loader follows the locator);
* one 16-byte leaf is inserted before the terminator of the host's leaf node,
  consuming part of the zero gap to the next node (no file-size change);
* one 24-byte index key is appended to the last index chain stream, consuming
  part of its 76-byte slack (STOP if it does not fit).

Stock zlib 1.3.1 is required (``--libz``) because the factory streams are the
encoder's own control: ``check_factory_encoder`` must reproduce all old pages.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
import zlib
from pathlib import Path

import cmpind
import cmpind_codec
import coord
import mutate_refer_poi as mrp
import point_census as pc
import point_pair_regen as regen
import point_move_poi as mrp_move
import zlibinfo

TOOL = "tools/point_add_poi.py"
TASK = "M5.82"
NAME_CHAIN = 1000
CELL_NAME_TRIE = pc.CELL_NAME_TRIE
NEW_NAME = "OSM2LEAF NEW POI"
INDEX_SLACK_LIMIT = 76                 # measured on POINT010 (see EXP)
LEAF_GAP_WORDS = 8                     # one 16-byte entry
SPATIAL_ENTRY = pc.SPATIAL_ENTRY       # >HIHHHI, size_w at +6
TERMINATOR_PREFIX = b"\x00\x05\xff\xff\xff\xff"   # census checks head + u32 only;
TERMINATOR_SIZE = 10                              # the last 4 bytes are per-node
INDEX_ENTRY = 24
POI_ORDINAL_FIELD = 20
CHAIN_WORDS_OFFSET = 0x1016            # ref at 0x1002 + 20 (verified, not 0x1012)


class AddError(ValueError):
    """The placement is refused; nothing is written."""


# ---------------------------------------------------------------------------
# synthetic fixtures (selftest only)
# ---------------------------------------------------------------------------


def synthetic_template() -> bytes:
    """A placeable class-3 name record with a 9-field area (no vendor bytes)."""
    rec = bytearray(64)
    struct.pack_into(">H", rec, 0, 0x6000 | (len(rec) // 2))
    struct.pack_into(">4H", rec, 2, 40000, 53000, 0x800 | 100, 200)
    rec[10:12] = b"\x00\x01"                      # loc = 2*(0+1+8) = 18
    lens = [2, 1, 1, 1, 1, 9, 1, 1, 1]            # 18 words; 10 B table -> 64 B
    for i, n in enumerate(lens):
        rec[18 + i] = n
    start = 18 + 10 + 2 * sum(lens[:mrp.NAME_FIELD])
    text = "OLD POI NAME".encode("latin-1").ljust(18, b"\x00")
    rec[start:start + 18] = text
    rec[-2:] = b"\xff\xff"
    mrp.name_field(bytes(rec))                     # raises if the layout is wrong
    return bytes(rec)


# ---------------------------------------------------------------------------
# name record
# ---------------------------------------------------------------------------


def build_record(template: bytes, name: str, ax: int, ay: int,
                 flon: int, flat: int) -> bytes:
    """Clone *template* and replace its position and its name field.

    The other fields (area, category levels, brand) are kept verbatim, so an
    index key cloned from the template still occurs in the new record.
    """
    try:
        start, words, layout = mrp.name_field(template)
    except mrp.PageError as exc:
        raise AddError(f"the template record is not placeable: {exc}") from exc
    text = name.encode("latin-1")
    if not text or any(c < 0x20 or c > 0x7E for c in text):
        raise AddError("the name must be printable ASCII (Latin-1, no NUL)")
    if len(text) % 2:
        text += b"\x00"
    new_words = len(text) // 2
    if len(template) + len(text) - 2 * words > 0x1FE:
        raise AddError(f"the new record would be {len(template) + len(text) - 2 * words} B "
                       "(len2 is one byte, max 510 B)")
    rec = bytearray(template)
    struct.pack_into(">4H", rec, 2, ax, ay, 0x800 | flon, flat)
    rec[start:start + 2 * words] = text
    # field-5 length byte moved with the text; set it in the final layout
    lay = mrp.field_layout(bytes(rec))
    rec[lay["loc"] + mrp.NAME_FIELD] = new_words
    rec[1] = len(rec) // 2
    struct.pack_into(">H", rec, 0, (rec[0] << 8) | rec[1])
    out = bytes(rec)
    if out[-2:] != b"\xff\xff":
        raise AddError("the new record does not end with the ff ff terminator")
    got_start, got_words, _ = mrp.name_field(out)
    if got_words != new_words or out[got_start:got_start + 2 * got_words] != text:
        raise AddError("the firmware field accessor would not read the new name")
    ax2, ay2, v6, v8 = pc.fine_fields(out)
    if (ax2, ay2, v6, v8) != (ax, ay, flon & 0x7FF, flat & 0x7FF):
        raise AddError("the fine position did not round-trip through the record")
    return out


# ---------------------------------------------------------------------------
# spatial tree: locate the host leaf's node
# ---------------------------------------------------------------------------


class LeafContext:
    __slots__ = ("tree", "base", "tree_words", "pos", "kx", "ky", "depth",
                 "term", "node_end", "node_size", "parent_csize", "gap_words")

    def __init__(self, **kw):
        for key, value in kw.items():
            setattr(self, key, value)

    @property
    def new_node_end(self) -> int:
        return self.node_end + 2 * LEAF_GAP_WORDS

    @property
    def allowed(self) -> tuple[tuple[int, int], ...]:
        return ((self.pos, self.term + 16 + TERMINATOR_SIZE),
                (self.parent_csize, self.parent_csize + 2))


def leaf_contexts(blob: bytes, ptr: int) -> list[LeafContext]:
    """Every leaf that points at record *ptr*, with its node and parent word."""
    out: list[LeafContext] = []
    for ref in mrp_move.spatial_refs(blob):
        tree_base, tree_words = ref["start"], ref["words"]
        stack = [(0, ref["root_words"], 0, (0, 0), None)]
        nodes: list[tuple[int, int, int]] = []
        found: list[tuple[int, int, int, int, int, int, int, int]] = []
        while stack:
            off, size, depth, key, parent_csize = stack.pop()
            nodes.append((off, size, depth))
            pos, end = tree_base + 2 * off, tree_base + 2 * (off + size)
            p, term, leaves = pos, None, []
            while p < end:
                (head,) = struct.unpack_from(">H", blob, p)
                if head == 5:
                    term = p
                    p += 10
                    continue
                if head != 8:
                    raise AddError(f"spatial {tree_base:#x}: bad entry head {head:#x} at {p:#x}")
                _, leaf_ptr, csize, kx, ky, _fine = SPATIAL_ENTRY.unpack_from(blob, p)
                if csize:
                    stack.append((leaf_ptr, csize, depth + 1,
                                  (kx, ky) if depth < pc.CELL_DEPTH else key, p + 6))
                elif leaf_ptr == ptr:
                    leaves.append((p, kx, ky))
                p += 16
            if p != end or term is None:
                raise AddError(f"spatial {tree_base:#x}: node {off:#x} overruns or has no terminator")
            for leaf_pos, kx, ky in leaves:
                found.append((leaf_pos, kx, ky, depth, term, end, parent_csize, off))
        nodes.sort()
        indexed = {off: i for i, (off, _, _) in enumerate(nodes)}
        sizes = {off: size for off, size, _ in nodes}
        for leaf_pos, kx, ky, depth, term, end, parent_csize, node_off in found:
            if parent_csize is None:
                continue                       # a leaf in the root would be shallow
            i = indexed[node_off]
            if i + 1 < len(nodes):
                gap = nodes[i + 1][0] - (node_off + sizes[node_off])
            else:
                gap = tree_words - (node_off + sizes[node_off])
            out.append(LeafContext(tree=tree_base, base=tree_base, tree_words=tree_words,
                                   pos=leaf_pos, kx=kx, ky=ky, depth=depth, term=term,
                                   node_end=end, node_size=sizes[node_off],
                                   parent_csize=parent_csize, gap_words=gap))
    return out


def insert_leaf(out: bytearray, ctx: LeafContext, ordinal: int,
                flon: int, flat: int) -> dict:
    """Insert one 0x0800 / code-63 leaf and grow its parent's csize."""
    if ctx.depth < pc.CELL_DEPTH:
        raise AddError(f"leaf at depth {ctx.depth} would be a shallow leaf")
    if ctx.gap_words < LEAF_GAP_WORDS:
        raise AddError(f"node at {ctx.pos:#x}: only {ctx.gap_words} words of gap, need "
                       f"{LEAF_GAP_WORDS}; no hand-patching")
    if ctx.new_node_end > ctx.base + 2 * ctx.tree_words:
        raise AddError(f"node at {ctx.pos:#x}: grown end {ctx.new_node_end:#x} is past "
                       f"the declared tree end {ctx.base + 2 * ctx.tree_words:#x}")
    fine = ((0x8800 | flon) << 16) | (0xF800 | flat)
    term_bytes = bytes(out[ctx.term:ctx.term + TERMINATOR_SIZE])
    if term_bytes[:6] != TERMINATOR_PREFIX:
        raise AddError(f"unexpected spatial terminator at {ctx.term:#x}: {term_bytes.hex()}")
    (old_csize,) = struct.unpack_from(">H", out, ctx.parent_csize)
    SPATIAL_ENTRY.pack_into(out, ctx.term, 8, ordinal, 0, ctx.kx, ctx.ky, fine)
    out[ctx.term + 16:ctx.term + 16 + TERMINATOR_SIZE] = term_bytes
    struct.pack_into(">H", out, ctx.parent_csize, old_csize + LEAF_GAP_WORDS)
    return {"pos": ctx.pos, "term": ctx.term, "parent_csize": ctx.parent_csize,
            "old_csize": old_csize, "new_csize": old_csize + LEAF_GAP_WORDS,
            "gap_words": ctx.gap_words, "depth": ctx.depth, "fine": f"{fine:#010x}"}


# ---------------------------------------------------------------------------
# name trie index chain: append one 24-byte key
# ---------------------------------------------------------------------------


def index_ref(blob: bytes) -> dict:
    """The descriptor reference of the whole-file name trie (cell 0x824)."""
    cells = {cell: (rec, _blocks) for cell, rec, _blocks in regen.directory(blob)}
    if CELL_NAME_TRIE not in cells:
        raise AddError("no name-trie directory cell")
    return pc.read_ref(blob, cells[CELL_NAME_TRIE][0] + 2)


def clone_index_key(data: bytes, template: bytes, ordinal: int) -> bytes:
    for pos in range(0, len(data) - INDEX_ENTRY + 1, INDEX_ENTRY):
        entry = data[pos:pos + INDEX_ENTRY]
        key = pc.index_key(entry)
        if key and key in template:
            out = bytearray(entry)
            struct.pack_into(">I", out, POI_ORDINAL_FIELD, ordinal)
            return bytes(out)
    raise AddError("no index key of an existing record occurs in the template")


def append_index_key(out: bytearray, old_blob: bytes, enc: regen.Encoder,
                     entry: bytes, break_key: bool = False) -> dict:
    """Recompress the last index stream with one more record, in its slack."""
    ref = index_ref(old_blob)
    start, words = ref["chain"], ref["chain_words"]
    n = 1
    while old_blob[start + 4 + 4 * n] != 0x78:
        n += 1
        if n > 4096:
            raise AddError("index chain has no stream table")
    lens = list(struct.unpack_from(f">{n}I", old_blob, start + 4))
    data, end, _streams = pc.read_index_chain(old_blob, start, words)
    if len(data) % INDEX_ENTRY:
        raise AddError("inflated index chain is not a whole number of records")
    # stream sizes are fixed at 20000 records except the last (M3.2)
    per_stream = pc.INDEX_PER_STREAM * INDEX_ENTRY
    prefix = data[:len(data) - (len(data) % per_stream or per_stream)]
    last = data[len(prefix):]
    if break_key:
        broken = bytearray(entry)
        broken[0] ^= 0x01                       # corrupt key word 0, keep the stream valid
        entry = bytes(broken)
    stream = enc.compress(last + entry)
    new_comp_w = (len(stream) + 1) // 2
    stream_at = start + 4 + 4 * n + 2 * sum(lens[:-1])
    new_end = stream_at + 2 * new_comp_w
    slack_needed = new_end - end
    if slack_needed > INDEX_SLACK_LIMIT:
        raise AddError(f"index stream needs {slack_needed} B of slack, only "
                       f"{INDEX_SLACK_LIMIT} B available; no hand-patching")
    if new_end >= 0xD7100:                    # next claimed structure on POINT010
        raise AddError(f"grown index chain ends at {new_end:#x}, past 0xd7100")
    out[stream_at:new_end] = stream.ljust(2 * new_comp_w, b"\x00")
    lens[-1] = new_comp_w
    struct.pack_into(f">{n}I", out, start + 4, *lens)
    struct.pack_into(">I", out, CHAIN_WORDS_OFFSET, words + INDEX_ENTRY // 2)
    new_words = words + INDEX_ENTRY // 2
    got, got_end, _ = pc.read_index_chain(bytes(out), start, new_words)
    if got != data + entry or got_end != new_end:
        raise AddError("the grown index chain does not read back byte for byte")
    return {"start": start, "old_words": words, "new_words": new_words,
            "old_end": end, "new_end": new_end, "slack_needed": slack_needed,
            "streams": n, "last_comp_w": new_comp_w}


# ---------------------------------------------------------------------------
# changed-byte envelope
# ---------------------------------------------------------------------------


def changed_ranges(old: bytes, new: bytes) -> list[tuple[int, int]]:
    out = []
    i = 0
    n = min(len(old), len(new))
    while i < n:
        if old[i] != new[i]:
            j = i + 1
            while j < n and old[j] != new[j]:
                j += 1
            out.append((i, j))
            i = j
        else:
            i += 1
    if len(new) > n:
        out.append((n, len(new)))
    return out


def envelope_ok(ranges: list[tuple[int, int]], allowed: list[tuple[int, int]]) -> list[tuple[int, int]]:
    return [(a, b) for a, b in ranges
            if not any(lo <= a and b <= hi for lo, hi in allowed)]


# ---------------------------------------------------------------------------
# main placement
# ---------------------------------------------------------------------------


def choose_target(blob: bytes, rows: list[dict], lat: float | None, lon: float | None):
    """Pick a host record and a new position in the same copy-A cell."""
    by_index = {r["index"]: r for r in rows}
    for row in rows:
        # A 0x60 name record needs a matching 400-chain INFORMATION record;
        # a 0x68 record does not (refer.md / joins' records_400 == tag60).
        if row["rec"][0] != 0x68:
            continue
        try:
            mrp.name_field(row["rec"])
        except mrp.PageError:
            continue
        ax, ay, v6, v8 = pc.fine_fields(row["rec"])
        raw6, raw8 = struct.unpack_from(">2H", row["rec"], 6)
        if raw6 >> 11 != 1 or raw8 > 0x7FF:
            continue
        ctxs = leaf_contexts(blob, row["index"])
        if not ctxs:
            continue
        ctx = next((c for c in ctxs if c.depth >= pc.CELL_DEPTH
                    and c.gap_words >= LEAF_GAP_WORDS), None)
        if ctx is None:
            continue
        if lat is None or lon is None:
            # one deterministic synthetic position ~36 m from the host,
            # guaranteed to be inside the same copy-A cell
            plat, plon = coord.decode_point_id(ax, ay, (v6 & 0x7FF) + 32, min(0x7FF, v8 + 32))
            tx, ty, t6, t8 = coord.encode_point_id(plat, plon)
            if (tx, ty) != (ax, ay):
                continue
            lat, lon = plat, plon
        else:
            tx, ty, t6, t8 = coord.encode_point_id(lat, lon)
            if (tx, ty) != (ax, ay):
                continue
        return row, ctx, lat, lon, (tx, ty, t6 & 0x7FF, t8 & 0x7FF)
    raise AddError("no host record has a leaf node with room in the requested cell")


def place(blob: bytes, enc: regen.Encoder, name: str, lat: float | None,
          lon: float | None, control: str = "none") -> tuple[bytes, dict]:
    old = bytes(blob)
    bad = regen.check_factory_encoder(old, regen.chain_via_locator(old, NAME_CHAIN), enc)
    if bad:
        raise AddError(f"encoder {enc.version} does not reproduce {len(bad)} factory pages")
    ch = regen.chain_via_locator(old, NAME_CHAIN)
    rows = mrp_move.name_records(old, ch)
    row, ctx, lat, lon, (ax, ay, flon, flat) = choose_target(old, rows, lat, lon)
    ordinal = len(rows)
    new_rec = build_record(row["rec"], name, ax, ay, flon, flat)
    iref = index_ref(old)
    index_data, _, _ = pc.read_index_chain(old, iref["chain"], iref["chain_words"])
    key = clone_index_key(index_data, new_rec, ordinal)

    # 1. relocate the grown 1000-page chain (M4.47 locator, no slot limit)
    inner_last = bytearray(ch.pages[-1][2])
    inner_last += new_rec
    new_inners = [p[2] for p in ch.pages]
    new_inners[-1] = bytes(inner_last)
    olds = [old[off:off + used] for off, used, _ in ch.pages]
    body, entries = regen.pack_chain(ch, new_inners, enc, olds)
    toc = regen.toc_bytes(ch.per_page, entries)
    if len(toc) != ch.toc_size:
        raise AddError("chain table size changed")
    new_base = -(-len(old) // regen.BLOCK) * regen.BLOCK
    out = bytearray(old) + bytes(new_base - len(old)) + body
    out += bytes((-len(out)) % regen.BLOCK)
    out[ch.base:ch.end] = bytes(ch.end - ch.base)
    out[ch.toc:ch.toc + len(toc)] = toc
    pb, _ = regen.locator_positions(old, NAME_CHAIN)
    struct.pack_into(">II", out, pb, regen.blk_addr(new_base), len(body) // 2)

    # 2. one spatial leaf, 3. one index key
    leaf = insert_leaf(out, ctx, ordinal, flon, flat)
    index = append_index_key(out, old, enc, key, break_key=(control == "break-index"))

    # 4. structural read-back before any bytes leave the process
    rep = pc.census(bytes(out), want_joins=True)
    if not rep.get("ok"):
        failed = [text for text, good in rep["checks"] if not good]
        raise AddError(f"point_census rejects the built blob: {failed[:3]}")
    if rep["classes"].get("unaccounted", 0):
        raise AddError(f"unaccounted bytes: {rep['classes']['unaccounted']}")
    # read the name back through the same accessor the firmware uses
    new_chain = regen.chain_via_locator(bytes(out), NAME_CHAIN)
    new_page = regen.walk_records(new_chain.pages[-1][2])
    if not new_page:
        raise AddError("the grown name page does not parse as a record chain")
    last_rec = new_chain.pages[-1][2][new_page[-1][0]:new_page[-1][0] + new_page[-1][1]]
    readback = mrp_move.record_name(last_rec)
    if readback.rstrip("\x00") != name:
        raise AddError(f"name read-back mismatch: {readback!r} != {name!r}")
    j = rep["joins"]
    if control != "break-index" and not (
            j["spatial"]["match"] == j["spatial"]["leaves"]
            and j["index"]["match"] == j["index"]["records"]
            and not j["index"]["id_out_of_range"]):
        raise AddError("point_census joins do not hold on the built blob")
    if j["spatial"]["leaves"] != 15379:
        raise AddError(f"expected exactly one new leaf (15,379), got {j['spatial']['leaves']}")

    allowed = [
        (ch.base, ch.end), (ch.toc, ch.toc + ch.toc_size), (pb, pb + 8),
        (new_base, len(out)),            # appended chain + its alignment padding
        (index["start"], index["new_end"] + 8),
        (CHAIN_WORDS_OFFSET, CHAIN_WORDS_OFFSET + 4),
    ] + list(ctx.allowed)
    outside = envelope_ok(changed_ranges(old, bytes(out)), allowed)
    if outside:
        raise AddError(f"{len(outside)} changed range(s) outside the named structures: "
                       f"{[(hex(a), hex(b)) for a, b in outside[:4]]}")

    new_page = new_base + 2 * entries[15][0]
    report = {
        "task": TASK, "tool": TOOL, "name": name, "lat": lat, "lon": lon,
        "host_record": row["index"], "host_name": mrp_move.record_name(row["rec"]),
        "ordinal": ordinal, "readback_name": readback,
        "position": [ax, ay, flon, flat],
        "cell": [ax, ay], "leaf": leaf, "index": index,
        "relocate": {"old_base": ch.base, "new_base": new_base,
                     "old_bytes": ch.end - ch.base, "new_bytes": len(body),
                     "page_15_inflated": len(inner_last), "table": ch.toc},
        "new_page": new_page, "new_page_slot": entries[15][1] * 2,
        "new_record_page_index": 469, "census": {"leaves": j["spatial"]["leaves"],
                                                "index": j["index"]["records"],
                                                "unaccounted": rep["classes"].get("unaccounted", 0)},
        "changed_ranges": len(changed_ranges(old, bytes(out))),
        "outside_changed": len(outside),
        "encoder": enc.describe(),
    }
    return bytes(out), report


def write_out(cmp_path: Path, out_dir: Path, old_blob: bytes,
              new_blob: bytes, enc: regen.Encoder) -> tuple[Path, Path]:
    blob, packed, offsets, _usize, chunk = regen.read_pair(cmp_path)
    cmp_new, ind_new = regen.write_pair_grown(packed, offsets, chunk, old_blob, new_blob, enc)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = cmp_path.name
    (out_dir / stem).write_bytes(cmp_new)
    (out_dir / stem.replace(".cmp", ".ind")).write_bytes(ind_new)
    return out_dir / stem, out_dir / stem.replace(".cmp", ".ind")


def run_add(args) -> int:
    if not args.libz and not args.allow_nonreference:
        print(f"REFUSED: stock zlib 1.3.1 is required (--libz); "
              f"this host is {zlibinfo.classify()}")
        return zlibinfo.EXIT_UNVERIFIABLE
    enc = regen.Encoder(args.libz)
    if not enc.is_reference and not args.allow_nonreference:
        print(f"REFUSED: encoder is zlib {enc.version}, not the pinned "
              f"{regen.REFERENCE_ZLIB}; byte identity is unverifiable on this host")
        return zlibinfo.EXIT_UNVERIFIABLE
    cmp_path = Path(args.cmp)
    blob, _packed, _offs, _usize, _chunk = regen.read_pair(cmp_path)
    if args.noop:
        out_dir = Path(args.outdir)
        c, i = write_out(cmp_path, out_dir, blob, blob, enc)
        same_c = c.read_bytes() == cmp_path.read_bytes()
        same_i = i.read_bytes() == Path(args.ind).read_bytes() if args.ind else True
        print(f"noop: cmp identical {same_c} ind identical {same_i}")
        if args.json:
            Path(args.json).write_text(json.dumps({"noop": True, "cmp_identical": same_c,
                                                   "ind_identical": same_i}, indent=1))
        return 0 if same_c and same_i else 1
    try:
        out, report = place(blob, enc, args.name or NEW_NAME, args.lat, args.lon,
                            control=args.control)
    except AddError as exc:
        print(f"REFUSED: {exc}")
        if args.json:
            Path(args.json).write_text(json.dumps({"refused": str(exc)}, indent=1))
        return 1
    if args.control == "break-leaf":
        mutated = bytearray(out)
        pos = report["leaf"]["pos"] + 14          # low half of the leaf's fine word
        mutated[pos] ^= 0x01
        out = bytes(mutated)
        report["control"] = "break-leaf"
    elif args.control == "break-index":
        report["control"] = "break-index"
    c, i = write_out(cmp_path, Path(args.outdir), blob, out, enc)
    report["sha256_cmp"] = hashlib.sha256(c.read_bytes()).hexdigest()
    report["sha256_ind"] = hashlib.sha256(i.read_bytes()).hexdigest()
    print(f"placed {report['name']!r} at {report['lat']:.7f},{report['lon']:.7f} "
          f"as record {report['ordinal']} (cell {report['cell']})")
    print(f"name chain {report['relocate']['old_base']:#x} -> "
          f"{report['relocate']['new_base']:#x}; leaf at {report['leaf']['pos']:#x}; "
          f"index {report['index']['old_words']} -> {report['index']['new_words']} words")
    print(f"census: leaves {report['census']['leaves']}, index {report['census']['index']}, "
          f"unaccounted {report['census']['unaccounted']}; changed ranges "
          f"{report['changed_ranges']}, outside {report['outside_changed']}")
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=1))
    return 0


# ---------------------------------------------------------------------------
# selftest (synthetic only)
# ---------------------------------------------------------------------------


def selftest() -> int:
    checks = []

    def ok(cond, label):
        checks.append(bool(cond))
        print(f"  {'ok' if cond else 'FAIL'}  {label}")

    t = synthetic_template()
    rec = build_record(t, "OSM2LEAF NEW POI", 40000, 53000, 132, 244)
    start, words, _ = mrp.name_field(rec)
    ok(rec[start:start + 2 * words].rstrip(b"\x00") == b"OSM2LEAF NEW POI", "name replaced")
    ok(pc.fine_fields(rec) == (40000, 53000, 132, 244), "position replaced")
    ok(rec[-2:] == b"\xff\xff" and len(rec) % 2 == 0, "framing intact")
    try:
        build_record(t, "X" * 600, 40000, 53000, 132, 244)
        ok(False, "over-long name refused")
    except AddError:
        ok(True, "over-long name refused")
    words12 = [0x1234, 0x5678, 0xFFFF, 0xFFFF, 0x0102, 0x0304,
               0x1111, 0x2222, 0x3333, 0x4444, 0, 7]
    entry = struct.pack(">12H", *words12)
    key = pc.index_key(entry)
    ok(len(key) > 0 and struct.unpack_from(">I", entry, 20)[0] == 7, "index key shape")
    b = bytearray(80)
    SPATIAL_ENTRY.pack_into(b, 0, 8, 7, 0, 123, 456, 0x88008000)
    b[16:26] = TERMINATOR_PREFIX + b"\x00\x00\x1a\x80"
    ctx = LeafContext(tree=0, base=0, tree_words=128, pos=0, kx=123, ky=456, depth=3,
                      term=16, node_end=26, node_size=13, parent_csize=64, gap_words=8)
    out = bytearray(80)
    out[:] = b
    struct.pack_into(">H", out, 64, 13)
    rep = insert_leaf(out, ctx, 99, 100, 200)
    ok(out[16:18] == b"\x00\x08" and SPATIAL_ENTRY.unpack_from(out, 16)[1] == 99,
       "leaf inserted before terminator")
    ok(out[32:42] == TERMINATOR_PREFIX + b"\x00\x00\x1a\x80", "terminator moved by 16")
    ok(rep["new_csize"] == 21, "parent csize grew by 8 words")
    narrow = LeafContext(tree=0, base=0, tree_words=128, pos=0, kx=123, ky=456, depth=3,
                         term=16, node_end=26, node_size=13, parent_csize=64, gap_words=3)
    try:
        insert_leaf(bytearray(80), narrow, 99, 100, 200)
        ok(False, "small gap refused")
    except AddError:
        ok(True, "small gap refused")
    ok(pc.fine_fields(rec)[2:] == (132, 244), "fine fields masked correctly")
    ok(changed_ranges(b"abc", b"abc") == [] and changed_ranges(b"abc", b"axc") == [(1, 2)],
       "changed-range scanner")
    ok(envelope_ok([(1, 2)], [(0, 4)]) == [] and envelope_ok([(9, 10)], [(0, 4)]) == [(9, 10)],
       "envelope guard")
    ok(zlib.decompress(zlib.compress(bytes(rec))) == bytes(rec), "zlib round trip")
    passed = sum(checks)
    print(f"selftest: {passed}/{len(checks)} checks")
    return 0 if passed == len(checks) else 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("cmp", nargs="?", help="POINT010.DAT.cmp")
    p.add_argument("outdir", nargs="?", help="output directory for the rebuilt pair")
    p.add_argument("--ind", help="matching .ind (only used by --noop)")
    p.add_argument("--name", help=f"new POI name (default {NEW_NAME!r})")
    p.add_argument("--lat", type=float, help="requested latitude (default: near a host)")
    p.add_argument("--lon", type=float, help="requested longitude")
    p.add_argument("--libz", help="stock zlib 1.3.1 libz.so.1.3.1")
    p.add_argument("--allow-nonreference", action="store_true",
                   help="use the host compressor (measurements, not a factory claim)")
    p.add_argument("--noop", action="store_true", help="rewrite the pair unchanged")
    p.add_argument("--control", choices=("none", "break-leaf", "break-index"), default="none",
                   help="deliberately corrupt one byte after placement (negative control)")
    p.add_argument("--json", help="write a JSON report")
    p.add_argument("--selftest", action="store_true")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.cmp or not args.outdir:
        print("error: CMP and OUTDIR are required (or use --selftest)", file=sys.stderr)
        return 2
    if (args.lat is None) != (args.lon is None):
        print("error: --lat and --lon must be given together", file=sys.stderr)
        return 2
    return run_add(args)


if __name__ == "__main__":
    raise SystemExit(main())
