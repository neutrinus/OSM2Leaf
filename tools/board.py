#!/usr/bin/env python3
"""Edit ``TODO.md`` and ``docs/research/claims.md`` by line operations.

Why (H123): agents used to rewrite these files whole. ``TODO.md`` is ~5k lines
and ``claims.md`` ~4.5k; a model that rewrites a file it has only partly read
drops what it did not read. PR #340 (commit ``6ca7bc3``) replaced 787 lines of
``TODO.md`` and 324 of ``claims.md`` with an older copy, and every checker
passed because each judges only the file in front of it (H121).

Every write here is one *splice*: lines ``[a, b)`` of the file are replaced by
new lines and everything else is copied byte for byte. Before writing, a guard
re-reads both versions and refuses the write when

* a task ID (``- [ ] **ID — …``) or a claim ID (``| C-nnnn |`` row) that was in
  the file is gone,
* the line count changed by anything but the splice's own delta,
* a task block other than the target changed, or
* the file on disk changed since it was read (another process wrote it).

The write is atomic (temp file + ``os.replace``). ``--dry-run`` prints the diff
and writes nothing.

Commands (``python3 tools/board.py CMD --help`` for each)::

    show ID                         print one task block
    claim ID --owner BRANCH         Status: in progress · Owner: BRANCH
    release ID                      Status: open · Owner: —
    status ID STATUS [--owner O]    set the status (and owner) only
    done ID --result TEXT           [x], Status: done, Result: TEXT
    block ID --blocker T --unblock IDS [--result T]
    field ID KEY VALUE [--append]   set (or extend) one field of one task
    add-task --section H FILE|-     insert a new task block at the end of a stream
             [--after ID]
    archive ID … --to HISTORY.md    move done task blocks to a todo-history file
    next-id STREAM                  next free task ID of a stream (H, M5, M9 …)
    next-claims                     next free claim block (TODO + claims.md)
    add-claims --section TITLE (--row ROW … | --file F) [--create]
    claim-status C-ID STATUS        change the Status cell of one claim row
    lost --base REF [--head REF] [FILE …]
                                    IDs present at REF and missing now (exit 1)
    resolve FILE                    merge a conflicted TODO/claims file by ID

``resolve`` replaces hand-resolution of a rebase or merge conflict in these two
files: it reads the three index stages (base, ours, theirs) and merges task
blocks and claim rows *by ID*, so both sides' additions survive. A unit changed
differently on both sides is left between conflict markers and the exit code
is 1. ``lost`` is the local form of H121's check; H121 reuses ``lost_ids``.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TODO_PATH = REPO_ROOT / "TODO.md"
CLAIMS_PATH = REPO_ROOT / "docs" / "research" / "claims.md"
DEFAULT_FILES = ("TODO.md", "docs/research/claims.md")

# Same grammar as tools/todo_check.py (TASK_RE, FIELD_RE) and
# tools/claims_check.py (ROW_RE); the selftest pins the two in step.
TASK_RE = re.compile(
    r"^- \[(?P<chk>[ xX])\] \*\*(?P<id>[A-Z][A-Za-z0-9./]*)(?:\s+[—–-]\s+|\*\*\s+)(?P<title>.+?)\*\*(?:\s.*)?$"
    r"|^- \[(?P<chk2>[ xX])\] \*\*(?P<id2>[A-Z][A-Za-z0-9./]*)(?:\s+[—–-]\s+|\*\*\s+)(?P<title2>.+?)$"
)
FIELD_RE = re.compile(r"^  - (?P<key>[A-Za-z][A-Za-z ]*?):\s*(?P<val>.*)$")
ROW_RE = re.compile(r"^\|\s*(C-\d+)\s*\|")
CLAIMS_FIELD_RE = re.compile(r"C-(\d+)\s*[–-]\s*C-(\d+)")
VALID_STATUS = ("open", "in progress", "blocked", "done")
NO_OWNER = "—"


class BoardError(Exception):
    """A refused operation; the message says why. Nothing was written."""


# ---------------------------------------------------------------- parsing

def split_lines(text: str) -> list[str]:
    return text.split("\n")


def join_lines(lines: list[str]) -> str:
    return "\n".join(lines)


def _fence_mask(lines: list[str]) -> list[bool]:
    """True for lines inside (or delimiting) a ``` fence."""
    mask, inside = [], False
    for line in lines:
        if line.startswith("```"):
            mask.append(True)
            inside = not inside
            continue
        mask.append(inside)
    return mask


def task_id_of(line: str):
    m = TASK_RE.match(line)
    if not m:
        return None
    return m.group("id") or m.group("id2")


def task_headers(lines: list[str]) -> list[tuple[int, str]]:
    mask = _fence_mask(lines)
    out = []
    for i, line in enumerate(lines):
        if mask[i]:
            continue
        tid = task_id_of(line)
        if tid:
            out.append((i, tid))
    return out


def task_ids(text: str) -> list[str]:
    return [tid for _, tid in task_headers(split_lines(text))]


def claim_ids(text: str) -> list[str]:
    out = []
    for line in split_lines(text):
        m = ROW_RE.match(line)
        if m:
            out.append(m.group(1))
    return out


def _block_end(lines: list[str], start: int, mask: list[bool]) -> int:
    """End (exclusive) of the task block starting at *start*, trailing blanks
    excluded. A block runs until the next header, heading, or flush-left text."""
    k = start + 1
    while k < len(lines):
        line = lines[k]
        if not mask[k] and (task_id_of(line) or line.startswith("#")):
            break
        if line and not line.startswith(" ") and not mask[k]:
            break
        k += 1
    while k > start + 1 and lines[k - 1].strip() == "":
        k -= 1
    return k


def find_task(lines: list[str], tid: str) -> tuple[int, int]:
    mask = _fence_mask(lines)
    hits = [i for i, t in task_headers(lines) if t == tid]
    if not hits:
        raise BoardError(f"task {tid} not found")
    if len(hits) > 1:
        raise BoardError(f"task {tid} appears {len(hits)} times (lines "
                         + ", ".join(str(h + 1) for h in hits) + "); fix the board first")
    return hits[0], _block_end(lines, hits[0], mask)


def task_blocks(text: str) -> dict[str, str]:
    lines = split_lines(text)
    mask = _fence_mask(lines)
    out = {}
    for i, tid in task_headers(lines):
        out.setdefault(tid, join_lines(lines[i:_block_end(lines, i, mask)]))
    return out


def _fields(lines: list[str], a: int, b: int) -> list[tuple[str, int, int]]:
    """[(key, start, end)] of the fields of block [a, b); continuation lines
    (indented 4+) belong to the field above them."""
    out = []
    k = a + 1
    while k < b:
        m = FIELD_RE.match(lines[k])
        if m:
            e = k + 1
            while e < b and lines[e].startswith("    "):
                e += 1
            out.append((m.group("key").strip(), k, e))
            k = e
        else:
            k += 1
    return out


def _field_text(lines: list[str], s: int, e: int) -> str:
    m = FIELD_RE.match(lines[s])
    parts = [m.group("val").strip()] + [l.strip() for l in lines[s + 1:e]]
    return " ".join(p for p in parts if p)


# ---------------------------------------------------------------- guard + IO

def lost_ids(old_text: str, new_text: str) -> dict[str, list[str]]:
    """Task and claim IDs whose count dropped from *old_text* to *new_text*.

    This is the primitive H121's CI check builds on (it adds the exemptions:
    the PR's own task, archive moves, RESERVED rows)."""
    def dropped(a, b):
        from collections import Counter
        ca, cb = Counter(a), Counter(b)
        return sorted((k for k in ca if cb[k] < ca[k]), key=_id_sort_key)
    return {
        "tasks": dropped(task_ids(old_text), task_ids(new_text)),
        "claims": dropped(claim_ids(old_text), claim_ids(new_text)),
    }


def _id_sort_key(s: str):
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", s)]


def guard(old_text: str, new_text: str, *, delta: int, target: str | None = None,
          allow_changed: tuple[str, ...] = (), allow_lost: tuple[str, ...] = ()) -> None:
    old_lines, new_lines = split_lines(old_text), split_lines(new_text)
    got = len(new_lines) - len(old_lines)
    if got != delta:
        raise BoardError(f"line count moved by {got:+d}, the operation accounts for {delta:+d}")
    lost = lost_ids(old_text, new_text)
    lost_t = [t for t in lost["tasks"] if t not in allow_lost]
    if lost_t or lost["claims"]:
        raise BoardError(f"refusing to drop IDs: tasks {lost_t} claims {lost['claims']}")
    keep = set(allow_changed) | set(allow_lost) | ({target} if target else set())
    ob, nb = task_blocks(old_text), task_blocks(new_text)
    changed = sorted(t for t in ob if t not in keep and nb.get(t) != ob[t])
    if changed:
        raise BoardError(f"other task blocks changed: {changed}")


class BoardFile:
    """A file read once; ``splice`` returns new text, ``write`` guards it."""

    def __init__(self, path: Path):
        self.path = Path(path)
        try:
            raw = self.path.read_bytes()
        except FileNotFoundError:
            raise BoardError(f"{self.path}: no such file")
        self.digest = hashlib.sha256(raw).hexdigest()
        self.text = raw.decode("utf-8")
        self.lines = split_lines(self.text)

    def splice(self, a: int, b: int, new: list[str]) -> tuple[str, int]:
        out = self.lines[:a] + list(new) + self.lines[b:]
        return join_lines(out), len(new) - (b - a)

    def write(self, new_text: str, *, delta: int, target: str | None = None,
              dry_run: bool = False, allow_changed: tuple[str, ...] = (),
              allow_lost: tuple[str, ...] = ()) -> None:
        guard(self.text, new_text, delta=delta, target=target, allow_changed=allow_changed,
              allow_lost=allow_lost)
        if dry_run:
            sys.stdout.writelines(difflib.unified_diff(
                self.text.splitlines(True), new_text.splitlines(True),
                str(self.path), str(self.path) + " (new)"))
            return
        now = hashlib.sha256(self.path.read_bytes()).hexdigest()
        if now != self.digest:
            raise BoardError(f"{self.path} changed on disk since it was read; run again")
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), prefix=".board-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
                fh.write(new_text)
            os.replace(tmp, self.path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise


# ---------------------------------------------------------------- TODO ops

def _set_status_line(line_text: str, status: str, owner: str | None) -> str:
    """Rewrite ``Status: X · Owner: Y · …`` keeping the other parts."""
    m = FIELD_RE.match(line_text)
    parts = [p.strip() for p in m.group("val").split("·")]
    parts[0] = status
    if owner is not None:
        for i, p in enumerate(parts):
            if p.lower().startswith("owner:"):
                parts[i] = f"Owner: {owner}"
                break
        else:
            parts.insert(1, f"Owner: {owner}")
    return "  - Status: " + " · ".join(parts)


def op_status(bf: BoardFile, tid: str, status: str, owner: str | None,
              tick: bool | None = None) -> tuple[str, int]:
    if status not in VALID_STATUS:
        raise BoardError(f"status must be one of {VALID_STATUS}")
    a, b = find_task(bf.lines, tid)
    fields = _fields(bf.lines, a, b)
    st = [f for f in fields if f[0] == "Status"]
    if not st:
        raise BoardError(f"task {tid} has no Status field")
    _, s, e = st[0]
    # A wrapped Status line (continuation carries "· Owner:") becomes one line.
    joined = "  - Status: " + _field_text(bf.lines, s, e)
    new_status = _set_status_line(joined, status, owner)
    block = bf.lines[a:b]
    block[s - a:e - a] = [new_status]
    if tick is not None:
        block[0] = re.sub(r"^- \[[ xX]\]", "- [x]" if tick else "- [ ]", block[0])
    return bf.splice(a, b, block)


def op_field(bf: BoardFile, tid: str, key: str, value: str, append: bool = False,
             lines: list[str] | None = None) -> tuple[str, int]:
    """Set field *key* of task *tid* to *value* (one line), or append to it.
    Works on *lines* (a block-local edit chain) when given."""
    base = lines if lines is not None else bf.lines
    a, b = find_task(base, tid)
    hit = [f for f in _fields(base, a, b) if f[0] == key]
    block = base[a:b]
    if hit:
        _, s, e = hit[0]
        if append:
            block[e - a:e - a] = [f"    {value}"]
        else:
            block[s - a:e - a] = [f"  - {key}: {value}"]
    else:
        block.append(f"  - {key}: {value}")
    out = base[:a] + block + base[b:]
    return join_lines(out), len(out) - len(bf.lines)


def op_done(bf: BoardFile, tid: str, result: str) -> tuple[str, int]:
    text, _ = op_status(bf, tid, "done", None, tick=True)
    text, delta = op_field(bf, tid, "Result", result, lines=split_lines(text))
    return text, delta


def op_block(bf: BoardFile, tid: str, blocker: str, unblock: str,
             result: str | None) -> tuple[str, int]:
    text, _ = op_status(bf, tid, "blocked", None, tick=False)
    text, _ = op_field(bf, tid, "Blocker", blocker, lines=split_lines(text))
    text, _ = op_field(bf, tid, "Unblock", unblock, lines=split_lines(text))
    if result:
        text, _ = op_field(bf, tid, "Result", result, lines=split_lines(text))
    return text, len(split_lines(text)) - len(bf.lines)


def _sections(lines: list[str]) -> list[tuple[int, int, str]]:
    """[(start, end, heading)] for every ``## `` section."""
    mask = _fence_mask(lines)
    heads = [i for i, l in enumerate(lines) if l.startswith("## ") and not mask[i]]
    return [(h, heads[k + 1] if k + 1 < len(heads) else len(lines), lines[h][3:].strip())
            for k, h in enumerate(heads)]


def _stream_of(tid: str) -> str:
    return tid.split(".")[0] if tid.startswith("M") else re.match(r"[A-Z]+", tid).group(0)


def _claim_blocks(todo_text: str) -> list[tuple[int, int]]:
    out = []
    for line in split_lines(todo_text):
        m = FIELD_RE.match(line)
        if m and m.group("key").strip() == "Claims":
            r = CLAIMS_FIELD_RE.search(m.group("val"))
            if r:
                out.append((int(r.group(1)), int(r.group(2))))
    return out


def op_add_task(bf: BoardFile, block_text: str, section: str | None,
                after: str | None) -> tuple[str, int, str]:
    new = split_lines(block_text.strip("\n"))
    heads = task_headers(new)
    if len(heads) != 1 or heads[0][0] != 0:
        raise BoardError("the new block must be exactly one task, starting with its '- [ ] **ID — title**' line")
    tid = heads[0][1]
    if tid in task_ids(bf.text):
        raise BoardError(f"task ID {tid} already exists; take `board.py next-id {_stream_of(tid)}`")
    fields = {k: _field_text(new, s, e) for k, s, e in _fields(new, 0, len(new))}
    for need in ("Status", "Depends", "Goal", "Done when", "Claims"):
        if need not in fields:
            raise BoardError(f"new task {tid} lacks the {need} field")
    r = CLAIMS_FIELD_RE.search(fields["Claims"])
    if not r:
        raise BoardError(f"Claims of {tid} is not a C-a–C-b range")
    lo, hi = int(r.group(1)), int(r.group(2))
    for a2, b2 in _claim_blocks(bf.text):
        if lo <= b2 and a2 <= hi:
            raise BoardError(f"claim block C-{lo}–C-{hi} overlaps C-{a2}–C-{b2}; take `board.py next-claims`")
    if after:
        _, at = find_task(bf.lines, after)
    else:
        if not section:
            section = _stream_of(tid)
        secs = [s for s in _sections(bf.lines) if s[2].split()[0] == section]
        if not secs:
            raise BoardError(f"no '## {section} …' section; pass --after ID")
        s0, s1, _ = secs[0]
        in_sec = [i for i, _t in task_headers(bf.lines) if s0 < i < s1]
        if not in_sec:
            raise BoardError(f"section '{secs[0][2]}' has no task to append after; pass --after ID")
        at = _block_end(bf.lines, in_sec[-1], _fence_mask(bf.lines))
    text, delta = bf.splice(at, at, [""] + new)
    return text, delta, tid


def op_archive(bf: BoardFile, ids: list[str]) -> tuple[str, int, list[str]]:
    """Cut the blocks of done tasks *ids* out of TODO (each with the blank
    line before it). Returns (new TODO text, delta, removed blocks)."""
    cuts, blocks = [], []
    for tid in ids:
        a, b = find_task(bf.lines, tid)
        if not bf.lines[a].startswith("- [x]"):
            raise BoardError(f"{tid} is not ticked [x]; only done tasks are archived")
        st = [f for f in _fields(bf.lines, a, b) if f[0] == "Status"]
        if not st or not _field_text(bf.lines, st[0][1], st[0][2]).lower().startswith("done"):
            raise BoardError(f"{tid} is not Status: done")
        lo = a - 1 if a > 0 and bf.lines[a - 1].strip() == "" else a
        cuts.append((lo, b))
        blocks.append(join_lines(bf.lines[a:b]))
    lines = list(bf.lines)
    for lo, b in sorted(cuts, reverse=True):
        del lines[lo:b]
    return join_lines(lines), len(lines) - len(bf.lines), blocks


def history_append(path: Path, blocks: list[str], date: str) -> tuple[str, str]:
    """(old text, new text) of the history file with *blocks* appended."""
    old = path.read_text(encoding="utf-8") if path.exists() else ""
    head = old if old else (f"# TODO history — {date}\n\nDone tasks moved from `TODO.md` on {date} "
                            f"with `tools/board.py archive`.\n")
    body = head.rstrip("\n") + "\n"
    for blk in blocks:
        body += "\n" + blk + "\n"
    return old, body


def next_id(todo_text: str, stream: str, history: bool = True) -> str:
    """Next free ID of *stream*, counting archived tasks too (an ID is never
    reused). Open PRs can hold IDs not yet on main: check them too."""
    ids = task_ids(todo_text)
    for path in [] if not history else sorted((REPO_ROOT / "docs" / "research").glob("todo-history-*.md")):
        ids += task_ids(path.read_text(encoding="utf-8"))
    if stream.startswith("M"):
        pat = re.compile(rf"^{re.escape(stream)}\.(\d+)")
    else:
        pat = re.compile(rf"^{re.escape(stream)}(\d+)$")
    nums = [int(m.group(1)) for t in ids for m in [pat.match(t)] if m]
    n = max(nums, default=0) + 1
    return f"{stream}.{n}" if stream.startswith("M") else f"{stream}{n}"


def next_claims(todo_text: str, claims_text: str) -> tuple[int, int]:
    blocks = _claim_blocks(todo_text)
    used = {int(c[2:]) for c in claim_ids(claims_text)}
    start = (max((a for a, _ in blocks), default=0) // 10 + 1) * 10
    while any(start <= u <= start + 9 for u in used) or any(
            start <= b and a <= start + 9 for a, b in blocks):
        start += 10
    return start, start + 9


# ---------------------------------------------------------------- claims ops

CLAIMS_HEADER = ["| ID | Claim | Status | Confidence | Evidence |",
                 "| --- | --- | --- | --- | --- |"]


def _row_cells(line: str) -> list[str]:
    return [c for c in re.split(r"(?<!\\)\|", line)[1:-1]]


def op_add_claims(bf: BoardFile, section: str, rows: list[str], create: bool) -> tuple[str, int]:
    have = set(claim_ids(bf.text))
    for r in rows:
        m = ROW_RE.match(r)
        if not m:
            raise BoardError(f"not a claim row: {r[:60]!r}")
        if not r.rstrip().endswith("|") or len(_row_cells(r)) < 5:
            raise BoardError(f"{m.group(1)}: a row has 5 cells and ends with '|'")
        if m.group(1) in have:
            raise BoardError(f"{m.group(1)} already exists in {bf.path.name}")
        have.add(m.group(1))
    secs = [s for s in _sections(bf.lines) if s[2] == section or s[2].startswith(section + " ")]
    if len(secs) > 1:
        raise BoardError(f"{len(secs)} sections match {section!r}; give the full heading")
    if not secs:
        if not create:
            raise BoardError(f"no section '## {section}'; pass --create to add it at the end")
        end = len(bf.lines)
        while end > 0 and bf.lines[end - 1].strip() == "":
            end -= 1
        return bf.splice(end, end, ["", f"## {section}"] + CLAIMS_HEADER + rows)
    s0, s1, _ = secs[0]
    last = max((i for i in range(s0, s1) if bf.lines[i].startswith("|")), default=None)
    if last is None:
        at = s0 + 1
        return bf.splice(at, at, CLAIMS_HEADER + rows)
    return bf.splice(last + 1, last + 1, rows)


def op_claim_status(bf: BoardFile, cid: str, status: str) -> tuple[str, int]:
    hits = [i for i, l in enumerate(bf.lines) if (m := ROW_RE.match(l)) and m.group(1) == cid]
    if len(hits) != 1:
        raise BoardError(f"{cid}: {len(hits)} rows (need exactly one)")
    i = hits[0]
    parts = re.split(r"(?<!\\)\|", bf.lines[i])
    if len(parts) < 6:
        raise BoardError(f"{cid}: row has fewer than 5 cells")
    parts[3] = f" {status} "
    return bf.splice(i, i + 1, ["|".join(parts)])


# ---------------------------------------------------------------- resolve

def _units(text: str) -> list[tuple[tuple, list[str]]]:
    """Split a file into keyed units: task blocks (key ``("T", id)``), claim
    rows (``("C", id)``) and runs of other lines (``("X", text, n)``, n = the
    occurrence of that same run)."""
    lines = split_lines(text)
    mask = _fence_mask(lines)
    out, seen, run = [], {}, []

    def flush():
        if run:
            body = join_lines(run)
            n = seen.get(body, 0)
            seen[body] = n + 1
            out.append((("X", body, n), list(run)))
            run.clear()

    i = 0
    while i < len(lines):
        tid = None if mask[i] else task_id_of(lines[i])
        m = None if mask[i] else ROW_RE.match(lines[i])
        if tid or m:
            # Blank lines right before a block or row travel with it, so an
            # inserted unit brings its own separator.
            lead = []
            while run and run[-1].strip() == "":
                lead.insert(0, run.pop())
            flush()
            if tid:
                e = _block_end(lines, i, mask)
                out.append((("T", tid), lead + lines[i:e]))
                i = e
            else:
                out.append((("C", m.group(1)), lead + [lines[i]]))
                i += 1
        else:
            run.append(lines[i])
            i += 1
    flush()
    return out


def merge3(base: str, ours: str, theirs: str) -> tuple[str, list[str], list[str]]:
    """Merge by unit key. Returns (text, conflicts, notes)."""
    bu, ou, tu = _units(base), _units(ours), _units(theirs)
    bmap, omap, tmap = dict(bu), dict(ou), dict(tu)
    conflicts, notes = [], []
    result: list[tuple[tuple, list[str]]] = []
    for key, body in ou:
        if key in tmap:
            tb = tmap[key]
            if tb == body:
                result.append((key, body))
            elif key in bmap and bmap[key] == body:
                result.append((key, tb))
            elif key in bmap and bmap[key] == tb:
                result.append((key, body))
            elif key[0] == "X":
                result.append((key, body))  # unreachable: X keys carry their text
            else:
                conflicts.append(f"{key[0]} {key[1]}")
                result.append((key, ["<<<<<<< ours"] + body + ["======="] + tb + [">>>>>>> theirs"]))
        elif key in bmap:
            if bmap[key] == body:
                if key[0] != "X":
                    notes.append(f"theirs deleted {key[1]}; kept deleted")
                continue
            conflicts.append(f"{key[0]} {key[1]} (changed here, deleted there)")
            result.append((key, body))
        else:
            result.append((key, body))
    placed = {k for k, _ in result}
    pos = {k: n for n, (k, _) in enumerate(result)}
    prev = None
    inserts: dict[object, list] = {}
    for key, body in tu:
        if key in placed or key in omap:
            prev = key if key in pos else prev
            continue
        if key in bmap:
            if bmap[key] == body:
                if key[0] != "X":
                    notes.append(f"ours deleted {key[1]}; kept deleted")
                continue
            conflicts.append(f"{key[0]} {key[1]} (deleted here, changed there)")
        inserts.setdefault(prev, []).append((key, body))
        prev = key
    def ours_added(key):
        return key not in bmap and key not in tmap

    final, pending = [], []

    def flush_pending():
        while pending:
            item = pending.pop(0)
            final.append(item)
            pending[0:0] = inserts.pop(item[0], [])

    for key, body in result:
        # Their additions after a shared unit go after our own additions there.
        if pending and not ours_added(key):
            flush_pending()
        final.append((key, body))
        pending.extend(inserts.pop(key, []))
    flush_pending()
    for k in list(inserts):  # predecessor never placed (None or deleted): append at end
        pending.extend(inserts.pop(k))
        flush_pending()
    out = []
    for _, body in final:
        out.extend(body)
    return join_lines(out), conflicts, notes


def _git_show(spec: str, cwd: Path = REPO_ROOT) -> str:
    r = subprocess.run(["git", "show", spec], cwd=str(cwd), capture_output=True)
    if r.returncode != 0:
        raise BoardError(f"git show {spec}: {r.stderr.decode().strip()}")
    return r.stdout.decode("utf-8")


# ---------------------------------------------------------------- CLI

def _read_block_arg(arg: str) -> str:
    return sys.stdin.read() if arg == "-" else Path(arg).read_text(encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog="See the module docstring for the command list.")
    ap.add_argument("--selftest", action="store_true", help="run the built-in tests")
    ap.add_argument("--todo", default=str(TODO_PATH), help="path to TODO.md")
    ap.add_argument("--claims", default=str(CLAIMS_PATH), help="path to claims.md")
    ap.add_argument("--dry-run", action="store_true", help="print the diff, write nothing")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("show"); p.add_argument("id")
    p = sub.add_parser("claim"); p.add_argument("id"); p.add_argument("--owner", required=True)
    p = sub.add_parser("release"); p.add_argument("id")
    p = sub.add_parser("status"); p.add_argument("id"); p.add_argument("status", choices=VALID_STATUS)
    p.add_argument("--owner")
    p = sub.add_parser("done"); p.add_argument("id"); p.add_argument("--result", required=True)
    p = sub.add_parser("block"); p.add_argument("id"); p.add_argument("--blocker", required=True)
    p.add_argument("--unblock", required=True); p.add_argument("--result")
    p = sub.add_parser("field"); p.add_argument("id"); p.add_argument("key"); p.add_argument("value")
    p.add_argument("--append", action="store_true", help="add VALUE as a continuation line")
    p = sub.add_parser("add-task"); p.add_argument("file", help="block file, or - for stdin")
    p.add_argument("--section", help="stream heading token (H, M5, …); default from the ID")
    p.add_argument("--after", help="insert right after this task instead")
    p = sub.add_parser("archive"); p.add_argument("ids", nargs="+")
    p.add_argument("--to", required=True, help="docs/research/todo-history-YYYY-MM-DD.md")
    p = sub.add_parser("next-id"); p.add_argument("stream")
    sub.add_parser("next-claims")
    p = sub.add_parser("add-claims"); p.add_argument("--section", required=True)
    p.add_argument("--row", action="append", default=[]); p.add_argument("--file")
    p.add_argument("--create", action="store_true")
    p = sub.add_parser("claim-status"); p.add_argument("id"); p.add_argument("status")
    p = sub.add_parser("lost"); p.add_argument("--base", required=True)
    p.add_argument("--head", help="git ref (default: the working tree)")
    p.add_argument("files", nargs="*", default=list(DEFAULT_FILES))
    p = sub.add_parser("resolve"); p.add_argument("file")
    p.add_argument("--base-file"); p.add_argument("--ours-file"); p.add_argument("--theirs-file")
    p.add_argument("-o", "--output", help="write here instead of FILE")

    args = ap.parse_args(argv)
    if args.selftest:
        return run_selftest()
    if not args.cmd:
        ap.print_help()
        return 2
    try:
        return _dispatch(args)
    except BoardError as exc:
        print(f"board: refused: {exc}", file=sys.stderr)
        return 1


def _dispatch(args) -> int:
    dry = args.dry_run
    c = args.cmd
    if c == "show":
        bf = BoardFile(args.todo)
        a, b = find_task(bf.lines, args.id)
        print(join_lines(bf.lines[a:b]))
        return 0
    if c in ("claim", "release", "status", "done", "block", "field"):
        bf = BoardFile(args.todo)
        if c == "claim":
            text, d = op_status(bf, args.id, "in progress", args.owner)
        elif c == "release":
            text, d = op_status(bf, args.id, "open", NO_OWNER)
        elif c == "status":
            text, d = op_status(bf, args.id, args.status, args.owner,
                                tick=True if args.status == "done" else None)
        elif c == "done":
            text, d = op_done(bf, args.id, args.result)
        elif c == "block":
            text, d = op_block(bf, args.id, args.blocker, args.unblock, args.result)
        else:
            text, d = op_field(bf, args.id, args.key, args.value, args.append)
        bf.write(text, delta=d, target=args.id, dry_run=dry)
        print(f"board: {c} {args.id}: {d:+d} lines")
        return 0
    if c == "add-task":
        bf = BoardFile(args.todo)
        text, d, tid = op_add_task(bf, _read_block_arg(args.file), args.section, args.after)
        bf.write(text, delta=d, target=tid, dry_run=dry)
        print(f"board: added {tid}: {d:+d} lines")
        return 0
    if c == "archive":
        bf = BoardFile(args.todo)
        text, d, blocks = op_archive(bf, args.ids)
        hist = Path(args.to)
        m = re.search(r"(\d{4}-\d{2}-\d{2})", hist.name)
        old_h, new_h = history_append(hist, blocks, m.group(1) if m else "undated")
        missing = [t for t in args.ids if task_ids(new_h).count(t) <= task_ids(old_h).count(t)]
        if missing or lost_ids(old_h, new_h)["tasks"] or lost_ids(old_h, new_h)["claims"]:
            raise BoardError(f"history file would not gain {missing}")
        if dry:
            print(f"would move {len(blocks)} block(s) to {hist}")
        else:
            # History first: a crash in between leaves a duplicate, never a loss.
            hist.write_text(new_h, encoding="utf-8")
        bf.write(text, delta=d, dry_run=dry, allow_lost=tuple(args.ids))
        print(f"board: archived {' '.join(args.ids)} to {hist}: TODO {d:+d} lines")
        return 0
    if c == "next-id":
        print(next_id(BoardFile(args.todo).text, args.stream))
        return 0
    if c == "next-claims":
        a, b = next_claims(BoardFile(args.todo).text, BoardFile(args.claims).text)
        print(f"C-{a}–C-{b}")
        return 0
    if c == "add-claims":
        bf = BoardFile(args.claims)
        rows = list(args.row)
        if args.file:
            rows += [l for l in split_lines(_read_block_arg(args.file)) if l.strip()]
        if not rows:
            raise BoardError("no rows given")
        text, d = op_add_claims(bf, args.section, rows, args.create)
        bf.write(text, delta=d, dry_run=dry)
        print(f"board: added {len(rows)} claim row(s): {d:+d} lines")
        return 0
    if c == "claim-status":
        bf = BoardFile(args.claims)
        text, d = op_claim_status(bf, args.id, args.status)
        bf.write(text, delta=d, dry_run=dry)
        print(f"board: {args.id} -> {args.status}")
        return 0
    if c == "lost":
        # The checkout the command runs in (any worktree), else this tool's.
        r = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
        root = Path(r.stdout.strip()) if r.returncode == 0 else REPO_ROOT
        bad = 0
        for f in args.files:
            old = _git_show(f"{args.base}:{f}", cwd=root)
            new = (_git_show(f"{args.head}:{f}", cwd=root) if args.head
                   else (root / f).read_text(encoding="utf-8"))
            lost = lost_ids(old, new)
            n = len(lost["tasks"]) + len(lost["claims"])
            bad += n
            print(f"{f}: {'OK' if not n else 'LOST'} tasks={len(lost['tasks'])} claims={len(lost['claims'])}")
            if lost["tasks"]:
                print("  tasks: " + " ".join(lost["tasks"]))
            if lost["claims"]:
                print("  claims: " + _ranges(lost["claims"]))
        return 1 if bad else 0
    if c == "resolve":
        # Index stages of the conflicted file, read from its own checkout
        # (works in any worktree): 1 = base, 2 = ours, 3 = theirs.
        fp = Path(args.file).resolve()

        def stage(n, override):
            if override:
                return Path(override).read_text(encoding="utf-8")
            return _git_show(f":{n}:./{fp.name}", cwd=fp.parent)
        base = stage(1, args.base_file)
        ours = stage(2, args.ours_file)
        theirs = stage(3, args.theirs_file)
        text, conflicts, notes = merge3(base, ours, theirs)
        for n in notes:
            print(f"note: {n}")
        out = Path(args.output or args.file)
        for side, src in (("ours", ours), ("theirs", theirs)):
            lost = lost_ids(src, text)
            kept_deleted = {n.split()[2].rstrip(";") for n in notes}
            really = [t for t in lost["tasks"] + lost["claims"] if t not in kept_deleted]
            if really:
                raise BoardError(f"merge would drop {side}'s IDs {really}; nothing written")
        if dry:
            print(text)
        else:
            out.write_text(text, encoding="utf-8")
        if conflicts:
            print(f"board: {len(conflicts)} unit(s) changed on both sides, left in conflict markers: "
                  + ", ".join(conflicts), file=sys.stderr)
            return 1
        print(f"board: merged {out} by ID ({len(split_lines(text))} lines); `git add` it")
        return 0
    raise BoardError(f"unknown command {c}")


def _ranges(ids: list[str]) -> str:
    nums = sorted(int(i[2:]) for i in ids)
    out, s = [], None
    for k, n in enumerate(nums):
        if s is None:
            s = n
        if k + 1 == len(nums) or nums[k + 1] != n + 1:
            out.append(f"C-{s}" if s == n else f"C-{s}–C-{n}")
            s = None
    return ", ".join(out) + f" ({len(nums)} rows)"


# ---------------------------------------------------------------- selftest

SAMPLE_TODO = """# TODO

```text
- [ ] **ID — title**
  - Status: open
```

## H — Housekeeping

- [x] **H1 — First**
  - Status: done · Owner: b1 · Critical: no
  - Depends: —
  - Goal: g.
  - Claims: C-100–C-109
  - Result: r.

- [ ] **H2 — Second**
  - Status: open · Owner: — · Critical: yes
  - Depends: H1
  - Goal: a goal
    that wraps.
  - Done when: x.
  - Claims: C-110–C-119


## M9 — L3

- [ ] **M9.1 — Third**
  - Status: open · Owner: —
    · Critical: no
  - Depends: —
  - Goal: g.
  - Done when: y.
  - Claims: C-120–C-129

## Retired leads

text
"""

SAMPLE_CLAIMS = """# Claims

## A section
| ID | Claim | Status | Confidence | Evidence |
| --- | --- | --- | --- | --- |
| C-100 | a | VERIFIED | H | `x` |
| C-101 | b \\| pipe | OBSERVED | M | y |

## B section
| ID | Claim | Status | Confidence | Evidence |
| --- | --- | --- | --- | --- |
| C-110 | c | UNKNOWN | — | — |
"""


def run_selftest() -> int:
    checks = 0
    failures = []

    def ok(cond, label):
        nonlocal checks
        checks += 1
        if not cond:
            failures.append(label)

    def refused(fn, label):
        try:
            fn()
        except BoardError:
            ok(True, label)
            return
        ok(False, label + " (not refused)")

    with tempfile.TemporaryDirectory() as td:
        todo = Path(td) / "TODO.md"
        claims = Path(td) / "claims.md"

        def reset():
            todo.write_text(SAMPLE_TODO, encoding="utf-8")
            claims.write_text(SAMPLE_CLAIMS, encoding="utf-8")

        def run(*a):
            import contextlib
            import io
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                return main(["--todo", str(todo), "--claims", str(claims), *a])

        def changed_lines(old, new):
            sm = difflib.SequenceMatcher(None, split_lines(old), split_lines(new))
            return [op for op in sm.get_opcodes() if op[0] != "equal"]

        reset()
        ok(task_ids(SAMPLE_TODO) == ["H1", "H2", "M9.1"], "fenced template header is not a task")
        ok(claim_ids(SAMPLE_CLAIMS) == ["C-100", "C-101", "C-110"], "claim rows parsed")

        # claim: one line changes, nothing else
        ok(run("claim", "H2", "--owner", "task/h2") == 0, "claim exit 0")
        new = todo.read_text()
        ok("  - Status: in progress · Owner: task/h2 · Critical: yes" in new, "claim sets status+owner")
        ok(len(changed_lines(SAMPLE_TODO, new)) == 1 and len(split_lines(new)) == len(split_lines(SAMPLE_TODO)),
           "claim is a one-line splice")

        # wrapped status line collapses into one line (delta -1), rest untouched
        reset()
        ok(run("claim", "M9.1", "--owner", "x") == 0, "claim of wrapped status")
        new = todo.read_text()
        ok("  - Status: in progress · Owner: x · Critical: no" in new
           and len(split_lines(new)) == len(split_lines(SAMPLE_TODO)) - 1, "wrapped status joined")

        # done: [x], status, Result appended at the end of the block
        reset()
        ok(run("done", "H2", "--result", "EXP-x; 3/3") == 0, "done exit 0")
        b = task_blocks(todo.read_text())["H2"]
        ok(b.startswith("- [x] **H2") and "Status: done · Owner: — · Critical: yes" in b
           and b.endswith("  - Result: EXP-x; 3/3"), "done block shape")
        ok(task_blocks(todo.read_text())["M9.1"] == task_blocks(SAMPLE_TODO)["M9.1"], "done leaves others")
        reset()
        ok(run("done", "H1", "--result", "r2") == 0 and "  - Result: r2" in todo.read_text()
           and todo.read_text().count("Result:") == 1, "done replaces an existing Result")

        # block
        reset()
        ok(run("block", "H2", "--blocker", "no image", "--unblock", "M9.1") == 0, "block exit 0")
        b = task_blocks(todo.read_text())["H2"]
        ok("Status: blocked" in b and "  - Unblock: M9.1" in b and b.startswith("- [ ]"), "block shape")

        # field: replace a wrapped field with one line; append continuation
        reset()
        ok(run("field", "H2", "Goal", "short.") == 0, "field exit 0")
        ok("  - Goal: short.\n  - Done when" in todo.read_text(), "field replaced incl. continuation")
        ok(run("field", "H2", "Goal", "more.", "--append") == 0
           and "  - Goal: short.\n    more.\n" in todo.read_text(), "field --append")

        # add-task: end of its stream, guarded ID/claims
        reset()
        blk = ("- [ ] **H3 — New**\n  - Status: open · Owner: — · Critical: no\n  - Depends: —\n"
               "  - Goal: g.\n  - Done when: z.\n  - Claims: C-130–C-139\n")
        bfile = Path(td) / "blk.md"
        bfile.write_text(blk)
        ok(run("add-task", str(bfile)) == 0, "add-task exit 0")
        t = todo.read_text()
        ok(task_ids(t) == ["H1", "H2", "H3", "M9.1"], "add-task lands at the end of section H")
        ok(t.count("\n\n\n## M9") == 1, "blank lines before the next section kept")
        ok(run("add-task", str(bfile)) == 1, "duplicate task ID refused")
        bfile.write_text(blk.replace("H3", "H4").replace("C-130–C-139", "C-115–C-124"))
        ok(run("add-task", str(bfile)) == 1, "overlapping claim block refused")
        bfile.write_text(blk.replace("H3", "M9.2").replace("C-130–C-139", "C-140–C-149"))
        ok(run("add-task", str(bfile)) == 0 and task_ids(todo.read_text())[-1] == "M9.2", "add-task M9")
        bfile.write_text("- [ ] **H5 — Two**\n  - Status: open\n- [ ] **H6 — x**\n")
        ok(run("add-task", str(bfile)) == 1, "two blocks in one add refused")

        # archive: done only, moved not lost
        reset()
        hist = Path(td) / "todo-history-2026-01-02.md"
        ok(run("archive", "H2", "--to", str(hist)) == 1 and not hist.exists(), "archive refuses an open task")
        ok(run("archive", "H1", "--to", str(hist)) == 0, "archive exit 0")
        ok(task_ids(todo.read_text()) == ["H2", "M9.1"] and task_ids(hist.read_text()) == ["H1"]
           and "\n\n\n" not in todo.read_text().split("## M9")[0].split("## H — Housekeeping")[1][:3],
           "archive moves the block")
        ok(hist.read_text().startswith("# TODO history — 2026-01-02"), "archive creates the history file")
        refused(lambda: guard(SAMPLE_TODO, todo.read_text(), delta=len(split_lines(todo.read_text()))
                              - len(split_lines(SAMPLE_TODO))), "guard without allow_lost refuses the move")

        # next-id / next-claims
        reset()
        ok(next_id(SAMPLE_TODO, "H", False) == "H3" and next_id(SAMPLE_TODO, "M9", False) == "M9.2", "next-id")
        ok(next_claims(SAMPLE_TODO, SAMPLE_CLAIMS) == (130, 139), "next-claims")
        ok(next_claims(SAMPLE_TODO, SAMPLE_CLAIMS + "| C-131 | z | UNKNOWN | — | — |\n") == (140, 149),
           "next-claims skips a block already used in claims.md")

        # add-claims
        ok(run("add-claims", "--section", "A section", "--row", "| C-102 | d | OBSERVED | M | z |") == 0,
           "add-claims exit 0")
        cl = claims.read_text()
        ok(claim_ids(cl) == ["C-100", "C-101", "C-102", "C-110"], "row appended to its section")
        ok(run("add-claims", "--section", "A section", "--row", "| C-110 | dup | X | L | - |") == 1,
           "duplicate claim ID refused")
        ok(run("add-claims", "--section", "Nope", "--row", "| C-200 | n | X | L | - |") == 1,
           "missing section needs --create")
        ok(run("add-claims", "--section", "New one", "--create", "--row", "| C-200 | n | X | L | - |") == 0
           and claims.read_text().rstrip().endswith("| C-200 | n | X | L | - |")
           and "## New one\n| ID |" in claims.read_text(), "--create adds a section at the end")
        ok(run("add-claims", "--section", "A section", "--row", "| C-300 | broken") == 1, "short row refused")

        # claim-status keeps escaped pipes
        ok(run("claim-status", "C-101", "RETRACTED") == 0, "claim-status exit 0")
        ok("| C-101 | b \\| pipe | RETRACTED | M | y |" in claims.read_text(), "status cell replaced")

        # guard: refuses ID loss, wrong delta, collateral edits, concurrent writes
        refused(lambda: guard(SAMPLE_TODO, SAMPLE_TODO.replace("- [ ] **H2 — Second**", "- H2"),
                              delta=0), "guard: dropped task header")
        refused(lambda: guard(SAMPLE_CLAIMS, SAMPLE_CLAIMS.replace("| C-110 | c | UNKNOWN | — | — |\n", ""),
                              delta=-1), "guard: dropped claim row")
        refused(lambda: guard(SAMPLE_TODO, SAMPLE_TODO + "x\n", delta=0), "guard: unexpected line delta")
        refused(lambda: guard(SAMPLE_TODO, SAMPLE_TODO.replace("  - Done when: y.", "  - Done when: q."),
                              delta=0, target="H2"), "guard: other block changed")
        reset()
        bf = BoardFile(todo)
        text, d = op_status(bf, "H2", "in progress", "me")
        todo.write_text(SAMPLE_TODO + "\n")
        refused(lambda: bf.write(text, delta=d, target="H2"), "write: file changed on disk")
        ok(todo.read_text() == SAMPLE_TODO + "\n", "refused write left the file alone")

        # lost_ids: the PR #340 shape (tail replaced by an older copy)
        old = SAMPLE_TODO
        cut = old[: old.index("## M9")] + "## Retired leads\n\ntext\n"
        lost = lost_ids(old, cut)
        ok(lost == {"tasks": ["M9.1"], "claims": []}, "lost_ids names the dropped task")
        ok(lost_ids(SAMPLE_CLAIMS, SAMPLE_CLAIMS.split("## B")[0])["claims"] == ["C-110"], "lost claim rows")

        # merge3: both sides append (the PR #340 conflict) -> both kept
        base = SAMPLE_TODO
        ours = base.replace("  - Claims: C-120–C-129\n",
                            "  - Claims: C-120–C-129\n\n- [ ] **M9.2 — Ours**\n  - Status: open\n  - Claims: C-140–C-149\n")
        theirs = base.replace("  - Claims: C-120–C-129\n",
                              "  - Claims: C-120–C-129\n\n- [ ] **M9.3 — Theirs**\n  - Status: open\n  - Claims: C-150–C-159\n")
        theirs = theirs.replace("- [ ] **H2 — Second**\n  - Status: open", "- [ ] **H2 — Second**\n  - Status: in progress")
        m, conf, _ = merge3(base, ours, theirs)
        ok(not conf and task_ids(m) == ["H1", "H2", "M9.1", "M9.2", "M9.3"], "merge3 keeps both appends")
        ok("Status: in progress" in task_blocks(m)["H2"], "merge3 takes the one-sided edit")
        ok(join_lines(split_lines(m)[: split_lines(m).index("## M9 — L3")]) ==
           join_lines(split_lines(theirs)[: split_lines(theirs).index("## M9 — L3")]), "merge3 text intact")
        both = ours.replace("- [ ] **H2 — Second**\n  - Status: open", "- [ ] **H2 — Second**\n  - Status: blocked")
        m2, conf2, _ = merge3(base, both, theirs)
        ok(conf2 == ["T H2"] and "<<<<<<< ours" in m2 and set(task_ids(m2)) >= {"M9.2", "M9.3"},
           "merge3 marks a two-sided edit and keeps the rest")
        cb = SAMPLE_CLAIMS
        co = cb.replace("| C-110 | c | UNKNOWN | — | — |\n", "| C-110 | c | UNKNOWN | — | — |\n| C-111 | o | X | L | - |\n")
        ct = cb + "\n## C section\n| ID | Claim | Status | Confidence | Evidence |\n| --- | --- | --- | --- | --- |\n| C-500 | t | X | L | - |\n"
        m3, conf3, _ = merge3(cb, co, ct)
        ok(not conf3 and claim_ids(m3) == ["C-100", "C-101", "C-110", "C-111", "C-500"]
           and "## C section" in m3, "merge3 on claims: row + new section")
        # resolve CLI on files
        for name, body in (("b", base), ("o", ours), ("t", theirs)):
            (Path(td) / name).write_text(body)
        out = Path(td) / "merged.md"
        ok(run("resolve", str(out), "--base-file", str(Path(td) / "b"), "--ours-file", str(Path(td) / "o"),
                 "--theirs-file", str(Path(td) / "t")) == 0 and task_ids(out.read_text())[-2:] == ["M9.2", "M9.3"],
           "resolve CLI")

        # the real board files split into units and join back byte for byte
        for real in (TODO_PATH, CLAIMS_PATH):
            if real.exists():
                t = real.read_text(encoding="utf-8")
                ok(merge3(t, t, t) == (t, [], []), f"merge3 identity on {real.name}")

        # grammar stays in step with the checkers
        sys.path.insert(0, str(REPO_ROOT / "tools"))
        try:
            import todo_check
            import claims_check
            ok(todo_check.TASK_RE.pattern == TASK_RE.pattern and todo_check.FIELD_RE.pattern == FIELD_RE.pattern,
               "TASK_RE/FIELD_RE equal todo_check's")
            ok(claims_check.ROW_RE.pattern == ROW_RE.pattern, "ROW_RE equals claims_check's")
            ok([t["id"] for t in todo_check.parse_tasks(SAMPLE_TODO)] == task_ids(SAMPLE_TODO),
               "same task list as todo_check.parse_tasks")
        except ImportError as exc:
            ok(False, f"import checker: {exc}")

    if failures:
        for f in failures:
            print(f"FAIL {f}")
        print(f"board selftest: FAILED ({len(failures)}/{checks} checks)")
        return 1
    print(f"board selftest: OK ({checks} checks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
