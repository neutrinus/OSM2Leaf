"""M4.55: drive the RPF section-2 consumer with the M9.65 native STDDLL binding.

Self-contained reproduction of EXP-2026-11-21-M4.55-rpf-consumer-import-block.
Run from the repo root with the EU 2011 card and firmware head in archive/.

M9.65 binds a second module: ``Client(... native=("STDDLL.dll", EXPORTS))``
loads STDDLL's real executable sections and re-points the Navi.exe import slots
at the export VAs, so the thunk ``0x003d1640`` runs STDDLL's own
``STD_MeshPnt_isValid`` (no host stub).  The consumer now passes its two
``isValid`` calls and the ``STD_MeshID_getAny`` it makes next; the unit-0
pointer is copied into the reply buffer at ``0x0061a020`` rather than
dereferenced here (see the EXP).
"""
import struct
import sys

sys.path.insert(0, "tools")
sys.path.insert(0, "tools/l3_harness")
import datask_req_l3 as R      # noqa: E402
import vcard_l3 as V            # noqa: E402

IMG = "archive/head256.img"
CARD = "archive/sd-images/LEAF_2011-2012_QSD-309-101_navi158_eu.img"
G = 0x0061A824                  # RPF globals (EU2011), found by the driver
RPF_INIT = 0x003360BC
RPF_CONSUMER = 0x003367A0       # the function 0x00336BF0 calls with the reply list
EXPORTS = ("STD_MeshPnt_isValid", "STD_MeshPnt_chgLv", "STD_MeshID_judgeLevel",
           "STD_MeshPnt_initPrm", "STD_MeshPnt_chgMapPnt", "STD_MeshID_getAny")

c = R.Client(IMG, V.make_card(None, CARD, {}), (51.70, 17.45),
             native=("STDDLL.dll", EXPORTS))
m = c.m
eng = m.eng

# 1. Ask the data-access task for section 2 of the level-1 record via kind 8.
res = c.request(0xA68CD68C, 0, 8, dump=64)
e = [x for rp in res["replies"] if "entries" in rp
     for x in rp["entries"] if x["status"] == 1][0]
print("reply: kind=%#x mesh=%#x ptrs=%s unit0=%#x"
      % (e["kind"], e["mesh"], [hex(p) for p in e["ptrs"]], e["ptrs"][0]))

# 2. Prep the RPF globals and a 32-byte reply list, then run the consumer with
#    two *valid* mesh points (isValid must be 1 for the unit-0 branch).
m.call(RPF_INIT, [], max_insns=2_000_000)
LIST = m.malloc(0x2004)
lb = bytearray(0x2004)
struct.pack_into("<H", lb, 0, 1)                       # one reply entry
struct.pack_into("<I", lb, 8, e["kind"])
struct.pack_into("<I", lb, 12, e["word8"] & 0xFFFFFFFF)
struct.pack_into("<H", lb, 14, e["divid"])
struct.pack_into("<I", lb, 16, e["mesh"])
struct.pack_into("<I", lb, 20, e["ptrs"][0])
m.put(LIST, bytes(lb))
A = m.malloc(0x10)
B = m.malloc(0x10)
m.put(A, struct.pack("<Ihh", e["mesh"], 100, 200))     # origin, valid level-1
m.put(B, struct.pack("<Ihh", e["mesh"], 300, 400))     # destination
SEQ = 0x00A680D680
m.put(G + 4, struct.pack("<I", e["mesh"]))
m.put(G + 20, struct.pack("<I", SEQ))
m.put(G + 24, struct.pack("<I", SEQ + 1))
m.put(G + 28, struct.pack("<I", SEQ + 2))

eng.watch(e["ptrs"][0], e["ptrs"][0] + 0x1000, "r", "unit0")
eng.arm_watch()
try:
    r0 = m.call(RPF_CONSUMER, [LIST, A, B, G + 8],
                stack_args=[G + 12, G + 16], max_insns=40_000_000)
    print("consumer returned r0 %#x" % r0)
except Exception as ex:                     # noqa: BLE001 - the fault is the result
    print("consumer fault: %s: %s" % (type(ex).__name__, str(ex)[:220]))

u0 = [h for h in eng.watch_hits() if h.name == "unit0"]
print("unit0 reads: %d" % len(u0))
for h in u0[:20]:
    print("  pc %08x off %d size %d val %#x"
          % (h.pc, h.va - e["ptrs"][0], h.size,
             int.from_bytes(eng.read_mem(h.va, h.size), "little")))
