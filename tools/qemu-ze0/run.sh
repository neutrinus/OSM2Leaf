#!/bin/sh
# Boot the ZE0 CE images under QEMU and leave a trace in a work directory.
#
# TODO M8.A7 (docs/research/full-system-emulation.md, stage F0). This script is
# an orchestrator only: stock QEMU 8.2 with -M none is enough, and -M ze0 is
# picked automatically once tools/qemu-ze0/build.sh (M8.A1) has built a QEMU
# that knows the machine. Nothing here is vendor data and nothing is written
# outside the work directory.
#
# What one command does:
#   1. picks the machine: -M ze0, else -M none -cpu sh7785 -m 512M;
#   2. with --image, cuts the kernel image (B/C) and the application image (A)
#      out of the SD image with `tail | head` and loads them with -device
#      loader, exactly as tools/ce_qemu_probe.py does (the card has no
#      bootloader; the IPL lives in on-board flash). The loader devices are
#      passed for -M ze0 too; when M8.A3 moves the copy into the machine
#      (-kernel), this block becomes the -M none fallback only.
#   3. runs QEMU with -d unimp,guest_errors,int -D WORK/qemu.log, an optional
#      gdbstub (--gdb) and a wall-clock --timeout, then asks the HMP monitor
#      for `info registers` before killing it;
#   4. prints ce_qemu_probe.summarize_log() of the log: the unmodelled register
#      accesses in first-seen order, the CPU exceptions and the final PC;
#   5. prints the gdb command that sources tools/qemu-ze0/gdb-ze0.py, which
#      prints the CE thread list and resolves each PC to a module/section
#      through WORK/memmap.json (written with `cerom.py memmap`).
#
# --dry-run prints the exact command sequence (mkdir, tail|head, qemu), one
# command per line, and writes or starts nothing. It also prints the command
# when QEMU is missing, but exits 0; a real run without QEMU is a hard
# MISSING_QEMU error (exit 3).
#
# Usage: ./run.sh [options]        (see --help)
# Exit codes: 0 ok, 1 runtime failure, 2 usage error, 3 MISSING_QEMU.

set -u

PROG=run.sh
HERE=$(CDPATH= cd "$(dirname "$0")" && pwd) || exit 1
TOOLS_DIR=$(CDPATH= cd "$HERE/.." && pwd) || exit 1
PYTHON=${PYTHON:-python3}

usage() {
  cat <<'EOF'
run.sh -- boot the ZE0 CE images under QEMU and leave a trace in a work dir.

Options:
  --image FILE        CE/SD image to boot (default: none, bare CPU + RAM)
  --kernel OFFSET     kernel image start (default 0x3e00200; C = 0x5200200)
  --app OFFSET        application image start (default 0x200200, 0 = none)
  --kernel-addr ADDR  physical load address (default 0x08000000)
  --app-addr ADDR     physical load address (default 0x0cae1000)
  --entry ADDR        initial PC (default 0x8800ebd0 = nk.exe entry, EXP-37)
  --mem MB            -M none RAM in MiB (default 512)
  --machine WHAT      auto | ze0 | none (default auto)
  --gdb[=PORT]        gdbstub on 127.0.0.1:PORT (default port 1234)
  --stop              add -S: freeze the CPU until gdb continues
  --timeout SECONDS   wall clock, 0 = run until killed (default 10)
  --workdir DIR       output directory (default: a new mktemp -d)
  --log FILE          QEMU -D log (default WORK/qemu.log)
  --qemu PATH         qemu-system-sh4 binary (default: from PATH)
  --no-summary        do not filter the log afterwards
  --memmap FILE       use this memmap JSON instead of writing one from the image
  --no-memmap         do not write WORK/memmap.json with cerom.py
  --dry-run           print the commands, write and start nothing
  -h, --help          this text

Outputs in the work dir: qemu.log (everything -d logged), registers.txt (HMP
`info registers` before the kill, when reachable), memmap.json (VA -> module
and section, from cerom.py), plus kernel.bin/app.bin when --image is given.
EOF
}

die() {
  printf '%s: %s\n' "$PROG" "$*" >&2
  exit 1
}

usage_error() {
  printf '%s: %s\n' "$PROG" "$*" >&2
  printf "Try '%s --help'.\n" "$PROG" >&2
  exit 2
}

info() {
  printf '%s\n' "$*" >&2
}

# Shell-quote one token for the --dry-run transcript (empty -> '').
quote() {
  if [ -z "$1" ]; then
    printf "''"
    return 0
  fi
  case $1 in
    *[!A-Za-z0-9_./:=@%+,-]*)
      _q=$(printf '%s' "$1" | sed "s/'/'\\\\''/g")
      printf "'%s'" "$_q"
      ;;
    *)
      printf '%s' "$1"
      ;;
  esac
}

# A decimal number that is also safe for $(()) as the shell wrote it.
want_int() { # option, value
  case $2 in
    '' | *[!0-9]*)
      usage_error "$1 needs a decimal number, got '$2'"
      ;;
  esac
}

# A hex address or offset, with an optional 0x prefix; 0 stays valid.
want_addr() { # option, value
  case $2 in
    '')
      usage_error "$1 needs an address, got ''"
      ;;
    [0-9]*)
      case $2 in
        *[!0-9a-fA-FxX]*)
          usage_error "$1 needs a hex address, got '$2'"
          ;;
      esac
      ;;
    *)
      usage_error "$1 needs a hex address, got '$2'"
      ;;
  esac
}

qemu_ok() {
  case $QEMU in
    */*) [ -x "$QEMU" ] ;;
    *) command -v "$QEMU" >/dev/null 2>&1 ;;
  esac
}

# Little-endian u32 at a file offset, as decimal (the CE image length).
le32() { # file, offset
  _h=$(od -A n -t x1 -N 4 -j "$2" "$1" 2>/dev/null | tr -d ' \t\n')
  if [ "${#_h}" -ne 8 ]; then
    return 1
  fi
  _b1=$(printf '%s' "$_h" | cut -c1-2)
  _b2=$(printf '%s' "$_h" | cut -c3-4)
  _b3=$(printf '%s' "$_h" | cut -c5-6)
  _b4=$(printf '%s' "$_h" | cut -c7-8)
  printf '%d\n' "$((0x$_b4$_b3$_b2$_b1))"
}

# Cut one CE image out of the SD image, record its loader spec in LOADER_SPEC.
# $1 image, $2 file offset, $3 physical address, $4 output file, $5 label.
# In --dry-run mode the cut is only described, never executed.
load_image() {
  _img=$1
  _off=$2
  _addr=$3
  _out=$4
  _label=$5

  # Positive control before any arithmetic: a CE segment has ECEC at +0x40
  # (AGENTS.md, tools/cerom.py). A wrong --kernel/--app offset fails here
  # instead of silently loading the wrong bytes.
  if ! od -A n -t x1 -N 4 -j "$((_off + 0x40))" "$_img" 2>/dev/null |
      tr -d ' \t\n' | grep -qx 45434543; then
    die "$_label image has no ECEC at 0x$(printf '%x' "$((_off + 0x40))"); wrong --kernel/--app offset?"
  fi

  _len=$(le32 "$_img" "$_off") || die "cannot read a u32 at 0x$(printf '%x' "$_off") in $_img"
  _size=$(wc -c < "$_img" | tr -d ' \t\n')
  if [ "$_len" -le 0 ] || [ "$_len" -gt 268435456 ]; then
    die "$_label image at 0x$(printf '%x' "$_off") claims $_len bytes, not a CE image"
  fi
  if [ "$((_off + _len))" -gt "$_size" ]; then
    die "$_label image 0x$(printf '%x' "$_off")+$_len runs past the $_size-byte image"
  fi

  info "$_label  load 0x$(printf '%08x' "$_addr")..0x$(printf '%08x' "$((_addr + _len))")  ($_len bytes from 0x$(printf '%x' "$_off"), VA 0x$(printf '%08x' "$((_addr + 0x80000000))"))"

  if [ "$DRY_RUN" -eq 1 ]; then
    PREP="$PREP
tail -c +$((_off + 1)) $(quote "$_img") | head -c $_len > $(quote "$_out")"
  else
    tail -c +"$((_off + 1))" "$_img" | head -c "$_len" > "$_out" ||
      die "cannot write $_out"
    _written=$(wc -c < "$_out" | tr -d ' \t\n')
    if [ "$_written" -ne "$_len" ]; then
      die "$_out has $_written bytes, expected $_len"
    fi
  fi

  LOADER_SPEC=$(printf 'loader,file=%s,addr=0x%x,force-raw=on' "$_out" "$_addr")
}

# HMP `info registers` while QEMU still runs; best effort, never fatal.
grab_registers() {
  if [ ! -S "$WORK/hmp.sock" ]; then
    return 0
  fi
  if ! command -v "$PYTHON" >/dev/null 2>&1; then
    return 0
  fi
  "$PYTHON" - "$TOOLS_DIR" "$WORK/hmp.sock" "$WORK/registers.txt" <<'PY' 2>/dev/null
import sys

sys.path.insert(0, sys.argv[1])
import ce_qemu_probe

text = ce_qemu_probe.hmp(sys.argv[2], "info registers")
with open(sys.argv[3], "w", encoding="utf-8", errors="replace") as handle:
    handle.write(text)
PY
  return 0
}

# The log filter: ce_qemu_probe.summarize_log() plus the final PC.
summarize() {
  if [ ! -f "$LOG" ]; then
    info "$PROG: no log at $LOG (did QEMU start?)"
    return 0
  fi
  if [ ! -s "$LOG" ]; then
    info "$PROG: log $LOG is empty (nothing was logged)"
    return 0
  fi
  if ! command -v "$PYTHON" >/dev/null 2>&1; then
    info "$PROG: cannot summarize $LOG: $PYTHON not found"
    return 0
  fi
  "$PYTHON" - "$TOOLS_DIR" "$LOG" "$WORK/registers.txt" <<'PY'
import os
import re
import sys

sys.path.insert(0, sys.argv[1])
from ce_qemu_probe import summarize_log

log_path, registers_path = sys.argv[2], sys.argv[3]
with open(log_path, "r", encoding="utf-8", errors="replace") as handle:
    accesses, exceptions = summarize_log(handle.read())

print("unmodelled register accesses (first-seen order): %d" % len(accesses))
for kind, addr in accesses:
    print("  %-5s 0x%08x" % (kind, addr))
print("exceptions: %d" % len(exceptions))
for code, name, pc in exceptions:
    print("  0x%03x %-20s pc=%s" % (code, name, "0x%08x" % pc if pc is not None else "?"))

if os.path.exists(registers_path):
    with open(registers_path, "r", encoding="utf-8", errors="replace") as handle:
        text = handle.read()
    match = re.search(r"\bpc=0x([0-9a-fA-F]+)", text)
    print("final pc: %s" % ("0x" + match.group(1) if match else "unknown"))
PY
}

# ---------------------------------------------------------------------------
# Arguments
# ---------------------------------------------------------------------------

IMAGE=
KERNEL_OFF=0x3e00200
APP_OFF=0x200200
KERNEL_ADDR=0x08000000
APP_ADDR=0x0cae1000
ENTRY=0x8800ebd0
MEM=512
MACHINE=auto
GDB=0
GDB_PORT=1234
STOP=0
TIMEOUT=10
WORK=
LOG=
QEMU=qemu-system-sh4
SUMMARY=1
MEMMAP=1
MEMMAP_SRC=
DRY_RUN=0
PREP=
LOADER_SPEC=

while [ "$#" -gt 0 ]; do
  _arg=$1
  _opt=${_arg%%=*}
  _val=
  _hasval=0
  case $_arg in
    *=*)
      _val=${_arg#*=}
      _hasval=1
      ;;
  esac

  case $_opt in
    --image | --kernel | --app | --kernel-addr | --app-addr | --entry | \
    --mem | --machine | --timeout | --workdir | --log | --qemu | --memmap)
      if [ "$_hasval" -eq 0 ]; then
        [ "$#" -ge 2 ] || usage_error "$_opt needs a value"
        _val=$2
        shift
      fi
      shift
      case $_opt in
        --image) IMAGE=$_val ;;
        --kernel) KERNEL_OFF=$_val ;;
        --app) APP_OFF=$_val ;;
        --kernel-addr) KERNEL_ADDR=$_val ;;
        --app-addr) APP_ADDR=$_val ;;
        --entry) ENTRY=$_val ;;
        --mem)
          want_int "$_opt" "$_val"
          MEM=$_val
          ;;
        --machine) MACHINE=$_val ;;
        --timeout)
          want_int "$_opt" "$_val"
          TIMEOUT=$_val
          ;;
        --workdir) WORK=$_val ;;
        --log) LOG=$_val ;;
        --qemu) QEMU=$_val ;;
        --memmap) MEMMAP_SRC=$_val ;;
      esac
      ;;
    --gdb)
      GDB=1
      if [ "$_hasval" -eq 1 ]; then
        want_int "$_opt" "$_val"
        GDB_PORT=$_val
      fi
      shift
      ;;
    --stop)
      STOP=1
      shift
      ;;
    --no-summary)
      SUMMARY=0
      shift
      ;;
    --no-memmap)
      MEMMAP=0
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      usage_error "unknown option: $_arg"
      ;;
  esac
done

case $MACHINE in
  auto | ze0 | none) ;;
  *) usage_error "--machine must be auto, ze0 or none, got '$MACHINE'" ;;
esac

want_addr --kernel "$KERNEL_OFF"
want_addr --app "$APP_OFF"
want_addr --kernel-addr "$KERNEL_ADDR"
want_addr --app-addr "$APP_ADDR"
want_addr --entry "$ENTRY"

KERNEL_OFF=$((KERNEL_OFF))
APP_OFF=$((APP_OFF))
KERNEL_ADDR=$((KERNEL_ADDR))
APP_ADDR=$((APP_ADDR))
ENTRY=$((ENTRY))

if [ -n "$IMAGE" ] && [ ! -f "$IMAGE" ]; then
  die "no such image: $IMAGE"
fi
if [ -n "$MEMMAP_SRC" ] && [ ! -f "$MEMMAP_SRC" ]; then
  die "no such memmap: $MEMMAP_SRC"
fi

# ---------------------------------------------------------------------------
# Machine and work directory
# ---------------------------------------------------------------------------

QEMU_PRESENT=1
if ! qemu_ok; then
  QEMU_PRESENT=0
  printf '%s: MISSING_QEMU: %s not found; build it with tools/qemu-ze0/build.sh (TODO M8.A1) or install qemu-system-misc (Debian/Ubuntu)\n' \
    "$PROG" "$QEMU" >&2
  if [ "$DRY_RUN" -eq 0 ]; then
    exit 3
  fi
fi

if [ "$MACHINE" = auto ]; then
  if [ "$QEMU_PRESENT" -eq 1 ] && "$QEMU" -M help 2>/dev/null | grep -qw ze0; then
    MACHINE=ze0
  else
    MACHINE=none
    if [ "$QEMU_PRESENT" -eq 1 ]; then
      info "$PROG: this QEMU has no -M ze0, falling back to -M none (stock CPU + RAM)"
    fi
  fi
fi

if [ -z "$WORK" ]; then
  if [ "$DRY_RUN" -eq 1 ]; then
    WORK=${TMPDIR:-/tmp}/qemu-ze0.dry-run
  else
    WORK=$(mktemp -d "${TMPDIR:-/tmp}/qemu-ze0.XXXXXX") || die "mktemp failed"
  fi
fi
if [ -z "$LOG" ]; then
  LOG=$WORK/qemu.log
fi

if [ "$DRY_RUN" -eq 0 ]; then
  mkdir -p "$WORK" || die "cannot create $WORK"
fi

# ---------------------------------------------------------------------------
# QEMU command line
# ---------------------------------------------------------------------------

set -- "$QEMU"

if [ "$MACHINE" = ze0 ]; then
  set -- "$@" -M ze0
else
  set -- "$@" -M none -cpu sh7785 -m "${MEM}M"
fi

set -- "$@" -nographic -serial none
set -- "$@" -monitor "unix:$WORK/hmp.sock,server,nowait"

if [ "$GDB" -eq 1 ]; then
  set -- "$@" -gdb "tcp:127.0.0.1:$GDB_PORT"
fi
if [ "$STOP" -eq 1 ]; then
  set -- "$@" -S
fi

set -- "$@" -d unimp,guest_errors,int -D "$LOG"

if [ -n "$IMAGE" ]; then
  load_image "$IMAGE" "$KERNEL_OFF" "$KERNEL_ADDR" "$WORK/kernel.bin" kernel
  set -- "$@" -device "$LOADER_SPEC"
  if [ "$APP_OFF" -ne 0 ]; then
    load_image "$IMAGE" "$APP_OFF" "$APP_ADDR" "$WORK/app.bin" app
    set -- "$@" -device "$LOADER_SPEC"
  fi
  set -- "$@" -device "loader,addr=0x$(printf '%x' "$ENTRY"),cpu-num=0"

fi

if [ -n "$MEMMAP_SRC" ]; then
  if [ "$DRY_RUN" -eq 1 ]; then
    PREP="$PREP
cp $(quote "$MEMMAP_SRC") $(quote "$WORK/memmap.json")"
  else
    cp "$MEMMAP_SRC" "$WORK/memmap.json" || die "cannot copy $MEMMAP_SRC"
    info "memmap $WORK/memmap.json (from $MEMMAP_SRC)"
  fi
elif [ -n "$IMAGE" ] && [ "$MEMMAP" -eq 1 ] && command -v "$PYTHON" >/dev/null 2>&1; then
  if [ "$DRY_RUN" -eq 1 ]; then
    PREP="$PREP
$(quote "$PYTHON") $(quote "$TOOLS_DIR/cerom.py") --image-start $(printf '0x%x' "$KERNEL_OFF") $(quote "$IMAGE") memmap --out $(quote "$WORK/memmap.json") --pretty"
  else
    if "$PYTHON" "$TOOLS_DIR/cerom.py" --image-start "$(printf '0x%x' "$KERNEL_OFF")" "$IMAGE" \
        memmap --out "$WORK/memmap.json" --pretty >/dev/null 2>"$WORK/memmap.err"; then
      info "memmap $WORK/memmap.json"
    else
      info "$PROG: memmap not written (see $WORK/memmap.err); gdb will print raw PCs"
    fi
  fi
fi

# ---------------------------------------------------------------------------
# Dry run: print the transcript and stop
# ---------------------------------------------------------------------------

if [ "$DRY_RUN" -eq 1 ]; then
  printf 'mkdir -p %s\n' "$(quote "$WORK")"
  if [ "$TIMEOUT" -gt 0 ]; then
    printf '# run.sh stops qemu after %ss; log and summary land in %s\n' \
      "$TIMEOUT" "$(quote "$WORK")"
  fi
  if [ -n "$PREP" ]; then
    printf '%s\n' "$PREP" | sed '/^$/d'
  fi
  printf '%s' "$(quote "$QEMU")"
  _first=1
  for _a in "$@"; do
    if [ "$_first" -eq 1 ]; then
      _first=0
      continue
    fi
    printf ' %s' "$(quote "$_a")"
  done
  printf '\n'
  exit 0
fi

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

info "$PROG: $MACHINE machine, log $LOG, timeout ${TIMEOUT}s"
if [ "$GDB" -eq 1 ]; then
  info "$PROG: gdbstub on 127.0.0.1:$GDB_PORT"
fi

QEMU_PID=
TIMED_OUT=0
INTERRUPTED=0

"$@" &
QEMU_PID=$!

# TERM first so QEMU can flush -D, then KILL if it is still alive after 3 s.
stop_qemu() {
  kill "$QEMU_PID" 2>/dev/null
  _n=0
  while [ "$_n" -lt 3 ] && kill -0 "$QEMU_PID" 2>/dev/null; do
    sleep 1
    _n=$((_n + 1))
  done
  if kill -0 "$QEMU_PID" 2>/dev/null; then
    kill -9 "$QEMU_PID" 2>/dev/null
  fi
}

trap 'INTERRUPTED=1; stop_qemu' INT TERM HUP

if [ "$TIMEOUT" -gt 0 ]; then
  _elapsed=0
  while [ "$_elapsed" -lt "$TIMEOUT" ] && kill -0 "$QEMU_PID" 2>/dev/null; do
    sleep 1
    _elapsed=$((_elapsed + 1))
  done
  if kill -0 "$QEMU_PID" 2>/dev/null; then
    TIMED_OUT=1
    grab_registers
    stop_qemu
  fi
fi

wait "$QEMU_PID" 2>/dev/null
STATUS=$?
trap - INT TERM HUP

if [ "$TIMED_OUT" -eq 1 ]; then
  info "$PROG: stopped after ${TIMEOUT}s"
elif [ "$INTERRUPTED" -eq 1 ]; then
  info "$PROG: interrupted"
elif [ "$STATUS" -ne 0 ]; then
  info "$PROG: qemu exited early with status $STATUS"
fi

if [ "$SUMMARY" -eq 1 ]; then
  summarize
fi

printf 'workdir: %s\n' "$WORK"
printf 'log:     %s\n' "$LOG"
if [ -f "$WORK/registers.txt" ]; then
  printf 'regs:    %s\n' "$WORK/registers.txt"
fi
if [ -f "$WORK/memmap.json" ]; then
  printf 'memmap:  %s\n' "$WORK/memmap.json"
fi
if [ "$GDB" -eq 1 ]; then
  printf 'gdb:     gdb-multiarch -q -ex %s -ex %s%s\n' \
    "$(quote "target remote 127.0.0.1:$GDB_PORT")" \
    "$(quote "source $HERE/gdb-ze0.py")" \
    "$(if [ -f "$WORK/memmap.json" ]; then printf ' -ex %s' "$(quote "set \$ze0_memmap=\"$WORK/memmap.json\"")"; fi)"
fi

exit 0
