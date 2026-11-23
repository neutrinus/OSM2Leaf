#!/usr/bin/env python3
"""L4 full-system emulator gate: card image in, one verdict out (M8.H13).

``l4check.py`` wraps the QEMU ``-M ze0`` boot recipe of
``docs/experiments/EXP-2026-11-22-M8.C1e-display-engine`` into the one-command
gate the other verification levels already have (``cardcheck``/``l2check``/
``l3check``).  It derives the unit record from the card, builds the IPL patch
and the qcow2 overlay, boots, and scores the kernel debug (DBGMSG) serial log.

Usage::

    python3 tools/l4check.py --card CARD.img [--head IMG256] [--qemu BIN]
                             [--json [PATH]] [--workdir DIR] [--timeout S]
                             [--ipl-patch FILE]
    python3 tools/l4check.py --selftest

Exit codes: ``0`` every card-verdict stage F0..F4 passed, ``1`` a stage failed
(the failed stage and the log line are named), ``2`` usage error, ``3`` not
runnable — no card, no firmware head, or no QEMU with ``-M ze0``.  An absent
prerequisite is **never** a pass.  F5 (idle) is informational: a slow host may
not reach it inside the run window; that does not reject the card.  The gate
never edits the standing ``gate.py`` checks.

Stage names F0..F4 are imported from ``tools/l4_status.py``; F5 (idle) is an
l4check extension, named here because l4_status.py has no F5 row today.  The
marker strings come from ``tools/ze0_sdhost.py``'s firmware-string table and
from the two measured boots in EXP-2026-11-22-M8.H13-l4check — not from prose.
"""

from __future__ import annotations

import argparse
import hashlib
import hashutil
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from l4_status import ROWS as L4_ROWS  # noqa: E402

SCHEMA = "osm2leaf.l4check/v1"
CLAIM = "C-7100"
EXP_RECORD = "EXP-2026-11-22-M8.H13-l4check"

EXIT_PASS, EXIT_FAIL, EXIT_USAGE, EXIT_NOT_RUNNABLE = 0, 1, 2, 3

# The run recipe (run.sh's machine options, EXP C1c/C1e/C1k/C1i).
KERNEL_OFF = 0x3E00200
APP_OFF = 0x200200
DBGMSG = 0x880404F4
ICOUNT = "shift=0,sleep=off"
DEFAULT_TIMEOUT = 900
OVERLAY_GIB = 8

# Log grammar.  Sources are quoted in the EXP Plan table.
RE_KERNEL_BANNER = re.compile(r"Windows CE Kernel for Hitachi SH")
RE_FILESYS = re.compile(r"Configuring: Primary pages")
RE_SD_OK = re.compile(r"ActivateSDCardDriver\(lpszDevKey=Drivers\\SD\\Card\) End\(OK")
RE_SD_NG = re.compile(r"ActivateSDCardDriver\(lpszDevKey=Drivers\\SD\\Card\) End\(NG|SD Check Error")
RE_STORE_READY = re.compile(r"Store Mgr Ready! \[DSK1:\]")
RE_SD_REJECT = re.compile(r"SD Card is \[Security lock state\] or \[no Security\]|Error InitCard")
RE_NAVI_CREATE = re.compile(r"AppLch >> Process Create!!! -> \\windows\\Navi\.exe")
RE_NAVI_NOT_CREATE = re.compile(r"Launch Process Not Create!!! -> \\windows\\Navi\.exe")
RE_VERINF = re.compile(r"VerInf:")
RE_MAPDB = re.compile(r"MapDBVer : ")
RE_ERROR_PROC = re.compile(r"AppLch >> Error Proc<")
RE_FAILSAFE = re.compile(r"\*\*\* FailSafe\.exe Start \*\*\*")
RE_NAVI_MAP_ERROR = re.compile(
    r"ErrorLogMsg\(\) Called\. \[ERR_PRC_NAVI\],\[0x28\],.*\[0x([0-9a-fA-F]+)\]")
RE_IDLE = re.compile(r"AppLch >> Finish Launch Threads!")

# Decisive evidence: stop the boot as soon as one of these appears.  The full
# log is still parsed afterwards; this only bounds a slow host's wall time.
RE_FATAL = (
    ("VerInf mismatch", RE_VERINF),
    ("MapDBVer out of range", RE_MAPDB),
    ("launcher Error Proc", RE_ERROR_PROC),
    ("FailSafe.exe started", RE_FAILSAFE),
    ("Navi.exe process not created", RE_NAVI_NOT_CREATE),
    ("Navi.exe map-data error", RE_NAVI_MAP_ERROR),
)

# One row per reported stage.  ``entry`` proves the stage was reached;
# ``reject`` markers turn a reached stage into a named FAIL.
STAGES: tuple[dict, ...] = (
    {
        "stage": "F0",
        "marker": RE_KERNEL_BANNER,
        "reject": (),
        "fail_detail": "no CE kernel banner in the serial log",
    },
    {
        "stage": "F1",
        "marker": RE_FILESYS,
        "reject": (),
        "fail_detail": "kernel booted but filesys did not start",
    },
    {
        "stage": "F2",
        "marker": RE_SD_OK,
        "reject": (RE_SD_NG,),
        "fail_detail": "SDHC driver did not activate OK",
    },
    {
        "stage": "F3",
        "marker": RE_STORE_READY,
        "reject": (RE_SD_REJECT,),
        "fail_detail": "DSK1: store never became ready",
    },
    {
        "stage": "F4",
        "marker": RE_NAVI_CREATE,
        "reject": (RE_VERINF, RE_MAPDB, RE_ERROR_PROC, RE_FAILSAFE,
                   RE_NAVI_NOT_CREATE, RE_NAVI_MAP_ERROR),
        "fail_detail": "Navi.exe did not start cleanly",
    },
    {
        "stage": "F5",
        "marker": RE_IDLE,
        "reject": (),
        "fail_detail": "launcher did not reach idle within the run window",
    },
)
L4_BY_STAGE = {row["stage"]: row for row in L4_ROWS}
STAGE_ORDER = [row["stage"] for row in STAGES]

# Reject markers on F4, named in the verdict (the string the EXP measured).
F4_REJECT_NAMES = (
    (RE_VERINF, "VerInf mismatch"),
    (RE_MAPDB, "MapDBVer out of range"),
    (RE_ERROR_PROC, "launcher Error Proc"),
    (RE_FAILSAFE, "FailSafe.exe started"),
    (RE_NAVI_NOT_CREATE, "Navi.exe process not created"),
    (RE_NAVI_MAP_ERROR, "Navi.exe map-data error ([ERR_PRC_NAVI],[0x28])"),
)


def stage_name(stage: str) -> str:
    """F0..F4 names come from l4_status.py; F5 is the l4check extension."""
    if stage == "F5":
        return "idle (l4check extension)"
    return L4_BY_STAGE[stage]["name"]


def stage_gate(stage: str) -> str:
    if stage == "F5":
        return "launcher reaches Finish Launch Threads! (M8.C1e idle)"
    return L4_BY_STAGE[stage]["gate"]


class NotRunnable(Exception):
    """A prerequisite is absent; the gate must exit 3, never pass."""


class CardError(Exception):
    """The card is present but cannot supply the derived unit values."""


# --------------------------------------------------------------------------
# Card-side derivation
# --------------------------------------------------------------------------


_sha256 = hashutil.sha256_file


def derive_card_values(card: Path) -> dict:
    """Read HDD_INFO.TXT and MMAIN001.DAT out of the card's FAT partition."""
    import hddinfo
    import mkcard

    with card.open("rb") as fh:
        part, geo, fat = mkcard.open_map_partition(fh)
        raw = mkcard.img_read(fh, geo, fat, "VER_INFO/HDD_INFO.TXT")
        rec = hddinfo.HddInfo.parse(raw)
        mv = hddinfo.extract_mapdbver(rec)
        mmain = mkcard._resolve(fh, geo, fat, "MMAIN001.DAT")[0]
        verinf = rec.text("base_code")[:11]
        if not verinf or mv["value"] is None:
            raise CardError("HDD_INFO.TXT has no usable line 1 / line 3")
    return {
        "verinf": verinf,
        "mapdb": "%d-%d" % (mv["value"], mv["value"]),
        "mapdbver": mv["value"],
        "mapdb_source": "HDD_INFO.TXT line 3 positions %s" % (mv["chars"],),
        "mmain_size": mmain.size,
        "root_label": geo.label,
        "partition_offset": part["offset"],
        "card_sha256": _sha256(card),
    }


# --------------------------------------------------------------------------
# Boot preparation
# --------------------------------------------------------------------------


def find_head(explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit).expanduser()
        if not p.is_file():
            raise NotRunnable("firmware head image not found: %s" % p)
        return p
    for p in (TOOLS_DIR.parent / "archive" / "head256.img",
              Path(os.environ.get("IMG256", "")),
              Path("/home/marek/projekty/OSM2Leaf/archive/head256.img")):
        if str(p) and p.is_file():
            return p
    raise NotRunnable("firmware head image not found (pass --head IMG256)")


def find_qemu(explicit: str | None) -> Path:
    candidates = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    else:
        candidates.append(Path.home() / ".cache/qemu-ze0/build/qemu-system-sh4")
        found = shutil.which("qemu-system-sh4")
        if found:
            candidates.append(Path(found))
    for p in candidates:
        if p.is_file() and os.access(p, os.X_OK):
            return p
    raise NotRunnable("no QEMU binary with -M ze0 (pass --qemu BIN; build.sh)")


def check_qemu_machine(qemu: Path) -> None:
    try:
        proc = subprocess.run([str(qemu), "-M", "help"], capture_output=True,
                              text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise NotRunnable("cannot query QEMU machine list: %s" % exc)
    if not re.search(r"^ze0\b", proc.stdout, re.MULTILINE):
        raise NotRunnable("QEMU has no -M ze0: %s" % qemu)


def build_ipl_patch(head: Path, work: Path, explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit).expanduser()
        if not p.is_file():
            raise CardError("IPL patch not found: %s" % p)
        return p
    out = work / "ipl.txt"
    for cmd in (
        [sys.executable, str(TOOLS_DIR / "ze0_ipl.py"), "patch", str(head),
         "--prefer-app", "auiapp.exe,auirtdll.dll", "--copy-dlls", "unitflash",
         "-o", str(work / "ipl_base.txt")],
        [sys.executable, str(TOOLS_DIR / "ze0_aui.py"), str(head),
         "--no-aui-timeout", "-o", str(work / "ipl_aui.txt")],
    ):
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if proc.returncode != 0:
            raise CardError("IPL patch step failed: %s" % (proc.stderr.strip()[:300],))
    out.write_bytes((work / "ipl_base.txt").read_bytes()
                    + (work / "ipl_aui.txt").read_bytes())
    return out


def build_overlay(card: Path, work: Path) -> Path:
    # tools/qemu-ze0 is not a Python package (the directory has a dash).
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "l4check_mkoverlay", TOOLS_DIR / "qemu-ze0" / "mkoverlay.py")
    mkoverlay = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mkoverlay)

    out = work / "card.qcow2"
    size = OVERLAY_GIB << 30
    if card.stat().st_size > size:
        raise CardError("card is larger than the %d GiB overlay" % OVERLAY_GIB)
    out.write_bytes(mkoverlay.build(str(card), size))
    return out


# --------------------------------------------------------------------------
# Boot and serial parsing
# --------------------------------------------------------------------------


def run_boot(qemu: Path, head: Path, overlay: Path, ipl: Path, derived: dict,
             work: Path, timeout: int) -> dict:
    """Launch QEMU, poll serial.log for the idle marker, stop after *timeout*."""
    serial = work / "serial.log"
    monitor = work / "hmp.sock"
    stderr = work / "qemu.stderr"
    for p in (serial, monitor, stderr):
        if p.exists() and p.is_file():
            p.unlink()
    machine = ",".join((
        "ze0", "kernel-off=0x%x" % KERNEL_OFF, "app-off=0x%x" % APP_OFF,
        "dbgmsg=0x%x" % DBGMSG, "verinf=%s" % derived["verinf"],
        "mapdb=%s" % derived["mapdb"], "ipl-patch=%s" % ipl,
    ))
    cmd = [str(qemu), "-M", machine, "-kernel", str(head),
           "-nographic", "-serial", "file:%s" % serial,
           "-monitor", "unix:%s,server,nowait" % monitor,
           "-icount", ICOUNT,
           "-drive", "if=sd,index=0,file=%s,format=qcow2" % overlay]
    started = time.monotonic()
    idle_at: float | None = None
    offset = 0
    stop_reason = "qemu-exit"
    fatal_at: float | None = None
    with stderr.open("wb") as errfh:
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=errfh)
        while True:
            elapsed = time.monotonic() - started
            if serial.is_file():
                with serial.open("rb") as fh:
                    fh.seek(offset)
                    chunk = fh.read()
                    offset = fh.tell()
                text = chunk.decode("utf-8", "replace")
                if idle_at is None and RE_IDLE.search(text):
                    idle_at = time.monotonic() - started
                    stop_reason = "idle"
                    break
                if fatal_at is None:
                    for name, rx in RE_FATAL:
                        if rx.search(text):
                            fatal_at = time.monotonic() - started
                            stop_reason = "fatal:" + name
                            break
                    if fatal_at is not None:
                        break
            if proc.poll() is not None or elapsed >= timeout:
                if proc.poll() is None:
                    stop_reason = "timeout"
                break
            time.sleep(0.5)
        timed_out = stop_reason == "timeout"
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
    elapsed = time.monotonic() - started
    return {
        "command": cmd,
        "serial_log": str(serial),
        "stderr_log": str(stderr),
        "timeout_s": timeout,
        "elapsed_s": round(elapsed, 2),
        "time_to_idle_s": round(idle_at, 2) if idle_at is not None else None,
        "fatal_at_s": round(fatal_at, 2) if fatal_at is not None else None,
        "stop_reason": stop_reason,
        "timed_out": timed_out,
        "qemu_returncode": proc.returncode,
    }


def parse_serial(text: str) -> dict:
    """Count every marker once and keep the first line number of each."""
    patterns = {
        "kernel_banner": RE_KERNEL_BANNER,
        "filesys": RE_FILESYS,
        "sd_ok": RE_SD_OK,
        "sd_ng": RE_SD_NG,
        "store_ready": RE_STORE_READY,
        "sd_reject": RE_SD_REJECT,
        "navi_create": RE_NAVI_CREATE,
        "navi_not_create": RE_NAVI_NOT_CREATE,
        "verinf": RE_VERINF,
        "mapdb": RE_MAPDB,
        "error_proc": RE_ERROR_PROC,
        "failsafe": RE_FAILSAFE,
        "navi_map_error": RE_NAVI_MAP_ERROR,
        "idle": RE_IDLE,
    }
    counts = {name: 0 for name in patterns}
    first_line = {}
    codes: set[str] = set()
    for lineno, line in enumerate(text.splitlines(), 1):
        for name, rx in patterns.items():
            if rx.search(line):
                counts[name] += 1
                first_line.setdefault(name, lineno)
                if name == "navi_map_error":
                    m = rx.search(line)
                    if m:
                        codes.add(m.group(1))
    return {"counts": counts, "first_line": first_line,
            "navi_error_codes": sorted(codes), "lines": len(text.splitlines())}


def score_stages(parsed: dict, boot: dict) -> list[dict]:
    """One row per F-stage: PASS (reached, no reject) or FAIL (named reason)."""
    rows = []
    for spec in STAGES:
        stage = spec["stage"]
        reached = parsed["counts"][_count_key(stage)] > 0
        detail = ""
        # A reject line names the failed stage even when its entry marker is
        # absent (e.g. the launcher's FailSafe path never creates Navi.exe).
        reject_detail = ""
        if stage == "F4":
            for _rx, label in F4_REJECT_NAMES:
                if parsed["counts"][_count_key_from_label(label)]:
                    reject_detail = label
                    break
        if reject_detail:
            status, detail = "FAIL", reject_detail
        elif not reached:
            # F5 is informational: a slow host may not reach idle inside the
            # run window, which is not a card rejection.  F0..F4 are the gate.
            status = "NOT RUN" if stage == "F5" else "FAIL"
            detail = spec["fail_detail"] + ((" (no marker before the %d s window)"
                                             % boot["timeout_s"]) if boot.get("timeout_s") else "")
            if stage == "F5":
                detail += " (idle is informational, not a card verdict)"
        else:
            status = "PASS"
        rows.append({
            "stage": stage,
            "name": stage_name(stage),
            "gate": stage_gate(stage),
            "status": status,
            "line": parsed["first_line"].get(_count_key(stage)),
            "detail": detail,
        })
    return rows


_COUNT_KEY = {
    "F0": "kernel_banner", "F1": "filesys", "F2": "sd_ok",
    "F3": "store_ready", "F4": "navi_create", "F5": "idle",
}
_LABEL_KEY = {
    "VerInf mismatch": "verinf",
    "MapDBVer out of range": "mapdb",
    "launcher Error Proc": "error_proc",
    "FailSafe.exe started": "failsafe",
    "Navi.exe process not created": "navi_not_create",
    "Navi.exe map-data error ([ERR_PRC_NAVI],[0x28])": "navi_map_error",
}


def _count_key(stage: str) -> str:
    return _COUNT_KEY[stage]


def _count_key_from_label(name: str) -> str:
    return _LABEL_KEY[name]


def make_verdict(rows: list[dict], parsed: dict) -> dict:
    """Aggregate stage rows into stage_reached / failed_stage / verdict."""
    reached = [r["stage"] for r in rows if r["status"] == "PASS"]
    # F5 (idle) is reported but is not a card verdict: a loaded host may not
    # reach it inside the window.  F0..F4 decide PASS/FAIL.
    failed = [r for r in rows if r["status"] == "FAIL" and r["stage"] != "F5"]
    first_failed = failed[0]["stage"] if failed else None
    # "stage reached" = highest consecutive passing stage before the first fail.
    consec = []
    for r in rows:
        if r["status"] != "PASS":
            break
        consec.append(r["stage"])
    map_verdict = ("ERROR" if parsed["counts"]["navi_map_error"] else
                   "OPENED" if parsed["counts"]["navi_create"] else "NOT RUN")
    launcher = "ACCEPT"
    # The launcher verdict uses only the launcher's own checks; the Navi map
    # error is the separate map_files verdict (both still fail stage F4).
    for _rx, label in F4_REJECT_NAMES[:5]:
        if parsed["counts"][_count_key_from_label(label)]:
            launcher = "REJECT: " + label
            break
    return {
        "stage_reached": consec[-1] if consec else "none",
        "stages_passed": reached,
        "failed_stage": first_failed,
        "result": "PASS" if not failed else "FAIL",
        "exit": EXIT_PASS if not failed else EXIT_FAIL,
        "launcher": {"verdict": launcher,
                     "markers": {k: parsed["counts"][k] for k in
                                 ("verinf", "mapdb", "error_proc", "failsafe",
                                  "navi_not_create", "navi_map_error", "idle")}},
        "map_files": {"verdict": map_verdict,
                      "navi_error_lines": parsed["counts"]["navi_map_error"],
                      "navi_error_codes": parsed["navi_error_codes"],
                      "detail": ("Navi.exe started; %d map-data error log line(s)"
                                 % parsed["counts"]["navi_map_error"])},
    }


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------


def not_runnable(reason: str, **extra) -> dict:
    doc = {
        "schema": SCHEMA, "claim": CLAIM, "exp": EXP_RECORD,
        "card": extra.get("card"), "head": extra.get("head"),
        "qemu": extra.get("qemu"), "result": "NOT RUNNABLE",
        "exit": EXIT_NOT_RUNNABLE, "problems": [reason],
    }
    return doc


def render_text(doc: dict) -> str:
    lines = ["l4check: one-command L4 verdict gate (claim %s)" % CLAIM,
             "exp      %s" % EXP_RECORD]
    if doc["result"] == "NOT RUNNABLE":
        lines.append("RESULT: NOT RUNNABLE (%s; exit 3, never a pass)"
                     % "; ".join(doc["problems"]))
        return "\n".join(lines)
    if "derived" not in doc or "boot" not in doc:
        for problem in doc.get("problems", []):
            lines.append("PROBLEM  %s" % problem)
        lines.append("RESULT: %s (exit %d)" % (doc["result"], doc["exit"]))
        return "\n".join(lines)
    lines.append("card     %s" % doc["card"])
    lines.append("head     %s" % doc["head"])
    lines.append("qemu     %s" % doc["qemu"])
    d = doc["derived"]
    lines.append("derived  verinf=%s mapdb=%s (MapDBVer %s), MMAIN001.DAT %s B"
                 % (d["verinf"], d["mapdb"], d["mapdb_source"], d["mmain_size"]))
    b = doc["boot"]
    lines.append("boot     elapsed=%ss time-to-idle=%ss stop=%s timeout=%ss serial=%s"
                 % (b["elapsed_s"], b["time_to_idle_s"], b["stop_reason"],
                    b["timeout_s"], b["serial_log"]))
    lines.append("")
    for row in doc["stages"]:
        lines.append("  [%s] %s %s: %s%s"
                     % (row["status"], row["stage"], row["name"],
                        row["detail"] or row["gate"],
                        " (log line %s)" % row["line"] if row["line"] else ""))
    v = doc["verdict"]
    lines.append("")
    lines.append("stage reached: %s   failed stage: %s"
                 % (v["stage_reached"], v["failed_stage"] or "-"))
    lines.append("launcher:      %s" % v["launcher"]["verdict"])
    lines.append("map files:     %s (%d error line(s), codes %s)"
                 % (v["map_files"]["verdict"], v["map_files"]["navi_error_lines"],
                    ",".join(v["map_files"]["navi_error_codes"]) or "-"))
    if doc.get("problems"):
        for problem in doc["problems"]:
            lines.append("PROBLEM  %s" % problem)
    lines.append("RESULT: %s (exit %d)"
                 % (doc["result"], doc["exit"]))
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--card", metavar="IMG", help="SD card image to boot")
    p.add_argument("--head", metavar="IMG256",
                   help="firmware head (default: archive/head256.img)")
    p.add_argument("--qemu", metavar="BIN",
                   help="qemu-system-sh4 with -M ze0")
    p.add_argument("--json", nargs="?", const="-", default=None, metavar="PATH",
                   help="write the report JSON to PATH (or stdout)")
    p.add_argument("--workdir", metavar="DIR",
                   help="output directory (default: scratch/m8.h13/l4check-*)")
    p.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, metavar="S",
                   help="wall-clock boot window in seconds (default %d)"
                        % DEFAULT_TIMEOUT)
    p.add_argument("--ipl-patch", metavar="FILE",
                   help="use a prebuilt IPL patch instead of generating one")
    p.add_argument("--selftest", action="store_true",
                   help="run the synthetic self-test (no card/QEMU needed)")
    return p


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv == ["--selftest"]:
        return selftest()
    args = build_parser().parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.card:
        build_parser().error("--card is required")
    if args.timeout <= 0:
        build_parser().error("--timeout must be positive")
    card = Path(args.card).expanduser()
    try:
        if not card.is_file():
            raise NotRunnable("card image not found: %s" % card)
        head = find_head(args.head)
        qemu = find_qemu(args.qemu)
        check_qemu_machine(qemu)
    except NotRunnable as exc:
        doc = not_runnable(str(exc), card=str(card), head=args.head, qemu=args.qemu)
        _emit(doc, args.json)
        return EXIT_NOT_RUNNABLE

    work = (Path(args.workdir).expanduser() if args.workdir else
            Path.home() / "projekty/leafre-work/scratch/m8.h13"
            / ("l4check-%d" % int(time.time())))
    work.mkdir(parents=True, exist_ok=True)
    problems: list[str] = []
    try:
        derived = derive_card_values(card)
        ipl = build_ipl_patch(head, work, args.ipl_patch)
        overlay = build_overlay(card, work)
        boot = run_boot(qemu, head, overlay, ipl, derived, work, args.timeout)
        serial = Path(boot["serial_log"])
        text = serial.read_text(encoding="utf-8", errors="replace") if serial.is_file() else ""
        parsed = parse_serial(text)
        if not text:
            problems.append("serial log is empty (QEMU returncode %s)"
                            % boot["qemu_returncode"])
        # -15 is our own terminate() after idle/fatal evidence or the timeout.
        if boot["stop_reason"] == "qemu-exit" and boot["qemu_returncode"] not in (0, None):
            problems.append("QEMU exited early with status %s" % boot["qemu_returncode"])
        rows = score_stages(parsed, boot)
        verdict = make_verdict(rows, parsed)
    except (CardError, OSError, ValueError) as exc:
        doc = not_runnable("boot preparation failed: %s" % exc,
                           card=str(card), head=str(head), qemu=str(qemu))
        doc["problems"].append("workdir: %s" % work)
        _emit(doc, args.json)
        return EXIT_NOT_RUNNABLE
    except Exception as exc:  # noqa: BLE001 - an unexpected stop is a FAIL, never a pass
        doc = {
            "schema": SCHEMA, "claim": CLAIM, "exp": EXP_RECORD,
            "card": str(card), "head": str(head), "qemu": str(qemu),
            "workdir": str(work), "stages": [],
            "verdict": {"stage_reached": "none", "failed_stage": "F0",
                        "result": "FAIL", "exit": EXIT_FAIL},
            "result": "FAIL", "exit": EXIT_FAIL,
            "problems": ["l4check crashed: %s: %s" % (type(exc).__name__, str(exc)[:300])],
        }
        _emit(doc, args.json)
        return EXIT_FAIL

    doc = {
        "schema": SCHEMA, "claim": CLAIM, "exp": EXP_RECORD,
        "command": "l4check", "build": "eu2011",
        "card": str(card), "head": str(head), "qemu": str(qemu),
        "workdir": str(work),
        "stage_source": "l4_status.ROWS F0-F4 + l4check F5 idle",
        "derived": derived, "boot": boot, "parsed": parsed,
        "stages": rows, "verdict": verdict,
        "result": verdict["result"], "exit": verdict["exit"],
        "problems": problems,
    }
    _emit(doc, args.json)
    return doc["exit"]


def _emit(doc: dict, json_path: str | None) -> None:
    if json_path is not None:
        text = json.dumps(doc, indent=2)
        if json_path == "-":
            print(text)
        else:
            Path(json_path).write_text(text + "\n", encoding="utf-8")
            print("report: %s" % json_path)
    else:
        print(render_text(doc))


# --------------------------------------------------------------------------
# self-test: canned logs, no card, head or QEMU
# --------------------------------------------------------------------------

FACTORY_LOG = r"""
Windows CE Kernel for Hitachi SH Built on Oct 23 2008 at 19:31:09
SH-4 Kernel
Windows CE Firmware Init
Configuring: Primary pages: 10345, Secondary pages: 32760, Filesystem pages = 80
DllEntry ++  SDHC Driver ++
###SDHC(Port=0)-->ActivateSDCardDriver(lpszDevKey=Drivers\SD\Card) End(OK!!!!)
AppLch >> SD Card Security Unlocked!
AppLch >> Mount System SD Proc Start
AppLch >> Process Create!!! -> \windows\Navi.exe [Arg = (NULL)]
AppLch >> Store Mgr Ready! [DSK1:]
AppLch >> Finish Launch Threads!
"""

BROKEN_LOG = r"""
Windows CE Kernel for Hitachi SH Built on Oct 23 2008 at 19:31:09
SH-4 Kernel
Windows CE Firmware Init
Configuring: Primary pages: 10345, Secondary pages: 32760, Filesystem pages = 80
DllEntry ++  SDHC Driver ++
###SDHC(Port=0)-->ActivateSDCardDriver(lpszDevKey=Drivers\SD\Card) End(OK!!!!)
AppLch >> SD Card Security Unlocked!
AppLch >> Process Create!!! -> \windows\Navi.exe [Arg = (NULL)]
AppLch >> Store Mgr Ready! [DSK1:]
ErrorLogMsg() Called. [ERR_PRC_NAVI],[0x28],[0x0B],[ERR_LVL_B],[0x00000105]
ErrorLogMsg() Called. [ERR_PRC_NAVI],[0x28],[0x08],[ERR_LVL_B],[0x00000101]
"""

REJECT_LOG = r"""
Windows CE Kernel for Hitachi SH Built on Oct 23 2008 at 19:31:09
SH-4 Kernel
Windows CE Firmware Init
Configuring: Primary pages: 10345, Secondary pages: 32760, Filesystem pages = 80
###SDHC(Port=0)-->ActivateSDCardDriver(lpszDevKey=Drivers\SD\Card) End(OK!!!!)
AppLch >> Store Mgr Ready! [DSK1:]
VerInf:QSD-302-101 / HddInf:QSD-302-100
AppLch >> Error Proc<00000050>!!
*** FailSafe.exe Start ***
"""


def selftest() -> int:
    fails = 0

    def chk(cond: bool, msg: str) -> None:
        nonlocal fails
        print("  %s %s" % ("ok  " if cond else "FAIL", msg))
        if not cond:
            fails += 1

    print("l4check selftest (canned logs, no vendor data)")
    boot = {"timeout_s": 300, "time_to_idle_s": 12.5}
    good = parse_serial(FACTORY_LOG)
    bad = parse_serial(BROKEN_LOG)
    reject = parse_serial(REJECT_LOG)

    chk(set(STAGE_ORDER) == {"F0", "F1", "F2", "F3", "F4", "F5"},
        "stage ladder is F0-F5")
    chk([stage_name(s) for s in ("F0", "F1", "F2", "F3", "F4")] ==
        [L4_BY_STAGE[s]["name"] for s in ("F0", "F1", "F2", "F3", "F4")],
        "F0-F4 names are imported from l4_status.py")
    chk(good["counts"]["navi_map_error"] == 0 and good["counts"]["idle"] == 1,
        "factory log: no map error, one idle marker")
    chk(bad["counts"]["navi_map_error"] == 2 and bad["counts"]["idle"] == 0,
        "broken log: two map errors, no idle marker")
    chk(bad["navi_error_codes"] == ["00000101", "00000105"],
        "broken log error codes are extracted from the log")
    chk(reject["counts"]["verinf"] == 1 and reject["counts"]["failsafe"] == 1,
        "reject log: VerInf and FailSafe markers counted")

    ok_rows = score_stages(good, boot)
    ok_verdict = make_verdict(ok_rows, good)
    chk(all(r["status"] == "PASS" for r in ok_rows), "factory log: all six stages PASS")
    chk(ok_verdict["exit"] == EXIT_PASS and ok_verdict["result"] == "PASS",
        "factory verdict: PASS / exit 0")
    chk(ok_verdict["stage_reached"] == "F5" and ok_verdict["failed_stage"] is None,
        "factory stage reached F5, no failed stage")
    chk(ok_verdict["map_files"]["verdict"] == "OPENED",
        "factory map files OPENED")

    bad_rows = score_stages(bad, boot)
    bad_verdict = make_verdict(bad_rows, bad)
    bad_by = {r["stage"]: r for r in bad_rows}
    chk(bad_by["F4"]["status"] == "FAIL" and
        "0x28" in bad_by["F4"]["detail"], "broken log: F4 FAIL names the 0x28 line")
    chk(bad_by["F5"]["status"] == "NOT RUN",
        "broken log: F5 idle NOT RUN, not a second card failure")
    no_idle = FACTORY_LOG.replace("AppLch >> Finish Launch Threads!\n", "")
    ni_parsed = parse_serial(no_idle)
    ni_rows = score_stages(ni_parsed, boot)
    ni_verdict = make_verdict(ni_rows, ni_parsed)
    chk(ni_verdict["result"] == "PASS" and
        ni_verdict["stage_reached"] == "F4" and
        {r["stage"]: r["status"] for r in ni_rows}["F5"] == "NOT RUN",
        "no idle in window: card verdict still PASS, stage reached F4")
    chk(bad_verdict["failed_stage"] == "F4" and
        bad_verdict["stage_reached"] == "F3",
        "broken verdict: failed stage F4, reached F3")
    chk(bad_verdict["exit"] == EXIT_FAIL and bad_verdict["result"] == "FAIL",
        "broken verdict: FAIL / exit 1")
    chk(bad_verdict["map_files"]["verdict"] == "ERROR" and
        bad_verdict["map_files"]["navi_error_lines"] == 2,
        "broken map files ERROR, 2 error lines")
    chk(bad_verdict["launcher"]["verdict"] == "ACCEPT",
        "launcher accepts both cards (discriminator is the Navi map error)")

    rej_rows = score_stages(reject, boot)
    rej_verdict = make_verdict(rej_rows, reject)
    rej_by = {r["stage"]: r for r in rej_rows}
    chk(rej_by["F4"]["status"] == "FAIL" and
        rej_by["F4"]["detail"] == "VerInf mismatch",
        "reject log: F4 FAIL names the VerInf mismatch")
    chk(rej_verdict["launcher"]["verdict"].startswith("REJECT:"),
        "reject log: launcher verdict REJECT")

    empty = parse_serial("")
    empty_rows = score_stages(empty, boot)
    chk(empty_rows[0]["status"] == "FAIL" and empty_rows[0]["stage"] == "F0",
        "empty log: F0 FAIL (never a pass)")
    chk(make_verdict(empty_rows, empty)["stage_reached"] == "none",
        "empty log: no stage reached")

    # Card-side derivation from a synthetic HDD_INFO record (no vendor bytes).
    import hddinfo
    synthetic = hddinfo.HddInfo.parse(
        b"QSD-302-100\r\nQSD-309-101\r\n02-110100-00\r\n"
        b"SDC08-EVEUR\r\n11-05\r\n470323501005")
    chk(synthetic.text("base_code")[:11] == "QSD-302-100",
        "HDD_INFO line 1 derives verinf=QSD-302-100")
    chk(hddinfo.extract_mapdbver(synthetic)["value"] == 16,
        "HDD_INFO line 3 derives MapDBVer 16 (mapdb 16-16)")

    # Not-runnable is a distinct class, never a pass, and selftest never boots.
    chk(not_runnable("no image")["exit"] == EXIT_NOT_RUNNABLE and
        not_runnable("no image")["result"] == "NOT RUNNABLE",
        "not-runnable report: exit 3, result NOT RUNNABLE")
    doc = {"result": "NOT RUNNABLE", "exit": EXIT_NOT_RUNNABLE,
           "exp": EXP_RECORD, "claim": CLAIM, "problems": ["no image"],
           "card": None, "head": None, "qemu": None}
    text = render_text(doc)
    chk("exit 3, never a pass" in text, "text report says exit 3 is never a pass")

    print("selftest: %s (%d failure(s))" % ("OK" if not fails else "FAIL", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
