# EXP-2026-11-17-H88: `fn_audit --corpus` on a missing image crashed instead of skipping

- **Status:** done
- **Date:** 2026-11-17
- **Sample:** `none (tool-only task)` — a synthetic 19-byte "image" and a
  snapshot written by `write_snapshot`; no vendor bytes.
- **Tools:** python3 3.15; repo tools `tools/fn_audit.py`, `tools/gate.py`,
  `tools/selftest.py`
- **Claims:** C-4110–C-4119
- **Supersedes:** none
- **Superseded by:** none

## Question

H85's gate classifies exit `2` **plus** a missing-input marker as `SKIP`, and
its own `fn_audit` row also short-circuits on a declared optional input. Is
`fn_audit` itself clean on a missing image, for a caller that does not go
through the gate?

## Hypothesis

The live path already prints `error: [Errno 2] No such file or directory:
'<path>'` and returns `2`, but the `--corpus` path hashes the image inside
`image_sha256()` **before** constructing `Image()`, so it hits an uncaught
`FileNotFoundError` instead. **Falsifier:** if both paths already print the
same line and exit `2`, there is nothing to fix and the task closes no-op.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `none (tool-only task)`; `archive/absent.img` (absent), a 4096-byte random file (corrupt), a real `archive/head256.img` |
| SHA-256 | `none (tool-only task)` |
| Offset(s) / VA(s) | — |
| Tool / version | python3 3.15 |
| Repo tool | `tools/fn_audit.py`, `tools/gate.py` |

## Method

1. **Sample.** The two `main()` branches that open the image: `--corpus` and
   the live scan.
2. **Commands.**
   ```bash
   python3 tools/fn_audit.py archive/absent.img; echo $?
   python3 tools/fn_audit.py archive/absent.img \
     --corpus docs/research/fn-audit-corpus-2026-11-16.json; echo $?
   python3 tools/fn_audit.py --selftest
   python3 tools/gate.py
   python3 tools/gate.py --image archive/absent.img
   ```
3. **Controls.** *Positive*: a present image keeps `gate: 4 pass`. *Negative*:
   a **present but corrupt** image (4 KiB of random bytes) must be `FAIL`, not
   a `SKIP` — the fix must not turn a real error into "no image".
4. **Scope.** `tools/fn_audit.py` only: one helper used by the `--corpus`
   branch, plus two selftest cases. No change to `gate.py`.
5. **Falsifier.** Stated in the Hypothesis.

## Observations

Before (the crash is in `image_sha256`, not in `Image`):

```
$ python3 tools/fn_audit.py archive/absent.img; echo $?
error: [Errno 2] No such file or directory: 'archive/absent.img'
2
$ python3 tools/fn_audit.py archive/absent.img --corpus docs/research/fn-audit-corpus-2026-11-16.json; echo $?
  File ".../tools/fn_audit.py", line 781, in image_sha256
    with open(path, "rb") as fh:
FileNotFoundError: [Errno 2] No such file or directory: 'archive/absent.img'
1
```

After:

```
$ python3 tools/fn_audit.py archive/absent.img --corpus docs/research/fn-audit-corpus-2026-11-16.json; echo $?
error: [Errno 2] No such file or directory: 'archive/absent.img'
2
$ python3 tools/fn_audit.py --selftest | tail -1
selftest: OK (72 checks, 0 failed)
```

Gate, unchanged: image present → `gate: 4 pass, 0 fail, 0 skip`;
`--image archive/absent.img` → `fn_audit SKIP … missing archive/absent.img`,
`gate: 3 pass, 0 fail, 1 skip`. Negative control, a 4 KiB random file:
`error: snapshot image_sha256 … does not match /tmp/opencode/trunc.img`, exit
`2`, and the gate reports `fn_audit FAIL` / `gate: 3 pass, 1 fail, 0 skip` —
a present file is never forgiven as a missing one.

## Interpretation

- **FACT:** the live path was already correct; the `--corpus` path was not,
  because it hashes the image before `Image()` is constructed. The two paths
  now share one helper, print identical wording, and both return `2`.
- **FACT:** the wording is the one `tools/gate.py`'s `no such file or
  directory: 'archive/` marker matches, so a direct caller and the gate agree.
- **FACT:** a corrupt-but-present image stays `FAIL`, so the repair does not
  widen what "missing" means.
- **LIMITATION:** the gate's `optional_input` short-circuit stays in place
  (defence in depth); it no longer hides a traceback, but it is still why the
  gate itself never reached the old crash.

## Conclusion

`fn_audit --corpus` with a missing image now prints the live path's
`error: [Errno 2] No such file or directory: '<path>'` and returns `2` on both
paths; `--selftest` pins the case (72 checks) and a present corrupt image is
still a `FAIL`.

## Reproduction

```bash
python3 tools/fn_audit.py archive/absent.img --corpus docs/research/fn-audit-corpus-2026-11-16.json; echo $?
# error: [Errno 2] No such file or directory: 'archive/absent.img'
# 2
python3 tools/fn_audit.py --selftest       # OK (72 checks, 0 failed)
python3 tools/gate.py                      # 4 pass with the image
```
