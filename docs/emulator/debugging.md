# Debugging the head-unit firmware under QEMU

How the firmware is debugged in this project: what connects to what, and
the commands. It assumes the emulator from [README.md](README.md) is built
(`QEMU=…/qemu-system-sh4`). The worked example is M8.C1q, which found why
Navi.exe did not start on the unit's own kernel
([EXP-2026-11-22-M8.C1q-navi-on-nk1](../experiments/EXP-2026-11-22-M8.C1q-navi-on-nk1.md)).

## What connects to what

```
                    ┌──────────── QEMU -M ze0 (SH-4, Windows CE) ────────────┐
 gdb / ze0_gdb.py ──┤ -gdb tcp::1240        gdbstub: break, step, regs, mem │
 ze0_gdb.py xp,   ──┤ -monitor unix:SOCK    HMP: xp (physical memory),      │
 ze0_screenshot.py  │                       info registers, pmemsave, stop  │
 serial.log  ◄──────┤ -serial file:…        debug SCIF: the kernel's debug  │
                    │   + dbgmsg=ADDR       text (RETAILMSG/NKDbgPrintf)    │
                    └─────────────────────────────────────────────────────────┘
 static side: cerom.py (ROM map), sh4dis.py (disassembly), sh4xref.py (xrefs)
```

Three channels, used together:

1. **Debug text** (`-serial file:serial.log` and `dbgmsg=`): what the
   firmware prints. It is the cheapest channel and comes first. `dbgmsg=` is
   the address of the kernel's debug-string routine (kernel B `0x880404f4`,
   NK1 `0x880404c4`). **NK1's log prints the SD card password; never commit a
   serial log.**
2. **HMP monitor** (`-monitor unix:SOCK,server,nowait`): reads physical
   memory at any time without stopping the guest. Good for counters and
   kernel structures (`xp`), for "where is the CPU spinning" (`info
   registers` sampled 20 times), and for screenshots.
3. **gdbstub** (`-gdb tcp::1240`, add `-S` to stop at the first
   instruction): breakpoints, watchpoints, single steps, registers.

## Start a run under the debugger

```bash
D=…/dumps          # Marek's unit flash dump, never in the repo
W=$(git rev-parse --show-toplevel)
python3 $W/tools/ze0_ipl.py patch CARD.img -o ipl.txt --nk $W/firmware/unit-flash/nk1-QY7200ND.bin
$QEMU -M ze0,dbgmsg=0x880404c4,nk=$W/firmware/unit-flash/nk1-QY7200ND.bin,ipl-patch=ipl.txt,flash=$D/nand.bin \
  -kernel CARD.img \
  -drive if=sd,index=0,id=sd0,file=CARD.img,format=raw,snapshot=on \
  -icount shift=0,sleep=off -nographic \
  -serial file:serial.log -monitor unix:mon.sock,server,nowait \
  -gdb tcp::1240 -S
```

With `-S` the guest waits for the debugger. Without `-gdb … -S` the same
line just runs (as in README.md). For the kernel-B setup (card kernel), use
the `ze0_ipl.py` line from the README and `dbgmsg=0x880404f4`.

## With gdb

A host gdb that knows SH-4 (`gdb-multiarch` on Debian/Ubuntu/Fedora):

```bash
gdb-multiarch -q \
  -ex 'set architecture sh4' -ex 'set endian little' \
  -ex 'target remote 127.0.0.1:1240' \
  -ex 'source tools/qemu-ze0/gdb-ze0.py'      # adds `ze0-threads`
```

Useful commands for this firmware:

| Goal | gdb |
| --- | --- |
| stop at a function | `hbreak *0x03e4bef4` or `break *0x03e4bef4` |
| print the image name passed in r4 (UTF-16) | `x/20hx $r4` (or `p (wchar_t*)$r4` with a wchar type) |
| continue past a breakpoint | `delete N` then `stepi` then re-add, see the trap below |
| watch a kernel variable | `watch *(int*)0x89e41b10` |
| registers | `info registers` (r0–r15, pc, pr, sr) |
| CE threads and the module behind each PC | `ze0-threads` (needs `memmap.json` from `cerom.py memmap`) |
| step one instruction | `stepi`, `x/8i $pc` |

## Without gdb: `tools/ze0_gdb.py`

The project's sandbox has no SH-4 gdb, so M8.C1q used a small client of the
same protocol. It works anywhere with Python 3:

```bash
python3 tools/ze0_gdb.py regs                                # stop once, print registers
python3 tools/ze0_gdb.py break 0x03e4bef4 --name-reg 4 --seconds 300
#   each hit: time, pc, pr, r0-r15, name=\windows\Navi.exe
python3 tools/ze0_gdb.py break 0x88026c1c,0x88026c26 --seconds 120
python3 tools/ze0_gdb.py watch 0x89e41b10 --min-delta 100    # slow: every write stops the guest
python3 tools/ze0_gdb.py xp --monitor mon.sock 0x89e41b00 32 # physical read through HMP
```

For anything more (arm breakpoints only after another one, single-step a
whole call and log every PC), import it:

```python
import sys; sys.path.insert(0, "tools"); import ze0_gdb
g = ze0_gdb.Gdb(1240); g.pkt("?")
g.pkt("Z0,%x,2" % 0x03e4bef4)          # breakpoint
g.cont(); r = g.regs()                 # r[16] = pc, r[17] = pr
g.step_over("0", r[16])                # remove, stepi, re-insert
```

## HMP monitor by hand

```bash
socat - UNIX-CONNECT:mon.sock          # or: python3 tools/ze0_gdb.py xp …
(qemu) xp /8wx 0x09e41b00              # physical = P1 address & 0x1fffffff
(qemu) info registers                  # sample 20× to find a spinning thread
(qemu) stop / cont
(qemu) pmemsave 0x0e700000 0x1860000 "vram.bin"
```

Screenshots: `python3 tools/ze0_screenshot.py screen --monitor mon.sock -o screen.png`.

## Addresses worth knowing (EU 2011 kernel B and NK1 share these)

| What | Address |
| --- | --- |
| KData (kernel data page) | P1 `0x89e41800` (phys `0x09e41800`), user view `0x5800` |
| current thread | KData `+0x94` (user `0x5894`) |
| thread LastError | THREAD `+0x38` |
| page-free count | KData `+0x310` (phys `0x09e41b10`) |
| memory info (sections) | pointer at KData `+0x320`; NK1 boot log lists `[0]` `0x89e74000`, `[1]` `0x90000000` |
| boot type | `0x89e43c8c` (low nibble) |
| `GetLastError` in coredll (kernel B run) | `0x3fac6f0` (call it by setting pc/pr) |
| NK1 AppLaunch `CreateProcessW` call | `0x03e4bef4` (name in r4), return `0x03e4bef8` |

Find the rest statically:

```bash
python3 tools/cerom.py --image-start 0 firmware/unit-flash/nk1-QY7200ND.bin memmap > memmap.json
python3 tools/qemu-ze0/gdb-ze0.py --memmap memmap.json --pc 0x8804a7da   # which module/section
python3 - <<'EOF'
import sys; sys.path.insert(0, "tools"); import sh4dis
mem = sh4dis.load_segments("firmware/unit-flash/nk1-QY7200ND.bin", 0, "nk.exe")
mem = mem[0] if isinstance(mem, tuple) else mem
for i in sh4dis.disasm(mem, 0x8804a878, 40): print(sh4dis.fmt(i))
EOF
```

## Traps

- **The breakpoint fires again after `c`.** QEMU's sh4 gdbstub stops on the
  same breakpoint again. Remove it, `stepi`, re-insert (`step_over`), or hit
  counts are wrong.
- **P1 reads fail in user mode.** When the guest is stopped in a user
  thread, `m 0x89e41b10,4` returns `E14`. Breakpoints on P1 still work
  (TCG matches the PC). Read kernel memory with HMP `xp` and the physical
  address.
- **Old QEMU holds the port.** `Failed to find an available port`, or a
  `T02` reply and a broken pipe: `pkill -f qemu-system-sh4` first.
- **Single-stepping goes through interrupts.** A step can land in the
  exception vector (`0x8801xxxx`) and the timer. Filter the trace by the
  address range of the function you care about.
- **A watch stop names the watchpoint, not the access.** The `T05…rwatch:ADDR`
  reply carries the start of the watched range, and pc is already past the
  load. Recompute the address from the load at pc-2 and the registers
  (`tools/ze0_sec2_watch.py decode` does this). Kill a client only after it
  removed its `Z3`s, or the next client gets a stale stop first (`watch`
  drains it).
- **Watchpoints are slow.** A watch on a busy counter stops the guest on
  every write; the boot then takes hours. Prefer a breakpoint on the code
  that writes it.
- **Timing differs from the unit.** `-icount shift=0,sleep=off` makes runs
  repeatable, but threads race differently than on the hardware (M8.C1q was
  such a race).
- **Logs and dumps stay out of git.** Serial logs (card password), the flash
  dump, screenshots (vendor map data).
