# Headless Ghidra decompile of Navi.exe (M4.98)

`NaviDecomp.java` is a Ghidra post-script. It maps `Navi.exe`'s decompressed
`.data` at `0x55d000`, creates every function listed in `.pdata` (7,596 in EU
2011 build A), and writes the decompiled C of the functions that hold the given
VAs (or `ALL`). No auto-analysis runs, so it is fast (about 20 s to import, a
few seconds per batch of functions).

```bash
G=…/ghidra_11.4.2_PUBLIC          # Ghidra 11.4.2, JDK 21
W=…/navi; P=…/proj                 # scratch dirs, outside the repository
python3 tools/cerom.py --image-start 0x200200 archive/head256.img extract Navi.exe -o $W
python3 tools/cerom.py --image-start 0x200200 archive/head256.img decompress --modules Navi.exe --out $W/dec
$G/support/analyzeHeadless $P navi -import $W/Navi.exe.00011000.bin -overwrite -noanalysis \
  -processor SuperH4:LE:32:default -loader BinaryLoader -loader-baseAddr 0x11000 \
  -scriptPath tools/ghidra -postScript NaviDecomp.java \
  $W/dec/Navi.exe.0054d000.bin $W/dec/Navi.exe.0153f000.bin out.c 0x363834 0x3582a4
# later runs on the same project: -process Navi.exe.00011000.bin instead of -import …
```

The output is decompiled vendor code: keep it out of the repository; commit
only VAs, field rules and counts. Pool constants show as `_DAT_xxxxxxxx`; read
their values from the `.bin` files. `tools/callgraph.py callers/callees` gives
the call hierarchy around a function.
