# -*- coding: utf-8 -*-
"""Fetch a high-zoom basemap crop for the core detail map (WGS-84 window)."""
import io
import json
import time
from basemap import build

if __name__ == "__main__":
    lon0, lat0, lon1, lat1 = 116.3110, 39.9410, 116.3960, 40.0310
    t0 = time.time()
    im, ext = build("light", 15, lon0, lat0, lon1, lat1)
    print("core %dx%d in %.1fs" % (im.size[0], im.size[1], time.time() - t0))
    im.save("base_core.png")
    with io.open("base_core_extent.json", "w", encoding="utf-8") as f:
        json.dump({"xmin": ext[0], "xmax": ext[1], "ymin": ext[2], "ymax": ext[3]}, f)
    im2, _ = build("ref", 15, lon0, lat0, lon1, lat1)
    im2.save("base_core_ref.png")
