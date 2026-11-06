#!/usr/bin/env bash
# Build the pinned QEMU with the out-of-tree ze0 machine (Nissan Leaf ZE0).
#
# QEMU is never vendored: the tarball, the source tree and the build tree live
# under --srcdir (default $HOME/.cache/qemu-ze0), outside the repository.  The
# script fetches and SHA-256-verifies the pinned release, applies every
# tools/qemu-ze0/patches/*.patch, configures only the SH-4 system target,
# builds it and finally requires `qemu-system-sh4 -M help` to list `ze0`.
#
# Usage:
#   ./build.sh                    fetch, patch, configure, build, verify
#   ./build.sh --dry-run          print every command; write nothing
#   ./build.sh --jobs 8           parallel make (default: nproc)
#   ./build.sh --force            discard src+build tree and start over
#   ./build.sh --verify-only      only run the `-M ze0` check on --qemu
#   ./build.sh --selftest         offline test of this script (no network)
#   ./build.sh --help             this text
#
# Exit codes: 0 ok · 1 failure · 2 usage · 3 network needed.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SELF="$HERE/$(basename "${BASH_SOURCE[0]}")"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"

# --------------------------------------------------------------------------
# Pin: change only together with README.md and an EXP entry.
# --------------------------------------------------------------------------
QEMU_VERSION="8.2.7"
QEMU_MIN_VERSION="8.2"
QEMU_URL_BASE="https://download.qemu.org"
QEMU_GIT_URL="https://gitlab.com/qemu-project/qemu.git"
QEMU_SHA256="1f0604f296ab9acb4854c054764a1ba408643fc299bd54a6500cccfaaca65b55"
QEMU_TARBALL_BYTES="132676368"

SRCDIR=""
QEMU_BIN=""
JOBS=""
PATCH_DIR="$HERE/patches"
USE_PATCHES=1
VERSION="$QEMU_VERSION"
URL_BASE="$QEMU_URL_BASE"
GIT_URL="$QEMU_GIT_URL"
FROM_GIT=0
FORCE=0
DRY_RUN=0
VERIFY_ONLY=0
SELFTEST=0

usage() {
  cat <<'EOF'
build.sh — build the pinned QEMU with the out-of-tree ze0 SH-4 machine

Usage:
  ./build.sh [options]

Options:
  --srcdir DIR       cache/source/build root (default $HOME/.cache/qemu-ze0);
                     must be outside the repository
  --qemu PATH        qemu-system-sh4 binary to verify
                     (default SRCDIR/build/qemu-system-sh4)
  --jobs N           parallel make jobs (default: nproc)
  --patch-dir DIR    where the local patches live (default tools/qemu-ze0/patches)
  --no-patch         do not apply patches/*.patch
  --version V        QEMU release to build (default 8.2.7, must be >= 8.2)
  --from-git         clone the pinned tag instead of using the release tarball
  --url-base URL     download base (default https://download.qemu.org)
  --force            remove the source and build trees, re-extract, rebuild
  --dry-run          print every command; write nothing, download nothing
  --verify-only      skip fetch/configure/build; check --qemu for -M ze0
  --selftest         offline test of the argument parsing and command plan
  -h, --help         this text

The first run needs network: the pinned tarball is ~127 MiB and the extracted
tree plus build tree need ~2 GiB.  Nothing is downloaded or built by
--dry-run or --selftest.  Exit codes: 0 ok, 1 failure, 2 usage, 3 network.
EOF
}

note() { printf 'build.sh: %s\n' "$*"; }
die() { printf 'build.sh: %s\n' "$*" >&2; exit 1; }
usage_error() { printf 'build.sh: %s\n' "$*" >&2; printf 'Try %s --help\n' "$SELF" >&2; exit 2; }

# run CMD...  — the single place that executes or prints a command.
run() {
  if [ "$DRY_RUN" -eq 1 ]; then
    printf 'dry-run:'
    printf ' %q' "$@"
    printf '\n'
  else
    "$@"
  fi
}

# run_in DIR CMD... — same, with the working directory changed.
run_in() {
  local dir="$1"
  shift
  if [ "$DRY_RUN" -eq 1 ]; then
    printf 'dry-run: (cd %q &&' "$dir"
    printf ' %q' "$@"
    printf ')\n'
  else
    ( cd "$dir" && "$@" )
  fi
}

# version_ge A B — true when A >= B, using sort -V.
version_ge() {
  [ "$1" = "$2" ] && return 0
  [ "$(printf '%s\n%s\n' "$1" "$2" | sort -V | tail -n 1)" = "$1" ]
}

abs_path() {
  if command -v realpath >/dev/null 2>&1; then
    realpath -m "$1"
  else
    ( cd "$1" 2>/dev/null && pwd ) || printf '%s\n' "$1"
  fi
}

network_needed() {
  cat >&2 <<EOF
build.sh: NETWORK NEEDED: cannot fetch $1
build.sh:
build.sh:   tarball: ${URL_BASE}/qemu-${VERSION}.tar.xz
build.sh:   git    : ${GIT_URL} (tag v${VERSION})
build.sh:
build.sh: QEMU is not vendored in this repository, so the first build has to
build.sh: download the pinned source (~127 MiB; source+build need ~2 GiB).
build.sh: Options:
build.sh:   * run this script once on a machine with network access, or
build.sh:   * copy qemu-${VERSION}.tar.xz to ${TARBALL}, or
build.sh:   * clone ${GIT_URL} at tag v${VERSION} and pass --srcdir.
build.sh: Nothing was built and nothing in the repository was changed.
EOF
  exit 3
}

# --------------------------------------------------------------------------
# Argument parsing
# --------------------------------------------------------------------------
while [ $# -gt 0 ]; do
  case "$1" in
    --srcdir)     [ $# -ge 2 ] || usage_error "--srcdir needs a value"; SRCDIR="$2"; shift 2 ;;
    --qemu)       [ $# -ge 2 ] || usage_error "--qemu needs a value"; QEMU_BIN="$2"; shift 2 ;;
    --jobs)       [ $# -ge 2 ] || usage_error "--jobs needs a value"; JOBS="$2"; shift 2 ;;
    --patch-dir)  [ $# -ge 2 ] || usage_error "--patch-dir needs a value"; PATCH_DIR="$2"; shift 2 ;;
    --no-patch)   USE_PATCHES=0; shift ;;
    --version)    [ $# -ge 2 ] || usage_error "--version needs a value"; VERSION="$2"; shift 2 ;;
    --from-git)   FROM_GIT=1; shift ;;
    --url-base)   [ $# -ge 2 ] || usage_error "--url-base needs a value"; URL_BASE="${2%/}"; shift 2 ;;
    --force)      FORCE=1; shift ;;
    --dry-run)    DRY_RUN=1; shift ;;
    --verify-only) VERIFY_ONLY=1; shift ;;
    --selftest)   SELFTEST=1; shift ;;
    -h|--help)    usage; exit 0 ;;
    *)            usage_error "unknown option: $1" ;;
  esac
done

case "$VERSION" in
  ''|*[!0-9.]*|.*|*.) usage_error "bad --version: $VERSION" ;;
esac
version_ge "$VERSION" "$QEMU_MIN_VERSION" \
  || usage_error "QEMU $VERSION is too old; this tree needs >= $QEMU_MIN_VERSION"

if [ -z "$JOBS" ]; then
  JOBS="$(nproc 2>/dev/null || getconf _NPROCESSORS_ONLN 2>/dev/null || echo 2)"
fi
case "$JOBS" in
  ''|*[!0-9]*) usage_error "bad --jobs: $JOBS" ;;
esac
[ "$JOBS" -ge 1 ] || usage_error "--jobs must be >= 1"

if [ -z "$SRCDIR" ]; then
  [ -n "${HOME:-}" ] || usage_error "HOME is unset; pass --srcdir DIR"
  SRCDIR="${XDG_CACHE_HOME:-$HOME/.cache}/qemu-ze0"
fi
SRCDIR="$(abs_path "$SRCDIR")"
TARBALL="$SRCDIR/qemu-$VERSION.tar.xz"
SRC="$SRCDIR/qemu-$VERSION"
BUILD="$SRCDIR/build"
if [ "$FROM_GIT" -eq 1 ]; then
  SRC="$SRCDIR/qemu-git"
fi
if [ -z "$QEMU_BIN" ]; then
  QEMU_BIN="$BUILD/qemu-system-sh4"
fi
QEMU_BIN="$(abs_path "$QEMU_BIN")"

# --------------------------------------------------------------------------
# Refusals (cheap, before any write)
# --------------------------------------------------------------------------
if [ "$SELFTEST" -eq 0 ] && [ "$(id -u)" -eq 0 ]; then
  die "refusing to run as root: QEMU is built and cached as your normal user ($SRCDIR); re-run without sudo"
fi

case "$SRCDIR" in
  /|"${HOME:-/nonexistent-home}") die "refusing to use $SRCDIR as --srcdir" ;;
esac
case "$SRCDIR/" in
  "$REPO_ROOT"/*)
    die "refusing to put the QEMU source tree inside the repository ($REPO_ROOT): QEMU is not vendored, use --srcdir outside the repo"
    ;;
esac

# --------------------------------------------------------------------------
# Verify: `-M help` must list the ze0 machine
# --------------------------------------------------------------------------
verify_machine() {
  if [ "$DRY_RUN" -eq 1 ]; then
    printf 'dry-run: %q -M help | grep -E "(^|[[:space:]])ze0([[:space:]]|$)"\n' "$QEMU_BIN"
    printf 'dry-run: would require a "ze0" line from %s\n' "$QEMU_BIN"
    return 0
  fi
  [ -e "$QEMU_BIN" ] || die "no qemu-system-sh4 at $QEMU_BIN — run $SELF first (or pass --qemu)"
  [ -x "$QEMU_BIN" ] || die "$QEMU_BIN is not executable"
  local out line
  if ! out="$("$QEMU_BIN" -M help 2>&1)"; then
    die "$QEMU_BIN -M help failed: $out"
  fi
  line="$(printf '%s\n' "$out" | grep -E '(^|[[:space:]])ze0([[:space:]]|$)' | head -n 3 || true)"
  if [ -z "$line" ]; then
    printf '%s\n' "build.sh: $QEMU_BIN does not list the machine 'ze0'." >&2
    printf '%s\n' "build.sh: The QEMU build succeeded but the ze0 machine is not in it." >&2
    printf '%s\n' "build.sh: Add the machine under tools/qemu-ze0/patches/*.patch (TODO M8.A2)," >&2
    printf '%s\n' "build.sh: then re-run with --force. Machines seen:" >&2
    printf '%s\n' "$out" | sed -n '1,25p' | sed 's/^/build.sh:   /' >&2
    exit 1
  fi
  note "OK: $line"
}

# --------------------------------------------------------------------------
# Patches
# --------------------------------------------------------------------------
apply_patches() {
  if [ "$USE_PATCHES" -eq 0 ]; then
    note "patches: skipped (--no-patch)"
    return 0
  fi
  if [ ! -d "$PATCH_DIR" ]; then
    note "patches: none ($PATCH_DIR does not exist)"
    return 0
  fi
  local list=() p
  while IFS= read -r p; do
    list+=("$p")
  done < <(find "$PATCH_DIR" -maxdepth 1 -type f -name '*.patch' | LC_ALL=C sort)
  if [ "${#list[@]}" -eq 0 ]; then
    note "patches: none in $PATCH_DIR"
    return 0
  fi
  for p in "${list[@]}"; do
    note "patches: applying $(basename "$p")"
    if ! run patch -d "$SRC" -p1 --forward --batch -i "$p"; then
      if [ "$DRY_RUN" -eq 0 ]; then
        rm -rf "$SRC"
        note "removed the half-patched source tree; fix the patch and re-run"
      fi
      die "patch failed: $p"
    fi
  done
}

stamp_source() {
  local stamp="$SRC/.ze0-version"
  if [ -f "$stamp" ] && [ "$(cat "$stamp")" != "$VERSION" ]; then
    die "$SRC was prepared for QEMU $(cat "$stamp"), pin is $VERSION — re-run with --force"
  fi
  if [ "$DRY_RUN" -eq 1 ]; then
    printf 'dry-run: printf %q > %q\n' "$VERSION" "$stamp"
  else
    printf '%s\n' "$VERSION" > "$stamp"
  fi
}

# --------------------------------------------------------------------------
# Fetch + prepare
# --------------------------------------------------------------------------
fetch_tarball() {
  if [ -s "$TARBALL" ]; then
    note "tarball: reusing $TARBALL"
    verify_tarball "$TARBALL"
    return 0
  fi
  local url="$URL_BASE/qemu-$VERSION.tar.xz" part="$TARBALL.part"
  if [ "$DRY_RUN" -eq 1 ]; then
    run mkdir -p "$SRCDIR"
    if command -v curl >/dev/null 2>&1; then
      run curl -fL --retry 3 --connect-timeout 20 -o "$TARBALL" "$url"
    else
      run wget --tries=3 -O "$TARBALL" "$url"
    fi
    printf 'dry-run: sha256sum %q  # must be %s\n' "$TARBALL" "$QEMU_SHA256"
    printf 'dry-run: check %s bytes\n' "$QEMU_TARBALL_BYTES"
    return 0
  fi
  run mkdir -p "$SRCDIR"
  note "downloading $url (~127 MiB, one-off)"
  if command -v curl >/dev/null 2>&1; then
    if ! curl -fL --retry 3 --connect-timeout 20 --progress-bar -o "$part" "$url"; then
      rm -f "$part"
      network_needed "$url"
    fi
  elif command -v wget >/dev/null 2>&1; then
    if ! wget --tries=3 -O "$part" "$url"; then
      rm -f "$part"
      network_needed "$url"
    fi
  else
    network_needed "$url"
  fi
  verify_tarball "$part"
  mv "$part" "$TARBALL"
}

# verify_tarball FILE — size and SHA-256 must match the pin.
verify_tarball() {
  local file="$1" size got
  if [ "$DRY_RUN" -eq 1 ]; then
    printf 'dry-run: sha256sum %q  # must be %s\n' "$file" "$QEMU_SHA256"
    printf 'dry-run: check %s bytes\n' "$QEMU_TARBALL_BYTES"
    return 0
  fi
  size="$(wc -c < "$file" | tr -d ' ')"
  [ "$size" -eq "$QEMU_TARBALL_BYTES" ] \
    || die "$(basename "$file") has $size bytes, expected $QEMU_TARBALL_BYTES (truncated download?) — delete it and re-run"
  got="$(sha256sum "$file" | awk '{print $1}')"
  [ "$got" = "$QEMU_SHA256" ] \
    || die "sha256 mismatch for $(basename "$file"): got $got, expected $QEMU_SHA256 — delete it and re-run"
  note "sha256: ok $QEMU_SHA256"
}

prepare_tarball_tree() {
  if [ -x "$SRC/configure" ] && [ "$FORCE" -eq 0 ]; then
    note "source: reusing $SRC"
    stamp_source
    return 0
  fi
  if [ "$FORCE" -eq 0 ] && [ -d "$SRC" ]; then
    note "source: $SRC exists without configure/ — re-extracting"
  fi
  run rm -rf "$SRC"
  fetch_tarball
  note "extracting $TARBALL"
  run tar -C "$SRCDIR" -xf "$TARBALL"
  if [ "$DRY_RUN" -eq 0 ] && [ ! -x "$SRC/configure" ]; then
    die "$SRC/configure missing after extraction (unexpected tarball layout)"
  fi
  stamp_source
  apply_patches
}

prepare_git_tree() {
  if [ -d "$SRC/.git" ] && [ "$FORCE" -eq 0 ]; then
    note "source: reusing git clone $SRC"
  else
    run rm -rf "$SRC"
    if [ "$DRY_RUN" -eq 1 ]; then
      run git clone --depth 1 --branch "v$VERSION" "$GIT_URL" "$SRC"
    else
      run mkdir -p "$SRCDIR"
      if ! git clone --depth 1 --branch "v$VERSION" "$GIT_URL" "$SRC"; then
        rm -rf "$SRC"
        network_needed "$GIT_URL"
      fi
    fi
    stamp_source
    apply_patches
  fi
  if [ "$DRY_RUN" -eq 0 ] && [ -d "$SRC/.git" ]; then
    local tag
    tag="$(git -C "$SRC" describe --tags --exact-match 2>/dev/null || true)"
    [ "$tag" = "v$VERSION" ] \
      || die "git clone at $SRC is not the pinned tag v$VERSION (got '${tag:-none}')"
    note "git: v$VERSION $(git -C "$SRC" rev-parse --short HEAD)"
  fi
}

# --------------------------------------------------------------------------
# Configure + build
# --------------------------------------------------------------------------
configure_and_build() {
  if [ "$FORCE" -eq 1 ]; then
    run rm -rf "$BUILD"
  fi
  if [ -f "$BUILD/Makefile" ] && [ "$FORCE" -eq 0 ]; then
    note "build: reusing $BUILD (make is incremental)"
  else
    run mkdir -p "$BUILD"
    note "configure: sh4-softmmu only, warnings not fatal"
    run_in "$BUILD" "$SRC/configure" \
      --target-list=sh4-softmmu \
      --disable-werror \
      --disable-docs
  fi
  note "build: make -j$JOBS"
  run_in "$BUILD" make -j"$JOBS"
}

# --------------------------------------------------------------------------
# Selftest: offline, no network, no writes outside its own sandbox
# --------------------------------------------------------------------------
SELFTEST_PASS=0
SELFTEST_FAIL=0

st_ok() {
  SELFTEST_PASS=$((SELFTEST_PASS + 1))
  printf 'ok   %s\n' "$*"
}

st_fail() {
  SELFTEST_FAIL=$((SELFTEST_FAIL + 1))
  printf 'FAIL %s\n' "$*" >&2
}

# st_run LABEL EXPECTED_RC -- CMD... ; combined output in $ST_OUT
st_run() {
  local label="$1" want="$2"
  shift 2
  [ "${1:-}" = "--" ] && shift
  local rc=0
  if ST_OUT="$("$@" 2>&1)"; then rc=0; else rc=$?; fi
  if [ "$rc" -eq "$want" ]; then
    st_ok "$label (exit $rc)"
  else
    st_fail "$label: exit $rc, expected $want"
    printf '%s\n' "$ST_OUT" | sed 's/^/     | /' >&2
  fi
}

st_contains() {
  local label="$1" needle="$2"
  if printf '%s\n' "$ST_OUT" | grep -Fq -- "$needle"; then
    st_ok "$label contains '$needle'"
  else
    st_fail "$label: output lacks '$needle'"
    printf '%s\n' "$ST_OUT" | sed 's/^/     | /' >&2
  fi
}

st_lacks() {
  local label="$1" needle="$2"
  if printf '%s\n' "$ST_OUT" | grep -Fq -- "$needle"; then
    st_fail "$label: output must not contain '$needle'"
  else
    st_ok "$label omits '$needle'"
  fi
}

tree_state() {
  find "$1" -mindepth 1 -printf '%y %p %s %T@\n' 2>/dev/null | LC_ALL=C sort
}

make_fake_qemu() {
  local path="$1" with_ze0="$2"
  mkdir -p "$(dirname "$path")"
  {
    printf '%s\n' '#!/usr/bin/env bash'
    printf '%s\n' 'set -eu'
    printf '%s\n' 'if [ "${1:-}" = "-M" ] && [ "${2:-}" = "help" ]; then'
    printf '%s\n' '  echo "Supported machines are:"'
    printf '%s\n' '  echo "none                 empty machine"'
    if [ "$with_ze0" -eq 1 ]; then
      printf '%s\n' '  echo "ze0                  Nissan Leaf ZE0 (SH-4A, 128 MiB)"'
    fi
    printf '%s\n' '  exit 0'
    printf '%s\n' 'fi'
    printf '%s\n' 'echo "fake qemu-system-sh4: unsupported args: $*" >&2'
    printf '%s\n' 'exit 1'
  } > "$path"
  chmod +x "$path"
}

selftest() {
  local tmp home_state repo_state
  tmp="$(mktemp -d "${TMPDIR:-/tmp}/qemu-ze0-selftest.XXXXXX")"
  trap "rm -rf $(printf '%q' "$tmp")" EXIT

  printf 'selftest: sandbox %s\n' "$tmp"
  mkdir -p "$tmp/home" "$tmp/cache" "$tmp/bin" "$tmp/bin-noid" "$tmp/bin-root" "$tmp/bin-bad"

  printf '#!/usr/bin/env bash\nprintf "1000\\n"\n' > "$tmp/bin-noid/id"
  printf '#!/usr/bin/env bash\nprintf "0\\n"\n' > "$tmp/bin-root/id"
  chmod +x "$tmp/bin-noid/id" "$tmp/bin-root/id"
  make_fake_qemu "$tmp/bin/qemu-system-sh4" 1
  make_fake_qemu "$tmp/bin-bad/qemu-system-sh4" 0

  # --- 1. argument parsing -------------------------------------------------
  st_run "--help" 0 -- "$SELF" --help
  st_contains "--help" "ze0 SH-4 machine"
  st_lacks "--help" "dry-run:"

  st_run "unknown option" 2 -- "$SELF" --definitely-not-an-option
  st_contains "unknown option" "unknown option"

  st_run "--jobs 0" 2 -- "$SELF" --jobs 0
  st_contains "--jobs 0" "--jobs must be >= 1"

  st_run "--version 8.1" 2 -- "$SELF" --version 8.1
  st_contains "--version 8.1" "too old"

  st_run "--version banana" 2 -- "$SELF" --version banana
  st_contains "--version banana" "bad --version"

  # --- 2. root refusal (fake id, no sudo needed) ---------------------------
  st_run "refuses root" 1 -- env PATH="$tmp/bin-root:$PATH" "$SELF" --dry-run --srcdir "$tmp/cache"
  st_contains "refuses root" "refusing to run as root"

  # --- 3. repository guard --------------------------------------------------
  st_run "refuses in-repo srcdir" 1 -- "$SELF" --dry-run --srcdir "$REPO_ROOT/tmp/qemu-ze0"
  st_contains "refuses in-repo srcdir" "inside the repository"

  # --- 4. the command plan --------------------------------------------------
  home_state="$(tree_state "$tmp/home")"
  repo_state="$(tree_state "$HERE")"
  local sandbox_before; sandbox_before="$(tree_state "$tmp")"

  st_run "dry-run plan" 0 -- env HOME="$tmp/home" "$SELF" --dry-run \
    --srcdir "$tmp/cache" --qemu "$tmp/bin/qemu-system-sh4" --jobs 3
  st_contains "dry-run plan" "qemu-$QEMU_VERSION.tar.xz"
  st_contains "dry-run plan" "sha256sum"
  st_contains "dry-run plan" "$QEMU_SHA256"
  st_contains "dry-run plan" "--target-list=sh4-softmmu"
  st_contains "dry-run plan" "--disable-werror"
  st_contains "dry-run plan" "make -j3"
  st_contains "dry-run plan" "-M help"
  if printf '%s\n' "$ST_OUT" | grep -Fq "dry-run:"; then
    st_ok "dry-run plan prefixes commands with 'dry-run:'"
  else
    st_fail "dry-run plan does not prefix commands"
  fi

  # --- 5. --dry-run writes nothing outside its cache ------------------------
  local sandbox_after; sandbox_after="$(tree_state "$tmp")"
  if [ "$sandbox_before" = "$sandbox_after" ] \
     && [ "$home_state" = "$(tree_state "$tmp/home")" ] \
     && [ "$repo_state" = "$(tree_state "$HERE")" ] \
     && [ -z "$(find "$tmp/cache" -mindepth 1 2>/dev/null)" ]; then
    st_ok "dry-run wrote nothing (sandbox, HOME and tools/qemu-ze0 unchanged; cache still empty)"
  else
    st_fail "dry-run wrote outside its cache"
    diff -u <(printf '%s\n' "$sandbox_before") <(printf '%s\n' "$sandbox_after") >&2 || true
  fi

  # --- 6. git plan is also planned, not executed ---------------------------
  st_run "dry-run git plan" 0 -- env HOME="$tmp/home" "$SELF" --dry-run --from-git \
    --srcdir "$tmp/cache" --qemu "$tmp/bin/qemu-system-sh4"
  st_contains "dry-run git plan" "git clone --depth 1 --branch v$QEMU_VERSION"
  st_contains "dry-run git plan" "$QEMU_GIT_URL"
  st_contains "dry-run git plan" "qemu-git"

  # --- 7. the -M ze0 check really passes and really fails ------------------
  st_run "verify fake ze0" 0 -- "$SELF" --verify-only --srcdir "$tmp/cache" \
    --qemu "$tmp/bin/qemu-system-sh4"
  st_contains "verify fake ze0" "ze0"
  st_contains "verify fake ze0" "OK:"

  st_run "verify without ze0 fails" 1 -- "$SELF" --verify-only --srcdir "$tmp/cache" \
    --qemu "$tmp/bin-bad/qemu-system-sh4"
  st_contains "verify without ze0 fails" "does not list the machine 'ze0'"

  st_run "missing qemu binary" 1 -- "$SELF" --verify-only --srcdir "$tmp/cache" \
    --qemu "$tmp/bin/nope/qemu-system-sh4"
  st_contains "missing qemu binary" "no qemu-system-sh4 at"

  # --- 8. network-needed message (file:// negative control) ----------------
  if command -v curl >/dev/null 2>&1 || command -v wget >/dev/null 2>&1; then
    st_run "network needed" 3 -- env HOME="$tmp/home" "$SELF" \
      --srcdir "$tmp/cache-net" --url-base "file://$tmp/no-such-mirror"
    st_contains "network needed" "NETWORK NEEDED"
    st_contains "network needed" "qemu-$QEMU_VERSION.tar.xz"
    if [ ! -e "$tmp/cache-net/qemu-$QEMU_VERSION.tar.xz" ]; then
      st_ok "network needed left no tarball behind"
    else
      st_fail "network needed left a tarball behind"
    fi
  else
    printf 'skip network-needed check (no curl/wget)\n'
  fi

  # --- 9. pin sanity --------------------------------------------------------
  if printf '%s' "$QEMU_SHA256" | grep -Eq '^[0-9a-f]{64}$'; then
    st_ok "pin sha256 is 64 lowercase hex characters"
  else
    st_fail "pin sha256 malformed"
  fi
  case "$QEMU_SHA256" in
    0000000000000000000000000000000000000000000000000000000000000000)
      st_fail "pin sha256 is a placeholder" ;;
    *) st_ok "pin sha256 is not a placeholder" ;;
  esac

  printf '\nselftest: %d passed, %d failed\n' "$SELFTEST_PASS" "$SELFTEST_FAIL"
  [ "$SELFTEST_FAIL" -eq 0 ] || exit 1
  return 0
}

# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
if [ "$SELFTEST" -eq 1 ]; then
  selftest
  exit $?
fi

if [ "$VERIFY_ONLY" -eq 1 ]; then
  verify_machine
  exit 0
fi

need_tool() {
  if command -v "$1" >/dev/null 2>&1; then
    return 0
  fi
  if [ "$DRY_RUN" -eq 1 ]; then
    note "warning: missing build tool: $1 (dry-run continues)"
    return 0
  fi
  die "missing build tool: $1"
}

for need in tar make meson ninja python3; do
  need_tool "$need"
done
if ! command -v cc >/dev/null 2>&1 && ! command -v gcc >/dev/null 2>&1; then
  if [ "$DRY_RUN" -eq 1 ]; then
    note "warning: no C compiler (cc/gcc) in PATH (dry-run continues)"
  else
    die "no C compiler (cc/gcc) in PATH"
  fi
fi

note "pin: QEMU $QEMU_VERSION from $QEMU_URL_BASE (sha256 $QEMU_SHA256)"
note "srcdir: $SRCDIR (outside the repository; QEMU is never vendored)"

if [ "$FROM_GIT" -eq 1 ]; then
  prepare_git_tree
else
  prepare_tarball_tree
fi
configure_and_build
verify_machine

if [ "$DRY_RUN" -eq 0 ]; then
  note "done: $QEMU_BIN"
  note "next: python3 tools/ce_qemu_probe.py --qemu $QEMU_BIN IMAGE"
else
  note "dry-run: nothing was fetched, patched, built or written"
fi
