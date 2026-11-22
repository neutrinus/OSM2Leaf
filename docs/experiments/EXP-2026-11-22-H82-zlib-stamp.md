# EXP-2026-11-22-H82: Stamp the zlib interpreter into recompression evidence

- **Status:** done
- **Date:** 2026-11-22
- **Sample:** `none (tool-only task)` — the change is to `tools/zlibinfo.py`, `docs/experiments/TEMPLATE.md`, and `prompt_common.txt`; no vendor bytes are read.
- **Tools:** python3 3.15.0 / zlib 1.3.1.zlib-ng (this host default, reported by `python3 tools/zlibinfo.py`); repo tools `tools/zlibinfo.py`, `tools/selftest.py`, `tools/board.py`, `tools/claims_check.py`, `tools/todo_check.py`
- **Claims:** C-4050–C-4059
- **Supersedes:** none
- **Superseded by:** none

## Question

Can recompression/byte-identical evidence be made self-describing about the zlib interpreter that produced the bytes, without changing compression behaviour or `--require-stock-zlib` exit codes?

## Hypothesis

A `--stamp` mode on `tools/zlibinfo.py` can emit nothing on the pinned stock zlib 1.3.1 runtime and exactly one WARNING line on any other runtime, so EXP logs carry the interpreter identity. **Falsifier:** if a stock 1.3.1 runtime emits a warning, a non-1.3.1 runtime emits nothing/multiple lines, or the stamp changes exit codes/compression behaviour, the claim is false.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `none (tool-only task)` |
| SHA-256 | `none (tool-only task)` |
| Offset(s) / VA(s) | — |
| Tool / version | python3 3.15.0 / zlib 1.3.1.zlib-ng (`python3 tools/zlibinfo.py`) |
| Repo tool | `tools/zlibinfo.py`, `tools/selftest.py`, `tools/board.py` |

## Method

1. **Sample and hash.** No vendor sample; tool-only task. Live host runtime is the observation target: `python3 tools/zlibinfo.py` reports zlib-ng 1.3.1.zlib-ng.
2. **Commands.**

```bash
cd /home/marek/projekty/OSM2Leaf.task-h82-zlib-stamp
python3 tools/zlibinfo.py
python3 tools/zlibinfo.py --stamp; echo "exit=$?"
python3 tools/zlibinfo.py --require-stock-zlib; echo "exit=$?"
python3 tools/zlibinfo.py --selftest
python3 tools/selftest.py --only zlibinfo
grep -n zlibinfo docs/experiments/TEMPLATE.md
grep -n zlibinfo prompt_common.txt
python3 tools/board.py add-claims --section "H82 — Stamp the zlib interpreter into recompression evidence (C-4050–C-4059)" --create --file /tmp/opencode/h82-claims.md
python3 tools/claims_check.py
python3 tools/todo_check.py
python3 tools/selftest.py
python3 tools/board.py lost --base origin/main
```

3. **Controls.** Positive: injected `Runtime("1.3.1","1.3.1",STOCK,ok=True,reference=True)` makes `stamp()` return `None` and print nothing. Negative: injected zlib-ng, zlib-ng-runtime-only, older stock 1.2.11, and unknown/mixed runtimes each produce exactly one `WARNING: zlibinfo: ...` line naming build/runtime/flavour and `stock zlib 1.3.1`; `--require-stock-zlib` still exits 3 on untrusted runtime (existing guard selftest preserved). Live host control: on this zlib-ng host `--stamp` exits 0 with one WARNING line; `--require-stock-zlib` exits 3.
4. **Scope.** Changed `tools/zlibinfo.py` (`--stamp` arg, `stamp()`, selftest cases), `docs/experiments/TEMPLATE.md` Tools row, `prompt_common.txt` evidence bullet, TODO/claims rows for H82, and this EXP. No compression behaviour changes; no other tools changed; no claim rewrites; no per-EXP backfill of the six historical EXPs named in H82 (Stop condition — recorded as follow-up in C-4058/C-4059).
5. **Falsifier.** Any of: stock 1.3.1 stamp emits output; any non-1.3.1 stamp emits no line or more than one line; `--stamp` exits non-zero; `--require-stock-zlib` exit code changes; `selftest.py` regresses; TEMPLATE/prompt_common omit the zlibinfo requirement.

## Observations

Precheck (task):

```text
$ python3 tools/zlibinfo.py
zlib: zlib 1.3.1.zlib-ng, runtime 1.3.1.zlib-ng (zlib-ng: not the reference compressor)
$ python3 tools/zlibinfo.py --require-stock-zlib; echo exit=$?
zlib: zlib 1.3.1.zlib-ng, runtime 1.3.1.zlib-ng (zlib-ng: not the reference compressor)
zlibinfo: --require-stock-zlib needs stock zlib; this interpreter reports zlib-ng (exit 3, unverifiable).
exit=3
```

Implementation checks:

```text
$ python3 tools/zlibinfo.py --stamp; echo exit=$?
WARNING: zlibinfo: interpreter links 1.3.1.zlib-ng (runtime 1.3.1.zlib-ng, zlib-ng); stock zlib 1.3.1 is required for byte-identical recompression claims. Record this interpreter in the EXP Tools row or rerun with stock zlib 1.3.1.
exit=0

$ python3 tools/zlibinfo.py --selftest
zlibinfo selftest: OK (21 checks, fake zlib-ng strings, zlib untouched)

$ python3 tools/selftest.py --only zlibinfo
tool:zlibinfo  PASS  0.03s
passed=1 failed=0 skipped=0 total=1 time=0.03s
selftest: OK
```

Doc wiring:

```text
$ grep -n zlibinfo docs/experiments/TEMPLATE.md
8:  `capstone 5.0.7`, `qemu 8.2.7`, `objdump` from `binutils-sh4-linux-gnu`), and
9:  for repo tools the path. For any recompression/byte-identical claim, include
10:  the `python3 tools/zlibinfo.py` (or `--stamp`) line that names the

$ grep -n zlibinfo prompt_common.txt
66:- For any recompression or byte-identical claim, record the interpreter that
67:  produced the bytes with `python3 tools/zlibinfo.py` (or `--stamp`); a
68:  `--stamp` WARNING means the runtime is not stock zlib 1.3.1 and the claim is
```

## Interpretation

- **FACT:** `zlibinfo.py --stamp` is silent on injected stock 1.3.1 and emits one WARNING line on injected non-1.3.1 runtimes; live zlib-ng host emits one WARNING and exits 0; `--require-stock-zlib` still exits 3 on zlib-ng.
- **OBSERVED:** `selftest.py --only zlibinfo` passes; TEMPLATE and prompt_common now require the zlibinfo line for recompression/byte-identical claims.
- **HYPOTHESIS:** none — tool-only behaviour.
- **UNKNOWN:** Per-EXP backfill of the six window EXPs named by H82 was not performed (Stop condition); C-4058/C-4059 reserved.

## Conclusion

H82 adds a lightweight, self-describing zlib stamp: `--stamp` makes recompression evidence name its interpreter without turning a metadata check into a refusal gate. The pinned contract is preserved: stock 1.3.1 is silent, anything else warns, `--require-stock-zlib` still refuses with exit 3. TEMPLATE and prompt_common now require the stamp for recompression/byte-identical claims. Historical EXP backfill remains a follow-up to avoid touching claim-bearing records.

## Overtaken by a later commit

none

## Reproduction

```bash
cd /home/marek/projekty/OSM2Leaf.task-h82-zlib-stamp
python3 tools/zlibinfo.py --selftest        # expected: 21 checks OK
python3 tools/zlibinfo.py --stamp; echo $?  # on zlib-ng: 1 WARNING + exit 0; on stock 1.3.1: no output + exit 0
python3 tools/zlibinfo.py --require-stock-zlib; echo $?  # on zlib-ng: exit 3
```

## Follow-ups

- [ ] H82 follow-up: backfill the six window EXPs named in the task with `zlibinfo.py`/interpreter lines without retyping tool versions or touching claims beyond necessary evidence references (Stop condition).
