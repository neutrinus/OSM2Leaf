# EXP-2026-11-24-H143 — consent tool picked the build from a rewritable name

- **Status:** done
- **Date:** 2026-11-24
- **Task:** TODO **H143** (follow-up of M8.C1p, found while preparing the
  owner's EU card for a US unit)
- **Sample:**
  - EU 2011 card `LEAF_2011-2012_QSD-309-101_navi158_eu.img`, SHA-256
    `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`;
  - US 2011 card `archive/leaf_2011_usa_sddump.img`, SHA-256
    `53342430a1bb58d3ed6eb68c5563f079c710a400134d522e6192489b324c5383`;
  - NK1 `firmware/unit-flash/nk1-QY7200ND.bin`, SHA-256
    `b4b3542bb95d336c55ed11e1a4854be2c5f3dce1b60e074629d2b185f3b9fb00`.
  Scratch copies of the cards stayed in
  `~/projekty/leafre-work/scratch/h143/` and were deleted; no card copy or
  patched ROM is committed.
- **Tools:** Python 3.14.10; repo tools `ze0_consent.py`,
  `card_mapcode.py`, `selftest.py`; git HEAD `5be6cb00`.
- **Claims:** C-10140–C-10144
- **Supersedes:** none
- **Superseded by:** EXP-2026-11-24-M8.C1p-eu-consent-l4 for the EU event ids
  (`0x08a6→0x0891` is the wrong handler; real EU ids `0x08a4→0x088f`)

## Question

Does `tools/ze0_consent.py` choose the card's own consent event ids on a card
whose NKOK build name was already rewritten by `card_mapcode.py`, as the
documented EU-on-US workflow does?

## Hypothesis

No. `detect()` selected the build from the NKOK name at NB00 `+0x16`, which
`card_mapcode.py` rewrites to the unit's build, so the tool should apply the
other market's ids and then "verify" its own write.

**Falsifier:** on the renamed EU card the tool still finds the EU consent id
`0x08a6` and patches that one site, i.e. the name never decided anything.

## Inputs

| Item | Value |
| --- | --- |
| EU card | `LEAF_2011-2012_QSD-309-101_navi158_eu.img` (7 456 MiB) |
| US card | `archive/leaf_2011_usa_sddump.img` (7 456 MiB) |
| NK1 | `firmware/unit-flash/nk1-QY7200ND.bin` |
| Card offsets | NKOK header NB00 `0x200000`, NB01 `0x2000000`; name `+0x16`, part number `+0x50`, `SUM4` `+0x34`; image A `0x200200` |
| Repo tools | `tools/ze0_consent.py`, `tools/card_mapcode.py`, `tools/selftest.py` |

## Method

1. **Sample and hash.** `sha256sum` of the three files above; both cards match
   `docs/research/image-versions.md` (C-001, C-070).
2. **Commands.** All runs are on reflinked scratch copies, so the originals are
   only read:

   ```bash
   S=$HOME/projekty/leafre-work/scratch/h143; mkdir -p "$S"
   EU=$HOME/Pobrane/LEAF_2011-2012_QSD-309-101_navi158_eu.img
   cp --reflink=auto "$EU" "$S/eu.img"; cp --reflink=auto "$EU" "$S/eu2.img"
   python3 tools/card_mapcode.py set --image "$S/eu.img" \
       --from-nk1 firmware/unit-flash/nk1-QY7200ND.bin --in-place
   python3 tools/card_mapcode.py set --image "$S/eu2.img" \
       --from-nk1 firmware/unit-flash/nk1-QY7200ND.bin --in-place
   # pre-fix behaviour of detect(), now reachable only by an explicit override
   python3 tools/ze0_consent.py patch  "$S/eu.img" --build us --in-place
   python3 tools/ze0_consent.py verify "$S/eu.img" --build us
   # fixed behaviour: identity from the part number
   python3 tools/ze0_consent.py find   "$S/eu2.img"
   python3 tools/ze0_consent.py patch  "$S/eu2.img" --in-place
   python3 tools/ze0_consent.py verify "$S/eu2.img"
   python3 tools/ze0_consent.py find archive/leaf_2011_usa_sddump.img
   python3 tools/ze0_consent.py --selftest
   python3 tools/selftest.py --only ze0_consent
   ```
3. **Controls.**
   - *Positive:* the pristine EU card yields one `0x08a6` site per copy; the US
     card yields two `0x089e` sites per copy (`find` on both).
   - *Negative:* the selftest synthesises a card with an unknown part number
     and requires `detect()` to exit non-zero; a mutated patch byte and a
     corrupted `SUM4` must be refused.
4. **Scope.** Image A (both NKOK copies) of the two 2011 cards, the consent
   comparator only. No L4 run: whether the patched EU card leaves
   `SRT_COLD_I_AGREE` in `-M ze0` stays with M8.C1p, which is blocked on the
   EU card never creating AuiApp/ScreenState. Nothing here says the patch
   behaves a given way in a car.
5. **Falsifier.** As in Hypothesis.

## Observations

**O1 — identity.** The first `0x200000` bytes are byte-identical on both cards:
`sha256 = c49b56595a3ef8d1d1fffc9098dd556a398b28da3119fbe95a76f86c74832137`
for the EU and the US card. The old `detect()` computed that hash and never
compared it. The fields that do differ are in the NKOK header at `0x200000`:
name `X210ECNI.158` vs `X210NBNI.147`, part number `470-2824-34` vs
`470-2818-33`.

**O2 — pre-fix behaviour on the renamed EU card** (reached with `--build us`):

```
build: US 2011 (part 470-2824-34)  agree 0x089e -> unlock 0x0889
patched copy 0x200000: 2 literal(s) 0x089e -> 0x0889 at 0x1405912,0x143f2c0; SUM4=0xcde37d9b over 0x1752c88 bytes
patched copy 0x2000000: 2 literal(s) 0x089e -> 0x0889 at 0x3205912,0x323f2c0; SUM4=0xcde37d9b over 0x1752c88 bytes
copy 0x200000: name=X210NBNI.147 SUM4 stored=0xcde37d9b computed=0xcde37d9b agree_id_replaced=True -> OK
copy 0x2000000: name=X210NBNI.147 SUM4 stored=0xcde37d9b computed=0xcde37d9b agree_id_replaced=True -> OK
verify: PASS
```

The EU consent comparator is the single `0x08a6` site found in O3, not either
of these two, so the write above changes two unrelated comparators and the
verify step passes because it searches for the id it just wrote.

**O3 — fixed behaviour, auto-detection on the same renamed card:**

```
note: NKOK name X210NBNI.147 is the launcher rename; card build is EU 2011 (part 470-2824-34)
build: EU 2011 (part 470-2824-34, NKOK name X210NBNI.147)  state index 610  SK_SCT_AGREE_CLICK id 0x08a6 -> SK_OTH_SCREEN_UNLOCK 0x0891
copy 0x0200000: name=X210NBNI.147 length=0x1752c88 stored SUM4=0xcdf87db0 computed=0xcdf87db0 OK
  site: mov.w at 0x13ebdde disp=0xae -> literal 0x13ebf3e = 0x08a6; cmp/eq at 0x13ebde0
copy 0x2000000: name=X210NBNI.147 length=0x1752c88 stored SUM4=0xcdf87db0 computed=0xcdf87db0 OK
  site: mov.w at 0x31ebdde disp=0xae -> literal 0x31ebf3e = 0x08a6; cmp/eq at 0x31ebde0
patched copy 0x200000: 1 literal(s) 0x08a6 -> 0x0891 at 0x13ebf3e; SUM4=0xcde37db0 over 0x1752c88 bytes
patched copy 0x2000000: 1 literal(s) 0x08a6 -> 0x0891 at 0x31ebf3e; SUM4=0xcde37db0 over 0x1752c88 bytes
verify: PASS
```

**O4 — US card (positive control for the other build):**

```
build: US 2011 (part 470-2818-33, NKOK name X210NBNI.147)  state index 609  SK_SCT_AGREE_CLICK id 0x089e -> SK_OTH_SCREEN_UNLOCK 0x0889
copy 0x0200000: ... stored SUM4=0x658b257c computed=0x658b257c OK
  site: mov.w at 0x1479a58 disp=0x1f -> literal 0x1479a9a = 0x089e; cmp/eq at 0x1479a5a
  site: mov.w at 0x147a03c disp=0xba -> literal 0x147a1b4 = 0x089e; cmp/eq at 0x147a03e
copy 0x2000000: ... the same two sites at +0x2000000
```

**O5 — tests.** `ze0_consent.py --selftest` prints 23 `ok` lines and
`selftest: PASS (0 failure(s))`; `selftest.py --only ze0_consent` prints
`tool:ze0_consent PASS` / `selftest: OK`.

## Interpretation

- **FACT:** the build name at NB00 `+0x16` is writable by design (it is what
  the unit compares with its kernel, C-8401) and `card_mapcode.py` rewrites
  it; the part number at `+0x50` is not touched by that tool or by the consent
  patch.
- **FACT:** on the EU 2011 card the consent comparator holds `0x08a6` in one
  site per copy; on the US 2011 card `0x089e` in two sites per copy. The id is
  therefore a property of the card build, and a wrong id scan can still find
  1–4 plausible-looking sites, which is why the count alone cannot choose.
- **OBSERVED:** the old detection had no identity at all — the hash it computed
  is identical on both cards and was never compared.
- **HYPOTHESIS (unchanged, M8.C1p):** redirecting the EU comparator to
  `0x0891` makes the EU card leave `SRT_COLD_I_AGREE` without a tap. Only an
  L4 run that reaches the state can show it.

## Conclusion

`tools/ze0_consent.py` now identifies the card by the NKOK part number
(`470-2824-34` EU 2011, `470-2818-33` US 2011), reports a renamed header as
the launcher rename, refuses an unknown card unless `--build eu|us` is given,
and has selftest cases for the renamed EU card, the US card, the unknown part
number and the forced override. `docs/hardware/eu-card-on-us-unit.md` now says
to run the consent patch before `card_mapcode.py` (or with `--build eu`) and
why. M8.C1p stays `blocked`: the EU patch is still unproven in L4.

## Overtaken by a later commit

none

## Reproduction

```bash
S=$HOME/projekty/leafre-work/scratch/h143; mkdir -p "$S"
cp --reflink=auto ~/Pobrane/LEAF_2011-2012_QSD-309-101_navi158_eu.img "$S/eu.img"
python3 tools/card_mapcode.py set --image "$S/eu.img" \
    --from-nk1 firmware/unit-flash/nk1-QY7200ND.bin --in-place
python3 tools/ze0_consent.py find "$S/eu.img"   # expected: EU 2011, one site 0x08a6 per copy
python3 tools/ze0_consent.py --selftest         # expected: PASS (0 failure(s))
```

## Follow-ups

- [ ] M8.C1p: re-run the patched EU card under `-M ze0` if any flash
  configuration ever reaches the consent state.
- [ ] Add the same part-number identity to any future tool that keys a patch on
  the card build.
