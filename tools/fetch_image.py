#!/usr/bin/env python3
"""Pinned, resumable downloads of the vendor SD-card images (H16).

Several tasks listed "no vendor image on this machine" as a blocker, although
``files.viaaq.eu`` is reachable and AGENTS rule 11 forbids that blocker. This
helper holds the four known images with their size and, where it is known,
SHA-256, so nobody transcribes a URL or a hash by hand.

Images
    IMG256   first 256 MiB of the EU 2011 card (firmware A, B, C heads)
    EU2011   LEAF_2011-2012_QSD-309-101_navi158_eu.img  (7.5 GiB)
    US       LEAF_2011-2012_US.img                       (7.5 GiB)
    EU2014   LEAF_2014_EU_QSD-357-101.img                 (7.4 GiB)
    EU2016   ENV200_2016_EU_QSD-390-100.img               (7.4 GiB)

    ``--part 256M`` downloads the first 256 MiB of any listed image. The SHA-256
    of that head is pinned only for EU2011 (it is IMG256); full-image SHA-256 is
    pinned for EU2011, US, EU2014 and EU2016 (H21 audit).

Modes
    --list                                 print the table
    --image KEY [--part 256M] -o PATH      download, resume, verify
    --verify PATH [--image KEY [--part 256M]]
                                           check an existing file; without
                                           --image, match the file against every
                                           pin of the same size

Resume and failure
    The download goes to ``PATH.part`` and is moved to ``PATH`` only after the
    size and (if pinned) SHA-256 match. A network error keeps ``PATH.part`` so the
    next run continues with an HTTP Range request. A verification failure deletes
    ``PATH.part``. Either way ``PATH`` is never created unless it verified.

Examples
    python3 tools/fetch_image.py --list
    python3 tools/fetch_image.py --image IMG256 -o archive/head256.img
    python3 tools/fetch_image.py --verify archive/head256.img
    python3 tools/fetch_image.py --selftest

Exit codes: 0 ok, 1 download or verification failed, 2 usage error.
"""

from __future__ import annotations

import argparse
import hashlib
import http.server
import os
import socket
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

BASE_URL = "https://files.viaaq.eu/sd-images/"
# The host answers 403 to urllib's default User-Agent; identify the tool instead.
USER_AGENT = "fetch_image.py (OSM2Leaf research; +https://github.com/neutrinus/OSM2Leaf)"
CHUNK = 1 << 20
MIB = 1 << 20
PART_SIZES = {"256M": 256 * MIB}


@dataclass(frozen=True)
class Image:
    key: str
    file: str
    size: int
    sha256: str | None
    note: str


IMAGES: dict[str, Image] = {
    "EU2011": Image(
        "EU2011",
        "LEAF_2011-2012_QSD-309-101_navi158_eu.img",
        8_057_257_984,
        "105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307",
        "EU 2011 card, label QSD-309-101",
    ),
    "US": Image(
        "US",
        "LEAF_2011-2012_US.img",
        8_057_257_984,
        "53342430a1bb58d3ed6eb68c5563f079c710a400134d522e6192489b324c5383",
        "US 2011 card, label QSD-301-103",
    ),
    "EU2014": Image(
        "EU2014",
        "LEAF_2014_EU_QSD-357-101.img",
        7_969_177_600,
        "4a8a21f477e9fc511f94406976b8d67037842f9c043f49ab24e1adc82d6da89b",
        "EU 2014 card, label QSD-357-101",
    ),
    "EU2016": Image(
        "EU2016",
        "ENV200_2016_EU_QSD-390-100.img",
        7_969_177_600,
        "f53d55f159fd4232caa0b100b9b12e3910c8fe3849201871a71ee38ac19007fb",
        "EU 2016 card, label QSD-390-100",
    ),
}

# Head pins: (image key, part) -> (size, sha256). IMG256 is an alias for EU2011
# with part 256M, the head that the firmware tasks have used since M1.2.
PART_PINS: dict[tuple[str, str], tuple[int, str]] = {
    ("EU2011", "256M"): (
        256 * MIB,
        "92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9",
    ),
}
ALIASES: dict[str, tuple[str, str | None]] = {"IMG256": ("EU2011", "256M")}


class FetchError(Exception):
    """A refusal or failure that the user must see; exit code 1 or 2."""

    def __init__(self, message: str, code: int = 1) -> None:
        super().__init__(message)
        self.code = code


def resolve(key: str, part: str | None) -> tuple[Image, int, str | None]:
    """Return (image, expected size, pinned sha or None) for a key and part."""
    if key in ALIASES:
        alias_key, alias_part = ALIASES[key]
        if part not in (None, alias_part):
            raise FetchError(f"{key} is the {alias_part} head; --part {part} is not valid", 2)
        key, part = alias_key, alias_part
    if key not in IMAGES:
        raise FetchError(f"unknown image {key!r}; use --list", 2)
    image = IMAGES[key]
    if part is None:
        return image, image.size, image.sha256
    if part not in PART_SIZES:
        raise FetchError(f"unknown part {part!r}; known: {', '.join(PART_SIZES)}", 2)
    pin = PART_PINS.get((key, part))
    if pin is None:
        return image, PART_SIZES[part], None
    return image, pin[0], pin[1]


def url_for(image: Image, base_url: str = BASE_URL) -> str:
    return base_url + image.file


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def check(path: Path, size: int, sha256: str | None) -> list[str]:
    """Return a list of mismatch messages; an empty list means verified."""
    problems = []
    actual = path.stat().st_size
    if actual != size:
        problems.append(f"size {actual} != expected {size}")
    if sha256 is not None:
        got = sha256_of(path)
        if got != sha256:
            problems.append(f"sha256 {got} != pinned {sha256}")
    return problems


def download(url: str, part_path: Path, size: int, timeout: float = 60.0) -> None:
    """Fetch ``url`` into ``part_path``, resuming from its current length."""
    have = part_path.stat().st_size if part_path.exists() else 0
    if have > size:
        part_path.unlink()
        have = 0
    if have == size:
        return
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    request.add_header("Range", f"bytes={have}-{size - 1}")
    try:
        response = urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        if exc.code == 416 and have:
            # The server rejects a range past EOF: the part is complete.
            return
        raise FetchError(f"HTTP {exc.code} for {url}") from exc
    except (urllib.error.URLError, socket.timeout, OSError) as exc:
        raise FetchError(f"network error for {url}: {exc}; re-run to resume") from exc
    with response:
        if have and response.status != 206:
            # The server ignored Range: start over rather than append garbage.
            have = 0
        mode = "ab" if have else "wb"
        with part_path.open(mode) as handle:
            try:
                while True:
                    block = response.read(CHUNK)
                    if not block:
                        break
                    handle.write(block)
            except (OSError, socket.timeout) as exc:
                raise FetchError(f"transfer interrupted: {exc}; re-run to resume") from exc


def fetch(key: str, part: str | None, out: Path, base_url: str = BASE_URL, force: bool = False) -> str:
    image, size, sha256 = resolve(key, part)
    if out.exists() and not force:
        raise FetchError(f"{out} exists; pass --force to replace it", 2)
    part_path = out.with_name(out.name + ".part")
    url = url_for(image, base_url)
    download(url, part_path, size)
    problems = check(part_path, size, sha256)
    if problems:
        part_path.unlink(missing_ok=True)
        raise FetchError("verification failed: " + "; ".join(problems))
    if sha256 is None:
        note = "size verified; no SHA-256 pinned"
    else:
        note = "SHA-256 verified"
    os.replace(part_path, out)
    return f"{out}: {size} bytes, {note}"


def verify(path: Path, key: str | None, part: str | None) -> str:
    if not path.is_file():
        raise FetchError(f"{path} is not a file", 2)
    if key is not None:
        _, size, sha256 = resolve(key, part)
        problems = check(path, size, sha256)
        if problems:
            raise FetchError(f"{path}: " + "; ".join(problems))
        return f"{path}: matches {key}{'' if part is None else ' ' + part}"
    size = path.stat().st_size
    got = sha256_of(path)
    matches = []
    for image in IMAGES.values():
        if image.size == size and image.sha256 == got:
            matches.append(image.key)
    for (pkey, ppart), (psize, psha) in PART_PINS.items():
        if psize == size and psha == got:
            matches.append(f"{pkey} {ppart}")
    if not matches:
        raise FetchError(f"{path}: size {size}, sha256 {got}: no pinned match")
    return f"{path}: {size} bytes, sha256 {got}: matches {', '.join(matches)}"


def listing() -> str:
    rows = [f"{'KEY':8} {'SIZE':>14}  {'SHA-256':64}  FILE"]
    for image in IMAGES.values():
        rows.append(f"{image.key:8} {image.size:>14}  {image.sha256 or '(not pinned)':64}  {image.file}")
    rows.append("")
    rows.append("IMG256 = EU2011 --part 256M (size 268435456, sha256 pinned)")
    rows.append(f"base URL: {BASE_URL}")
    return "\n".join(rows)


def run(argv: list[str] | None = None, base_url: str = BASE_URL) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--list", action="store_true", help="print the image table")
    parser.add_argument("--image", metavar="KEY", help="IMG256, EU2011, US, EU2014 or EU2016")
    parser.add_argument("--part", metavar="SIZE", help="only the first SIZE bytes (256M)")
    parser.add_argument("-o", "--output", type=Path, metavar="PATH", help="where to write the image")
    parser.add_argument("--force", action="store_true", help="replace an existing output")
    parser.add_argument("--verify", type=Path, metavar="PATH", help="check an existing file")
    parser.add_argument("--selftest", action="store_true", help="run the built-in tests")
    args = parser.parse_args(argv)

    try:
        if args.selftest:
            return selftest()
        if args.list:
            print(listing())
            return 0
        if args.verify is not None:
            print(verify(args.verify, args.image, args.part))
            return 0
        if args.image is None or args.output is None:
            parser.error("--image KEY and -o PATH are required (or --list / --verify)")
        print(fetch(args.image, args.part, args.output, base_url, args.force))
        return 0
    except FetchError as exc:
        print(f"fetch_image: {exc}", file=sys.stderr)
        return exc.code


# ---------------------------------------------------------------- self-test


class _RangeHandler(http.server.BaseHTTPRequestHandler):
    """Serves one fixture file with HTTP Range support (206/416)."""

    payload: bytes = b""
    honour_range = True

    def log_message(self, *args: object) -> None:  # keep test output quiet
        return

    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        data = self.payload
        start = 0
        header = self.headers.get("Range")
        if header and self.honour_range:
            start = int(header.split("=", 1)[1].split("-", 1)[0])
            if start >= len(data):
                self.send_response(416)
                self.end_headers()
                return
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{len(data) - 1}/{len(data)}")
        else:
            self.send_response(200)
        body = data[start:]
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _serve(payload: bytes, honour_range: bool = True) -> tuple[http.server.HTTPServer, str]:
    handler = type("Handler", (_RangeHandler,), {"payload": payload, "honour_range": honour_range})
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/"


def selftest() -> int:
    failures: list[str] = []

    def expect(name: str, ok: bool) -> None:
        print(("ok   " if ok else "FAIL ") + name)
        if not ok:
            failures.append(name)

    def expect_raises(name: str, fn, code: int | None = None) -> None:
        try:
            fn()
        except FetchError as exc:
            expect(name, code is None or exc.code == code)
        else:
            expect(name, False)

    payload = bytes(range(256)) * 4096  # 1 MiB fixture, deterministic
    payload_sha = hashlib.sha256(payload).hexdigest()
    fixture = Image("FIX", "fixture.img", len(payload), payload_sha, "fixture")

    with tempfile.TemporaryDirectory(prefix="fetch-image-") as tmp:
        root = Path(tmp)
        server, base = _serve(payload)
        try:
            # 1. Pinned fixture downloads, verifies, no .part left behind.
            out = root / "fixture.img"
            url = url_for(fixture, base)
            download(url, out.with_name(out.name + ".part"), fixture.size)
            problems = check(out.with_name(out.name + ".part"), fixture.size, fixture.sha256)
            expect("download of pinned fixture verifies", problems == [])
            (out.with_name(out.name + ".part")).rename(out)

            # 2. Resume: a truncated .part is continued with a Range request.
            resume = root / "resume.img"
            part = resume.with_name(resume.name + ".part")
            part.write_bytes(payload[: len(payload) // 3])
            download(url_for(fixture, base), part, fixture.size)
            expect("resume continues a truncated part", part.read_bytes() == payload)

            # 3. Server that ignores Range: the part restarts, not appends.
            ignore_server, ignore_base = _serve(payload, honour_range=False)
            try:
                bad = root / "norange.img"
                badpart = bad.with_name(bad.name + ".part")
                badpart.write_bytes(payload[:1000])
                download(url_for(fixture, ignore_base), badpart, fixture.size)
                expect("server without Range restarts the part", badpart.read_bytes() == payload)
            finally:
                ignore_server.shutdown()

            # 4. Wrong pinned hash: refused, no .part, no output.
            wrong = Image("WRONG", "fixture.img", len(payload), "0" * 64, "bad pin")
            target = root / "wrong.img"
            expect_raises(
                "hash mismatch is refused",
                lambda: _fetch_with(wrong, base, target),
            )
            expect("hash mismatch leaves no output or part",
                   not target.exists() and not target.with_name(target.name + ".part").exists())

            # 5. Wrong size: refused.
            short = Image("SHORT", "fixture.img", len(payload) + 1, None, "bad size")
            target = root / "short.img"
            expect_raises("size mismatch is refused", lambda: _fetch_with(short, base, target))
            expect("size mismatch leaves no output or part",
                   not target.exists() and not target.with_name(target.name + ".part").exists())

            # 6. Network failure keeps the part for a later resume.
            dead_url = "http://127.0.0.1:9/none.img"
            keep = root / "keep.img"
            keep_part = keep.with_name(keep.name + ".part")
            keep_part.write_bytes(payload[:500])
            expect_raises("unreachable host is refused", lambda: download(dead_url, keep_part, len(payload)))
            expect("network failure keeps the part", keep_part.exists() and keep_part.stat().st_size == 500)

            # 7. Existing output is not overwritten without --force.
            expect_raises(
                "existing output needs --force",
                lambda: fetch("EU2011", None, out, base, force=False),
                code=2,
            )
        finally:
            server.shutdown()

        # 8. verify: matching and non-matching files.
        ok_file = root / "ok.bin"
        ok_file.write_bytes(payload)
        expect("verify without pin reports no match for a fixture",
               _raises(lambda: verify(ok_file, None, None)))
        expect_raises("verify against wrong image refuses", lambda: verify(ok_file, "EU2011", None))
        expect_raises("unknown image refused", lambda: resolve("NOPE", None), code=2)
        expect_raises("unknown part refused", lambda: resolve("US", "1G"), code=2)
        expect_raises("IMG256 with another part refused", lambda: resolve("IMG256", "1G"), code=2)

        # 9. Pins are consistent: IMG256 resolves to the 256M head pin.
        image, size, sha = resolve("IMG256", None)
        expect("IMG256 resolves to EU2011 256M head",
               image.key == "EU2011" and size == 256 * MIB and sha == PART_PINS[("EU2011", "256M")][1])
        expect("EU2016 full image is SHA-256 pinned",
               resolve("EU2016", None)[2] == IMAGES["EU2016"].sha256 and IMAGES["EU2016"].sha256 is not None)
        expect("un-pinned part resolves with sha None", resolve("EU2014", "256M")[2] is None)
        expect("listing names all five keys", all(k in listing() for k in ("IMG256", "EU2011", "US", "EU2014", "EU2016")))

    print("failures: %d" % len(failures))
    return 1 if failures else 0


def _fetch_with(image: Image, base: str, target: Path) -> str:
    """Run fetch() with a custom image entry (fixtures only)."""
    global IMAGES
    saved = IMAGES
    IMAGES = {**IMAGES, image.key: image}
    try:
        return fetch(image.key, None, target, base, force=True)
    finally:
        IMAGES = saved


def _raises(fn) -> bool:
    try:
        fn()
    except FetchError:
        return True
    return False


if __name__ == "__main__":
    sys.exit(run())
