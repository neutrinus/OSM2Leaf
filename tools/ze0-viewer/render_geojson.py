#!/usr/bin/env python3
"""Render a decoded ZE0 GeoJSON to PNG (equirectangular, north up).

    python3 render_geojson.py IN.geojson OUT.png [--width 1400] [--height 0]

Pillow is used when available; without it the renderer falls back to a
standard-library PNG writer that draws outlines only (no fills).  The output
is a diagnostic view, not cartography: layers get fixed colours and there is
no label or road rendering yet.
"""
import argparse
import json
import math
import struct
import zlib

# layer -> RGB, and whether it is drawn before the others
COLORS = {
    0: (150, 140, 120),    # built-up
    1: (58, 96, 150),      # sea
    3: (58, 105, 64),      # forest / park
    4: (92, 112, 72),
    5: (104, 100, 74),
    7: (52, 88, 142),      # inland water
    8: (110, 110, 100),
    9: (120, 112, 84),
    11: (90, 70, 40),      # coastline
    25: (220, 50, 50),     # point labels / markers
    200: (70, 130, 220),   # ferry
    204: (130, 90, 60),    # other network
    205: (40, 40, 40),     # main road layer
    206: (190, 90, 30),    # second road layer
    400: (210, 50, 160),   # section-4 administrative point
}
DEFAULT_COLOR = (140, 140, 140)
BG = (204, 196, 174)   # land is implicit in this format: sea is drawn, land is not
LAND = (204, 196, 174)


def iter_points(geom):
    t = geom['type']
    if t == 'Point':
        yield geom['coordinates']
    elif t == 'LineString':
        yield from geom['coordinates']
    elif t == 'Polygon':
        for ring in geom['coordinates']:
            yield from ring
    elif t == 'MultiPolygon':
        for poly in geom['coordinates']:
            for ring in poly:
                yield from ring


def bounds(features):
    xs, ys = [], []
    for f in features:
        for x, y in iter_points(f['geometry']):
            xs.append(x); ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


def render_pil(features, out, width, height, coverage=(), view=None, labels=False):
    from PIL import Image, ImageDraw
    x0, y0, x1, y1 = view or bounds(features)
    if height <= 0:
        height = max(1, int(width * (y1 - y0) / max(1e-9, (x1 - x0))))
    sx = width / max(1e-9, x1 - x0)
    sy = height / max(1e-9, y1 - y0)

    def px(p):
        return ((p[0] - x0) * sx, (y1 - p[1]) * sy)

    img = Image.new('RGB', (width, height), BG)
    d = ImageDraw.Draw(img)

    cov_by_level = {}
    for rect in coverage:
        if len(rect) == 5:
            cov_by_level.setdefault(rect[4], []).append(rect[:4])
        else:
            cov_by_level.setdefault(0, []).append(rect)
    feats_by_level = {}
    for f in features:
        feats_by_level.setdefault(f['properties'].get('level', 0), []).append(f)

    # coarse first, fine last: the finest level that has a parcel repaints it
    for level in sorted(set(cov_by_level) | set(feats_by_level), reverse=True):
        for lon0, lat0, lon1, lat1 in cov_by_level.get(level, []):
            a, b = px((lon0, lat0)), px((lon1, lat1))
            d.rectangle([min(a[0], b[0]), min(a[1], b[1]),
                         max(a[0], b[0]), max(a[1], b[1])], fill=LAND)
        order = sorted(feats_by_level.get(level, []),
                       key=lambda f: (1 if f['properties'].get('road') else 0,
                                      f['properties'].get('layer') == 11,
                                      f['properties'].get('layer') == 25,
                                      f['properties'].get('layer') == 0))
        for f in order:
            p = f['properties']
            layer = p.get('layer', -1)
            geom = f['geometry']
            color = COLORS.get(layer, DEFAULT_COLOR)
            lw = 1
            if p.get('road'):
                # class word 0x140 behaves like a higher class than 0; one-way
                # uses the 0x3000 style flag (HYPOTHESIS, see ROUND3.md).
                color = (150, 30, 30) if p.get('class_word') == 0x140 else (45, 45, 45)
                lw = 2 if p.get('class_word') == 0x140 else 1
                if p.get('oneway'):
                    color = (40, 80, 160)
            if geom['type'] == 'Polygon':
                ring = [px(q) for q in geom['coordinates'][0]]
                if len(ring) >= 3:
                    d.polygon(ring, fill=color)
            elif geom['type'] == 'LineString':
                pts = [px(q) for q in geom['coordinates']]
                d.line(pts, fill=color, width=lw)
                if labels and p.get('name') and len(pts) >= 2:
                    mid = pts[len(pts) // 2]
                    d.text((mid[0] + 2, mid[1] - 8), p['name'], fill=(20, 20, 20))
            else:
                x, y = px(geom['coordinates'])
                d.ellipse([x - 2, y - 2, x + 2, y + 2], fill=color)
                if labels and p.get('names'):
                    d.text((x + 3, y - 3), ', '.join(p['names'][:2]), fill=(80, 0, 60))
    img.save(out)
    return width, height


class Canvas:
    """Minimal RGB canvas with line and point drawing, for the no-Pillow path."""
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.buf = bytearray(BG * (w * h))

    def point(self, x, y, c):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = 3 * (y * self.w + x)
            self.buf[i:i + 3] = bytes(c)

    def line(self, a, b, c):
        (x0, y0), (x1, y1) = a, b
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        while True:
            self.point(x0, y0, c)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy; x0 += sx
            if e2 <= dx:
                err += dx; y0 += sy

    def png(self, path):
        raw = b''.join(b'\x00' + bytes(self.buf[y * self.w * 3:(y + 1) * self.w * 3])
                       for y in range(self.h))

        def chunk(tag, data):
            return (struct.pack('>I', len(data)) + tag + data +
                    struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff))
        out = b'\x89PNG\r\n\x1a\n'
        out += chunk(b'IHDR', struct.pack('>IIBBBBB', self.w, self.h, 8, 2, 0, 0, 0))
        out += chunk(b'IDAT', zlib.compress(raw, 6))
        out += chunk(b'IEND', b'')
        open(path, 'wb').write(out)


def render_std(features, out, width, height, coverage=(), view=None, labels=False):
    x0, y0, x1, y1 = view or bounds(features)
    if height <= 0:
        height = max(1, int(width * (y1 - y0) / max(1e-9, (x1 - x0))))
    sx = width / max(1e-9, x1 - x0)
    sy = height / max(1e-9, y1 - y0)

    def px(p):
        return (int((p[0] - x0) * sx), int((y1 - p[1]) * sy))

    c = Canvas(width, height)
    for lon0, lat0, lon1, lat1 in coverage:
        a, b = px((lon0, lat0)), px((lon1, lat1))
        for yy in range(min(a[1], b[1]), max(a[1], b[1]) + 1):
            c.line((a[0], yy), (b[0], yy), LAND)
    for f in features:
        p = f['properties']; layer = p.get('layer', -1)
        color = COLORS.get(layer, DEFAULT_COLOR)
        geom = f['geometry']
        if geom['type'] == 'Point':
            x, y = px(geom['coordinates'])
            c.point(x, y, color); c.point(x + 1, y, color)
        else:
            pts = [px(q) for q in (geom['coordinates'][0] if geom['type'] == 'Polygon'
                                   else geom['coordinates'])]
            for a, b in zip(pts, pts[1:]):
                c.line(a, b, color)
    c.png(out)
    return width, height


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('geojson'); ap.add_argument('out')
    ap.add_argument('--width', type=int, default=1400)
    ap.add_argument('--height', type=int, default=0)
    ap.add_argument('--bbox', default='', help='lon0,lat0,lon1,lat1 view override')
    ap.add_argument('--labels', action='store_true', help='draw road names')
    args = ap.parse_args()
    gj = json.load(open(args.geojson))
    feats = gj['features']
    coverage = gj.get('ze0_coverage', [])
    view = tuple(float(x) for x in args.bbox.split(',')) if args.bbox else None
    if not feats:
        raise SystemExit('no features')
    try:
        w, h = render_pil(feats, args.out, args.width, args.height, coverage, view, args.labels)
    except ImportError:
        w, h = render_std(feats, args.out, args.width, args.height, coverage, view, args.labels)
    x0, y0, x1, y1 = view or bounds(feats)
    print('%s: %d features, %dx%d px, lon %.3f..%.3f lat %.3f..%.3f'
          % (args.out, len(feats), w, h, x0, x1, y0, y1))


if __name__ == '__main__':
    main()
