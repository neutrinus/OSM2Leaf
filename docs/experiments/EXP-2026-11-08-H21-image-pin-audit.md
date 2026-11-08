# EXP-2026-11-08-H21 — Image pin audit (archive hashes, EU2016 pin)

**Date:** 2026-11-08
**Task:** H21 — Image pin audit: hash the archive images, pin 2016
**Branch / commit:** `task/h21-image-pin-audit` (this EXP; recovered and re-merged after a coordinator merge error that dropped the original branch)
**Status:** done

## Question
Do the local copies in `archive/sd-images/` match the recorded/pinned SHA-256
values, and can the missing full-image pin for EU2016 be added to
`tools/fetch_image.py` from a verified local copy (hashing only, no download)?

## Method

### 1. Sample + hash
Read-only local images (not committed):

| Local image | Size (bytes) | SHA-256 |
| --- | ---: | --- |
| `LEAF_2011-2012_QSD-309-101_navi158_eu.img` | 8,057,257,984 | `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307` |
| `LEAF_2011-2012_US.img` | 8,057,257,984 | `53342430a1bb58d3ed6eb68c5563f079c710a400134d522e6192489b324c5383` |
| `LEAF_2014_EU_QSD-357-101.img` | 7,969,177,600 | `4a8a21f477e9fc511f94406976b8d67037842f9c043f49ab24e1adc82d6da89b` |
| `ENV200_2016_EU_QSD-390-100.img` | 7,969,177,600 | `f53d55f159fd4232caa0b100b9b12e3910c8fe3849201871a71ee38ac19007fb` |

### 2. Runnable commands
```bash
sha256sum archive/sd-images/*.img
python3 tools/fetch_image.py --list
python3 tools/fetch_image.py --selftest
python3 tools/claims_check.py
python3 tools/selftest.py
```

### 3. Controls (positive / negative)
- Positive: each computed hash compared to the value recorded in
  `docs/research/image-versions.md` / `tools/fetch_image.py`; EU2011 matches the
  long-pinned value (C-001 lineage).
- Negative/guard: EU2014 was already SHA-256-pinned in `fetch_image.py`; its
  local copy verified (not re-pinned). EU2016 head-part (256M) is intentionally
  **not** pinned in `PART_PINS` (only EU2011/IMG256 head is pinned) — selftest
  confirms an un-pinned part resolves with `sha None` for `EU2014 --part 256M`
  and EU2016 full resolves to its pinned hash.

### 4. Scope / counted corpus
All 4 `.img` files present in `archive/sd-images/` (the ZE0/related SD images
available locally). Scope was hashing/metadata only; **no image was downloaded**.
EU2019 and `.7z` map-tree archives were out of scope (not in `archive/sd-images/`,
not pinned as full images in `fetch_image.py`).

### 5. Falsifier
A mismatch between a local copy's SHA-256 and the recorded/pinned value, or a
local image absent when a download is not allowed (to be reported as a finding /
gap, not silently accepted). Neither occurred.

## Observations
- 0 mismatches across 4 audited images. EU2011, US, EU2014 hashes match prior
  records/pins exactly. EU2016 (`f53d55f1…`, 7,969,177,600 bytes) matches the
  value recorded in `docs/research/image-versions.md`.
- `tools/fetch_image.py` previously had `EU2016.sha256 = None` with a
  "not pinned yet" note and a selftest asserting EU2016 resolves with `sha None`.

## Interpretation
EU2016's full-image SHA-256 can be pinned from the verified local copy. Head-part
SHA-256 pins remain only for `EU2011/256M` (`IMG256`), unchanged. No claim IDs
added (H21 states "Claims: none").

## Changes made
- `tools/fetch_image.py`: pinned EU2016 full-image SHA-256 and updated
  docstring/note; updated `--selftest` (replaced invalid "unpinned EU2016" case
  with `EU2014 --part 256M` un-pinned-part `sha None` + `EU2016 full image is
  SHA-256 pinned`).
- `docs/research/image-versions.md`: added H21 "local copy verified" evidence for
  the 4 audited SD images.
- `TODO.md`: H21 marked `[x]`/done with Result; Shared inputs EU2014/EU2016 rows
  updated to `fetch_image.py` with verified SHA-256.

## Reproduction
From a worktree with `archive/sd-images/*.img` present (read-only):
```bash
sha256sum archive/sd-images/*.img
python3 tools/fetch_image.py --selftest
python3 tools/claims_check.py
```

## Follow-ups
- If EU2019 / `.7z` archives become in-scope for pinning, audit and pin them in a
  separate task (out of H21 scope).
- EU2016 256M head part remains unpinned (no recorded head SHA-256); pin only if
  a verified head hash is established.
