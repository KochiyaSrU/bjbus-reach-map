# -*- coding: utf-8 -*-
"""Deliverable self-check: record counts across CSV / GeoJSON / DBF / SHP."""
import io
import json
import os
import struct
import sys


def check(folder):
    print("=" * 62)
    print(folder)
    csv_p = os.path.join(folder, u"60分钟可达站点明细.csv")
    gj_p = os.path.join(folder, u"60分钟可达站点.geojson")
    if not os.path.exists(csv_p):
        print("  no CSV -> 0-stop case (only 结果说明.md expected)")
        return
    n_csv = sum(1 for _ in io.open(csv_p, encoding="utf-8-sig")) - 1
    gj = json.load(io.open(gj_p, encoding="utf-8"))
    n_gj = len(gj["features"])
    shp = [f for f in os.listdir(folder) if f.endswith(".shp")]
    n_shp = None
    if shp:
        with open(os.path.join(folder, shp[0]), "rb") as f:
            head = f.read(100)
        n_shp = struct.unpack(">i", head[24:28])[0] * 2      # 16-bit words -> bytes
        n_shp = struct.unpack(">i", head[24:28])[0]
        # file length in 16-bit words includes the 100-byte header
        total = n_shp * 2
        with open(os.path.join(folder, shp[0]), "rb") as f:
            data = f.read()
        # count records
        cnt, i = 0, 100
        while i < len(data):
            rec_len = struct.unpack(">i", data[i + 4:i + 8])[0] * 2
            cnt += 1
            i += 8 + rec_len
        n_shp = cnt
        dbf = shp[0].replace(".shp", ".dbf")
        n_dbf = None
        if os.path.exists(os.path.join(folder, dbf)):
            with open(os.path.join(folder, dbf), "rb") as f:
                h = f.read(32)
            n_dbf = struct.unpack("<I", h[4:8])[0]
    else:
        n_dbf = None
    print("  CSV   %d" % n_csv)
    print("  GeoJSON %d" % n_gj)
    print("  SHP   %s" % n_shp)
    print("  DBF   %s" % n_dbf)
    ok = (n_csv == n_gj == n_shp == n_dbf)
    pngs = [f for f in os.listdir(folder) if f.endswith(".png")]
    print("  PNG   %d" % len(pngs))
    names = sorted(os.listdir(folder))
    print("  files %d: %s" % (len(names), ", ".join(names[:12])))
    print("  RESULT: %s" % ("OK" if ok and len(pngs) >= 2 else "MISMATCH"))


for d in sys.argv[1:]:
    if os.path.isdir(d):
        check(d)
