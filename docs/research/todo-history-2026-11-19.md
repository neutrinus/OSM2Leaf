# TODO history — 2026-11-19 (PO grooming archive, 17th pass)

Done tasks moved from `TODO.md` on 2026-11-19: `Status: done`, the block's
ID named by no open or blocked task's text (fixpoint over the live board,
not only Depends/Unblock), and completed on `origin/main` more than 24 h ago.

- [x] **H88 — `fn_audit --corpus` with a missing image prints a traceback instead of the "no image" exit**
  - Status: done · Owner: task/h88-corpus-no-image · Critical: no · Pair: solo
  - Depends: H85 (the gate's SKIP contract assumes `fn_audit` reports a missing image cleanly)
  - Goal: the live path is clean — `python3 tools/fn_audit.py archive/absent.img; echo $?` prints `error: [Errno 2] No such file or directory: 'archive/absent.img'` and exits `2`. The **`--corpus` path is not**: `python3 tools/fn_audit.py archive/absent.img --corpus docs/research/fn-audit-corpus-2026-11-16.json` raises `FileNotFoundError` (`tools/fn_audit.py`, the `Image(...)` call after `load_corpus`), so a snapshot audit on a checkout without the image shows a traceback. `tools/gate.py` hides it by short-circuiting on the declared `optional_input`; a direct caller sees the crash.
  - Precheck: the live command above prints `error: …` + exit `2`; the `--corpus` command prints `Traceback` / `FileNotFoundError` and does not exit `2`.
  - Scope: `tools/fn_audit.py` only: guard the `Image(...)` in the `--corpus` branch with the same existence check the live path effectively gets, so a missing image prints the same `error: [Errno 2] No such file or directory: '<path>'` line and returns `2`; one `--selftest` case for the `--corpus` + missing-image path. No change to `gate.py`.
  - Input: `tools/fn_audit.py` `main()` (`except OSError` around `Image(...)`, the `args.corpus` branch), `tools/gate.py` `SKIP_MARKERS`.
  - Hints: keep the wording byte-compatible with the live path (`error: [Errno 2] No such file or directory: '<path>'`) so `tools/gate.py`'s `no such file or directory: 'archive/` marker still matches; do not swallow a genuine OSError on a *present* file into a missing-image SKIP.
  - Done when: `python3 tools/fn_audit.py archive/absent.img --corpus docs/research/fn-audit-corpus-2026-11-16.json; echo $?` prints the `error: … No such file or directory` line (no traceback) and `2`; `python3 tools/fn_audit.py --selftest` passes with the new case; `python3 tools/gate.py` (image present, and `--image archive/absent.img`) unchanged; `python3 tools/todo_check.py` and `python3 tools/gate.py` green.
  - Stop: none.
  - Result: EXP-2026-11-17-H88-corpus-no-image; C-4110–C-4114. Both `main()` image paths now share `_image_sha_or_error`: a missing image under `--corpus` prints the live path's `error: [Errno 2] No such file or directory: '<path>'` and returns `2` (it used to raise inside `image_sha256` at line 781 and exit `1`). `--selftest` `OK (72 checks, 0 failed)` with two new cases; a present-but-corrupt image is still a SHA-256 mismatch (`FAIL`, exit `2`), so "missing" did not widen; `tools/gate.py` unchanged (image present `4 pass`; declared-absent `SKIP`).
  - Claims: C-4110–C-4119
- [x] **M3.10 — Decode the `DRSTR001`/`CMP.LST` functions found by M3.4**
  - Status: done · Owner: task/m3.10-drstr-cmplst-fns · Critical: no
  - Depends: — (M1.9 helps)
  - Goal: find the checks the firmware applies to `DRSTR001.DAT` and
- [x] **M5.1 — OSM ingest to IMF**
  - Status: done · Owner: session-ZMxuBT · Critical: yes
  - Note: reopened by the 2026-11-06 review because `tools/osm_ingest.py` was
- [x] **M5.2 — Mesh splitter**
  - Status: done · Owner: session-ZMxuBT · Critical: yes
  - Depends: M4.8, M5.1
  - Done when: every way is assigned to meshes and clipped at borders, and
