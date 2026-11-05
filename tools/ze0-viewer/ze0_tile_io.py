#!/usr/bin/env python3
"""Tile writer wrapper with a preserve fallback for unchanged factory tiles.

`clarion_tile.write_tile` reconstructs the container in its own layout.  On the
2011 reference that layout happens to be byte-identical to the factory file.
The 2013-2016 dense `B30R048R` uses shared/earlier blocks and a non-monotonic
layout that the writer compacts, so an unchanged factory tile would not
round-trip.

`write_tile` first runs the real writer (so unchanged 2011 and all changed
tiles still exercise it).  If the result differs and the caller allows
preserve, the tile is unchanged (`_dirty` is false) and we return the source
bytes.  This is the tile equivalent of the preserved-stream `.cmp` writer: the
container is understood, but an unmodified tile is kept verbatim.
"""
from __future__ import annotations

import clarion_tile


def write_tile(tile, allow_preserve: bool = True, **kwargs):
    out = clarion_tile.write_tile(tile, **kwargs)
    src = tile.get("_src")
    if (
        allow_preserve
        and src is not None
        and not tile.get("_dirty")
        and out != src
    ):
        tile["_preserved"] = True
        return bytes(src)
    tile["_preserved"] = False
    return out
