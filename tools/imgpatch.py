#!/usr/bin/env python3
"""Patch one file inside an existing card image, in place, without a FAT rebuild.

``mkcard.py`` builds a whole card: it re-populates the map partition, which
re-orders the FAT, allocates fresh clusters and (before M5.12b) drops the
factory root volume-label entry. That makes an S1/S2 card differ from S0 in
more than the file under test. This tool does the opposite: it copies the
image (or patches it in place), resolves the file's **existing** cluster
chain and writes the new bytes there, changing only

* the file's data clusters (plus a deterministic zero fill after the new EOF
  when the size changes),
* the 32-byte directory entry (cluster and size fields; timestamps untouched),
* on a cluster-count change only: the FAT links in every FAT copy and the
  FSInfo free count / next-free hint,
* with ``--update-version-copy``: the 72-byte ``VER_INFO/HDD_INFO.TXT`` copy
  at ``0x06000000``.

Everything else -- pre-partition bytes (MBR, firmware, ``0x06000000`` when not
asked to update it) and the post-partition tail -- is never written, so a
byte diff between input and output lies in the patched file's clusters, its
directory entry and (on a resize) the FAT/FSInfo entries named above.

Modes
    patch   (default)  --image IMG --file PATH/IN/CARD --from NEWFILE [-o OUT]
    verify  --verify   --image IMG --file PATH/IN/CARD --from NEWFILE

Guards
    * the "same-length" guard: a size change is refused unless
      ``--allow-resize`` (``--same-length`` states the default explicitly);
    * ``-o`` must not name the source image (``same-image``);
    * ``--update-version-copy`` is accepted only for ``VER_INFO/HDD_INFO.TXT``
      and requires a 72-byte file (the factory copy length);
    * a missing host file, a missing card path or a FAT-copy disagreement
      is refused before anything is written.

Exit codes: 0 success, 1 verification mismatch, 2 usage error, 3 refused by a
guard (size change, same image, wrong ``--update-version-copy`` target, missing
file). A refusal never writes to the image; ``--dry-run`` never writes at all.

Usage:
    python3 tools/imgpatch.py --image IMG --file REFER001/POINT010.DAT.cmp \\
        --from POINT010.DAT.cmp -o OUT.img
    python3 tools/imgpatch.py --verify --image OUT.img \\
        --file REFER001/POINT010.DAT.cmp --from POINT010.DAT.cmp
    python3 tools/imgpatch.py --selftest
"""

from __future__ import annotations

import argparse
import hashlib
import hashutil
import json
import os
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mkcard  # noqa: E402

SECTOR = 512
HDD_COPY_OFFSET = 0x06000000
HDD_COPY_LEN = 72
VERSION_FILE = "VER_INFO/HDD_INFO.TXT"
EOC = 0x0FFFFFF8


class PatchError(Exception):
    """A refused patch or a verify failure, with a machine-readable reason."""

    def __init__(self, reason: str, message: str, exit_code: int = 3):
        super().__init__(message)
        self.reason = reason
        self.message = message
        self.exit_code = exit_code


# --- small helpers ---------------------------------------------------------

_sha256 = hashutil.sha256_bytes


def _rel(path: str) -> str:
    rel = path.replace("\\", "/").strip("/")
    parts = rel.split("/")
    if not rel or any(p in ("", ".", "..") for p in parts):
        raise PatchError("bad-path", f"not a file path inside the card: {path!r}")
    return rel


def _same_path(a: Path, b: Path) -> bool:
    try:
        if a.exists() and b.exists():
            return os.path.samefile(a, b)
    except OSError:
        pass
    return a.resolve() == b.resolve()


def _slot_abs(geo: mkcard.FatGeo, dir_chain: list[int], slot_offset: int) -> int:
    """Absolute image offset of a 32-byte slot inside a directory chain."""
    index, within = divmod(slot_offset, geo.cluster_bytes)
    if index >= len(dir_chain):
        raise PatchError("bad-image", "directory slot outside its cluster chain")
    return geo.cluster_offset(dir_chain[index]) + within


def _fat_bytes_at(handle, offset: int) -> int:
    handle.seek(offset)
    raw = handle.read(4)
    if len(raw) != 4:
        raise PatchError("bad-image", f"short FAT entry at 0x{offset:08x}")
    return struct.unpack("<I", raw)[0]


def _fat_payload(old_raw: int, value: int) -> bytes:
    return struct.pack("<I", (old_raw & 0xF0000000) | (value & 0x0FFFFFFF))


def _free_clusters_after(fat: bytes, cluster: int, span: int) -> int:
    """How many of the ``span`` clusters after ``cluster`` are free.

    Informational only: it lets the plan report that the free run it is about
    to use is a hole behind another file's tail, so the record can state
    whether the allocator chose that hole deliberately (M5.30).
    """
    return sum(1 for i in range(1, span + 1)
               if mkcard.fat_get(fat, cluster + i) == 0)


def _cluster_count(geo: mkcard.FatGeo) -> int:
    """Data clusters addressable by the BPB.

    The FAT is often longer than the partition's data area (the EU 2011 card
    has 115,200 FAT entries for 115,185 clusters: 14,743,768 data sectors at
    128 sectors/cluster, last valid cluster 115,186), so its length must not be
    used as the allocation bound: a cluster past ``last_valid`` has no bytes
    inside the partition. ``alloc_clusters`` cannot know the geometry; callers
    that hold a ``FatGeo`` must pass this bound to it (M5.30 / EXP-M5.47).
    """
    return (geo.total_sectors - geo.reserved
            - geo.fat_count * geo.fat_sectors) // geo.spc


# --- directory lookup ------------------------------------------------------

def _locate(handle, geo: mkcard.FatGeo, fat: bytes, rel: str) -> dict:
    """Find a file's directory chain, raw directory blob and short entry."""
    parts = rel.split("/")
    base = parts[-1]
    if len(parts) == 1:
        dir_chain = mkcard.chain(fat, geo.root_cluster)
    else:
        parent = "/".join(parts[:-1])
        try:
            parent_entry, _ = mkcard._resolve(handle, geo, fat, parent)
        except FileNotFoundError:
            raise PatchError("file-not-found", f"{rel}: {parent}/ is not on the card")
        except NotADirectoryError:
            raise PatchError("not-a-file", f"{rel}: {parent}/ is not a directory")
        if parent_entry is None or not parent_entry.is_dir:
            raise PatchError("not-a-file", f"{rel}: {parent}/ is not a directory")
        dir_chain = mkcard.chain(fat, parent_entry.cluster)

    blob = b"".join(mkcard.read_cluster(handle, geo, c) for c in dir_chain)
    entries = mkcard.parse_dir_raw(blob)
    entry = next((e for e in entries if e.name == base), None)
    if entry is None:
        entry = next((e for e in entries if e.name.lower() == base.lower()), None)
    if entry is None:
        raise PatchError("file-not-found", f"{rel}: no such file on the card")
    if entry.is_dir:
        raise PatchError("not-a-file", f"{rel}: is a directory, not a file")

    short_offset = entry.slot_offset + (entry.slot_count - 1) * 32
    raw_slot = blob[short_offset : short_offset + 32]
    if len(raw_slot) != 32 or raw_slot[0] == 0xE5 or raw_slot[11] == 0x0F:
        raise PatchError("bad-image", f"{rel}: cannot locate the short directory entry")
    return {
        "name": entry.name,
        "size": entry.size,
        "cluster": entry.cluster,
        "dir_chain": dir_chain,
        "dir_entry_offset": _slot_abs(geo, dir_chain, short_offset),
        "dir_entry_raw": raw_slot,
    }


# --- plan ------------------------------------------------------------------

def _build_plan(handle, geo: mkcard.FatGeo, fat: bytes, rel: str, data: bytes, *,
                allow_resize: bool, update_version_copy: bool,
                preserve_stale_tail: bool = False) -> dict:
    info = _locate(handle, geo, fat, rel)
    old_size = info["size"]
    new_size = len(data)
    cluster_bytes = geo.cluster_bytes

    if update_version_copy:
        if rel.upper() != VERSION_FILE:
            raise PatchError(
                "version-copy-target",
                f"--update-version-copy is only for {VERSION_FILE}, not {rel}",
            )
        if new_size != HDD_COPY_LEN:
            raise PatchError(
                "version-copy-size",
                f"{VERSION_FILE} must be {HDD_COPY_LEN} bytes for the 0x06000000 "
                f"copy, got {new_size}",
            )

    if new_size != old_size and not allow_resize:
        raise PatchError(
            "size-change",
            f"{rel}: {old_size} -> {new_size} bytes is a size change; "
            f"pass --allow-resize to grow/shrink the chain",
        )

    old_chain = mkcard.chain(fat, info["cluster"]) if info["cluster"] else []
    need = mkcard.clusters_needed(new_size, cluster_bytes)
    start_before = info["cluster"]

    # Mirrored FATs must agree before we touch them.
    for cluster in old_chain:
        values = {
            _fat_bytes_at(handle, geo.fat_offset + copy * geo.fat_bytes + cluster * 4)
            & 0x0FFFFFFF
            for copy in range(geo.fat_count)
        }
        if len(values) != 1 or values != {mkcard.fat_get(fat, cluster)}:
            raise PatchError(
                "fat-mismatch",
                f"FAT copies disagree at cluster {cluster}; refusing to patch",
            )

    new_fat = bytearray(fat)
    chain_after = list(old_chain)
    extra: list[int] = []
    max_cluster = _cluster_count(geo) + 1
    if need > len(old_chain):
        hint = old_chain[-1] + 1 if old_chain else 2
        try:
            extra = mkcard.alloc_clusters(new_fat, need - len(old_chain),
                                          start_hint=hint,
                                          max_cluster=max_cluster)
        except ValueError as exc:
            raise PatchError("no-space", f"{rel}: {exc}") from exc
        if old_chain:
            mkcard.fat_set(new_fat, old_chain[-1], extra[0])
        chain_after = old_chain + extra
    elif need < len(old_chain):
        for cluster in old_chain[need:]:
            mkcard.fat_set(new_fat, cluster, 0)
        if need:
            mkcard.fat_set(new_fat, old_chain[need - 1], EOC)
        chain_after = old_chain[:need]

    for i in range(len(chain_after) - 1):
        mkcard.fat_set(new_fat, chain_after[i], chain_after[i + 1])
    # Keep the factory end-of-chain marker when the chain already ends in one
    # (0x0FFFFFF8..0x0FFFFFFF are all EOC); rewriting it is a needless FAT diff.
    if chain_after and mkcard.fat_get(new_fat, chain_after[-1]) < EOC:
        mkcard.fat_set(new_fat, chain_after[-1], EOC)
    start_after = chain_after[0] if chain_after else 0

    ops: list[tuple[str, int, bytes]] = []
    fat_changes: list[dict] = []

    # 1. data clusters (exactly the bytes of the new file)
    for i, cluster in enumerate(chain_after):
        chunk = data[i * cluster_bytes : (i + 1) * cluster_bytes]
        if chunk:
            ops.append((f"data cluster {cluster}", geo.cluster_offset(cluster), chunk))

    # 2. slack after the new EOF (resize only). Default: deterministic zero fill.
    # preserve_stale_tail keeps existing bytes in a cluster that was already in the
    # factory chain; a newly allocated last cluster is still zero-filled for
    # determinism (M5.31). Slack bytes are after EOF and not read by size-bounded
    # readers; cardcheck/FAT/dir/DRSTR invariants are unchanged.
    stale_tail_preserved = False
    if chain_after and new_size != old_size and new_size % cluster_bytes:
        tail = cluster_bytes - (new_size % cluster_bytes)
        offset = geo.cluster_offset(chain_after[-1]) + (new_size % cluster_bytes)
        if preserve_stale_tail and chain_after[-1] in set(old_chain):
            stale_tail_preserved = True
        else:
            ops.append((f"zero cluster {chain_after[-1]}", offset, b"\x00" * tail))

    # 3. FAT links in every copy, only entries whose value changes
    for cluster in sorted(set(old_chain) | set(chain_after)):
        before = mkcard.fat_get(fat, cluster)
        after = mkcard.fat_get(new_fat, cluster)
        if before == after:
            continue
        for copy in range(geo.fat_count):
            offset = geo.fat_offset + copy * geo.fat_bytes + cluster * 4
            raw = _fat_bytes_at(handle, offset)
            ops.append((f"FAT copy {copy} cluster {cluster}", offset,
                        _fat_payload(raw, after)))
        fat_changes.append({"cluster": cluster, "before": before, "after": after,
                            "copies": geo.fat_count})

    # 4. FSInfo, only on a cluster-count change
    fsinfo: list[dict] = []
    delta = need - len(old_chain)
    if delta:
        fsinfo = _plan_fsinfo(handle, geo, delta,
                              extra[0] if extra else 0)
        for item in fsinfo:
            for write in item["writes"]:
                ops.append((f"FSInfo {item['sector']} 0x{write['offset'] & 0xFFFF:x}",
                            write["offset"], struct.pack("<I", write["after"])))

    # 5. the directory entry (size and start cluster; timestamps untouched)
    slot = bytearray(info["dir_entry_raw"])
    struct.pack_into("<H", slot, 20, (start_after >> 16) & 0xFFFF)
    struct.pack_into("<H", slot, 26, start_after & 0xFFFF)
    struct.pack_into("<I", slot, 28, new_size)
    if bytes(slot) != info["dir_entry_raw"]:
        ops.append(("dir entry", info["dir_entry_offset"], bytes(slot)))

    # 6. the optional 0x06000000 copy of VER_INFO/HDD_INFO.TXT
    version_copy = None
    if update_version_copy:
        old_file = (mkcard.read_chain(handle, geo, fat, info["cluster"], old_size)
                    if old_size else b"")
        handle.seek(HDD_COPY_OFFSET)
        copy_before = handle.read(HDD_COPY_LEN)
        if len(copy_before) != HDD_COPY_LEN:
            raise PatchError("bad-image", "image is too small for the 0x06000000 copy")
        version_copy = {
            "offset": HDD_COPY_OFFSET,
            "length": HDD_COPY_LEN,
            "copied_old_file": copy_before == old_file,
            "before_sha256": _sha256(copy_before),
            "after_sha256": _sha256(data),
        }
        ops.append(("0x06000000 copy", HDD_COPY_OFFSET, data))

    _check_envelope(ops, geo)

    return {
        "file": rel,
        "old_size": old_size,
        "new_size": new_size,
        "start_cluster_before": start_before,
        "start_cluster_after": start_after,
        "clusters_before": len(old_chain),
        "clusters_after": len(chain_after),
        "chain_before": old_chain,
        "chain_after": chain_after,
        "extra_clusters": extra,
        "free_after_tail": (_free_clusters_after(fat, old_chain[-1], len(extra))
                            if old_chain and extra else None),
        "fat_changes": fat_changes,
        "fsinfo": fsinfo,
        "dir_entry": {
            "offset": info["dir_entry_offset"],
            "size_before": old_size,
            "size_after": new_size,
            "cluster_before": start_before,
            "cluster_after": start_after,
        },
        "version_copy": version_copy,
        "preserve_stale_tail": preserve_stale_tail,
        "stale_tail_preserved": stale_tail_preserved,
        "ops": ops,
    }


def _plan_fsinfo(handle, geo: mkcard.FatGeo, delta: int, first_new: int) -> list[dict]:
    out = []
    candidates = [("primary", geo.fsinfo_sector)]
    if geo.backup_boot:
        candidates.append(("backup", geo.backup_boot + geo.fsinfo_sector))
    for label, sector in candidates:
        if not sector or sector >= geo.reserved:
            continue
        offset = geo.part_offset + sector * geo.bps
        handle.seek(offset)
        block = handle.read(geo.bps)
        if len(block) < geo.bps or block[0:4] != b"RRaA":
            continue
        free = mkcard._u32(block, 0x1E8)
        hint = mkcard._u32(block, 0x1EC)
        entry = {"sector": label, "offset": offset, "free_before": free,
                 "free_after": free, "hint_before": hint, "hint_after": hint,
                 "writes": []}
        if free != 0xFFFFFFFF:
            new_free = max(0, free - delta)
            if new_free != free:
                entry["free_after"] = new_free
                entry["writes"].append({"offset": offset + 0x1E8, "length": 4,
                                        "before": free, "after": new_free})
        if delta > 0 and first_new:
            new_hint = first_new + 1
            if new_hint != hint:
                entry["hint_after"] = new_hint
                entry["writes"].append({"offset": offset + 0x1EC, "length": 4,
                                        "before": hint, "after": new_hint})
        if entry["writes"]:
            out.append(entry)
    return out


def _check_envelope(ops: list[tuple[str, int, bytes]], geo: mkcard.FatGeo) -> None:
    """Every write must land in the map partition or the 0x06000000 copy."""
    allowed = [
        (geo.part_offset, geo.part_offset + geo.part_bytes),
        (HDD_COPY_OFFSET, HDD_COPY_OFFSET + HDD_COPY_LEN),
    ]
    for label, offset, payload in ops:
        end = offset + len(payload)
        if not any(start <= offset and end <= stop for start, stop in allowed):
            raise PatchError(
                "internal-range",
                f"{label}: 0x{offset:08x}-0x{end:08x} falls outside the map "
                f"partition and the 0x06000000 copy",
            )


def _apply(handle, ops: list[tuple[str, int, bytes]]) -> None:
    for _label, offset, payload in ops:
        handle.seek(offset)
        handle.write(payload)


def _public_plan(plan: dict) -> dict:
    out = {k: v for k, v in plan.items() if k != "ops"}
    out["writes"] = [{"what": label, "offset": offset, "length": len(payload)}
                     for label, offset, payload in plan["ops"]]
    return out


# --- verify ----------------------------------------------------------------

def verify_image(image, file, source, *, update_version_copy: bool = False,
                 expected: bytes | None = None) -> dict:
    """Read the file back through ``cardcheck.Fat32Image`` and compare it.

    ``cardcheck`` is the L1 reader used by the rest of the verification
    ladder, so a pass here means the file is visible through the same
    directory/FAT path the validator uses.
    """
    rel = _rel(file)
    data = expected if expected is not None else Path(source).read_bytes()
    copy: bytes | None = None
    import cardcheck  # local import: only verify needs it

    try:
        img = cardcheck.Fat32Image(Path(image))
    except Exception as exc:  # noqa: BLE001 - reported as a verify failure
        raise PatchError("verify-failed",
                         f"cannot open {image} with cardcheck: {exc}", 1)
    try:
        actual = img.read(rel)
        if update_version_copy:
            copy = img.read_absolute(HDD_COPY_OFFSET, len(data))
    finally:
        img.close()

    result = {
        "method": "cardcheck.Fat32Image",
        "file": rel,
        "size": len(actual),
        "expected_size": len(data),
        "sha256": _sha256(actual),
        "expected_sha256": _sha256(data),
        "matches": actual == data,
    }
    if update_version_copy:
        result["version_copy"] = {
            "offset": HDD_COPY_OFFSET,
            "size": len(copy or b""),
            "sha256": _sha256(copy or b""),
            "matches": copy == data,
        }
    result["ok"] = bool(result["matches"]) and (
        not update_version_copy or result["version_copy"]["matches"]
    )
    return result


# --- patch -----------------------------------------------------------------

def patch_image(image, file, source, output=None, *, allow_resize: bool = False,
                dry_run: bool = False, update_version_copy: bool = False,
                hash_output: bool = False, preserve_stale_tail: bool = False) -> dict:
    image_path = Path(image)
    source_path = Path(source)
    rel = _rel(file)

    if not image_path.is_file():
        raise PatchError("image-not-found", f"{image_path}: no such image")
    if not source_path.is_file():
        raise PatchError("file-not-found", f"{source_path}: no such host file")
    data = source_path.read_bytes()

    if update_version_copy and rel.upper() != VERSION_FILE:
        raise PatchError("version-copy-target",
                         f"--update-version-copy is only for {VERSION_FILE}, not {rel}")
    if update_version_copy and len(data) != HDD_COPY_LEN:
        raise PatchError("version-copy-size",
                         f"{VERSION_FILE} must be {HDD_COPY_LEN} bytes for the "
                         f"0x06000000 copy, got {len(data)}")

    out_path = Path(output) if output else None
    if out_path is not None and _same_path(image_path, out_path):
        raise PatchError("same-image",
                         f"output {out_path} is the source image; refusing to "
                         f"overwrite it")
    if out_path is not None and out_path.exists() and not out_path.is_file():
        raise PatchError("bad-output", f"{out_path}: not a regular file")

    target = image_path
    if out_path is not None and not dry_run:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        mkcard.copy_image(image_path, out_path)
        target = out_path

    mode = "rb" if dry_run else "r+b"
    try:
        with target.open(mode) as handle:
            try:
                _part, geo, fat = mkcard.open_map_partition(handle)
            except ValueError as exc:
                raise PatchError("not-fat32", f"{target}: {exc}") from exc
            plan = _build_plan(handle, geo, fat, rel, data,
                               allow_resize=allow_resize,
                               update_version_copy=update_version_copy,
                               preserve_stale_tail=preserve_stale_tail)
            if not dry_run:
                _apply(handle, plan["ops"])
                handle.flush()
                os.fsync(handle.fileno())
    except PatchError:
        raise
    except FileNotFoundError as exc:
        raise PatchError("file-not-found", str(exc)) from exc
    except (ValueError, struct.error) as exc:
        raise PatchError("bad-image", f"{target}: {exc}") from exc
    except OSError as exc:
        raise PatchError("write-failed", f"{target}: {exc}") from exc

    report = _public_plan(plan)
    report.update({
        "ok": True,
        "mode": "patch",
        "dry_run": dry_run,
        "image": str(image_path),
        "output": str(out_path) if out_path else None,
        "target": str(target),
        "source": str(source_path),
        "patched_in_place": out_path is None and not dry_run,
        "envelope": {
            "partition": [geo.part_offset, geo.part_offset + geo.part_bytes],
            "hdd_copy": [HDD_COPY_OFFSET, HDD_COPY_OFFSET + HDD_COPY_LEN],
        },
    })
    if dry_run:
        report["verify"] = None
    else:
        verify = verify_image(target, rel, source_path,
                              update_version_copy=update_version_copy, expected=data)
        report["verify"] = verify
        if not verify["ok"]:
            report["ok"] = False
        if hash_output:
            report["output_sha256"] = mkcard.sha256_file(target)
    return report


# --- independent diff check (M5.24) ----------------------------------------

def _merge_ranges(ranges):
    merged: list[list[int]] = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(a, b) for a, b in merged]


def _ranges_contained(ranges, allowed) -> bool:
    """Whether every differing run fits inside the union of allowed ranges."""
    merged = _merge_ranges(allowed)
    return all(any(a <= start and end <= b for a, b in merged)
               for start, end in ranges)


def _outside_ranges(ranges, allowed):
    """Diff ranges (or parts) not covered by the allowed union."""
    merged = _merge_ranges(allowed)
    outside = []
    for start, end in ranges:
        cur = start
        for a, b in merged:
            if b <= cur:
                continue
            if a >= end:
                break
            if a > cur:
                outside.append((cur, min(a, end)))
            cur = max(cur, b)
            if cur >= end:
                break
        if cur < end:
            outside.append((cur, end))
    return outside


def _metadata_markers(geo, files, ref_fat: bytes, ref_handle, ref_geo,
                      img_fat: bytes) -> dict:
    """Where a file allocation may legitimately change metadata.

    ``files`` is a list of (rel, new_chain); ``ref_fat``/``ref_handle``/
    ``ref_geo`` are an independent read of the reference and ``img_fat`` the
    independent read of the patched image. An entry is *expected* only when it
    lies on the replaced file's old or new chain and its 28-bit value actually
    changed. A relocation rewrites only those entries (``fat{0,1}_link``) and,
    when the allocation changed, the FSInfo free-count / next-free words
    (``fsinfo_free`` / ``fsinfo_nxt``). Every other FAT entry, FSInfo byte or
    sector byte is ``fat{0,1}_slack`` / ``fsinfo_unknown`` -- not a link of the
    move, refused by strict mode (M5.51).
    """
    entries: dict[int, dict] = {}
    grew = False
    for rel, new_chain in files:
        if not new_chain:
            continue
        try:
            ref_info = _locate(ref_handle, ref_geo, ref_fat, rel)
        except PatchError:
            ref_info = None
        old_chain = (mkcard.chain(ref_fat, ref_info["cluster"])
                     if ref_info and ref_info["cluster"] else [])
        if len(new_chain) > len(old_chain):
            grew = True
        for cluster in sorted(set(old_chain) | set(new_chain)):
            before = (mkcard.fat_get(ref_fat, cluster)
                      if cluster in old_chain else 0)
            after = mkcard.fat_get(img_fat, cluster)
            if before == after:
                continue
            entries[cluster] = {"file": rel, "cluster": cluster,
                                "before": before, "after": after,
                                "old": cluster in old_chain,
                                "new": cluster in new_chain,
                                "field": "link" if after != 0 else "free"}

    last_valid = _cluster_count(geo) + 1
    ref_free = sum(1 for c in range(2, last_valid + 1)
                   if mkcard.fat_get(ref_fat, c) == 0)
    img_free = sum(1 for c in range(2, last_valid + 1)
                   if mkcard.fat_get(img_fat, c) == 0)
    free_expected = ref_free != img_free

    fsinfo = []
    for label, sector in (("primary", geo.fsinfo_sector),
                          ("backup", geo.backup_boot + geo.fsinfo_sector
                           if geo.backup_boot else 0)):
        if not sector or sector >= geo.reserved:
            continue
        base = geo.part_offset + sector * geo.bps
        ref_handle.seek(base)
        block = ref_handle.read(geo.bps)
        if len(block) < geo.bps or block[0:4] != b"RRaA":
            continue
        fsinfo.append({"sector": label, "base": base,
                       "free": mkcard._u32(block, 0x1E8),
                       "hint": mkcard._u32(block, 0x1EC),
                       "free_expected": free_expected
                       and mkcard._u32(block, 0x1E8) != 0xFFFFFFFF,
                       "nxt_expected": grew})
    return {"entries": entries, "fsinfo": fsinfo,
            "fat": {"offset": geo.fat_offset, "bytes": geo.fat_bytes,
                    "count": geo.fat_count}}


def _metadata_reason(start: int, end: int, info: dict) -> dict:
    """Reason for a metadata diff range: which FAT entry/copy and byte it
    covers, or which FSInfo field. A byte outside the move's own entries is
    ``fat{0,1}_slack``; a byte outside an expected FSInfo word is
    ``fsinfo_unknown``. Neither is a link of the move (M5.51)."""
    entries = info.get("entries") or {}
    fsinfo = info.get("fsinfo") or []
    fat_geo = info.get("fat") or {}
    count = fat_geo.get("count") or 0
    bytes_ = fat_geo.get("bytes") or 0
    base_fat = fat_geo.get("offset") or 0
    for copy in range(count):
        f0 = base_fat + copy * bytes_
        if start >= f0 and end <= f0 + bytes_:
            first = (start - f0) // 4
            last = (end - 1 - f0) // 4
            entry = entries.get(first) if first == last else None
            if entry is not None and f0 + first * 4 <= start \
                    and end <= f0 + first * 4 + 4:
                return {"kind": "fat", "entry": first, "copy": copy,
                        "entry_offset": f0 + first * 4,
                        "byte_offset": start - (f0 + first * 4),
                        "file": entry.get("file"),
                        "before": entry.get("before"),
                        "after": entry.get("after"),
                        "field": entry.get("field"),
                        "reason": f"fat{copy}_link"}
            return {"kind": "fat", "entry": first, "copy": copy,
                    "entry_offset": f0 + first * 4,
                    "byte_offset": start - (f0 + first * 4),
                    "file": None, "before": None, "after": None,
                    "field": "slack", "reason": f"fat{copy}_slack"}
    for sector in fsinfo:
        base = sector["base"]
        if base + 0x1E8 <= start and end <= base + 0x1EC:
            reason = ("fsinfo_free" if sector["free_expected"]
                      else "fsinfo_unknown")
            return {"kind": "fsinfo", "sector": sector["sector"],
                    "field_name": "free",
                    "byte_offset": start - base - 0x1E8,
                    "field": "free", "reason": reason}
        if base + 0x1EC <= start and end <= base + 0x1F0:
            reason = ("fsinfo_nxt" if sector["nxt_expected"]
                      else "fsinfo_unknown")
            return {"kind": "fsinfo", "sector": sector["sector"],
                    "field_name": "nxt",
                    "byte_offset": start - base - 0x1EC,
                    "field": "nxt", "reason": reason}
    return {"kind": "unknown", "field": "unknown", "reason": "fsinfo_unknown"}


_EXPECTED_REASONS = frozenset(("fat0_link", "fat1_link",
                               "fsinfo_free", "fsinfo_nxt"))


def _expected_metadata_reason(reason: dict) -> bool:
    """Whether a range's reason is one of the move's expected link fields.

    Expected: a byte of a FAT entry that lies on the replaced files' old or new
    chain and whose value actually changed, in each FAT copy
    (``fat0_link`` / ``fat1_link``), and the FSInfo free-count / next-free
    words when the allocation changed (``fsinfo_free`` / ``fsinfo_nxt``).
    ``fat*_slack`` and ``fsinfo_unknown`` are not links of the move -- the
    M5.51 falsifier, refused by ``--strict-metadata``.
    """
    return reason.get("reason") in _EXPECTED_REASONS


def allowed_ranges_from_bpb(image, files, *, reference=None) -> dict:
    """Resolve each replaced file's clusters and dir entry from an independent
    BPB+FAT read, not from a patch plan or write offset.

    ``image`` is the patched image. Returns the allowed byte ranges (cluster
    data for each file's chain plus its 32-byte directory entry) and the
    per-file metadata the independent read produced. With ``reference`` the
    move's expected FAT links and FSInfo fields are resolved from a second
    independent read, so each metadata range can carry a per-entry reason.
    """
    image_path = Path(image)
    if not image_path.is_file():
        raise PatchError("image-not-found", f"{image_path}: no such image")
    rels = [_rel(f) for f in files]
    try:
        with image_path.open("rb") as handle:
            try:
                _part, geo, fat = mkcard.open_map_partition(handle)
            except ValueError as exc:
                raise PatchError("not-fat32", f"{image_path}: {exc}") from exc
            per_file = []
            allowed = []
            for rel in rels:
                info = _locate(handle, geo, fat, rel)
                chain_list = mkcard.chain(fat, info["cluster"]) if info["cluster"] else []
                clusters = []
                for cluster in chain_list:
                    off = geo.cluster_offset(cluster)
                    clusters.append({"cluster": cluster, "offset": off,
                                     "length": geo.cluster_bytes})
                    allowed.append((off, off + geo.cluster_bytes))
                entry = {"offset": info["dir_entry_offset"], "length": 32}
                allowed.append((entry["offset"], entry["offset"] + 32))
                per_file.append({
                    "file": rel,
                    "method": "independent BPB+FAT read (mkcard.open_map_partition/_locate)",
                    "start_cluster": info["cluster"],
                    "size": info["size"],
                    "chain": chain_list,
                    "cluster_ranges": clusters,
                    "dir_entry": entry,
                })
            # A size change rewrites FAT links (both copies) and FSInfo. They are
            # not file bytes but they are the only allowed metadata, and only in
            # the FAT sectors and the FSInfo sectors -- never "FAT/FSInfo" as a
            # euphemism for any metadata (M5.30).
            fat_ranges = [(geo.fat_offset + copy * geo.fat_bytes,
                           geo.fat_offset + (copy + 1) * geo.fat_bytes)
                          for copy in range(geo.fat_count)]
            fsinfo_ranges = []
            for sector in [geo.fsinfo_sector] + ([geo.backup_boot + geo.fsinfo_sector]
                                                 if geo.backup_boot else []):
                if sector and sector < geo.reserved:
                    off = geo.part_offset + sector * geo.bps
                    fsinfo_ranges.append((off, off + geo.bps))
            metadata = _merge_ranges(fat_ranges + fsinfo_ranges)
            markers = None
            if reference is not None:
                # The move's expected links come from a second independent read
                # (the reference image's FAT + FSInfo), so a metadata range can
                # be named per FAT entry / FSInfo word instead of per sector
                # (M5.51). Without it the class stays whole-sector (M5.30).
                ref_path = Path(reference)
                if not ref_path.is_file():
                    raise PatchError("image-not-found",
                                     f"{ref_path}: no such image")
                with ref_path.open("rb") as ref_handle:
                    try:
                        _rp, ref_geo, ref_fat = mkcard.open_map_partition(ref_handle)
                    except ValueError as exc:
                        raise PatchError("not-fat32",
                                         f"{ref_path}: {exc}") from exc
                    markers = _metadata_markers(
                        geo,
                        [(f["file"], f["chain"]) for f in per_file],
                        ref_fat, ref_handle, ref_geo, fat)
    except PatchError:
        raise
    except (ValueError, struct.error, OSError) as exc:
        raise PatchError("bad-image", f"{image_path}: {exc}") from exc
    return {
        "image": str(image_path),
        "reference": str(reference) if reference is not None else None,
        "files": per_file,
        "allowed_ranges": _merge_ranges(allowed),
        "metadata_ranges": metadata,
        "metadata_markers": markers,
    }


def check_diff_ranges(image, reference, files, *, limit: int = 10**7,
                      allow_metadata: bool = False,
                      strict_metadata: bool = False) -> dict:
    """Verify every byte diff lies in replaced-file clusters/dir entries.

    The allowed ranges come from ``allowed_ranges_from_bpb`` on ``image`` (an
    independent BPB+FAT read), never from patch write offsets. A mismatch is
    any diff outside the file bytes. With ``allow_metadata`` the whole FAT
    sectors and the whole FSInfo sectors are an additional allowed class,
    reported separately: a size change must rewrite FAT links and the FSInfo
    count, and those are not file bytes (M5.30). The class is whole-sector, not
    the named fields: any byte outside the FAT/FSInfo sectors and the files'
    clusters/directory entries still fails, and strict mode (no flag) plus the
    per-range classification bound what the flag admits.

    With ``reference`` each metadata range is *named* (``fat0_link`` /
    ``fat1_link`` for the FAT entry copy it covers, ``fsinfo_free`` /
    ``fsinfo_nxt`` for the FSInfo word) by a second independent read of the
    reference's FAT and FSInfo (M5.51). ``strict_metadata`` additionally fails
    any metadata range whose reason is not one of the move's own expected link
    fields -- a byte in FAT slack (any entry not on the old/new chain) or in an
    FSInfo byte that is not a free-count/next-free word is refused, so a
    whole-sector class becomes a named one. Strict mode implies
    ``allow_metadata`` (the named ranges are still admitted).
    """
    strict_metadata = strict_metadata or False
    if strict_metadata:
        allow_metadata = True
    ref_path = Path(reference)
    img_path = Path(image)
    if not ref_path.is_file():
        raise PatchError("image-not-found", f"{ref_path}: no such image")
    allowed = allowed_ranges_from_bpb(image, files, reference=ref_path)
    diff = mkcard.diff_ranges(ref_path, img_path, limit=limit)
    if allow_metadata:
        permitted = _merge_ranges(list(allowed["allowed_ranges"])
                                  + list(allowed["metadata_ranges"]))
        outside = _outside_ranges(diff, permitted)
        in_metadata = [r for r in diff
                       if _ranges_contained([r], allowed["metadata_ranges"])]
    else:
        outside = _outside_ranges(diff, allowed["allowed_ranges"])
        in_metadata = []
    # Name every metadata range: which FAT entry (and copy) or FSInfo word it
    # covers, or that it is slack / unknown -- the per-range reason that the
    # whole-sector class lacked (M5.51). ``unexpected_metadata`` is what strict
    # mode refuses; without a reference read every range is unnamed.
    markers = allowed.get("metadata_markers")
    metadata_reasons = []
    unexpected = []
    for start, end in in_metadata:
        if markers is None:
            reason = {"kind": "unknown", "field": "unknown",
                      "reason": "unnamed",
                      "expected": False}
        else:
            reason = _metadata_reason(start, end, markers)
            reason["expected"] = _expected_metadata_reason(reason)
        reason = dict(reason, start=start, end=end, bytes=end - start)
        metadata_reasons.append(reason)
        if not reason["expected"]:
            unexpected.append(reason)
    strict_fail = strict_metadata and bool(unexpected)
    # Attribute every differing byte to the class of range it falls in, so the
    # record can say "N ranges / M bytes in file data, dir entries, metadata"
    # without listing each run, and any unclassified byte is visible (M5.30).
    labeled = []
    for item in allowed["files"]:
        for c in item["cluster_ranges"]:
            labeled.append((c["offset"], c["offset"] + c["length"],
                            "file_data", item["file"]))
        e = item["dir_entry"]
        labeled.append((e["offset"], e["offset"] + e["length"],
                        "dir_entry", item["file"]))
    for s, e in allowed["metadata_ranges"]:
        labeled.append((s, e, "metadata", "FAT/FSInfo"))
    classification: dict[str, dict[str, int]] = {}
    for start, end in diff:
        for segment in mkcard._split_range_by_labels(start, end, labeled):
            kind = segment["kind"]
            bucket = classification.setdefault(kind, {"ranges": 0, "bytes": 0})
            bucket["ranges"] += 1
            bucket["bytes"] += segment["bytes"]
    result = {
        "mode": "check-diff",
        "ok": not outside and not strict_fail,
        "image": str(img_path),
        "reference": str(ref_path),
        "method": "mkcard.diff_ranges classified against independent BPB+FAT ranges",
        "allow_metadata": allow_metadata,
        "strict_metadata": strict_metadata,
        "diff_range_count": len(diff),
        "diff_bytes": sum(e - s for s, e in diff),
        "classification": classification,
        "diff_ranges_sample": diff[:50],
        "metadata_diff_ranges": in_metadata,
        "metadata_reasons": metadata_reasons,
        "unexpected_metadata_count": len(unexpected),
        "outside_range_count": len(outside),
        "outside_ranges_sample": outside[:50],
        "files": allowed["files"],
        "allowed_ranges": allowed["allowed_ranges"],
        "metadata_ranges": allowed["metadata_ranges"],
    }
    return result


def _describe_metadata_reason(reason: dict) -> str:
    """One-line human description of a metadata range's reason."""
    tag = reason.get("reason") or "unknown"
    if reason.get("kind") == "fat":
        entry = reason.get("entry")
        field = reason.get("field")
        detail = (f"FAT copy {reason.get('copy')} entry {entry} "
                  f"(cluster {entry})")
        if field == "link":
            detail += (f" link {reason.get('before')} -> {reason.get('after')}"
                       f" for {reason.get('file')}")
        else:
            detail += " not on the move's old/new chain (slack)"
        return f"{tag}: {detail}"
    if reason.get("kind") == "fsinfo":
        return (f"{tag}: FSInfo {reason.get('sector')} sector "
                f"{reason.get('field_name')} word")
    return f"{tag}: not a FAT copy or an FSInfo sector of the move"


def _print_check_diff(result: dict) -> None:
    state = "OK" if result["ok"] else "MISMATCH"
    print(f"check-diff: {state}")
    print(f"  image:     {result['image']}")
    print(f"  reference: {result['reference']}")
    print(f"  method:    {result['method']}")
    print(f"  diffs: {result['diff_range_count']} range(s), "
          f"outside: {result['outside_range_count']}, "
          f"metadata: {len(result.get('metadata_diff_ranges') or [])}")
    if result.get("strict_metadata"):
        print(f"  strict:    on, unexpected metadata: "
              f"{result.get('unexpected_metadata_count', 0)}")
    for kind, bucket in sorted((result.get("classification") or {}).items()):
        print(f"  class: {kind:<24} {bucket['ranges']} range(s) / {bucket['bytes']} B")
    for item in result["files"]:
        print(f"  file: {item['file']}  start {item['start_cluster']}  "
              f"clusters {len(item['chain'])} (@{item['chain'][:3]}…{item['chain'][-2:]})")
        print(f"        dir entry 0x{item['dir_entry']['offset']:08x}  "
              f"(independent BPB+FAT read)")
    reasons = result.get("metadata_reasons") or []
    if reasons:
        for reason in reasons:
            mark = "" if reason.get("expected") else "  NOT-EXPECTED"
            print(f"  METADATA 0x{reason['start']:08x}-0x{reason['end']:08x}"
                  f"  ({reason['bytes']} B)  {_describe_metadata_reason(reason)}"
                  f"{mark}")
    else:
        for start, end in result.get("metadata_diff_ranges") or []:
            print(f"  METADATA 0x{start:08x}-0x{end:08x}  ({end - start} B)")
    if result["outside_ranges_sample"]:
        for start, end in result["outside_ranges_sample"][:10]:
            print(f"  OUTSIDE 0x{start:08x}-0x{end:08x}  ({end - start} B)")


# --- reporting -------------------------------------------------------------

def _print_patch(report: dict) -> None:
    if report["dry_run"]:
        print("dry run: no bytes written")
    print(f"file:   {report['file']}")
    print(f"  {report['old_size']} -> {report['new_size']} B, "
          f"clusters {report['clusters_before']} -> {report['clusters_after']}, "
          f"start {report['start_cluster_before']} -> "
          f"{report['start_cluster_after']}")
    for write in report["writes"]:
        print(f"  {write['what']:<28} 0x{write['offset']:08x}  {write['length']} B")
    if report.get("version_copy") and not report["version_copy"]["copied_old_file"]:
        print("  warning: the 0x06000000 copy did not match the old file; "
              "it is overwritten")
    if report.get("target"):
        print(f"image:  {report['target']}")
    verify = report.get("verify")
    if verify:
        state = "OK" if verify["ok"] else "MISMATCH"
        print(f"verify: {verify['method']}  {verify['size']} B  "
              f"sha256 {verify['sha256'][:16]}...  {state}")
        if "version_copy" in verify:
            copy = verify["version_copy"]
            print(f"        0x06000000 copy  {copy['size']} B  "
                  f"{'OK' if copy['matches'] else 'MISMATCH'}")


def _print_verify(result: dict) -> None:
    state = "OK" if result["ok"] else "MISMATCH"
    print(f"file:   {result['file']}  {result['size']} B  "
          f"sha256 {result['sha256'][:16]}...  {state}")
    print(f"source: {result['expected_size']} B  "
          f"sha256 {result['expected_sha256'][:16]}...")
    if "version_copy" in result:
        copy = result["version_copy"]
        print(f"0x06000000 copy: {copy['size']} B  "
              f"{'OK' if copy['matches'] else 'MISMATCH'}")


def _emit(report: dict, as_json: bool, verify_only: bool = False,
          check_diff: bool = False) -> None:
    if as_json:
        print(json.dumps(report, indent=2))
    elif check_diff:
        _print_check_diff(report)
    elif verify_only:
        _print_verify(report)
    else:
        _print_patch(report)


# --- self-test -------------------------------------------------------------

def make_selftest_image(path: Path) -> None:
    """Build the synthetic fixture: three root files plus VER_INFO/HDD_INFO.TXT.

    Public so the self-test and the experiment record build the same image;
    it needs no vendor data.
    """
    files = {
        "REPORT.BIN": bytes(range(256)) * 40,   # 10240 B = 3 x 4096
        "SMALL.BIN": b"x" * 100,                # 1 cluster
        "NOTE.TXT": b"hello world\n",           # 12 B, same-length rename
        "EMPTY.TXT": b"",                       # cluster 0, grows from empty
    }
    part_lba = mkcard.HDD_COPY_OFFSET // SECTOR + 256
    mkcard.make_synthetic_image(path, files, part_lba=part_lba,
                                total_sectors=part_lba + 1024, spc=8)
    with path.open("r+b") as handle:
        part, geo, fat = mkcard.open_map_partition(handle)
        # one-cluster directory, one-cluster file (allocated separately)
        dir_cluster = mkcard.alloc_clusters(fat, 1, 3)[0]
        file_cluster = mkcard.alloc_clusters(fat, 1, 3)[0]
        slots = (
            mkcard.make_short_entry(b".          ", 0x10, dir_cluster, 0)
            + mkcard.make_short_entry(b"..         ", 0x10, geo.root_cluster, 0)
            + mkcard.make_short_entry(b"HDD_INFOTXT", 0x20, file_cluster,
                                      len(mkcard.SYNTH_HDD))
        )
        mkcard.write_chain(handle, geo, [dir_cluster], slots)
        mkcard.write_chain(handle, geo, [file_cluster], mkcard.SYNTH_HDD)
        root_offset = geo.cluster_offset(geo.root_cluster)
        root = mkcard.read_cluster(handle, geo, geo.root_cluster)
        slot_offset = next(o for o in range(0, len(root), 32) if root[o] == 0x00)
        entry = mkcard.make_short_entry(b"VER_INFO   ", 0x10, dir_cluster, 0)
        handle.seek(root_offset + slot_offset)
        handle.write(entry)
        for copy in range(geo.fat_count):
            handle.seek(geo.fat_offset + copy * geo.fat_bytes)
            handle.write(fat)
        # a real free count, so the FSInfo delta path is exercised
        fsi_offset = part["offset"] + geo.fsinfo_sector * geo.bps
        handle.seek(fsi_offset)
        fsi = bytearray(handle.read(geo.bps))
        free = sum(1 for c in range(2, len(fat) // 4)
                   if mkcard.fat_get(fat, c) == 0)
        struct.pack_into("<I", fsi, 0x1E8, free)
        struct.pack_into("<I", fsi, 0x1EC, free + 2)
        handle.seek(fsi_offset)
        handle.write(fsi)


def _fat_copies(path: Path) -> list[bytes]:
    with path.open("rb") as handle:
        _part, geo, _fat = mkcard.open_map_partition(handle)
        out = []
        for copy in range(geo.fat_count):
            handle.seek(geo.fat_offset + copy * geo.fat_bytes)
            out.append(handle.read(geo.fat_bytes))
        return out


def _cluster_offset(path: Path, cluster: int) -> int:
    with path.open("rb") as handle:
        _part, geo, _fat = mkcard.open_map_partition(handle)
        return geo.cluster_offset(cluster)


def _contained(ranges, allowed) -> bool:
    """Whether every differing run fits inside the union of planned writes."""
    return _ranges_contained(ranges, allowed)


def expect_refusal(reason: str, func, *args, **kwargs) -> PatchError:
    try:
        func(*args, **kwargs)
    except PatchError as exc:
        if exc.reason != reason:
            raise AssertionError(
                f"expected refusal {reason!r}, got {exc.reason!r}: {exc.message}"
            ) from None
        return exc
    raise AssertionError(f"expected refusal {reason!r}, the call succeeded")


def selftest() -> int:
    import tempfile

    print("imgpatch self-test")
    errors = 0
    checks = 0

    def check(name: str, condition: bool, detail: str = "") -> None:
        nonlocal errors, checks
        checks += 1
        if condition:
            print(f"  ok: {name}")
        else:
            errors += 1
            print(f"  FAIL: {name}" + (f" ({detail})" if detail else ""))

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        fixture = tmp / "fixture.img"
        make_selftest_image(fixture)

        # --- fixture sanity, read through cardcheck --------------------
        import cardcheck
        img = cardcheck.Fat32Image(fixture)
        try:
            hdd = img.read(VERSION_FILE)
            note = img.read("NOTE.TXT")
            report = img.read("REPORT.BIN")
        finally:
            img.close()
        check("fixture: VER_INFO/HDD_INFO.TXT readable", hdd == mkcard.SYNTH_HDD)
        check("fixture: NOTE.TXT readable", note == b"hello world\n")
        check("fixture: REPORT.BIN readable", report == bytes(range(256)) * 40)

        # --- 1. same-length patch into a copy -------------------------
        same = tmp / "same.img"
        note_off = _cluster_offset(fixture, 7)
        new_note = b"HELLO world\n"          # same 12 bytes, 5 differ
        source = tmp / "note.txt"
        source.write_bytes(new_note)
        rep = patch_image(fixture, "NOTE.TXT", source, same)
        check("same-length: accepted without --allow-resize", rep["ok"])
        check("same-length: sizes equal",
              (rep["old_size"], rep["new_size"]) == (12, 12))
        check("same-length: chain unchanged",
              rep["chain_before"] == rep["chain_after"] == [7])
        check("same-length: no FAT/FSInfo/dir changes",
              rep["fat_changes"] == [] and rep["fsinfo"] == []
              and rep["dir_entry"]["size_before"] == rep["dir_entry"]["size_after"])
        check("same-length: only one data write",
              [w["what"] for w in rep["writes"]] == ["data cluster 7"])
        diff = mkcard.diff_ranges(fixture, same)
        check("same-length: exact diff range",
              diff == [(note_off, note_off + 5)], f"{diff}")
        check("same-length: verify read-back", rep["verify"]["matches"])

        # --- 2. grow across a new cluster -----------------------------
        grow = tmp / "grow.img"
        grow_data = b"S" * 5000             # 100 B / 1 cluster -> 2 clusters
        grow_source = tmp / "small.bin"
        grow_source.write_bytes(grow_data)
        rep = patch_image(same, "SMALL.BIN", grow_source, grow, allow_resize=True)
        check("grow: cluster count 1 -> 2",
              (rep["clusters_before"], rep["clusters_after"]) == (1, 2))
        check("grow: start cluster kept",
              rep["start_cluster_before"] == rep["start_cluster_after"] == 6)
        check("grow: chain is [6, 10]", rep["chain_after"] == [6, 10],
              str(rep["chain_after"]))
        copies = _fat_copies(grow)
        check("grow: FAT copies identical", copies[0] == copies[1])
        check("grow: chain linked in both FAT copies",
              all(mkcard.fat_get(f, 6) == 10 and mkcard.fat_get(f, 10) == EOC
                  for f in copies))
        check("grow: FSInfo free count -1 and hint updated",
              len(rep["fsinfo"]) == 1
              and rep["fsinfo"][0]["free_after"] ==
                  rep["fsinfo"][0]["free_before"] - 1
              and rep["fsinfo"][0]["hint_after"] == 11)
        check("grow: dir entry size and cluster updated",
              rep["dir_entry"]["size_after"] == 5000
              and rep["dir_entry"]["cluster_after"] == 6)
        check("grow: verify read-back", rep["verify"]["matches"])
        allowed = [(w["offset"], w["offset"] + w["length"]) for w in rep["writes"]]
        diff = mkcard.diff_ranges(same, grow)
        check("grow: diffs inside the planned writes", _contained(diff, allowed))
        check("grow: some bytes actually changed", bool(diff))

        # --- 3. shrink and free the tail cluster ----------------------
        shrink = tmp / "shrink.img"
        shrink_data = b"T" * 300
        shrink_source = tmp / "small2.bin"
        shrink_source.write_bytes(shrink_data)
        with grow.open("rb") as handle:
            handle.seek(_cluster_offset(grow, 10))
            freed_before = handle.read(4096)
        rep = patch_image(grow, "SMALL.BIN", shrink_source, shrink, allow_resize=True)
        check("shrink: cluster count 2 -> 1",
              (rep["clusters_before"], rep["clusters_after"]) == (2, 1))
        copies = _fat_copies(shrink)
        check("shrink: freed cluster is 0 in both FATs",
              all(mkcard.fat_get(f, 10) == 0 for f in copies))
        check("shrink: last kept cluster is EOC",
              all(mkcard.fat_get(f, 6) == EOC for f in copies))
        check("shrink: FSInfo free count +1",
              rep["fsinfo"][0]["free_after"] == rep["fsinfo"][0]["free_before"] + 1)
        with shrink.open("rb") as handle:
            handle.seek(_cluster_offset(shrink, 10))
            freed_after = handle.read(4096)
            handle.seek(_cluster_offset(shrink, 6) + 300)
            zero_tail = handle.read(4096 - 300)
        check("shrink: freed cluster untouched", freed_after == freed_before)
        check("shrink: slack after new EOF zeroed", zero_tail == b"\x00" * 3796)
        check("shrink: verify read-back", rep["verify"]["matches"])
        allowed = [(w["offset"], w["offset"] + w["length"]) for w in rep["writes"]]
        diff = mkcard.diff_ranges(grow, shrink)
        check("shrink: diffs inside the planned writes", _contained(diff, allowed))

        # --- 4. the 0x06000000 version copy ---------------------------
        ver = tmp / "ver.img"
        new_hdd = b"QSD-901-401\r\n" + mkcard.SYNTH_HDD[13:]
        hdd_source = tmp / "HDD_INFO.TXT"
        hdd_source.write_bytes(new_hdd)
        rep = patch_image(shrink, VERSION_FILE, hdd_source, ver,
                          update_version_copy=True)
        check("copy: old 0x06000000 copy matched the old file",
              rep["version_copy"]["copied_old_file"])
        check("copy: file read-back and copy verified",
              rep["verify"]["ok"] and rep["verify"]["version_copy"]["matches"])
        with ver.open("rb") as handle:
            handle.seek(HDD_COPY_OFFSET)
            copy_bytes = handle.read(HDD_COPY_LEN)
        check("copy: 0x06000000 holds the new 72 bytes", copy_bytes == new_hdd)
        allowed = [(w["offset"], w["offset"] + w["length"]) for w in rep["writes"]]
        diff = mkcard.diff_ranges(shrink, ver)
        check("copy: diffs only in the file cluster and the copy",
              _contained(diff, allowed)
              and any(HDD_COPY_OFFSET <= start < HDD_COPY_OFFSET + HDD_COPY_LEN
                      for start, _ in diff))

        # --- 5. an empty file (start cluster 0) grows -----------------
        empty_source = tmp / "empty.bin"
        empty_source.write_bytes(b"now non-empty\n")
        rep = patch_image(ver, "EMPTY.TXT", empty_source, tmp / "empty.img",
                          allow_resize=True)
        check("empty file: start cluster 0 -> allocated",
              rep["start_cluster_before"] == 0
              and rep["start_cluster_after"] != 0)
        check("empty file: dir entry size updated",
              rep["dir_entry"]["size_before"] == 0
              and rep["dir_entry"]["size_after"] == 14)
        check("empty file: verify read-back", rep["verify"]["matches"])

        # --- 6. --dry-run and --verify -------------------------------
        before = mkcard.sha256_file(ver)
        dry = patch_image(ver, "NOTE.TXT", source, dry_run=True)
        check("dry-run: plan produced without verifying",
              dry["dry_run"] and dry["verify"] is None and dry["writes"])
        check("dry-run: image unchanged", mkcard.sha256_file(ver) == before)
        ver_result = verify_image(ver, VERSION_FILE, hdd_source,
                                  update_version_copy=True)
        check("verify mode: read-back matches", ver_result["ok"])
        wrong = tmp / "wrong.txt"
        wrong.write_bytes(b"nope\n")
        bad = verify_image(ver, "NOTE.TXT", wrong)
        check("verify mode: a mismatch is reported, not raised", bad["ok"] is False)

        # --- 7. refusals (none may write) ----------------------------
        expect_refusal("file-not-found", patch_image, ver, "REFER001/NOPE.DAT",
                       source, tmp / "x.img")
        expect_refusal("file-not-found", patch_image, ver, "NOTE.TXT",
                       tmp / "missing.txt", tmp / "x.img")
        expect_refusal("size-change", patch_image, ver, "NOTE.TXT", grow_source,
                       tmp / "x.img")
        expect_refusal("same-image", patch_image, ver, "NOTE.TXT", source, ver)
        expect_refusal("version-copy-target", patch_image, ver, "NOTE.TXT",
                       hdd_source, tmp / "x.img", update_version_copy=True)
        short_hdd = tmp / "short.txt"
        short_hdd.write_bytes(new_hdd[:-1])
        expect_refusal("version-copy-size", patch_image, ver, VERSION_FILE,
                       short_hdd, tmp / "x.img", update_version_copy=True)
        check("refusals: image bytes unchanged", mkcard.sha256_file(ver) == before)

        # --- 8. CLI exit codes and JSON ------------------------------
        import contextlib
        import io

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = main(["--image", str(ver), "--file", "NOTE.TXT",
                         "--from", str(source), "--dry-run", "--json"])
        payload = json.loads(buffer.getvalue())
        check("cli: dry-run --json exits 0", code == 0)
        check("cli: json reports the plan",
              payload["dry_run"] and payload["file"] == "NOTE.TXT"
              and payload["ok"])

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = main(["--image", str(ver), "--file", "NOTE.TXT",
                         "--from", str(source), "-o", str(ver), "--json"])
        payload = json.loads(buffer.getvalue())
        check("cli: output == source exits 3",
              code == 3 and payload["error"] == "same-image")
        check("cli: refusal json is ok=false", payload["ok"] is False)

        buffer = io.StringIO()
        try:
            with contextlib.redirect_stdout(buffer), \
                    contextlib.redirect_stderr(io.StringIO()):
                code = main(["--image", str(ver), "--file", "NOTE.TXT",
                             "--from", str(source), "--same-length",
                             "--allow-resize"])
        except SystemExit as exc:
            code = exc.code
        check("cli: --same-length with --allow-resize is a usage error (2)", code == 2)

        # --- 9. independent BPB+FAT diff check (M5.24) ---------------
        # Positive: S2-style case on synthetic image. 'same' differs from
        # 'fixture' only in NOTE.TXT's cluster/dir entry; allowed ranges
        # come from an independent BPB+FAT read, not write offsets.
        dc = check_diff_ranges(same, fixture, ["NOTE.TXT"])
        check("check-diff: in-range diffs pass", dc["ok"])
        check("check-diff: diffs found", dc["diff_range_count"] > 0)
        check("check-diff: no outside ranges", dc["outside_range_count"] == 0)
        check("check-diff: method names independent BPB+FAT read",
              "independent BPB+FAT read" in dc["files"][0]["method"])
        check("check-diff: chain resolved from BPB/FAT",
              dc["files"][0]["chain"] == [7])

        # Multi-file: grow changed SMALL.BIN vs same. A resize also changes
        # FAT/FSInfo (legitimate metadata); the cluster+dir-entry check from
        # an independent BPB+FAT read must contain the file's data diffs, and
        # any outside ranges must be only FAT/FSInfo metadata.
        dc2 = check_diff_ranges(grow, same, ["SMALL.BIN"])
        with grow.open("rb") as handle:
            _part, geo, _fat = mkcard.open_map_partition(handle)
            meta = [(geo.fat_offset, geo.fat_offset + geo.fat_count * geo.fat_bytes)]
            for sec in [geo.fsinfo_sector] + ([geo.backup_boot + geo.fsinfo_sector]
                                               if geo.backup_boot else []):
                if sec and sec < geo.reserved:
                    off = geo.part_offset + sec * geo.bps
                    meta.append((off, off + geo.bps))
        file_allowed = dc2["allowed_ranges"]
        file_ok = _ranges_contained(
            [r for r in mkcard.diff_ranges(same, grow)
             if _ranges_contained([r], file_allowed)
             or not _ranges_contained([r], _merge_ranges(meta))],
            file_allowed)  # no non-meta, non-file diffs
        meta_outside = _outside_ranges(
            mkcard.diff_ranges(same, grow), file_allowed)
        check("check-diff: resize file clusters/dir found by BPB+FAT",
              any(f["chain"] for f in dc2["files"]))
        check("check-diff: resize outside diffs are only FAT/FSInfo metadata",
              _ranges_contained(meta_outside, meta),
              f"outside={[r for r in meta_outside[:3]]}")

        # easier multi-file positive: fixture vs grow allows NOTE+SMALL.
        # fixture had original NOTE/SMALL; grow has new NOTE? no - grow was
        # built from 'same' (patched NOTE) then SMALL grown. So fixture->grow
        # differs in NOTE.TXT and SMALL.BIN.
        dc3 = check_diff_ranges(grow, fixture, ["NOTE.TXT", "SMALL.BIN"])
        meta_outside3 = _outside_ranges(mkcard.diff_ranges(fixture, grow),
                                        dc3["allowed_ranges"])
        check("check-diff: multi-file clusters/dir resolved independently",
              len(dc3["files"]) == 2 and dc3["files"][0]["chain"] == [7])
        check("check-diff: multi-file outside diffs only FAT/FSInfo metadata",
              _ranges_contained(meta_outside3, meta),
              f"outside={dc3['outside_range_count']}")

        # Negative: flip one byte outside every allowed range and report.
        bad_img = tmp / "bad-diff.img"
        mkcard.copy_image(grow, bad_img)
        allowed_union = _merge_ranges(
            (c["offset"], c["offset"] + c["length"])
            for f in dc3["files"] for c in f["cluster_ranges"]
        ) + [(f["dir_entry"]["offset"], f["dir_entry"]["offset"] + 32)
             for f in dc3["files"]]
        allowed_union = _merge_ranges(allowed_union)
        # pick a byte inside the map partition but outside allowed ranges
        with bad_img.open("r+b") as handle:
            _part, geo, _fat = mkcard.open_map_partition(handle)
            probe = geo.part_offset + geo.bps * 2  # early in partition
            for _ in range(10000):
                if not any(a <= probe < b for a, b in allowed_union):
                    handle.seek(probe)
                    orig = handle.read(1)
                    handle.seek(probe)
                    handle.write(bytes([orig[0] ^ 0xFF]))
                    break
                probe += 257
            else:
                raise AssertionError("could not find a probe byte outside allowed ranges")
        dc4 = check_diff_ranges(bad_img, fixture, ["NOTE.TXT", "SMALL.BIN"])
        check("check-diff: outside diff reported", not dc4["ok"])
        check("check-diff: outside range counted", dc4["outside_range_count"] >= 1)
        check("check-diff: classification names file_data and an outside byte",
              "file_data" in dc4["classification"]
              and "unclassified_in_envelope" in dc4["classification"],
              str(sorted(dc4["classification"])))

        # --- 9b. per-range metadata reasons and --strict-metadata (M5.51) --
        # A resize rewrites only the move's own FAT links and FSInfo words.
        # With a reference read each metadata range is named; strict mode
        # accepts those names and refuses any other byte in the FAT/FSInfo.
        dsm = check_diff_ranges(grow, same, ["SMALL.BIN"],
                                allow_metadata=True, strict_metadata=True)
        reasons = dsm["metadata_reasons"]
        check("strict-metadata: real move has no unexpected metadata",
              dsm["unexpected_metadata_count"] == 0, str(reasons))
        check("strict-metadata: every range carries a reason",
              all(r.get("reason") for r in reasons),
              str([r.get("reason") for r in reasons]))
        check("strict-metadata: the move's links are named fat*_link",
              any(r["reason"] in ("fat0_link", "fat1_link") for r in reasons),
              str(sorted({r["reason"] for r in reasons})))
        check("strict-metadata: ok is true on the real move", dsm["ok"])

        # Negative: flip a byte in a FAT entry that is NOT on SMALL.BIN's
        # old/new chain -> strict mode must name it slack and fail.
        fslack = tmp / "fat-slack.img"
        mkcard.copy_image(grow, fslack)
        with fslack.open("r+b") as handle:
            _part, geo_s, fat_s = mkcard.open_map_partition(handle)
            # find a free FAT entry (value 0) in FAT0 that is NOT one of the
            # move's own metadata ranges, so planting there is genuine slack
            own = dsm["metadata_diff_ranges"]
            victim = None
            for c in range(60, 400):
                off_c = geo_s.fat_offset + c * 4
                if mkcard.fat_get(fat_s, c) != 0:
                    continue
                if any(a <= off_c < b for a, b in own):
                    continue
                victim = c
                break
            assert victim is not None
            entry_off = geo_s.fat_offset + victim * 4
            handle.seek(entry_off)
            handle.write(b"\x01\x00\x00\x00")
            victim_entry = victim
        dsmb = check_diff_ranges(fslack, same, ["SMALL.BIN"],
                                 allow_metadata=True, strict_metadata=True)
        named = [r for r in dsmb["metadata_reasons"]
                 if r.get("kind") == "fat" and r.get("entry") == victim_entry]
        check("strict-metadata: planted FAT slack entry is named",
              bool(named) and named[0]["reason"].endswith("_slack"),
              str(named[:1]))
        check("strict-metadata: planted FAT slack fails strict",
              (not dsmb["ok"]) and dsmb["unexpected_metadata_count"] >= 1)
        # But without strict it is still admitted as metadata (the M5.30 class)
        dwide = check_diff_ranges(fslack, same, ["SMALL.BIN"],
                                  allow_metadata=True)
        check("allow-metadata: the slack byte is still admitted wide",
              dwide["ok"])


        # --- 10. allocation is bounded by the partition, not the FAT (M5.30) --
        # The fixture's 128 FAT entries address 123 data clusters (2..124), so a
        # growth that needs the clusters at 125..127 must fail loudly as "no
        # space", not bind a chain whose offsets fall outside the partition.
        with ver.open("rb") as handle:
            _p, geo_v, fat_v = mkcard.open_map_partition(handle)
        valid_last = _cluster_count(geo_v) + 1
        check("bound: fixture last valid cluster is 124",
              valid_last == 124, str(valid_last))
        free_valid = sum(1 for c in range(2, valid_last + 1)
                         if mkcard.fat_get(fat_v, c) == 0)
        small_len = len(mkcard.chain(fat_v, 6))
        over = b"O" * ((small_len + free_valid + 1) * geo_v.cluster_bytes)
        over_source = tmp / "over.bin"
        over_source.write_bytes(over)
        try:
            patch_image(ver, "SMALL.BIN", over_source, tmp / "over.img",
                        allow_resize=True)
        except PatchError as exc:
            over_reason = exc.reason
        else:
            over_reason = "none"
        check("bound: over-partition growth refuses as no-space, not internal-range",
              over_reason == "no-space", over_reason)
        fit_source = tmp / "fit.bin"
        fit_source.write_bytes(b"F" * ((small_len + free_valid) * geo_v.cluster_bytes))
        fit_img = tmp / "fit.img"
        rep_fit = patch_image(ver, "SMALL.BIN", fit_source, fit_img,
                              allow_resize=True)
        drawn = [c for c in rep_fit["chain_after"] if c >= 10]
        check("bound: fitting growth draws only in-partition clusters",
              rep_fit["ok"] and drawn and max(drawn) <= valid_last,
              f"max drawn {max(drawn) if drawn else None} > {valid_last}")
        check("bound: fitting growth verifies", rep_fit["verify"]["matches"])
        # Negative control for the test itself: the *old* bound (the FAT length)
        # would have offered 125..127 to the same request.
        probe_fat = bytearray(128 * 4)
        for c in range(2, 10):
            mkcard.fat_set(probe_fat, c, 0x0FFFFFF8)
        probe_valid = 124
        probe_free = sum(1 for c in range(2, probe_valid + 1)
                         if mkcard.fat_get(probe_fat, c) == 0)
        try:
            mkcard.alloc_clusters(bytearray(probe_fat), probe_free + 1,
                                  start_hint=10, max_cluster=probe_valid)
            raised = False
        except ValueError:
            raised = True
        check("bound: alloc_clusters with max_cluster refuses the overflow", raised)
        unbound = mkcard.alloc_clusters(bytearray(probe_fat), probe_free + 1,
                                       start_hint=10)
        check("bound: the same request without max_cluster escapes past 124",
              max(unbound) > probe_valid, str(max(unbound)))

        # CLI (same-cluster-count case: NOTE.TXT only, no FAT/FSInfo diffs)
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = main(["--check-diff", "--image", str(same),
                         "--reference", str(fixture),
                         "--file", "NOTE.TXT", "--json"])
        payload = json.loads(buffer.getvalue())
        check("cli: --check-diff --json exits 0", code == 0 and payload["ok"])
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = main(["--check-diff", "--image", str(bad_img),
                         "--reference", str(fixture),
                         "--file", "NOTE.TXT", "--file", "SMALL.BIN", "--json"])
        payload = json.loads(buffer.getvalue())
        check("cli: --check-diff mismatch exits 1",
              code == 1 and not payload["ok"])

        if errors == 0:
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = main(["--verify", "--image", str(ver), "--file",
                             VERSION_FILE, "--from", str(hdd_source),
                             "--update-version-copy", "--json"])
            check("cli: --verify --json exits 0", code == 0)

    if errors:
        print(f"imgpatch self-test: {errors}/{checks} FAILED")
        return 1
    print(f"imgpatch self-test: OK ({checks} checks)")
    return 0


# --- CLI -------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Exit codes: 0 success, 1 verify mismatch, 2 usage error, "
               "3 refused by a guard.",
    )
    parser.add_argument("--image", help="SD card image to patch or verify")
    parser.add_argument("--file", action="append", dest="files",
                        help="path inside the card, e.g. REFER001/X.DAT.cmp "
                             "(repeatable with --check-diff)")
    parser.add_argument("--from", dest="source", metavar="NEWFILE",
                        help="host file with the new content")
    parser.add_argument("-o", "--out", help="write the patched copy here "
                                            "(default: patch --image in place)")
    parser.add_argument("--dry-run", action="store_true",
                        help="parse, resolve and report; write nothing")
    parser.add_argument("--json", action="store_true", help="machine-readable report")
    parser.add_argument("--allow-resize", action="store_true",
                        help="allow a size change (grow/shrink the chain)")
    parser.add_argument("--same-length", action="store_true",
                        help="state the default guard explicitly: size must not change")
    parser.add_argument("--update-version-copy", action="store_true",
                        help=f"also copy {VERSION_FILE} to 0x{HDD_COPY_OFFSET:08x}")
    parser.add_argument("--verify", action="store_true",
                        help="only read the file back and compare hashes")
    parser.add_argument("--check-diff", action="store_true",
                        help="check that every diff vs --reference lies in each "
                             "--file's clusters/dir entry, resolved from an "
                             "independent BPB+FAT read (M5.24)")
    parser.add_argument("--allow-metadata", action="store_true",
                        help="with --check-diff: allow FAT-sector and FSInfo "
                             "diffs too (a size change must touch them); they "
                             "are still reported separately (M5.30)")
    parser.add_argument("--strict-metadata", action="store_true",
                        help="with --check-diff: fail any metadata range whose "
                             "reason is not one of the move's own FAT links "
                             "(fat0_link/fat1_link) or FSInfo words "
                             "(fsinfo_free/fsinfo_nxt); implies --allow-metadata")
    parser.add_argument("--reference", metavar="REFIMG",
                        help="baseline image for --check-diff")
    parser.add_argument("--hash", action="store_true",
                        help="include the output image SHA-256 in the report")
    parser.add_argument("--selftest", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()
    files = args.files or []
    file_arg = files[0] if files else None
    if args.check_diff:
        if not args.image or not args.reference or not files:
            parser.error("--check-diff requires --image, --reference and --file")
        if args.source or args.out or args.dry_run or args.verify:
            parser.error("--check-diff does not accept --from/-o/--dry-run/--verify")
        try:
            result = check_diff_ranges(args.image, args.reference, files,
                                       allow_metadata=args.allow_metadata,
                                       strict_metadata=args.strict_metadata)
        except PatchError as exc:
            if args.json:
                print(json.dumps({"ok": False, "mode": "check-diff",
                                  "error": exc.reason, "message": exc.message},
                                 indent=2))
            else:
                print(f"imgpatch: {exc.message}", file=sys.stderr)
            return exc.exit_code
        _emit(result, args.json, check_diff=True)
        return 0 if result["ok"] else 1
    if not args.image or not file_arg or not args.source:
        parser.error("--image, --file and --from are required (or use --selftest)")
    if len(files) > 1 and not args.verify:
        parser.error("patch/verify accept a single --file; use --check-diff for multiple")
    if args.same_length and args.allow_resize:
        parser.error("--same-length and --allow-resize are mutually exclusive")
    if args.verify and (args.out or args.dry_run):
        parser.error("--verify does not accept -o/--dry-run")

    if args.verify:
        try:
            result = verify_image(args.image, file_arg, args.source,
                                  update_version_copy=args.update_version_copy)
        except PatchError as exc:
            if args.json:
                print(json.dumps({"ok": False, "mode": "verify",
                                  "error": exc.reason, "message": exc.message},
                                 indent=2))
            else:
                print(f"imgpatch: {exc.message}", file=sys.stderr)
            return exc.exit_code
        _emit(result, args.json, verify_only=True)
        return 0 if result["ok"] else 1

    try:
        report = patch_image(
            args.image, file_arg, args.source, args.out,
            allow_resize=args.allow_resize, dry_run=args.dry_run,
            update_version_copy=args.update_version_copy,
            hash_output=args.hash,
        )
    except PatchError as exc:
        if args.json:
            print(json.dumps({"ok": False, "mode": "patch", "error": exc.reason,
                              "message": exc.message}, indent=2))
        else:
            print(f"imgpatch: refused ({exc.reason}): {exc.message}",
                  file=sys.stderr)
        return exc.exit_code

    if args.json:
        _emit(report, True)
    else:
        _print_patch(report)
        if report["target"] and not report["dry_run"]:
            print("patched in place" if report["patched_in_place"]
                  else f"wrote {report['target']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
