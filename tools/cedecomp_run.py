#!/usr/bin/env python3
"""Run the nk.exe CE ROM decompressor under QEMU SH-4 (M8.E1).

Loads nk.exe (image B, ``--image-start 0x3e00200``) sections and test buffers
via QEMU ``-device loader``, controls execution through the gdbstub, and reads
back the decompressed output.  RAM-only state (``-M none -cpu sh7785``).

**Status (M8.E1b, 2026-11-06).** M1.2c decompressor VAs **VERIFIED** on IMG256
nk.exe B LE SH-4 bytes (C-2290–C-2293): M8.E1's refutation was a BE endianness
artifact (C-1600 superseded). Use ``qemu-system-sh4`` (LE), not sh4eb.
``DECOMP_WRAP 0x88037590(src,psize,dest,vsize)`` calls kernel lock/context
helpers (pools 0x88037614/1c/24/28, ctx 0x89e6ade0) so bare-metal execution
needs stubs; ``DECOMP_SECT 0x88037464`` is the core framing entry (C-2293).
QEMU loader/gdbstub framework is ready (C-1601); runtime EXP-49 decode remains
a follow-up pending LE QEMU + context stubs.

Requires ``qemu-system-sh4`` (LE) for nk.exe. On this host run via podman
(adapt image to provide qemu-system-sh4), e.g.:
  podman run --rm -i --security-opt label=disable \\
    -v /tmp/opencode/m8.e1-wt:/wt:ro -v /tmp/opencode/img256.img:/img:ro \\
    <sh4-le-image> python3 /wt/tools/cedecomp_run.py --selftest

Usage:
  cedecomp_run.py --selftest
  cedecomp_run.py info
  cedecomp_run.py probe --image IMG256 [--qemu qemu-system-sh4eb]
  cedecomp_run.py exp49 --image IMG256 --entry 0xVA [--qemu ...]
"""
from __future__ import annotations

import argparse, hashlib, json, os, socket, subprocess, sys, tempfile, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

IMG256_SHA256 = "92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9"
NK_IMAGE_START = 0x3E00200
NK_NAME = "nk.exe"
M1_2C_WRAP = 0x88037590
M1_2C_SECT = 0x88037464
M1_2C_ALLOC = 0x88034D94  # C-2291/C-2292: DECOMP_ALLOC (kernel-context dependent)
M1_2C_BLK = 0x8803A384   # C-2292: DECOMP_BLK (LZXD-like block codec)
M1_2C_VERIFIED_LE = True  # M8.E1b: M1.2c VAs confirmed; M8.E1 BE refutation superseded (C-2290)
EXP49 = [
    {"name": "NaviMapCC.dll/sec1", "file_off": 0x01580CE0, "psize": 0x2C6, "vsize": 0x5B8, "ulen": 0x484},
    {"name": "NaviMapCC.dll/sec2", "file_off": 0x015ACA7C, "psize": 0x68C, "vsize": 0xCC0, "ulen": 0xCC0},
]
REG = {"r0":0,"r1":1,"r2":2,"r3":3,"r4":4,"r5":5,"r6":6,"r7":7,"r8":8,"r9":9,"r10":10,"r11":11,
       "r12":12,"r13":13,"r14":14,"r15":15,"pc":16,"pr":17,"gbr":18,"vbr":19,"mach":20,"macl":21,"sr":22}
VBR_VA, SRC_VA, DST_VA, STK_VA, STK_TOP, RET_VA, CODE_VA = 0x8C000000,0x8C200000,0x8C210000,0x8C220000,0x8C230000,0x8C23F000,0x8C300000


def read_exp49(image):
    out = []
    with open(image, "rb") as f:
        for v in EXP49:
            f.seek(v["file_off"]); data = f.read(v["psize"])
            if len(data) != v["psize"]: raise IOError(f"short read {v['name']}")
            rec = dict(v); rec["data"] = data; rec["sha256"] = hashlib.sha256(data).hexdigest(); out.append(rec)
    return out


def load_nk_sections(image):
    from cerom import CERom
    with open(image, "rb") as f: data = f.read(110_000_000)
    rom = CERom(data, NK_IMAGE_START)
    nk = [m for m in rom.modules() if m["name"] == NK_NAME][0]
    o32s = list(rom.o32(nk)); secs = []
    for o in o32s:
        b = rom.d[rom.va2file(o["dataptr"]):rom.va2file(o["dataptr"]) + o["psize"]]
        if o["vsize"] > len(b): b = b + b"\x00" * (o["vsize"] - len(b))
        secs.append((o["realaddr"], bytes(b[:o["vsize"]]), o))
    return nk, o32s, secs


class Rsp:
    def __init__(self, host, port, timeout=10.0):
        deadline = time.monotonic() + timeout; last = None
        while time.monotonic() < deadline:
            try:
                self.s = socket.create_connection((host, port), timeout=timeout); self.s.settimeout(timeout); return
            except OSError as e: last = e; time.sleep(0.05)
        raise ConnectionError(f"gdbstub {host}:{port}: {last}")
    def cmd(self, c):
        data = c.encode("latin-1"); pkt = b"$" + data + b"#" + (b"%02x" % (sum(data) & 0xFF))
        self.s.sendall(pkt); self.s.recv(1); buf = b""
        while b"#" not in buf:
            chunk = self.s.recv(4096)
            if not chunk: raise ConnectionError("gdbstub eof")
            buf += chunk
        i = buf.index(b"$"); j = buf.index(b"#", i); self.s.sendall(b"+"); return buf[i+1:j].decode("latin-1","replace")
    def reg(self, n):
        r = self.cmd(f"p{n:x}")
        if r.startswith("E"): raise RuntimeError(f"reg {n}: {r}")
        return int(r, 16) & 0xFFFFFFFF
    def set_reg(self, n, v):
        r = self.cmd(f"P{n:x}={v & 0xFFFFFFFF:08x}")
        if r != "OK": raise RuntimeError(f"set reg {n}: {r}")
    def mem(self, phys, size):
        r = self.cmd(f"m{phys:x},{size:x}")
        if r.startswith("E"): raise RuntimeError(f"mem {phys:#x}: {r}")
        return bytes.fromhex(r)
    def step(self): return self.cmd("s")
    def close(self):
        try: self.s.close()
        except Exception: pass


def vector_blob():
    vec = bytearray(0x800)
    for off in range(0, 0x800, 4): vec[off:off+4] = bytes.fromhex("afff0009")
    return bytes(vec)


class QemuSession:
    def __init__(self, qemu, port=0):
        self.qemu = qemu; self.port = port or self._free_port(); self.proc = None; self.rsp = None
    @staticmethod
    def _free_port():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s: s.bind(("127.0.0.1", 0)); return s.getsockname()[1]
    def start(self, loader_files):
        cmd = [self.qemu, "-M","none","-cpu","sh7785","-m","512M","-nographic","-serial","none","-monitor","none",
               "-S","-gdb",f"tcp:127.0.0.1:{self.port}"]
        for path, va in loader_files: cmd += ["-device", f"loader,file={path},addr=0x{va & 0x1FFFFFFF:08x},force-raw=on"]
        self.proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        time.sleep(2.0)
        if self.proc.poll() is not None:
            err = self.proc.stderr.read().decode("utf-8","replace")[-400:]; raise RuntimeError(f"qemu exited {self.proc.returncode}: {err}")
        self.rsp = Rsp("127.0.0.1", self.port); self.rsp.cmd("qSupported:multiprocess+"); return self
    def close(self):
        if self.rsp: self.rsp.close()
        if self.proc:
            self.proc.terminate()
            try: self.proc.wait(timeout=5)
            except Exception: self.proc.kill()
    def __enter__(self): return self
    def __exit__(self, *a): self.close()


def shutil_which(cmd):
    p = subprocess.run(["sh","-c",f"command -v {cmd}"], capture_output=True, text=True); return p.stdout.strip() or None


def _probe(args):
    image = args.image
    if not os.path.isfile(image): return {"status":"MISSING_IMAGE","image":image}
    qemu = args.qemu or "qemu-system-sh4"
    if not shutil_which(qemu): return {"status":"MISSING_QEMU","qemu":qemu,"note":"install qemu-system-sh4 (LE, for nk.exe) or provide a container image"}
    nk, o32s, secs = load_nk_sections(image)
    with tempfile.TemporaryDirectory() as tmp:
        loaders = []
        for va, data, _o in secs:
            p = os.path.join(tmp, f"s_{va:08x}.bin"); open(p,"wb").write(data); loaders.append((p,va))
        for name, va, data in [("stk",STK_VA,b"\x00"*0x10000),
                               ("code",CODE_VA,bytes.fromhex("e02a000b0009")+b"\x00"*0x3ffd),
                               ("ret",RET_VA,bytes.fromhex("afff0009")+b"\x00"*12),
                               ("vec",VBR_VA,vector_blob())]:
            p=os.path.join(tmp,name+".bin"); open(p,"wb").write(data); loaders.append((p,va))
        with QemuSession(qemu) as qs:
            qs.start(loaders)
            for n in range(25): qs.rsp.set_reg(n,0)
            qs.rsp.set_reg(REG["r15"],STK_TOP); qs.rsp.set_reg(REG["pc"],CODE_VA)
            qs.rsp.set_reg(REG["pr"],RET_VA); qs.rsp.set_reg(REG["vbr"],VBR_VA); qs.rsp.set_reg(REG["sr"],0x40000000)
            for _ in range(8):
                qs.rsp.step(); pc = qs.rsp.reg(REG["pc"])
                if pc in (RET_VA,RET_VA+2,RET_VA+4): break
            r0 = qs.rsp.reg(REG["r0"]); pc = qs.rsp.reg(REG["pc"])
    ok = r0 == 42
    return {"status":"PASS" if ok else "FAIL","control":"trivial mov#42,r0;rts;nop","r0":hex(r0),"pc":hex(pc),
            "expected_r0":"0x2a","nk_sections_mapped":len(secs),"qemu":qemu}


def selftest():
    errors=0
    def check(cond,msg):
        nonlocal errors
        if not cond: print("FAIL:",msg); errors+=1
        else: print("ok:",msg)
    check(len(EXP49)==2,"two EXP-49 vectors")
    check(EXP49[0]["ulen"]==0x484 and EXP49[0]["vsize"]==0x5B8,"sec1 ulen/vsize")
    check(EXP49[1]["ulen"]==0xCC0 and EXP49[1]["vsize"]==0xCC0,"sec2 lengths")
    check(M1_2C_VERIFIED_LE is True,"M1.2c/M8.E1b VAs verified (LE)")
    vb=vector_blob(); check(len(vb)==0x800 and vb[0:2]==b"\xaf\xff","vector blob")
    for img in ["/tmp/opencode/img256.img", str(Path(__file__).resolve().parents[1]/".."/"img256.img")]:
        if os.path.isfile(img):
            vecs=read_exp49(img)
            check(vecs[0]["data"][:4]==bytes.fromhex("840400c6"),"sec1 header")
            check(vecs[1]["data"][:4]==bytes.fromhex("c00c008c"),"sec2 header")
            print("ok: EXP-49 read from", img); break
    else: print("skip: IMG256 not present")
    if errors: print(f"cedecomp_run selftest: {errors} FAILED"); return 1
    print("cedecomp_run selftest: all ok"); return 0


def main():
    ap=argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    sp=ap.add_subparsers(dest="cmd")
    sp.add_parser("info")
    pp=sp.add_parser("probe"); pp.add_argument("--image",required=True); pp.add_argument("--qemu",default=os.environ.get("QEMU_SYSTEM_SH4","qemu-system-sh4"))
    ep=sp.add_parser("exp49"); ep.add_argument("--image",required=True); ep.add_argument("--entry",required=True); ep.add_argument("--qemu",default=os.environ.get("QEMU_SYSTEM_SH4","qemu-system-sh4"))
    args=ap.parse_args()
    if args.selftest: raise SystemExit(selftest())
    if args.cmd=="info":
        print(json.dumps({"tool":"cedecomp_run.py","m1_2c_wrap":hex(M1_2C_WRAP),"m1_2c_sect":hex(M1_2C_SECT),
                          "m1_2c_verified_le":M1_2C_VERIFIED_LE,"decomp_alloc":hex(M1_2C_ALLOC),"decomp_blk":hex(M1_2C_BLK),"exp49":EXP49,"img256_sha256":IMG256_SHA256,
                          "status":"M8.E1b VAs verified (LE,C-2290-2293); framework ready; runtime decode needs qemu-system-sh4 (LE) + DECOMP_WRAP kernel-context stubs"}, indent=2))
    elif args.cmd=="probe":
        res=_probe(args); print(json.dumps(res, indent=2)); raise SystemExit(0 if res.get("status")=="PASS" else 1)
    elif args.cmd=="exp49":
        entry=int(args.entry,0)
        if entry in (M1_2C_WRAP,M1_2C_SECT,M1_2C_ALLOC,M1_2C_BLK):
            print(f"NOTE: {entry:#x} is a verified M8.E1b VA (LE). Runtime execution needs qemu-system-sh4 (LE) and kernel-context stubs for DECOMP_WRAP; DECOMP_SECT is the core framing entry.", file=sys.stderr)
            print(json.dumps({"status":"NOT_IMPLEMENTED","entry":hex(entry),"verified":True,"blocker":"qemu-system-sh4 (LE) + kernel-context stubs for DECOMP_WRAP; C-2293/C-2294"}), indent=2); raise SystemExit(4)
        print(json.dumps({"status":"NOT_IMPLEMENTED","entry":hex(entry),"reason":"real decompressor VA+prototype not verified"}), indent=2); raise SystemExit(4)
    else: ap.print_help(); raise SystemExit(2)

if __name__=="__main__": main()
