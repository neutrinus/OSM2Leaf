"""M4.55 negative: drive the RPF section-2 consumer and record where it stops.

Self-contained reproduction of EXP-2026-11-21-M4.55-rpf-consumer-import-block.
Run from the repo root with the EU 2011 card and firmware head in archive/.
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

c = R.Client(IMG, V.make_card(None, CARD, {}), (51.70, 17.45))
m = c.m
eng = m.eng

# 1. Ask the data-access task for section 2 of the level-1 record via kind 8.
res = c.request(0xA68CD68C, 0, 8, dump=64)
e = [x for rp in res["replies"] if "entries" in rp
     for x in rp["entries"] if x["status"] == 1][0]
print("reply: kind=%#x mesh=%#x ptrs=%s unit0=%#x"
      % (e["kind"], e["mesh"], [hex(p) for p in e["ptrs"]], e["ptrs"][0]))

# 2. Init the RPF globals, then hand the reply list to the consumer.
m.call(RPF_INIT, [], max_insns=2_000_000)
LIST = m.malloc(0x2004)
lb = bytearray(0x2004)
struct.pack_into("<H", lb, 0, 1)
struct.pack_into("<H", lb, 4, 1)
struct.pack_into("<I", lb, 8, e["kind"])
struct.pack_into("<I", lb, 12, e["word8"] & 0xFFFFFFFF)
struct.pack_into("<H", lb, 14, e["divid"])
struct.pack_into("<I", lb, 16, e["mesh"])
for i, p in enumerate(e["ptrs"]):
    struct.pack_into("<I", lb, 20 + 4 * i, p)
m.put(LIST, bytes(lb))
SEQ = 0x00A680D680
m.put(G + 4, struct.pack("<I", e["mesh"]))
m.put(G + 20, struct.pack("<I", SEQ))
m.put(G + 24, struct.pack("<I", SEQ + 1))
m.put(G + 28, struct.pack("<I", SEQ + 2))
MSG = m.malloc(0x40)
mb = bytearray(0x40)
struct.pack_into("<HH", mb, 8, 0x14B6, 5)
struct.pack_into("<I", mb, 12, 1)
struct.pack_into("<I", mb, 20, LIST)
struct.pack_into("<I", mb, 28, SEQ)
m.put(MSG, bytes(mb))

start = m.malloc(0x20)
tmp1 = m.malloc(0x20)
tmp2 = m.malloc(0x20)
g8, g12, g16 = m.u32(G + 8), m.u32(G + 12), m.u32(G + 16)
for v, nm in ((g8, "g8"), (g12, "g12"), (g16, "g16")):
    eng.watch(v, v + 0x804, "rw", nm)
eng.arm_watch()
try:
    r0 = m.call(RPF_CONSUMER, [start, tmp1, tmp2, g8],
                stack_args=[g12, g16], max_insns=40_000_000)
    print("consumer returned r0 %#x" % r0)
except Exception as ex:                     # noqa: BLE001 - the fault is the result
    print("consumer fault: %s: %s" % (type(ex).__name__, str(ex)[:220]))

u0 = [h for h in eng.watch_hits() if h.name == "unit0"]
print("unit0 reads: %d" % len(u0))
for h in u0[:20]:
    print("  pc %08x off %d size %d val %#x"
          % (h.pc, h.va - e["ptrs"][0], h.size,
             int.from_bytes(eng.read_mem(h.va, h.size), "little")))
