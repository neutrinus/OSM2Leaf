#!/usr/bin/env python3
"""Let the screen state machine leave ``INI_STARTUP`` on ``-M ze0`` (M8.C1n).

Why the UI stays in ``INI_STARTUP``
-----------------------------------
``ScreenStateCC.dll`` (card ROM image A) leaves ``INI_STARTUP`` on the
event ``SS_JON_TRANSITION_LAST_SCREEN``.  Its handler asks SystemCC for the
last screen (``GET_LAST_SCREEN_KIND``) and on ``SYSTEM_CC_FNR_LAST_SCREEN_MAP``
moves to ``MAP_RELAY``.  ``SS_JON_TRANSITION_LAST_SCREEN`` is a *composite*
("join") event.  The state calls ``State::ExecuteCompositeEvent(id, 2, a, b)``
from its event path, and the event fires only after both ``a`` =
``ANTITHEFT_CC_NTF_COMP_OK`` and ``b`` = ``NOTICE_AUDIO_SOURCE`` have
arrived.  On the emulator the anti-theft app sends ``COMP_OK`` (about 120 s
of guest time, after AppLaunch's 60 s module wait).  ``NOTICE_AUDIO_SOURCE``
never comes: ScreenStateCC raises it only after it sets
``VAR_CURRENT_AUDIO_SOURCE``, on an audio-source change from SystemCC.  That
change needs the audio side, i.e. the audio micom on ``SCI1:``, which is
not modelled (M8.H45).  Record:
``docs/experiments/EXP-2026-11-23-M8.C1n-ini-startup-join.md``.

What this tool does
-------------------
It finds every call site ``mov #a,r7; mov.w id,r5; mov #2,r6; mov.l
thunk,r2; jsr @r2`` in ScreenStateCC's code and turns the count 2 into 1
(``e602`` -> ``e601``), so the join fires on ``COMP_OK`` alone.  The bytes
are an emulator-only patch.  They are not written to the card.  NK1 loads
ROM image A from the card itself, so an IPL patch line is overwritten.  The
tool therefore writes the bytes through the gdb stub: it breaks on each
site's ``jsr``, sets ``r6 = 1`` for that call, writes ``e601`` over every
site through its code VA (the stop is in the ScreenState process, in user
mode, where the gdb stub cannot reach P1 addresses; the debug write goes to
the physical page of NK1's RAM copy of image A), and detaches once a later hit finds
the bytes still in place (NK1's copy of image A has then passed them).

Usage::

    ze0_uistart.py find CARD.img                # list the sites, no QEMU
    ze0_uistart.py run CARD.img --port 1240     # attach, patch, detach
    ze0_uistart.py run CARD.img --port 1240 --touch-unlock   # then also touch
    ze0_uistart.py --selftest

Touch
-----
Leaving ``INI_STARTUP`` is not enough for touch.  ``kepdrv.dll`` starts with
its key guard ``m_byKeyGuardAllKey = 0xf1`` and drops every touch while the
low nibble is set.  The guard is cleared by ``CApi_AntitheftUnlock``
(``commondll.dll``, IOCTL ``0x801f2028``), which Audio.exe and the system
components call on the audio path, so it is also missing on the emulator.
``--touch-unlock`` keeps a breakpoint on NK1's ``IsKeyControlNotify`` after
the join patch and writes 0 to the guard byte at the first touch, which
then passes.  It holds the gdb stub until that touch.

Touch coordinates are Y-flipped by the firmware (``docs/firmware/touch.md``
section 4): a button at screen (x, y) takes ``tap x 480-y`` on ``panel.ctl``.

``tools/ze0_launch.py --ui-start`` runs ``run --touch-unlock`` for you (it
needs ``--gdb``).
"""
from __future__ import annotations

import argparse
import mmap
import os
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cerom import CERom  # noqa: E402

APP_OFF = 0x200200          # card ROM image A (NB00 + 0x200 header)
MODULE = "ScreenStateCC.dll"
MOV_R6_2, MOV_R6_1 = 0xE602, 0xE601
MAX_SITES = 4

# NK1 kepdrv.dll (vbase 0x03d20000): IsKeyControlNotify and the key-guard byte.
# kepdrv's constructor sets m_byKeyGuardAllKey (object +0xc5) to 0xf1; for touch
# IsKeyControlNotify drops the event while (obj[+0xc4] | obj[+0xc5]) & 0x0f is
# nonzero.  CApi_AntitheftUnlock (commondll.dll, called by Audio.exe, SystemEXE,
# SystemCC, CameraCC, AvCCWrapper) writes it through IOCTL 0x801f2028; on the
# emulator nobody calls it (EXP-2026-11-23-M8.C1n-ini-startup-join).
NK1_SHA256 = "b4b3542bb95d336c55ed11e1a4854be2c5f3dce1b60e074629d2b185f3b9fb00"
NK1_IS_KEY_CONTROL_NOTIFY = 0x03D27344
NK1_IS_KEY_CONTROL_PROLOGUE = bytes.fromhex("862f962fa62fb62fc62fd62f224ff07f")
NK1_KEPDRV_TEXT = (0x03D21000, 0x001DA000)      # realaddr, file offset of .text
KEY_GUARD_OFF = 0xC5


def find_sites(text: bytes, base: int) -> list[dict]:
    """Return the join call sites in ``text`` (code bytes at VA ``base``).

    Pattern (5 halfwords, little-endian): ``mov #a,r7`` (e7xx), ``mov.w
    @(d,pc),r5`` (95xx), ``mov #2,r6`` (e602), ``mov.l @(d,pc),r2`` (d2xx),
    ``jsr @r2`` (420b).  The sites must agree on ``a``, the event id and the
    called thunk; otherwise the pattern is not the one this tool knows.
    """
    h = lambda o: struct.unpack_from("<H", text, o)[0]  # noqa: E731
    sites = []
    for o in range(0, len(text) - 10, 2):
        w = [h(o + 2 * k) for k in range(5)]
        if (w[0] >> 8) == 0xE7 and (w[1] >> 8) == 0x95 and w[2] == MOV_R6_2 \
                and (w[3] >> 8) == 0xD2 and w[4] == 0x420B:
            ev_at = o + 2 + 4 + (w[1] & 0xFF) * 2
            lit_at = ((o + 6 + 4) & ~3) + (w[3] & 0xFF) * 4
            if ev_at + 2 > len(text) or lit_at + 4 > len(text):
                continue
            sites.append(dict(va=base + o, count_va=base + o + 4, jsr_va=base + o + 8,
                              first=w[0] & 0xFF, event=h(ev_at),
                              thunk=struct.unpack_from("<I", text, lit_at)[0]))
    keys = {(s["first"], s["event"], s["thunk"]) for s in sites}
    if not sites:
        raise SystemExit("ze0_uistart: no join site found in %s" % MODULE)
    if len(keys) != 1 or len(sites) > MAX_SITES:
        raise SystemExit("ze0_uistart: %d sites with %d different (a, id, thunk); refusing"
                         % (len(sites), len(keys)))
    return sites


def code_section(rom: CERom, name: str = MODULE):
    """(text bytes, realaddr VA, dataptr VA) of the module's first section."""
    mod = rom.module(name)
    sec = next(rom.o32(mod))
    if sec["flags"] & 0x2000:
        raise SystemExit("ze0_uistart: %s code section is compressed" % name)
    off = rom.va2file(sec["dataptr"])
    return rom.d[off:off + sec["vsize"]], sec["realaddr"], sec["dataptr"]


def load(card: str):
    f = open(card, "rb")
    data = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    rom = CERom(data, APP_OFF)
    text, real, dataptr = code_section(rom)
    sites = find_sites(text, real)
    for s in sites:
        s["p1"] = dataptr + (s["count_va"] - real)   # ROM copy in RAM, P1 (cached)
    return sites


def cmd_find(a) -> int:
    for s in load(a.card):
        print("site 0x%08x: ExecuteCompositeEvent(id %d, 2, %d, ...) via 0x%08x; "
              "count at 0x%08x (P1 0x%08x)"
              % (s["va"], s["event"], s["first"], s["thunk"], s["count_va"], s["p1"]))
    return 0


def cmd_run(a) -> int:
    """Hold breakpoints on every site's ``jsr`` until the patch survives.

    NK1 copies ROM image A from the card into RAM while the system already
    runs from the copy the IPL made, so a write made too early is
    overwritten by identical card bytes (seen in run S4 of the EXP).  On
    each hit the tool sets ``r6 = 1`` for that call and writes ``e601`` over
    every site; it detaches at the first hit that finds the bytes still
    written, i.e. after the copy has passed them.
    """
    from ze0_gdb import Gdb, PC
    sites = load(a.card)
    g = Gdb(a.port)
    g.pkt("?")
    jsrs = {s["jsr_va"] for s in sites}
    for j in jsrs:
        g.pkt("Z0,%x,2" % j)
    t0 = time.time()
    hits = 0
    survived = False

    def read(va):
        try:
            return struct.unpack("<H", g.mem(va, 2))[0]
        except OSError:
            return None     # page not mapped in this process right now

    try:
        while time.time() - t0 < a.seconds:
            if g.cont(max(1, a.seconds - (time.time() - t0))) is None:
                break
            r = g.regs()
            if r[PC] not in jsrs:
                continue
            hits += 1
            here = next(s for s in sites if s["jsr_va"] == r[PC])
            if read(here["count_va"]) == MOV_R6_1:
                survived = True
                print("%.1f s: hit %d at 0x%08x, patch still in place; detaching"
                      % (time.time() - t0, hits, r[PC]), flush=True)
                break
            g.pkt("P6=01000000")
            done = []
            for s in sites:
                if read(s["count_va"]) is None:
                    continue
                g.pkt("M%x,2:%02x%02x" % (s["count_va"], MOV_R6_1 & 0xFF, MOV_R6_1 >> 8))
                if read(s["count_va"]) == MOV_R6_1:
                    done.append("0x%08x" % s["count_va"])
            print("%.1f s: hit %d at 0x%08x: r6 := 1; e601 written at %s"
                  % (time.time() - t0, hits, r[PC], ", ".join(done) or "no site"), flush=True)
            g.step_over("0", r[PC])
    finally:
        for j in jsrs:
            g.pkt("z0,%x,2" % j)
        g.pkt("D")
    return 0 if survived else 1


def check_nk1(path: str) -> None:
    import hashlib
    data = open(path, "rb").read()
    if hashlib.sha256(data).hexdigest() != NK1_SHA256:
        raise SystemExit("ze0_uistart: --touch-unlock knows only NK1 %s" % NK1_SHA256[:16])
    off = NK1_KEPDRV_TEXT[1] + NK1_IS_KEY_CONTROL_NOTIFY - NK1_KEPDRV_TEXT[0]
    if data[off:off + 16] != NK1_IS_KEY_CONTROL_PROLOGUE:
        raise SystemExit("ze0_uistart: IsKeyControlNotify prologue differs")


def touch_unlock(a) -> int:
    """Clear kepdrv's key guard at the first touch that reaches IsKeyControlNotify."""
    from ze0_gdb import Gdb, PC
    g = Gdb(a.port)
    g.pkt("?")
    bp = NK1_IS_KEY_CONTROL_NOTIFY
    g.pkt("Z0,%x,2" % bp)
    t0 = time.time()
    ok = False
    try:
        while time.time() - t0 < a.seconds:
            if g.cont(max(1, a.seconds - (time.time() - t0))) is None:
                break
            r = g.regs()
            if r[PC] != bp:
                continue
            obj = r[4]
            before = g.mem(obj + 0xC4, 2)
            g.pkt("M%x,1:00" % (obj + KEY_GUARD_OFF))
            after = g.mem(obj + 0xC4, 2)
            print("%.1f s: kepdrv object 0x%08x key control/guard %s -> %s (touch unlocked)"
                  % (time.time() - t0, obj, before.hex(), after.hex()), flush=True)
            ok = after[1] == 0
            break
    finally:
        g.pkt("z0,%x,2" % bp)
        g.pkt("D")
    return 0 if ok else 1


def selftest() -> int:
    fails = 0

    def check(label, got, want):
        nonlocal fails
        ok = got == want
        fails += not ok
        print("%s %s: got %r want %r" % ("ok  " if ok else "FAIL", label, got, want))

    # one site at 0x100: mov #41,r7; mov.w @(+N),r5; mov #2,r6; mov.l @(..),r2; jsr @r2;
    # nop; then the literal pool: event 0x0cc1 and thunk 0x02c66bd0
    code = bytearray(0x200)
    o = 0x100
    words = [0xE729, 0x9504, MOV_R6_2, 0xD202, 0x420B, 0x0009]
    for k, w in enumerate(words):
        struct.pack_into("<H", code, o + 2 * k, w)
    struct.pack_into("<H", code, o + 2 + 4 + 4 * 2, 0x0CC1)          # mov.w target
    struct.pack_into("<I", code, ((o + 6 + 4) & ~3) + 2 * 4, 0x02C66BD0)  # mov.l target
    s = find_sites(bytes(code), 0x02A71000)
    check("one site", len(s), 1)
    check("site VA", s[0]["va"], 0x02A71100)
    check("count VA", s[0]["count_va"], 0x02A71104)
    check("jsr VA", s[0]["jsr_va"], 0x02A71108)
    check("event id", s[0]["event"], 0x0CC1)
    check("first event", s[0]["first"], 41)
    check("thunk", s[0]["thunk"], 0x02C66BD0)
    # negative: mov #3,r6 is not the 2-event join
    bad = bytearray(code)
    struct.pack_into("<H", bad, o + 4, 0xE603)
    try:
        find_sites(bytes(bad), 0x02A71000)
        check("no site refused", "accepted", "refused")
    except SystemExit:
        check("no site refused", "refused", "refused")
    # negative: two sites that disagree on the event are refused
    two = bytearray(code) + bytearray(code)
    struct.pack_into("<H", two, 0x200 + o + 2 + 4 + 4 * 2, 0x0CC2)
    try:
        find_sites(bytes(two), 0x02A71000)
        check("mixed sites refused", "accepted", "refused")
    except SystemExit:
        check("mixed sites refused", "refused", "refused")
    nk = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "firmware", "unit-flash", "nk1-QY7200ND.bin")
    if os.path.exists(nk):
        try:
            check_nk1(nk)
            check("NK1 IsKeyControlNotify prologue", "match", "match")
        except SystemExit as exc:
            check("NK1 IsKeyControlNotify prologue", str(exc), "match")
    print("selftest: %s (%d failure(s))" % ("PASS" if not fails else "FAIL", fails))
    return 1 if fails else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    f = sub.add_parser("find", help="list the join sites in the card's ScreenStateCC.dll")
    f.add_argument("card")
    r = sub.add_parser("run", help="attach to the gdb stub and patch the join count")
    r.add_argument("card")
    r.add_argument("--port", type=int, default=1240)
    r.add_argument("--seconds", type=float, default=1800)
    r.add_argument("--touch-unlock", action="store_true",
                   help="then clear kepdrv's key guard (NK1 only) at the first touch")
    r.add_argument("--nk", default=os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "firmware", "unit-flash", "nk1-QY7200ND.bin"))
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.cmd == "find":
        return cmd_find(a)
    if a.cmd == "run":
        if a.touch_unlock:
            check_nk1(a.nk)
        rc = cmd_run(a)
        if rc == 0 and a.touch_unlock:
            print("waiting for the first touch to clear the key guard", flush=True)
            rc = touch_unlock(a)
        return rc
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
