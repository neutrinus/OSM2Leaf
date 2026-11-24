# EXP-2026-11-24-H148-osm2clarion-comparison

- **Status:** done
- **Date:** 2026-11-24
- **Sample:** none (tool-only task): a read of the public repository `https://github.com/albertbm/osm2clarion` at commit `458f5f0da3466de704190f8b2778d2c85688be9e`; no card image and no factory data was opened
- **Tools:** git 2.43.0, grep, python3 3.13.18 (only for `tools/board.py`); the upstream code was read, not executed
- **Claims:** C-10370–C-10376
- **Supersedes:** none
- **Superseded by:** none

## Question

What does osm2clarion support today, how does it compare with what this repository has established, what could we contribute to it, and does a separate OSM2Leaf map compiler still make sense?

## Hypothesis

Exploratory. Expectation from `docs/research/sources.md`: osm2clarion covers the QY8 (`X08-03-00`) family only and is prior art, not a ZE0 tool. Falsifier: native `X08-02-00` support in its current tree.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | git clone of `https://github.com/albertbm/osm2clarion` |
| SHA-256 | n/a (git commit `458f5f0da3466de704190f8b2778d2c85688be9e`) |
| Offset(s) / VA(s) | n/a |
| Tool / version | git 2.43.0, grep |
| Repo tool | none; this repository's side comes from `docs/format/`, `docs/research/claims.md` and the EXP records named in the comparison page |

## Method

1. **Sample and hash.** The upstream repository at the commit above, cloned into a new empty directory outside this repository.
2. **Commands.**
   ```bash
   mkdir -p ~/ext && cd ~/ext && git clone https://github.com/albertbm/osm2clarion osm2clarion && cd osm2clarion
   git rev-parse HEAD
   git rev-list --count HEAD
   git log --format='%ad' --date=short | sort | sed -n '1p;$p'
   git cat-file -t 07fbf78d049e7765db887818e77419ffc3dd499a
   ls tools/*.py | wc -l; ls tests/test_*.py | wc -l; grep -c "def test_" tests/*.py | awk -F: '{s+=$2} END {print s}'
   grep -n "X08_02 = Format" -A 12 tools/clarion_format.py
   grep -n "generate mode writes" build.py
   grep -n "blocks_count\|meta_data" tools/decompress_fast.py; grep -n "<IIII" tools/card_pack.py
   grep -n "0x09  7 bytes" docs/FORMAT.md
   grep -rni "zlib-ng\|zlib_ng\|ZLIB_VERSION" tools tests build.py | wc -l
   grep -n "COORD" docs/FORMAT.md
   grep -n "Oulu\|emulator" README.md
   ```
3. **Controls.** Positive: `grep -n "X08-03-00" tools/clarion_format.py` finds the QY8 format the old source note describes. Negative: `git cat-file -t` on the commit pinned by `tools/ze0-viewer/tools_ze0/PROVENANCE.md` must succeed if the pin is still reachable; it fails.
4. **Scope.** `README.md`, `LICENSES.md`, `CONTRIBUTING.md`, the seven files in `docs/` except `ADDRESS-IMPORT.md`, `tools/clarion_format.py`, `profiles/finland.toml`, and targeted greps over `tools/` and `tests/`. Not read line by line: the other 81 tools and the tests. No upstream code was executed, so no statement here is about its behaviour on a card.
5. **Falsifier.** A `Format` object for `X08-02-00` in the current tree refutes "QY8 only".

## Observations

```text
$ git rev-parse HEAD
458f5f0da3466de704190f8b2778d2c85688be9e
$ git rev-list --count HEAD
343
$ git log --format='%ad' --date=short | sort | sed -n '1p;$p'
2026-10-06
2026-11-23
$ git cat-file -t 07fbf78d049e7765db887818e77419ffc3dd499a
fatal: git cat-file: could not get object info
$ ls tools/*.py | wc -l; ls tests/test_*.py | wc -l; grep -c "def test_" ...
82
36
742
$ grep -n "generate mode writes" build.py
655:  raise SystemExit('profile %s: generate mode writes x08-03 (QY8) cards only, not %s' % (P.name, P.fmt.name))
$ grep -n "blocks_count\|meta_data" tools/decompress_fast.py
38:        "blocks_count": data[8],
39:        "meta_data": data[9:0x10].hex(),
$ grep -n "<IIII" tools/card_pack.py
34:    n, _, blocks, _ = struct.unpack_from('<IIII', ind)
$ grep -rni "zlib-ng\|zlib_ng\|ZLIB_VERSION" tools tests build.py | wc -l
0
$ grep -n "Oulu" README.md
203:- Setting a destination near Oulu crashes the unit. Not fixed.
```

`tools/clarion_format.py` defines `X08_02 = Format('x08-02', 'QY7', …)` with `HITACHI`, `CLA-NAVI05-01`, `FORMAT VERSION X08-02-00`, `V05.00.00`, zlib magic `78 9c`, window 15, padding 4, `x_base=1024`, Latin-1, 341 section slots. The first commit that names QY7 is dated 2026-11-11 (`Add the QY7 map format next to the QY8 one`). `profiles/finland.toml` targets volume `QSD-357-101` with seven cells. `docs/FORMAT.md` lists under "Not established": the 7 bytes at `0x09` of each `.ind`; `COORD`, `ZIPFR` and `FRWAY` unexamined.

## Interpretation

- **FACT:** osm2clarion at `458f5f0d` reads and writes `X08-02-00` (QY7) tiles and coarse files next to `X08-03-00`; the "QY8 only" note in `sources.md` is out of date.
- **FACT:** its from-scratch ("generate") chain refuses an `X08-02` profile; QY7 is served by "area" mode, which keeps the factory background and rebuilds roads.
- **FACT:** the commit pinned by `tools/ze0-viewer` is not in the upstream history any more.
- **FACT:** `docs/FORMAT.md` and `tools/decompress_fast.py` upstream read the `.ind` header as a `uint8` count plus 7 unknown bytes, while `tools/card_pack.py` upstream and `docs/format/cmp-ind.md` here read two `uint32 LE` fields.
- **OBSERVED:** the README reports address, intersection and POI search, speed limits, cameras and guidance as working on QY8 units, and routes tried on one QY7 unit. Not reproduced here.
- **UNKNOWN:** whether an osm2clarion area-mode card built on the EU 2011 base (`QSD-309-101`) boots in `-M ze0`; which emulator their README refers to; whether their cited `Navi.exe` addresses are from a build we hold.

## Conclusion

`docs/research/osm2clarion-comparison.md` is new and holds the side-by-side table, what we can learn, a proposed contribution list (nothing sent upstream) and the assessment that stream M5 as a separate compiler is overtaken while the emulator, firmware and unit-side work are not. `docs/research/sources.md` row updated. Two follow-up tasks filed: M5.104 (run their area mode on the EU 2011 base and boot it in `-M ze0`) and H149 (the vendored `ze0-viewer` pin no longer exists upstream). The decision on direction and on what to send upstream is the owner's.

## Overtaken by a later commit

none

## Reproduction

```bash
git clone https://github.com/albertbm/osm2clarion /tmp/osm2clarion && cd /tmp/osm2clarion
git checkout 458f5f0da3466de704190f8b2778d2c85688be9e
grep -c "X08_02 = Format" tools/clarion_format.py          # expected: 1
git cat-file -t 07fbf78d049e7765db887818e77419ffc3dd499a   # expected: fatal (object missing)
```

## Follow-ups

- [ ] M5.104: osm2clarion area mode for Dolnośląskie on the EU 2011 base, boot in `-M ze0`.
- [ ] H149: replace or re-pin the vendored `tools/ze0-viewer` upstream copy.
- [ ] After the owner agrees: prepare contribution items A1–A3 of the comparison page.
