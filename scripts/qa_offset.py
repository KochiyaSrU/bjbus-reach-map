# -*- coding: utf-8 -*-
"""Coordinate-bias self check: the stop cloud should align with the basemap roads.

    python qa_offset.py          # run inside a project directory

It reports the shift that would best align stops with roads.  Anything much
larger than a few pixels means the GCJ-02 -> WGS-84 conversion is missing.
"""
import io
import json
import math
import os
import sys

import numpy as np
from PIL import Image

R = 6378137.0


def merc(lon, lat):
    lon = np.asarray(lon, dtype=float)
    lat = np.asarray(lat, dtype=float)
    return (np.radians(lon) * R,
            np.log(np.tan(np.pi / 4 + np.radians(lat) / 2)) * R)


def load(n):
    with io.open(n, encoding="utf-8") as f:
        return json.load(f)


def measure(base, ext, stops, step=1, span=120):
    im = np.asarray(Image.open(base).convert("L")).astype(np.float32)
    H, W = im.shape
    xmin, xmax = ext["xmin"], ext["xmax"]
    ymin, ymax = ext["ymin"], ext["ymax"]
    X, Y = merc([s["lon"] for s in stops], [s["lat"] for s in stops])
    px = (X - xmin) / (xmax - xmin) * W
    py = (ymax - Y) / (ymax - ymin) * H
    ok = (px > span + 2) & (px < W - span - 2) & (py > span + 2) & (py < H - span - 2)
    px, py = px[ok], py[ok]
    if len(px) < 20:
        return None, W / (xmax - xmin), len(px)
    best = None
    for dy in range(-span, span + 1, step):
        for dx in range(-span, span + 1, step):
            ix = np.clip(px + dx, 0, W - 1).astype(int)
            iy = np.clip(py + dy, 0, H - 1).astype(int)
            v = im[iy, ix].mean()
            if best is None or v > best[0]:
                best = (v, dx, dy)
    return best, W / (xmax - xmin), len(px)


def main():
    reach = load("out_reach_geo.json")["reach"]
    ok = True
    measured = False
    for base, extfile, label in (("base_light.png", "base_extent.json", "overview"),
                                 ("base_core.png", "base_core_extent.json", "core")):
        if not (os.path.exists(base) and os.path.exists(extfile)):
            print("%-9s skipped (missing %s / %s)" % (label, base, extfile))
            continue
        ext = load(extfile)
        # only stops inside this raster
        pts = [s for s in reach
               if ext["xmin"] <= merc(s["lon"], s["lat"])[0] <= ext["xmax"]
               and ext["ymin"] <= merc(s["lon"], s["lat"])[1] <= ext["ymax"]]
        if len(pts) < 12:
            print("%-9s SKIPPED - only %d stops inside, NOT checked" % (label, len(pts)))
            continue
        best, ppm, n = measure(base, ext, pts)
        if best is None:
            print("%-9s skipped (not enough stops near the middle)" % label)
            continue
        v, dx, dy = best
        measured = True
        print("%-9s n=%4d  best shift dx=%+d dy=%+d px  (%.0f m E, %.0f m N)"
              % (label, n, dx, dy, dx / ppm, -dy / ppm))
        if abs(dx) > 6 or abs(dy) > 6:
            ok = False
    print("")
    if not measured:
        print("NOT CHECKED: no basemap available - run basemap.py first")
        return
    print("OK: stops align with the basemap" if ok
          else "WARNING: systematic offset - check the GCJ-02 -> WGS-84 conversion")


if __name__ == "__main__":
    main()
