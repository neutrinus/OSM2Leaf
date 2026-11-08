# EXP-2026-11-08-H16: pinned vendor-image downloads

- **Status:** done
- **Date:** 2026-11-08
- **Sample:** `LEAF_2011-2012_QSD-309-101_navi158_eu.img`, first 256 MiB
  (`IMG256`), 268435456 bytes, SHA-256
  `92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9`
  (downloaded from `https://files.viaaq.eu/sd-images/`, not committed)
- **Tools:** `tools/fetch_image.py` (this change), python3 3.15 (system),
  `sha256sum` (coreutils)
- **Claims:** none (tool task, no format claim)
- **Supersedes:** none
- **Superseded by:** none

## Question

Can one command fetch and verify the vendor images the board refers to, so
that "no image on this machine" stops being a blocker (H16)?

## Hypothesis

`tools/fetch_image.py --image IMG256 -o PATH` produces a file whose SHA-256
equals the pinned value, and refuses to leave any output when size or hash is
wrong. Falsifier: the real download's hash differs from the pin, or a
wrong-pin fixture leaves an output file behind.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `IMG256` = EU2011 `--part 256M` |
| SHA-256 | `92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9` |
| Offset(s) / VA(s) | none (bytes 0–268435455) |
| Tool / version | `tools/fetch_image.py` (H16); python3 3.15 |
| Repo tool | `tools/fetch_image.py` |

## Method

1. **Sample and hash.** As in Inputs. The pinned hash is in the tool.
2. **Commands.**
   ```bash
   python3 tools/fetch_image.py --selftest
   python3 tools/fetch_image.py --list
   python3 tools/fetch_image.py --image IMG256 -o archive/head256.img
   python3 tools/fetch_image.py --verify archive/head256.img
   sha256sum archive/head256.img
   ```
3. **Controls.** Positive: the real download of `IMG256` verifies against
   the pinned hash (and `sha256sum` agrees). Negative: selftest checks 4–5
   refuse a wrong hash and a wrong size and leave no output or `.part`.
   Also selftest 6: an unreachable host keeps the `.part`; test 2: a
   truncated `.part` is resumed with a Range request; test 3: a server that
   ignores Range restarts instead of appending.
4. **Scope.** One 256 MiB head downloaded from the network. Selftests run
   against a local HTTP fixture of 1 MiB (18 checks), not `file://`: urllib
   does not do Range on `file://`, and resume must be tested. Not covered:
   the full 7.5 GB images (only their sizes were read from `Content-Length`).
   EU2016 has no pinned SHA-256, so it is checked by size only.
5. **Falsifier.** A hash other than `92aa525d…` for the downloaded head, or any
   output file left after a refused fixture download.

## Observations

- `--selftest`: 18 checks, `failures: 0`; `tools/selftest.py --only fetch_image`:
  `passed=1 failed=0`.
- Real download (first run, bug): without a bounded `Range` header the request
  read to EOF; the `.part` reached 4.0 GB before it was stopped. Fixed: every
  request is `bytes=N-(size-1)`.
- Real download (second run, bug): the first attempt got HTTP 403 for
  `urllib`'s default User-Agent (`curl` and a tool-named UA get 206). Fixed:
  the tool sends `fetch_image.py (OSM2Leaf research; …)`.
- Real download, final run: `archive/head256.img` 268435456 bytes in 10.2 s;
  `--verify` → `matches EU2011 256M`; `sha256sum` →
  `92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9`.
- `archive/sd-images/` already held the four full images from 2026-11-07
  (EU2011 8057257984 B, US 8057257984 B, EU2014 7969177600 B, EU2016
  7969177600 B). Their sizes match the table. Their hashes were not computed
  here; the EU2011 first 256 MiB hashed to `92aa525d…`.
- `--list` output: four keys, sizes, pinned hashes (EU2016 `(not pinned)`).

## Interpretation

- **FACT:** `fetch_image.py --image IMG256` produces the pinned 256 MiB head
  (observed above).
- **FACT:** the Range bound and the User-Agent were both needed; without
  them the tool fetches 8 GB or gets 403.
- **UNKNOWN:** SHA-256 of EU2016 (needs a full download and a pin).

## Conclusion

H16 done: `tools/fetch_image.py` exists with `--list`, `--image KEY [--part
256M] -o PATH`, `--verify PATH`, and a self-test that needs no network.
`tools/README.md`, the Shared-inputs table and rule 11 point to it. The
tool's selftest and the real download pass.

## Reproduction

```bash
python3 tools/fetch_image.py --selftest                              # failures: 0
python3 tools/fetch_image.py --image IMG256 -o archive/head256.img   # size 268435456, SHA-256 verified
sha256sum archive/head256.img                                        # 92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9
```

## Follow-ups

- [ ] Pin the SHA-256 of `ENV200_2016_EU_QSD-390-100.img` (needs a full download).
- [ ] Hash the four full images in `archive/sd-images/` against the pins.
