#!/usr/bin/env python3
"""Kernel debug-serial evidence for the QEMU ``ze0`` machine (TODO M8.A6).

Four questions, one sub-command each:

  refs IMG     Which nk.exe code touches the debug SCIF window, and who calls
               the polling writer?  Lists every literal-pool word whose value
               lies in ``--window`` (default the SCIF channel at
               ``0xffe46000``, 0x1000 bytes), each ``mov.l @(disp,PC)`` that
               loads it, and the callers of ``--writer`` (default
               ``0x8804cfa4``, EU2011) through literal pools *and* ``bsr``,
               then walks the caller chain up ``--depth`` levels.  This is
               the static half: if the writer has one caller and that caller
               is the exception reporter, the boot banner cannot reach the
               SCIF through it.

  shim -o OUT  Write a 20-byte SH-4 stub (our bytes, no vendor data) that
               loads ``--string`` into r4, calls ``--writer`` and then spins
               on ``bra .``.  Loaded with ``-device loader`` at a free RAM
               address and used as the entry point, it is the *positive
               control*: the firmware's own writer must put the string on the
               serial model, so an empty serial log on a real boot is not a
               wiring fault.

  banner LOG   Which known kernel lines appear in a captured serial log
               (``-serial file:LOG``)?  Exit 0 when a boot-banner line is
               present, 1 when none is.

  dbgcmp SERIAL DBGLOG
               Does the kernel debug text on the serial port (``-M
               ze0,dbgmsg=0x880404f4``, TODO M8.B6) equal what
               ``ze0_dbgmsg.py run`` read over the gdbstub?  Both are cut
               into text lines (serial: on ``\n``; the gdbstub log: one
               message per hook line, ``" | "`` marks an embedded CRLF),
               empty lines dropped, and the first ``--lines`` are compared.
               A serial line that the gdbstub line is a prefix of, where the
               gdbstub string hit ``--max-len`` (256 UTF-16 units), counts as
               ``truncated``, not as a difference.  Exit 0 when there is no
               other difference.

Addresses are EU2011 (``archive/head256.img``, image B at ``0x3e00200``) and
come from ``tools/cerom.py``/``tools/sh4xref.py``; the SH-4 decoding is
``tools/sh4dis.py`` (little-endian, pinned there).  Stdlib only.

Usage:
  ze0_serial.py refs IMG [--image-start 0x3e00200] [--module nk.exe]
                [--window 0xffe46000:0x1000] [--writer 0x8804cfa4] [--depth 3]
  ze0_serial.py shim -o FILE [--base 0x8f000000] [--string 0x88001060]
                [--writer 0x8804cfa4]
  ze0_serial.py banner LOG
  ze0_serial.py dbgcmp SERIAL DBGLOG [--lines 200] [--max-chars 256]
  ze0_serial.py peer PATH [--listen] [--send-hex HEX] [--expect-hex HEX]
                [--count N] [--timeout S] [--nowait]
                A host peer for a --serial-peer socket (M8.H1). The line is
                a raw byte stream: --send-hex writes to the guest,
                --expect-hex checks what comes back. Length-prefixed frames
                (4-byte big-endian) are used by peer control channels and
                are covered by --selftest.
  ze0_serial.py hmp SOCK COMMAND
                Send one HMP command (e.g. "xp/16xb 0xa999e800") and print
                the monitor reply, for guest-side evidence of a received fix.
  ze0_serial.py --selftest

Method and results: docs/experiments/EXP-2026-11-19-M8.A6-debug-serial.md
"""

import argparse
import os
import re
import socket
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sh4dis import Mem, bsr_target, decode, fmt, jsr_reg, movl_pc_target  # noqa: E402

NK_IMAGE_START = 0x3E00200          # EU2011 image B (cerom.py romhdr)
DEBUG_SCIF = 0xFFE46000             # C-534
WRITER_EU2011 = 0x8804CFA4          # C-534, EXP-2026-11-05-37
BANNER_EU2011 = 0x88001060          # L"\r\nWindows CE Kernel for Hitachi SH ..."

BANNER_LINES = (
    b"Windows CE Kernel for Hitachi SH",
    b"Booting Windows CE version",
)
OTHER_LINES = (
    b"SH-4 Kernel",
    b"Exception occurred!!",
    b"AER Exception Report Start",
)


# --------------------------------------------------------------------------
# refs
# --------------------------------------------------------------------------

def pool_words_in(exec_segs, lo, hi):
    """(pool_va, value) for every 4-aligned word with lo <= value < hi."""
    out = []
    for base, blob in exec_segs:
        start = (-base) % 4
        for off in range(start, len(blob) - 3, 4):
            v = struct.unpack_from("<I", blob, off)[0]
            if lo <= v < hi:
                out.append((base + off, v))
    return out


def pool_loads(mem, pool_va):
    """``mov.l @(disp,PC),Rn`` instructions that read ``pool_va``."""
    out = []
    for a in range(max(0, pool_va - 1024 - 4), pool_va, 2):
        t = movl_pc_target(a, mem.u16(a))
        if t and t[1] == pool_va:
            out.append((a, t[0]))
    return out


def bsr_callers(exec_segs, target):
    out = []
    for base, blob in exec_segs:
        for off in range(0, len(blob) - 1, 2):
            a = base + off
            w = struct.unpack_from("<H", blob, off)[0]
            if (w & 0xF000) == 0xB000 and bsr_target(a, w) == target:
                out.append(a)
    return out


def callers(mem, exec_segs, target):
    """[(site_va, kind)] that transfer control to ``target``: a literal load
    of it followed by ``jsr/jmp`` (kind 'pool'), or a ``bsr`` (kind 'bsr')."""
    out = []
    for pool_va, _v in pool_words_in(exec_segs, target, target + 1):
        for load, reg in pool_loads(mem, pool_va):
            for k in range(1, 13):
                j = jsr_reg(mem.u16(load + 2 * k))
                if j and j[1] == reg:
                    out.append((load + 2 * k, "pool"))
                    break
            else:
                out.append((load, "load-only"))
    out += [(a, "bsr") for a in bsr_callers(exec_segs, target)]
    return sorted(out)


def caller_chain(mem, exec_segs, fn_of, target, depth):
    """Breadth-first: level 0 = callers of target, level k = callers of the
    functions that hold the level k-1 sites.  Returns a list of lines."""
    lines, seen, frontier = [], set(), [target]
    for level in range(depth):
        nxt = []
        for t in frontier:
            if t in seen:
                continue
            seen.add(t)
            sites = callers(mem, exec_segs, t)
            if not sites:
                lines.append("  L%d 0x%08x  no static caller" % (level, t))
            for site, kind in sites:
                fn = fn_of(site)
                lines.append("  L%d 0x%08x  <- %s at 0x%08x in fn %s"
                             % (level, t, kind, site,
                                "0x%08x" % fn if fn is not None else "?"))
                if fn is not None:
                    nxt.append(fn)
        frontier = nxt
        if not frontier:
            break
    return lines


def cmd_refs(args):
    import sh4xref
    mem, exec_segs, _imp, _exp = sh4xref.load_module(
        args.image, args.image_start, args.module)

    pdata_of = getattr(mem, "fn_of", None)

    def fn_of(va):
        # pdata only: a heuristic start inside a pdata gap can land in the
        # middle of the previous function's literal pool (fn_audit INSIDE).
        return pdata_of(va) if pdata_of is not None else sh4xref.fn_start(mem, va)

    lo, size = args.window
    words = pool_words_in(exec_segs, lo, lo + size)
    nbytes = sum(len(b) for _, b in exec_segs)
    print("module %s  exec sections %d (%d bytes)" % (args.module, len(exec_segs), nbytes))
    print("window 0x%08x+0x%x: %d pool word(s)" % (lo, size, len(words)))
    nloads = 0
    regs = set()
    for pool_va, v in words:
        loads = pool_loads(mem, pool_va)
        nloads += len(loads)
        regs.add(v)
        for load, reg in loads:
            fn = fn_of(load)
            print("  pool 0x%08x = 0x%08x  load 0x%08x (r%d) fn %s"
                  % (pool_va, v, load, reg, "0x%08x" % fn if fn is not None else "? (pdata gap: leaf)"))
    print("window registers referenced: %s" % (" ".join("+0x%02x" % (r - lo) for r in sorted(regs)) or "none"))
    print("window loads: %d" % nloads)
    sites = callers(mem, exec_segs, args.writer)
    print("writer 0x%08x: %d call site(s) (pool %d, bsr %d)"
          % (args.writer, len(sites), sum(k == "pool" for _, k in sites),
             sum(k == "bsr" for _, k in sites)))
    print("caller chain (depth %d):" % args.depth)
    for line in caller_chain(mem, exec_segs, fn_of, args.writer, args.depth):
        print(line)
    return 0


# --------------------------------------------------------------------------
# shim
# --------------------------------------------------------------------------

def build_shim(base, string_va, writer_va):
    """mov.l @(lit0),r4; mov.l @(lit1),r1; jsr @r1; nop; bra .; nop; lit0; lit1.

    ``base`` must be 4-aligned so the PC-relative literals land on 0x0c/0x10.
    """
    if base % 4:
        raise ValueError("shim base must be 4-aligned")
    w = [
        0xD402,   # 0x00 mov.l @(0x0c,pc),r4   (0+4)&~3 + 2*4 = 0x0c
        0xD103,   # 0x02 mov.l @(0x10,pc),r1   (2+4)&~3 + 3*4 = 0x10
        0x410B,   # 0x04 jsr @r1
        0x0009,   # 0x06 nop (delay slot)
        0xAFFE,   # 0x08 bra 0x08 (spin; PC+4-4)
        0x0009,   # 0x0a nop (delay slot)
    ]
    return struct.pack("<6H", *w) + struct.pack("<II", string_va, writer_va)


def disasm_shim(blob, base):
    mem = Mem([(base, blob)])
    return [fmt(decode(mem.u16(base + i), base + i, mem)) for i in range(0, 12, 2)]


def cmd_shim(args):
    blob = build_shim(args.base, args.string, args.writer)
    with open(args.out, "wb") as fh:
        fh.write(blob)
    print("shim %s: %d bytes at VA 0x%08x (phys 0x%08x), r4=0x%08x, call 0x%08x"
          % (args.out, len(blob), args.base, args.base & 0x1FFFFFFF, args.string, args.writer))
    for line in disasm_shim(blob, args.base):
        print("  " + line)
    return 0


# --------------------------------------------------------------------------
# banner
# --------------------------------------------------------------------------

def scan_log(data):
    """{line: count} for the banner and the other known kernel lines."""
    return {s: data.count(s) for s in BANNER_LINES + OTHER_LINES}


def cmd_banner(args):
    try:
        with open(args.log, "rb") as fh:
            data = fh.read()
    except OSError as e:
        print("banner: cannot read %s: %s" % (args.log, e), file=sys.stderr)
        return 2
    hits = scan_log(data)
    print("serial log %s: %d bytes" % (args.log, len(data)))
    for s, n in hits.items():
        print("  %-36s %d" % (s.decode(), n))
    found = any(hits[s] for s in BANNER_LINES)
    print("banner: %s" % ("PRESENT" if found else "ABSENT"))
    return 0 if found else 1


DBGMSG_LINE = re.compile(r"^\s*[0-9.]+ 0x[0-9a-f]{8} pr=0x[0-9a-f]{8} r\d+=0x[0-9a-f]{8} ?(.*)$")
DBGMSG_TAIL = re.compile(r"^(word|dump|count) 0x[0-9a-f]{8}|^hook hits: ")


def serial_lines(data):
    """Text lines of a serial log (UTF-8), CR stripped, empty lines dropped."""
    text = data.decode("utf-8", "replace")
    return [ln.rstrip("\r") for ln in text.split("\n") if ln.rstrip("\r")]


def dbgmsg_lines(text):
    """Text lines of a ze0_dbgmsg.py run log, in the same cut as serial_lines.

    One hook line holds one message (trailing CRLF stripped, inner CRLF
    written as " | "); a raw newline inside a message continues it on the
    next log line.  The word/dump/count/hook-hits tail is skipped."""
    msgs = []
    for raw in text.split("\n"):
        m = DBGMSG_LINE.match(raw)
        if m:
            msgs.append(m.group(1))
        elif DBGMSG_TAIL.match(raw) or not msgs:
            continue
        else:
            msgs[-1] += "\n" + raw
    out = []
    for msg in msgs:
        for part in msg.split(" | "):
            for ln in part.split("\n"):
                ln = ln.rstrip("\r")
                if ln:
                    out.append(ln)
    return out


def compare_lines(ser, dbg, n, max_chars=256):
    """Compare the first n lines; returns (same, truncated, diffs)."""
    same = trunc = 0
    diffs = []
    for i in range(min(n, max(len(ser), len(dbg)))):
        a = ser[i] if i < len(ser) else None
        b = dbg[i] if i < len(dbg) else None
        if a == b:
            same += 1
        elif a is not None and b is not None and len(b) < len(a) and a.startswith(b) \
                and len(b) >= max_chars - 2:
            trunc += 1
        else:
            diffs.append((i + 1, a, b))
    return same, trunc, diffs


def cmd_dbgcmp(args):
    try:
        with open(args.serial, "rb") as fh:
            ser = serial_lines(fh.read())
        with open(args.dbglog, encoding="utf-8", errors="replace") as fh:
            dbg = dbgmsg_lines(fh.read())
    except OSError as e:
        print("dbgcmp: %s" % e, file=sys.stderr)
        return 2
    n = min(args.lines, max(len(ser), len(dbg)))
    same, trunc, diffs = compare_lines(ser, dbg, args.lines, args.max_chars)
    print("serial lines %d, gdbstub lines %d, compared %d" % (len(ser), len(dbg), n))
    print("equal %d, truncated by gdbstub max-len %d, different %d" % (same, trunc, len(diffs)))
    for i, a, b in diffs[:20]:
        print("  line %d\n    serial : %r\n    gdbstub: %r" % (i, a, b))
    if n < args.lines:
        print("dbgcmp: only %d line(s) to compare (want %d)" % (n, args.lines))
        return 1
    return 0 if not diffs else 1


# --------------------------------------------------------------------------
# socket framing (M8.H1)
# --------------------------------------------------------------------------

FRAME_MAX = 0x100000       # 1 MiB: refuse a bogus length before allocating


def frame_bytes(payload):
    """One peer-control message: big-endian u32 length, then the bytes."""
    if len(payload) > FRAME_MAX:
        raise ValueError("frame too large: %d bytes" % len(payload))
    return struct.pack(">I", len(payload)) + payload


def frames_in(buf):
    """(complete payloads, unconsumed tail) from a stream buffer."""
    out = []
    while len(buf) >= 4:
        n = struct.unpack_from(">I", buf)[0]
        if n > FRAME_MAX:
            raise ValueError("frame too large: %d bytes" % n)
        if len(buf) < 4 + n:
            break
        out.append(buf[4:4 + n])
        buf = buf[4 + n:]
    return out, buf


def recv_exact(sock, n):
    """Read exactly n bytes; a short peer is an error, not a partial success."""
    out = bytearray()
    while len(out) < n:
        part = sock.recv(n - len(out))
        if not part:
            raise EOFError("socket closed after %d of %d bytes" % (len(out), n))
        out.extend(part)
    return bytes(out)


def send_frame(sock, payload):
    sock.sendall(frame_bytes(payload))


def recv_frame(sock):
    n = struct.unpack(">I", recv_exact(sock, 4))[0]
    if n > FRAME_MAX:
        raise ValueError("frame too large: %d bytes" % n)
    return recv_exact(sock, n)


def cmd_peer(args):
    """Exchange raw bytes with a host socket attached to a guest SCIF."""
    try:
        if args.listen:
            try:
                os.unlink(args.path)
            except FileNotFoundError:
                pass
            srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            srv.bind(args.path)
            srv.listen(1)
            srv.settimeout(args.timeout)
            sock, _ = srv.accept()
            srv.close()
        else:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(args.timeout)
            sock.connect(args.path)
        with sock:
            sent = bytes.fromhex(args.send_hex or "")
            if sent:
                sock.sendall(sent)
            if args.nowait:
                print("peer: sent %d byte(s), no reply requested" % len(sent))
                return 0
            want = bytes.fromhex(args.expect_hex or "")
            n = args.count or (len(want) or 64)
            got = recv_exact(sock, n)
            ok = not want or want in got
            print("peer: sent %d byte(s), received %s" %
                  (len(sent), got.hex()))
            print("peer: expect %s: %s" %
                  (want.hex() or "any", "PASS" if ok else "FAIL"))
            return 0 if ok else 1
    except (OSError, EOFError, ValueError) as e:
        print("peer: %s" % e, file=sys.stderr)
        return 2


def cmd_hmp(args):
    """One Human Monitor Protocol command, for guest-side evidence."""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(args.timeout)
            sock.connect(args.sock)
            sock.sendall((args.command + "\n").encode())
            data = bytearray()
            while True:
                try:
                    part = sock.recv(65536)
                except socket.timeout:
                    break
                if not part:
                    break
                data.extend(part)
                # QEMU echoes the command character by character; stop only
                # when a prompt follows a newline after that echo.  Long
                # pmemsave dumps need the caller to raise --timeout.
                if re.search(rb"\n\(qemu\) $", data.replace(b"\r", b"")):
                    break
        text = data.decode("utf-8", "replace").replace("\r", "")
        text = re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]", "", text)
        print("\n".join(ln for ln in text.split("\n") if ln.strip()))
        return 0
    except OSError as e:
        print("hmp: %s" % e, file=sys.stderr)
        return 2


# --------------------------------------------------------------------------
# selftest
# --------------------------------------------------------------------------

def _synthetic():
    """A tiny code block at 0x10000 with a writer, one pool caller, one bsr
    caller, a window load and a decoy pool word just outside the window.

      0x10000 rts; nop                      previous function end
      0x10004 sts.l pr,@-r15                fn A
      0x10006 mov.l @(0x10020),r3           -> writer 0x10040
      0x10008 jsr @r3; nop
      0x1000c rts; nop
      0x10010 sts.l pr,@-r15                fn B
      0x10012 bsr 0x10040; nop
      0x10016 rts; nop
      0x10020 pool 0x10040
      0x1003c rts; nop
      0x10040 writer: mov.l @(0x10048),r3 ; rts ; nop
      0x10048 pool 0xffe46010 (window)
      0x1004c pool 0xffe47000 (decoy, outside a 0x1000 window)
    """
    base = 0x10000
    b = bytearray(0x50)

    def put(va, w):
        struct.pack_into("<H", b, va - base, w)

    put(0x10000, 0x000B); put(0x10002, 0x0009)
    put(0x10004, 0x4F22)
    put(0x10006, 0xD300 | ((0x10020 - ((0x10006 + 4) & ~3)) // 4))
    put(0x10008, 0x430B); put(0x1000A, 0x0009)
    put(0x1000C, 0x000B); put(0x1000E, 0x0009)
    put(0x10010, 0x4F22)
    put(0x10012, 0xB000 | (((0x10040 - (0x10012 + 4)) // 2) & 0xFFF)); put(0x10014, 0x0009)
    put(0x10016, 0x000B); put(0x10018, 0x0009)
    struct.pack_into("<I", b, 0x20, 0x10040)
    struct.pack_into("<I", b, 0x48, 0xFFE46010)
    struct.pack_into("<I", b, 0x4C, 0xFFE47000)
    put(0x1003C, 0x000B); put(0x1003E, 0x0009)
    put(0x10040, 0xD300 | ((0x10048 - ((0x10040 + 4) & ~3)) // 4))
    put(0x10042, 0x000B); put(0x10044, 0x0009)
    blob = bytes(b)
    return Mem([(base, blob)]), [(base, blob)]


def selftest():
    import sh4xref
    fails = 0

    def check(label, got, want):
        nonlocal fails
        ok = got == want
        fails += not ok
        print("%s %s: got %r want %r" % ("ok  " if ok else "FAIL", label, got, want))

    mem, segs = _synthetic()
    words = pool_words_in(segs, DEBUG_SCIF, DEBUG_SCIF + 0x1000)
    check("window pool words", words, [(0x10048, 0xFFE46010)])
    check("decoy outside window", pool_words_in(segs, 0xFFE47000, 0xFFE47004), [(0x1004C, 0xFFE47000)])
    check("window load", pool_loads(mem, 0x10048), [(0x10040, 3)])
    sites = callers(mem, segs, 0x10040)
    check("writer callers", sites, [(0x10008, "pool"), (0x10012, "bsr")])
    check("no caller", callers(mem, segs, 0x10010), [])

    def fn_of(va):
        return sh4xref.function_start(mem, va)

    chain = caller_chain(mem, segs, fn_of, 0x10040, 2)
    check("chain level 0 has two sites", sum(" L0 " in l for l in chain), 2)
    check("chain finds fn A and fn B",
          sorted(l.split("fn ")[1] for l in chain if " L0 " in l), ["0x00010004", "0x00010010"])
    check("chain level 1 ends", all("no static caller" in l for l in chain if " L1 " in l), True)

    blob = build_shim(0x8F000000, BANNER_EU2011, WRITER_EU2011)
    check("shim length", len(blob), 20)
    shm = Mem([(0x8F000000, blob)])
    check("shim lit0 via decoder", movl_pc_target(0x8F000000, shm.u16(0x8F000000)), (4, 0x8F00000C))
    check("shim lit1 via decoder", movl_pc_target(0x8F000002, shm.u16(0x8F000002)), (1, 0x8F000010))
    check("shim r4 value", shm.u32(0x8F00000C), BANNER_EU2011)
    check("shim writer value", shm.u32(0x8F000010), WRITER_EU2011)
    check("shim jsr @r1", jsr_reg(shm.u16(0x8F000004)), ("jsr", 1))
    check("shim spins", bsr_target(0x8F000008, 0xBFFE), 0x8F000008)
    text = disasm_shim(blob, 0x8F000000)
    check("shim disasm bra self", "bra 0x8f000008" in text[4], True)
    try:
        build_shim(0x8F000002, 0, 0)
        check("misaligned base refused", False, True)
    except ValueError:
        check("misaligned base refused", True, True)

    log = b"junk\r\nWindows CE Kernel for Hitachi SH Built on X\r\nSH-4 Kernel\r\n"
    hits = scan_log(log)
    check("banner present", hits[BANNER_LINES[0]], 1)
    check("other line", hits[b"SH-4 Kernel"], 1)
    check("empty log has no banner", any(scan_log(b"")[s] for s in BANNER_LINES), False)
    # UTF-16 text is not what the writer emits (mov.b of the low byte), so a
    # wide-char log must not count as a banner.
    wide = "Windows CE Kernel for Hitachi SH".encode("utf-16le")
    check("utf-16 log is not a banner", scan_log(wide)[BANNER_LINES[0]], 0)

    ser = serial_lines(b"\r\nWindows CE Kernel\r\nSH-4 Kernel\r\nA\r\n\r\nB\nlong" + b"x" * 300 + b"\n")
    check("serial lines", ser[:4], ["Windows CE Kernel", "SH-4 Kernel", "A", "B"])
    dlog = ("   0.010 0x880404f4 pr=0xa8010420 r4=0x88001060 Windows CE Kernel\n"
            "   0.011 0x880404f4 pr=0xa8010428 r4=0x88001044 SH-4 Kernel\n"
            "   0.012 0x880404f4 pr=0x88000000 r4=0x88000000 A |  | B\n"
            "   0.013 0x880404f4 pr=0x88000000 r4=0x88000000 long" + "x" * 252 + "\n"
            "word 0x89e41888: 0x00000001\nhook hits: 4\n")
    dbg = dbgmsg_lines(dlog)
    check("dbgmsg lines", dbg[:4], ["Windows CE Kernel", "SH-4 Kernel", "A", "B"])
    check("dbgmsg tail skipped", len(dbg), 5)
    same, trunc, diffs = compare_lines(ser, dbg, 5)
    check("compare equal+truncated", (same, trunc, len(diffs)), (4, 1, 0))
    same, trunc, diffs = compare_lines(ser, ["Windows CE Kernel", "SH-4 Kernel!"], 2)
    check("compare finds a difference (negative)", (same, len(diffs)), (1, 1))
    check("compare: empty serial differs", len(compare_lines([], dbg, 2)[2]), 2)
    check("continuation line joins", dbgmsg_lines(
        "   1.000 0x880404f4 pr=0x0 r4=0x0 x\ny\n".replace("pr=0x0 r4=0x0", "pr=0x00000000 r4=0x00000000")),
        ["x", "y"])

    # Socket framing of M8.H1 peer control channels: pure encoding, stream
    # reassembly, and two real AF_UNIX socket pairs (positive and negative).
    check("frame bytes", frame_bytes(b"\x10\x02"), b"\x00\x00\x00\x02\x10\x02")
    check("frame empty", frame_bytes(b""), b"\x00\x00\x00\x00")
    stream = frame_bytes(b"ab") + frame_bytes(b"") + frame_bytes(b"xyz")[:6]
    msgs, tail = frames_in(stream)
    check("frames in stream", msgs, [b"ab", b""])
    check("frames leaves partial tail", tail, frame_bytes(b"xyz")[:6])
    try:
        frame_bytes(b"x" * (FRAME_MAX + 1))
        check("oversize send refused", False, True)
    except ValueError:
        check("oversize send refused", True, True)
    try:
        frames_in(struct.pack(">I", FRAME_MAX + 1))
        check("oversize receive refused", False, True)
    except ValueError:
        check("oversize receive refused", True, True)

    class OneByteSocket:
        def __init__(self, data):
            self.data = data

        def recv(self, n):
            b, self.data = self.data[:1], self.data[1:]
            return b

    check("recv_exact loops short reads",
          recv_exact(OneByteSocket(b"abcdef"), 6), b"abcdef")
    try:
        recv_exact(OneByteSocket(b"ab"), 4)
        check("truncated read is an error", False, True)
    except EOFError:
        check("truncated read is an error", True, True)

    a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        send_frame(a, b"gps 52.23 21.01")
        check("socket frame round-trip", recv_frame(b), b"gps 52.23 21.01")
        a.sendall(frame_bytes(b"x")[:3])
        b.close()
        try:
            recv_frame(a)
            check("short framed peer is an error", False, True)
        except (EOFError, OSError):
            check("short framed peer is an error", True, True)
    finally:
        a.close()
        b.close()

    print("selftest: %s (%d failure(s))" % ("PASS" if not fails else "FAIL", fails))
    return 1 if fails else 0


def _int(s):
    return int(s, 0)


def _window(s):
    a, _, b = s.partition(":")
    return int(a, 0), int(b or "0x1000", 0)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("refs")
    r.add_argument("image")
    r.add_argument("--image-start", type=_int, default=NK_IMAGE_START)
    r.add_argument("--module", default="nk.exe")
    r.add_argument("--window", type=_window, default=(DEBUG_SCIF, 0x1000))
    r.add_argument("--writer", type=_int, default=WRITER_EU2011)
    r.add_argument("--depth", type=int, default=3)
    s = sub.add_parser("shim")
    s.add_argument("-o", "--out", required=True)
    s.add_argument("--base", type=_int, default=0x8F000000)
    s.add_argument("--string", type=_int, default=BANNER_EU2011)
    s.add_argument("--writer", type=_int, default=WRITER_EU2011)
    b = sub.add_parser("banner")
    b.add_argument("log")
    c = sub.add_parser("dbgcmp")
    c.add_argument("serial")
    c.add_argument("dbglog")
    c.add_argument("--lines", type=int, default=200)
    c.add_argument("--max-chars", type=int, default=256,
                   help="ze0_dbgmsg.py --max-len in UTF-16 units (default 512 bytes = 256)")
    p = sub.add_parser("peer")
    p.add_argument("path", help="AF_UNIX socket of a --serial-peer chardev")
    p.add_argument("--listen", action="store_true",
                   help="bind and wait for the guest instead of connecting")
    p.add_argument("--send-hex", default="", help="raw bytes to write to the guest")
    p.add_argument("--expect-hex", default="", help="bytes that must come back")
    p.add_argument("--count", type=int, default=0,
                   help="bytes to read (default: len(--expect-hex) or 64)")
    p.add_argument("--nowait", action="store_true",
                   help="send and return without reading a reply")
    p.add_argument("--timeout", type=float, default=10.0)
    m = sub.add_parser("hmp")
    m.add_argument("sock", help="HMP unix socket of run.sh")
    m.add_argument("command", help="one monitor command")
    m.add_argument("--timeout", type=float, default=10.0)
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "refs":
        return cmd_refs(args)
    if args.cmd == "shim":
        return cmd_shim(args)
    if args.cmd == "banner":
        return cmd_banner(args)
    if args.cmd == "dbgcmp":
        return cmd_dbgcmp(args)
    if args.cmd == "peer":
        return cmd_peer(args)
    if args.cmd == "hmp":
        return cmd_hmp(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
