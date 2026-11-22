"""M9.65 positive control: the bound STDDLL in vcard_l3 answers like poi_position_l3.

``poi_position_l3`` runs each POINT010 name record through ``Navi.exe``
``fn 0x003c032c`` and its own ``STDDLL`` engine.  Here the **same** records go
through ``poi_position_l3`` (its verdict is the reference) and the mesh point it
returns is fed to ``STD_MeshPnt_isValid`` **inside** a ``vcard_l3.Machine``
whose ``STDDLL.dll`` the M9.65 native binding loaded.  No verdict is
recomputed: the agreement is between two independent loads of the factory
module on identical input.

Usage: m9.65-stddll-parity.py IMG --dir PAIRS --file POINT010
"""
import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, "tools")
sys.path.insert(0, "tools/l3_harness")
import poi_position_l3 as P     # noqa: E402
import point_walk_l3 as pw      # noqa: E402
import vcard_l3 as V            # noqa: E402

EXPORTS = ("STD_MeshPnt_isValid",)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--dir", required=True)
    ap.add_argument("--file", default="POINT010")
    ap.add_argument("--count", type=int, default=3)
    args = ap.parse_args(argv)

    image = pw.load_image(args.image)
    ref = P.Firmware(image)
    reng = ref.engine()
    card = V.make_card(None, "archive/sd-images/LEAF_2011-2012_QSD-309-101_navi158_eu.img", {})
    bound = V.Machine(Path(args.image).read_bytes(), card, imports_text="",
                      native=("STDDLL.dll", EXPORTS))
    isv = bound.native["STD_MeshPnt_isValid"]

    recs = P.name_records(Path(args.dir), args.file)
    normal = [r for r in recs if 1 <= r[0] >> 5 <= 3 and r[0] & 0xFC != 0xFC]
    step = max(1, len(normal) // args.count)
    sample = normal[::step][:args.count]
    mp_va = bound.malloc(0x10)
    agree = total = 0
    for rec in sample:
        res = P.firmware_position(ref, reng, rec)
        if res["status"] != 0:
            continue
        bound.put(mp_va, struct.pack("<Ihh", res["mesh_id"], res["x"], res["y"]))
        bound.eng.set_regs(r15=V.STACK_VA + V.STACK_SIZE - 0x1000)
        mine = bound.eng.call(isv, [mp_va])
        total += 1
        agree += mine == 1
        print("record %s -> mesh %08x x=%d y=%d  isValid=%d"
              % (rec[:8].hex(), res["mesh_id"], res["x"], res["y"], mine))
    print("isValid parity: %d/%d" % (agree, total))
    return 0 if total and agree == total else 1


if __name__ == "__main__":
    sys.exit(main())
