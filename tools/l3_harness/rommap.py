#!/usr/bin/env python3
"""Convert a CE ROM TOC report into a Ghidra loader memory map (JSON).

Input is the JSON report produced by ``tools/cerom.py ... memmap`` (or the
legacy ``tools/ce_rom_parse.py``) plus a
section table per module::

    {
      "image": "...", "image_size": 123, "image_sha256": "...",
      "segments": [
        {"segment_base": "0x200200", "phys_base": "0x8cae1000",
         "romhdr": {"ulRAMStart": ..., "ulRAMEnd": ...},
         "modules": [
           {"name": "Navi.exe", "vbase": "0x...",
            "sections": [
              {"name": ".text", "va": "0x...", "file_offset": 1234,
               "size": 4096, "characteristics": "0x60000020",
               "compressed": false}
            ]}
         ]}
      ]
    }

Section fields accept the ``o32_rom`` aliases as well (``realaddr``/``dataptr``/
``vsize``/``psize``/``flags``), so the map can be built directly from
``tools/cerom.py`` once it exists.  ``va`` is the runtime address
(``o32_realaddr``) and ``file_offset`` is the image offset of the stored bytes
(``p2f(o32_dataptr)``).

Output is one segment per document: a Ghidra program is one build, so builds
A/B/C are converted separately with ``--segment``.  Every block carries
``address``/``size``/``file_offset``/``permissions``/``loadable``; a BSS
section has no file bytes, and a compressed section is **rejected** because
nothing in the repo can decompress it yet.

This module never imports ``tools/cerom.py``: it only needs the documented
JSON contract.

Usage::

    python3 tools/l3_harness/rommap.py convert \\
        --report /tmp/ce-rom-report.json \\
        --segment 0 --out /tmp/l3/rommap.json
    python3 tools/l3_harness/rommap.py validate /tmp/l3/rommap.json
    python3 tools/l3_harness/rommap.py selftest

Exit codes: ``0`` ok, ``1`` invalid report/map, ``2`` usage error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SCHEMA = "osm2leaf.l3.rommap/v1"
GENERATOR = "tools/l3_harness/rommap.py"

#: Ghidra language id.  ``verified`` stays false until a real run confirms it.
PROCESSOR_ID = "SuperH:BE:32:SH-4"
PROCESSOR_VERIFIED = False

MEM_EXECUTE = 0x20000000
MEM_READ = 0x40000000
MEM_WRITE = 0x80000000
CNT_CODE = 0x00000020
CNT_INITIALIZED_DATA = 0x00000040
CNT_UNINITIALIZED_DATA = 0x00000080
SCN_COMPRESSED = 0x00002000

ADDRESS_LIMIT = 0x1_0000_0000

#: Canonical section field -> accepted aliases (first present wins).
SECTION_ALIASES = {
    "name": ("name",),
    "va": ("va", "realaddr", "o32_realaddr", "address"),
    "size": ("size", "vsize", "o32_vsize"),
    "stored_size": ("stored_size", "psize", "o32_psize"),
    "file_offset": ("file_offset", "dataptr", "o32_dataptr", "offset"),
    "characteristics": ("characteristics", "flags", "o32_flags"),
    "compressed": ("compressed",),
}

BLOCK_KEYS = {
    "name",
    "module",
    "section",
    "address",
    "end",
    "size",
    "stored_size",
    "file_offset",
    "file_backed",
    "loadable",
    "permissions",
    "characteristics",
    "init_len",
    "guard_init",
    "init_source",
}

_PERMISSIONS_RE = re.compile(r"^[r-][w-][x-]$")


class RommapError(ValueError):
    """Raised when a report cannot be converted into a valid memory map."""

    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__("; ".join(self.problems))


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _int(value, field: str, problems: list[str]) -> int | None:
    if _is_int(value):
        return value
    if isinstance(value, str):
        try:
            return int(value, 0)
        except ValueError:
            problems.append(f"{field}: not an integer: {value!r}")
            return None
    problems.append(f"{field}: missing or not an integer: {value!r}")
    return None


def _first(mapping: dict, names):
    for name in names:
        if name in mapping:
            return mapping[name]
    return None


def _hex(value: int) -> str:
    return f"0x{value:x}"


def _permissions(characteristics: int) -> str:
    if characteristics & (MEM_EXECUTE | MEM_READ | MEM_WRITE):
        read = bool(characteristics & MEM_READ)
        execute = bool(characteristics & MEM_EXECUTE)
        write = bool(characteristics & MEM_WRITE)
    else:
        # No MEM_* bits: fall back to the content flags.
        read = True
        execute = bool(characteristics & CNT_CODE)
        write = bool(characteristics & CNT_UNINITIALIZED_DATA)
    return ("r" if read else "-") + ("w" if write else "-") + (
        "x" if execute else "-"
    )


def load(path) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _select_segment(segments, selection):
    if selection is None:
        index = 0
    elif _is_int(selection):
        index = selection
    elif isinstance(selection, str):
        try:
            index = int(selection, 0)
        except ValueError:
            raise RommapError([f"bad segment selector {selection!r}"])
    else:
        raise RommapError([f"bad segment selector {selection!r}"])

    if not (0 <= index < len(segments)):
        raise RommapError(
            [f"segment index {index} out of range (report has {len(segments)})"]
        )
    return index, segments[index]


def _collect(report, selection, selected_modules, skip_compressed,
             bss_zero=False, init_guard=False, image_path=None,
             image_start=0x200200, resolve_with=None):
    problems: list[str] = []
    resolve_with = list(resolve_with or [])
    if not isinstance(report, dict):
        raise RommapError(["report must be a JSON object"])
    segments = report.get("segments")
    if not isinstance(segments, list) or not segments:
        raise RommapError(["report has no segments"])

    index, segment = _select_segment(segments, selection)
    if not isinstance(segment, dict):
        raise RommapError([f"segments[{index}] is not an object"])

    segment_base = _int(segment.get("segment_base"), "segment_base", problems)
    phys_base = _int(segment.get("phys_base"), "phys_base", problems)
    romhdr = segment.get("romhdr") if isinstance(segment.get("romhdr"), dict) else {}

    ram = None
    ram_start = _int(romhdr.get("ulRAMStart"), "romhdr.ulRAMStart", [])
    ram_end = _int(romhdr.get("ulRAMEnd"), "romhdr.ulRAMEnd", [])
    if ram_start is not None and ram_end is not None:
        if ram_start < ram_end:
            ram = {
                "start": _hex(ram_start),
                "end": _hex(ram_end),
                "size": ram_end - ram_start,
                "writable": True,
                "zero_fill": True,
                "source": "ROMHDR.ulRAMStart..ulRAMEnd",
            }
        else:
            problems.append(
                "romhdr.ulRAMStart must be below romhdr.ulRAMEnd"
            )

    modules = segment.get("modules")
    if not isinstance(modules, list) or not modules:
        raise RommapError([f"segments[{index}] has no modules"])

    wanted = set(selected_modules or ())
    seen_modules: set[str] = set()
    blocks: list[dict] = []
    skipped: list[dict] = []
    iat_bindings: list[dict] = []
    init_guards: list[dict] = []
    sec_models: dict[str, dict] = {}
    sec_iats: dict[str, dict] = {}

    if bss_zero or init_guard:
        if not image_path:
            raise RommapError([
                "--bss-zero/--init-guard need --image (to read comphdr and imports)"
            ])
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
            import cerom
            import va_class
            with open(image_path, "rb") as handle:
                image_data = handle.read()
            rom = cerom.CERom(image_data, image_start)
            resolvers = [rom] + [cerom.CERom(image_data, s) for s in resolve_with]
        except Exception as exc:  # noqa: BLE001
            raise RommapError([f"cannot load sec1 model from {image_path}: {exc}"])


    for module_index, module in enumerate(modules):
        if not isinstance(module, dict):
            problems.append(f"modules[{module_index}] is not an object")
            continue
        module_name = module.get("name")
        if not isinstance(module_name, str) or not module_name:
            problems.append(f"modules[{module_index}]: missing name")
            continue
        if wanted and module_name not in wanted:
            continue
        if module_name in seen_modules:
            problems.append(f"{module_name}: duplicate module name")
        seen_modules.add(module_name)

        sections = module.get("sections")
        if not isinstance(sections, list) or not sections:
            problems.append(f"{module_name}: no sections")
            continue

        if (bss_zero or init_guard) and module_name not in sec_models:
            try:
                sec_models[module_name] = {
                    s["index"]: s
                    for s in va_class.section_layout(
                        rom, image_data, module_name, image_start
                    )
                }
                sec_iats[module_name] = va_class.import_slots(
                    rom, module_name, resolvers
                )
            except Exception as exc:  # noqa: BLE001
                problems.append(f"{module_name}: cannot build load model: {exc}")
                sec_models[module_name] = {}
                sec_iats[module_name] = {}

        for section_index, section in enumerate(sections):
            if not isinstance(section, dict):
                problems.append(
                    f"{module_name}: sections[{section_index}] is not an object"
                )
                continue
            where = f"{module_name}: sections[{section_index}]"

            section_name = _first(section, SECTION_ALIASES["name"])
            if not isinstance(section_name, str) or not section_name:
                section_name = f"sec{section_index}"

            va = _int(
                _first(section, SECTION_ALIASES["va"]), f"{where}.va", problems
            )
            size = _int(
                _first(section, SECTION_ALIASES["size"]), f"{where}.size", problems
            )
            characteristics = _int(
                _first(section, SECTION_ALIASES["characteristics"]),
                f"{where}.characteristics",
                problems,
            )
            if characteristics is None:
                characteristics = 0

            stored_raw = _first(section, SECTION_ALIASES["stored_size"])
            stored_size = (
                size
                if stored_raw is None
                else _int(stored_raw, f"{where}.stored_size", problems)
            )

            if va is None or size is None:
                continue
            if size <= 0:
                problems.append(f"{where}: size must be positive")
                continue
            if va < 0 or va + size > ADDRESS_LIMIT:
                problems.append(
                    f"{where}: address range {_hex(va)}..{_hex(va + size)} "
                    "does not fit a 32-bit address space"
                )
                continue

            compressed = section.get("compressed")
            if compressed is None:
                compressed = bool(characteristics & SCN_COMPRESSED)
            elif not isinstance(compressed, bool):
                problems.append(f"{where}: compressed must be a boolean")
                continue
            if characteristics & SCN_COMPRESSED:
                compressed = True

            uninitialized = characteristics & CNT_UNINITIALIZED_DATA
            file_backed = not (uninitialized and stored_size == 0)
            file_offset = None
            if file_backed:
                file_offset = _int(
                    _first(section, SECTION_ALIASES["file_offset"]),
                    f"{where}.file_offset",
                    problems,
                )
                if file_offset is not None and file_offset < 0:
                    problems.append(f"{where}: file_offset must be non-negative")
                    continue

            if compressed:
                if bss_zero or init_guard:
                    model = (sec_models.get(module_name) or {}).get(section_index)
                    iat_map = sec_iats.get(module_name) or {}
                    init_len = None if model is None else model.get("init_len")
                    runtime_size = _int(
                        _first(section, ("vsize", "o32_vsize", "size")),
                        f"{where}.vsize",
                        problems,
                    )
                    if runtime_size is None:
                        continue
                    if init_len is None:
                        problems.append(
                            f"{where} ({section_name}): compressed section has no "
                            "parsed comphdr/uncompressed_len; cannot model BSS/INIT"
                        )
                        continue
                    init_len = int(init_len)
                    if init_len < 0 or init_len > runtime_size:
                        problems.append(
                            f"{where} ({section_name}): init_len {init_len} outside "
                            f"section vsize {runtime_size}"
                        )
                        continue
                    slots = []
                    for slot_va, (dll, name) in sorted(iat_map.items()):
                        if va <= slot_va < va + init_len:
                            slots.append({
                                "va": _hex(slot_va),
                                "dll": dll,
                                "name": name,
                            })
                    if init_guard and slots:
                        for slot in slots:
                            if slot not in iat_bindings:
                                iat_bindings.append(slot)
                    if init_guard and init_len > 0:
                        init_guards.append({
                            "module": module_name,
                            "section": section_name,
                            "start": _hex(va),
                            "end": _hex(va + init_len),
                            "init_len": init_len,
                            "iat_slots": [slot["va"] for slot in slots],
                            "reason": "INIT bytes need M1.2f; IAT slots are exceptions",
                        })
                    block = {
                        "name": f"{module_name}/{section_name}",
                        "module": module_name,
                        "section": section_name,
                        "address": _hex(va),
                        "end": _hex(va + runtime_size),
                        "size": runtime_size,
                        "stored_size": 0,
                        "file_offset": None,
                        "file_backed": False,
                        "loadable": True,
                        "permissions": _permissions(characteristics),
                        "characteristics": _hex(characteristics),
                        "init_len": init_len,
                        "guard_init": bool(init_guard),
                        "init_source": "zero-bss-init-guard" if init_guard else "zero-bss",
                    }
                    blocks.append(block)
                    continue
                if skip_compressed:
                    skipped.append(
                        {
                            "module": module_name,
                            "section": section_name,
                            "va": _hex(va),
                            "size": size,
                            "stored_size": stored_size,
                            "characteristics": _hex(characteristics),
                            "reason": (
                                "IMAGE_SCN_COMPRESSED (0x2000); the CE "
                                "decompressor is not implemented"
                            ),
                        }
                    )
                    continue
                problems.append(
                    f"{where} ({section_name}): compressed section "
                    f"(characteristics {_hex(characteristics)}); the CE "
                    "decompressor is not implemented, so it cannot be loaded. "
                    "Pass --skip-compressed to omit it explicitly."
                )
                continue

            block = {
                "name": f"{module_name}/{section_name}",
                "module": module_name,
                "section": section_name,
                "address": _hex(va),
                "end": _hex(va + size),
                "size": size,
                "stored_size": stored_size,
                "file_offset": _hex(file_offset) if file_offset is not None else None,
                "file_backed": file_backed,
                "loadable": True,
                "permissions": _permissions(characteristics),
                "characteristics": _hex(characteristics),
            }
            blocks.append(block)

    if wanted and not seen_modules:
        problems.append(f"no module matched {sorted(wanted)}")

    image_size = report.get("image_size")
    if _is_int(image_size) and image_size > 0:
        for block in blocks:
            if block["file_offset"] is None:
                continue
            offset = int(block["file_offset"], 0)
            if offset + block["stored_size"] > image_size:
                problems.append(
                    f"{block['name']}: file range {_hex(offset)}.."
                    f"{_hex(offset + block['stored_size'])} is outside the "
                    f"image ({_hex(image_size)} bytes)"
                )

    if problems:
        raise RommapError(problems)

    blocks.sort(key=lambda block: int(block["address"], 0))
    _check_overlaps(blocks)

    image_name = report.get("image")
    image_basename = Path(str(image_name)).name if image_name else None
    if not image_basename and image_path:
        image_basename = Path(str(image_path)).name
    doc = {
        "schema": SCHEMA,
        "generator": GENERATOR,
        "source": {
            "image": image_basename,
            "image_size": image_size if _is_int(image_size) else None,
            "image_sha256": report.get("image_sha256"),
            # cerom.py hashes a window, not always the whole file: the scope
            # text says which bytes the hash covers ("first N of M bytes").
            "image_sha256_scope": report.get("image_sha256_scope"),
            "report_schema": "cerom.py memmap JSON, sections normalised",
            "segment_index": index,
            "segment_base": _hex(segment_base) if segment_base is not None else None,
            "phys_base": _hex(phys_base) if phys_base is not None else None,
            "pTOC": _hex(segment["pTOC"])
            if _is_int(segment.get("pTOC"))
            else None,
            "romhdr": {
                "physfirst": _hex(romhdr["physfirst"])
                if _is_int(romhdr.get("physfirst"))
                else None,
                "physlast": _hex(romhdr["physlast"])
                if _is_int(romhdr.get("physlast"))
                else None,
                "ulRAMStart": _hex(ram_start) if ram_start is not None else None,
                "ulRAMEnd": _hex(ram_end) if ram_end is not None else None,
            },
        },
        "processor": {
            "id": PROCESSOR_ID,
            "endian": "big",
            "bits": 32,
            "verified": PROCESSOR_VERIFIED,
        },
        "ram": ram,
        "skipped": skipped,
        "blocks": blocks,
    }
    if bss_zero or init_guard:
        doc["load_model"] = {
            "mode": "bss-zero-init-guard" if init_guard else "bss-zero",
            "image": Path(str(image_path)).name if image_path else None,
            "image_start": _hex(image_start),
            "resolve_with": [_hex(v) for v in resolve_with],
        }
        doc["iat_bindings"] = iat_bindings
        doc["init_guards"] = init_guards
    problems = validate(doc)
    if problems:
        raise RommapError(problems)
    return doc


def _check_overlaps(blocks):
    for previous, current in zip(blocks, blocks[1:]):
        previous_end = int(previous["address"], 0) + previous["size"]
        current_start = int(current["address"], 0)
        if current_start < previous_end:
            raise RommapError(
                [
                    "overlapping sections: "
                    f"{previous['name']} [{previous['address']}.."
                    f"{previous['end']}) and {current['name']} "
                    f"[{current['address']}..{current['end']})"
                ]
            )


def validate(doc) -> list[str]:
    """Return structural problems in a generated memory map."""

    problems: list[str] = []
    if not isinstance(doc, dict):
        return ["memory map must be a JSON object"]
    if doc.get("schema") != SCHEMA:
        problems.append(f"schema: expected {SCHEMA!r}, got {doc.get('schema')!r}")

    processor = doc.get("processor")
    if not isinstance(processor, dict):
        problems.append("processor: missing or not an object")
    else:
        if not isinstance(processor.get("id"), str) or not processor.get("id"):
            problems.append("processor.id: missing")
        if processor.get("endian") not in ("big", "little"):
            problems.append("processor.endian: must be 'big' or 'little'")
        if processor.get("bits") != 32:
            problems.append("processor.bits: must be 32 for this ROM")

    source = doc.get("source")
    if not isinstance(source, dict):
        problems.append("source: missing or not an object")
    else:
        digest = source.get("image_sha256")
        if digest is not None:
            if not isinstance(digest, str) or not re.match(r"^[0-9a-f]{64}$", digest):
                problems.append("source.image_sha256: not a lowercase SHA-256")

    ram = doc.get("ram")
    if ram is not None:
        if not isinstance(ram, dict):
            problems.append("ram: must be an object or null")
        else:
            start = _int(ram.get("start"), "ram.start", problems)
            end = _int(ram.get("end"), "ram.end", problems)
            if start is not None and end is not None and start >= end:
                problems.append("ram: start must be below end")

    blocks = doc.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        problems.append("blocks: missing or empty")
        return problems

    names: set[str] = set()
    parsed: list[tuple[int, int, dict]] = []
    for index, block in enumerate(blocks):
        where = f"blocks[{index}]"
        if not isinstance(block, dict):
            problems.append(f"{where}: not an object")
            continue
        name = block.get("name")
        if not isinstance(name, str) or not name:
            problems.append(f"{where}: missing name")
        else:
            where = f"blocks[{index}] ({name})"
            if name in names:
                problems.append(f"{where}: duplicate block name")
            names.add(name)

        unknown = sorted(set(block) - BLOCK_KEYS)
        if unknown:
            problems.append(f"{where}: unknown key(s) {unknown}")

        for key in ("module", "section"):
            if not isinstance(block.get(key), str) or not block.get(key):
                problems.append(f"{where}: {key} must be a non-empty string")

        address = _int(block.get("address"), f"{where}.address", problems)
        end = _int(block.get("end"), f"{where}.end", problems)
        size = _int(block.get("size"), f"{where}.size", problems)
        stored_size = _int(
            block.get("stored_size"), f"{where}.stored_size", problems
        )
        characteristics = _int(
            block.get("characteristics"), f"{where}.characteristics", problems
        )
        if address is None or end is None or size is None:
            continue
        if size <= 0:
            problems.append(f"{where}: size must be positive")
            continue
        if end != address + size:
            problems.append(
                f"{where}: end {_hex(end)} != address+size "
                f"{_hex(address + size)}"
            )
        if address < 0 or end > ADDRESS_LIMIT:
            problems.append(f"{where}: address range outside 32 bits")
            continue
        if stored_size is not None and stored_size > size:
            problems.append(
                f"{where}: stored_size {stored_size} exceeds size {size}"
            )
        if characteristics is not None and characteristics & SCN_COMPRESSED:
            if block.get("loadable") and not block.get("guard_init") and block.get("init_source") not in ("zero-bss", "zero-bss-init-guard"):
                problems.append(
                    f"{where}: compressed section marked loadable"
                )

        if not isinstance(block.get("file_backed"), bool):
            problems.append(f"{where}: file_backed must be a boolean")
        if not isinstance(block.get("loadable"), bool):
            problems.append(f"{where}: loadable must be a boolean")
        permissions = block.get("permissions")
        if not isinstance(permissions, str) or not _PERMISSIONS_RE.match(permissions):
            problems.append(f"{where}: permissions must look like 'r-x'")

        if "init_len" in block and block["init_len"] is not None:
            ilen = _int(block.get("init_len"), f"{where}.init_len", problems)
            if ilen is not None and (ilen < 0 or ilen > size):
                problems.append(f"{where}: init_len outside block size")
        if "guard_init" in block and not isinstance(block.get("guard_init"), bool):
            problems.append(f"{where}: guard_init must be a boolean")

        file_offset = block.get("file_offset")
        if block.get("file_backed"):
            offset = _int(file_offset, f"{where}.file_offset", problems)
            if offset is not None and offset < 0:
                problems.append(f"{where}: file_offset must be non-negative")
        elif file_offset is not None:
            problems.append(
                f"{where}: non-file-backed block must have a null file_offset"
            )

        parsed.append((address, end, block))

    parsed.sort(key=lambda item: item[0])
    for (prev_start, prev_end, prev), (cur_start, cur_end, cur) in zip(
        parsed, parsed[1:]
    ):
        if cur_start < prev_end:
            problems.append(
                "overlapping sections: "
                f"{prev['name']} [{_hex(prev_start)}..{_hex(prev_end)}) and "
                f"{cur['name']} [{_hex(cur_start)}..{_hex(cur_end)})"
            )

    return problems


def convert(
    report,
    segment=None,
    modules=None,
    skip_compressed: bool = False,
    bss_zero: bool = False,
    init_guard: bool = False,
    image: str | None = None,
    image_start: int = 0x200200,
    resolve_with=None,
) -> dict:
    """Convert a cerom-style report into a memory map document."""

    return _collect(
        report, segment, modules, skip_compressed,
        bss_zero=bss_zero, init_guard=init_guard,
        image_path=image, image_start=image_start,
        resolve_with=resolve_with,
    )


def render_block_text(doc) -> str:
    """Diagnostic listing: one ``start end name`` line per block."""

    lines = []
    for block in doc.get("blocks", []):
        lines.append(
            f"{block['address']} {block['end']} {block['name']} "
            f"{block['permissions']}"
        )
    return "\n".join(lines) + ("\n" if lines else "")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CE ROM report -> Ghidra memory map")
    sub = parser.add_subparsers(dest="command", required=True)

    convert_cmd = sub.add_parser("convert", help="convert a report")
    convert_cmd.add_argument("--report", required=True)
    convert_cmd.add_argument("--out", help="write JSON here (default: stdout)")
    convert_cmd.add_argument(
        "--segment",
        default=None,
        help="segment index (0-based) or hex segment_base (default: 0)",
    )
    convert_cmd.add_argument(
        "--module",
        action="append",
        default=[],
        help="only this module (repeatable; default: all)",
    )
    convert_cmd.add_argument(
        "--skip-compressed",
        action="store_true",
        help="omit compressed sections instead of failing",
    )
    convert_cmd.add_argument(
        "--bss-zero",
        action="store_true",
        help="map compressed sections as zero-filled rw blocks using comphdr init_len (M9.35)",
    )
    convert_cmd.add_argument(
        "--init-guard",
        action="store_true",
        help="with --bss-zero, guard INIT reads outside IAT as BLOCKED INIT (M9.35)",
    )
    convert_cmd.add_argument(
        "--image",
        help="firmware image for --bss-zero/--init-guard (comphdr/imports)",
    )
    convert_cmd.add_argument(
        "--image-start",
        default="0x200200",
        help="CE image start for --image (default: 0x200200)",
    )
    convert_cmd.add_argument(
        "--resolve-with",
        action="append",
        default=[],
        help="extra CE image start(s) for ordinal import resolution (repeatable)",
    )
    convert_cmd.add_argument(
        "--text",
        action="store_true",
        help="print the block listing instead of JSON",
    )

    validate_cmd = sub.add_parser("validate", help="validate a memory map")
    validate_cmd.add_argument("rommap")
    validate_cmd.add_argument("--json", action="store_true")

    sub.add_parser("selftest", help="run the package self-test")
    return parser


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["--selftest"]:
        argv = ["selftest"]

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "selftest":
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from l3_harness import selftest

        return selftest.main([])

    if args.command == "convert":
        try:
            report = load(args.report)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"error: cannot read {args.report}: {exc}", file=sys.stderr)
            return 1
        try:
            resolve_with = [int(v, 0) for v in (getattr(args, "resolve_with", []) or [])]
            image_start = int(str(getattr(args, "image_start", "0x200200")), 0)
            doc = convert(
                report,
                segment=args.segment,
                modules=args.module,
                skip_compressed=args.skip_compressed,
                bss_zero=getattr(args, "bss_zero", False),
                init_guard=getattr(args, "init_guard", False),
                image=getattr(args, "image", None),
                image_start=image_start,
                resolve_with=resolve_with,
            )
        except RommapError as exc:
            for problem in exc.problems:
                print(f"error: {problem}", file=sys.stderr)
            return 1
        if args.text:
            sys.stdout.write(render_block_text(doc))
            return 0
        text = json.dumps(doc, indent=2) + "\n"
        if args.out:
            out = Path(args.out)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text, encoding="utf-8")
            print(
                f"wrote {out} ({len(doc['blocks'])} blocks, "
                f"{len(doc['skipped'])} skipped)"
            )
        else:
            sys.stdout.write(text)
        return 0

    if args.command == "validate":
        try:
            doc = load(args.rommap)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"error: cannot read {args.rommap}: {exc}", file=sys.stderr)
            return 1
        problems = validate(doc)
        if args.json:
            print(
                json.dumps(
                    {
                        "rommap": args.rommap,
                        "blocks": len(doc.get("blocks", []) or []),
                        "problems": problems,
                        "result": "PASS" if not problems else "FAIL",
                    },
                    indent=2,
                )
            )
        else:
            for problem in problems:
                print(f"FAIL {problem}")
            if problems:
                print(f"RESULT: FAIL ({len(problems)} problem(s))")
            else:
                print(
                    f"RESULT: PASS ({len(doc.get('blocks', []))} blocks, "
                    f"segment {doc.get('source', {}).get('segment_base')})"
                )
        return 0 if not problems else 1

    parser.error(f"unknown command {args.command!r}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
