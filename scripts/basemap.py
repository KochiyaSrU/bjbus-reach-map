# -*- coding: utf-8 -*-
"""Download & stitch Esri tiles for a lon/lat bbox; cache to disk."""
import io
import json
import math
import os
import time
import urllib.request

TILE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tiles")
if not os.path.isdir(TILE_DIR):
    os.makedirs(TILE_DIR)

BASE = {
    "light": "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
    "ref": "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}",
    "street": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",
}

R = 6378137.0


def merc(lon, lat):
    x = math.radians(lon) * R
    y = math.log(math.tan(math.pi / 4.0 + math.radians(lat) / 2.0)) * R
    return x, y


def lonlat_to_tile(lon, lat, z):
    n = 2.0 ** z
    x = (lon + 180.0) / 360.0 * n
    lat_r = math.radians(lat)
    y = (1.0 - math.log(math.tan(lat_r) + 1.0 / math.cos(lat_r)) / math.pi) / 2.0 * n
    return x, y


def tile_bounds(x, y, z):
    n = 2.0 ** z
    lon0 = x / n * 360.0 - 180.0
    lon1 = (x + 1) / n * 360.0 - 180.0
    lat1 = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    lat0 = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))
    return lon0, lat0, lon1, lat1


def fetch_tile(style, z, x, y):
    p = os.path.join(TILE_DIR, "%s_%d_%d_%d.png" % (style, z, x, y))
    if os.path.exists(p) and os.path.getsize(p) > 100:
        return p
    url = BASE[style].format(z=z, x=x, y=y)
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            data = urllib.request.urlopen(req, timeout=25).read()
            with open(p, "wb") as f:
                f.write(data)
            return p
        except Exception as e:
            if attempt == 2:
                raise
            time.sleep(1.0 + attempt)
    return p


def build(style, z, lon0, lat0, lon1, lat1, verbose=True, workers=12):
    from PIL import Image
    from concurrent.futures import ThreadPoolExecutor
    x0f, y0f = lonlat_to_tile(lon0, lat1, z)
    x1f, y1f = lonlat_to_tile(lon1, lat0, z)
    x0, x1 = int(math.floor(x0f)), int(math.floor(x1f))
    y0, y1 = int(math.floor(y0f)), int(math.floor(y1f))
    nx, ny = x1 - x0 + 1, y1 - y0 + 1
    if verbose:
        print("[tiles] %s z=%d grid %dx%d = %d tiles" % (style, z, nx, ny, nx * ny))
    canvas = Image.new("RGB", (nx * 256, ny * 256), (255, 255, 255))
    got = 0
    cells = [(i, j, x, y) for i, x in enumerate(range(x0, x1 + 1))
             for j, y in enumerate(range(y0, y1 + 1))]

    def one(c):
        i, j, x, y = c
        return i, j, fetch_tile(style, z, x, y)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for i, j, p in ex.map(one, cells):
            try:
                canvas.paste(Image.open(p).convert("RGB"), (i * 256, j * 256))
                got += 1
            except Exception as e:
                if verbose:
                    print("[tiles] bad tile z=%d %d/%d: %s" % (z, i, j, e))
    if verbose:
        print("[tiles] %s z=%d %d/%d tiles, %d workers" % (style, z, got, len(cells), workers))
    # geographic extent of the stitched canvas
    lt = tile_bounds(x0, y0, z)
    rb = tile_bounds(x1, y1, z)
    xmin = merc(lt[0], 0)[0]
    xmax = merc(rb[2], 0)[0]
    ymax = merc(0, lt[3])[1]
    ymin = merc(0, rb[1])[1]
    if verbose:
        print("[tiles] %s ok=%d/%d extent merc x %.0f..%.0f y %.0f..%.0f"
              % (style, got, nx * ny, xmin, xmax, ymin, ymax))
    return canvas, (xmin, xmax, ymin, ymax)


if __name__ == "__main__":
    reach = json.load(io.open("out_reach.json", encoding="utf-8"))["reach"]
    lon = [x["lon"] for x in reach]
    lat = [x["lat"] for x in reach]
    lon0, lon1 = min(lon) - 0.011, max(lon) + 0.011
    lat0, lat1 = min(lat) - 0.009, max(lat) + 0.009
    print("bbox %.4f %.4f %.4f %.4f" % (lon0, lat0, lon1, lat1))
    t0 = time.time()
    im, ext = build("light", 14, lon0, lat0, lon1, lat1)
    print("light %dx%d in %.1fs" % (im.size[0], im.size[1], time.time() - t0))
    im.save("base_light.png")
    with io.open("base_extent.json", "w", encoding="utf-8") as f:
        json.dump({"xmin": ext[0], "xmax": ext[1], "ymin": ext[2], "ymax": ext[3]}, f)
    im2, _ = build("ref", 14, lon0, lat0, lon1, lat1)
    im2.save("base_ref.png")
