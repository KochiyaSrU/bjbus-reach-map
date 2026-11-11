# -*- coding: utf-8 -*-
"""Write the delivery tables: CSV + GeoJSON of everything reachable in 60 min."""
import io
import json
import csv
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    with io.open(os.path.join(HERE, name), encoding="utf-8") as f:
        return json.load(f)


KIND_CN = {"direct": u"直达", "walk": u"步行", "transfer": u"换乘一次"}
KIND_EN = {"direct": "direct", "walk": "walk", "transfer": "transfer"}


def origin_name():
    try:
        with io.open(os.path.join(HERE, "out_origin.txt"), encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return "reach60"


def main():
    reach = load("out_reach_geo.json")["reach"]
    reach.sort(key=lambda z: (z["t"], z["stop"]))

    with io.open(os.path.join(HERE, u"60分钟可达站点明细.csv"), "w",
                 encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow([u"站点名称", u"经度", u"纬度", u"预计总耗时(分钟)", u"类型",
                    u"换乘站", u"第1程线路", u"第2程线路", u"经停线路数",
                    u"第1程乘车(分钟)", u"第2程乘车(分钟)", u"候车1(分钟)", u"候车2(分钟)", u"换乘步行(分钟)"])
        for x in reach:
            w.writerow([
                x["stop"], "%.6f" % x["lon"], "%.6f" % x["lat"], "%.1f" % (x["t"] / 60.0),
                KIND_CN.get(x["kind"], u"换乘一次"),
                x.get("via") or "", x["legs"][0], x["legs"][1] if len(x["legs"]) > 1 else "",
                x.get("n_lines", ""),
                "%.1f" % (x.get("leg1_ride", 0) / 60.0) if x["kind"] == "transfer" else "",
                "%.1f" % (x.get("leg2_ride", 0) / 60.0) if x["kind"] == "transfer" else "",
                "%.1f" % (x.get("wait1", 0) / 60.0) if x["kind"] == "transfer" else "",
                "%.1f" % (x.get("wait2", 0) / 60.0) if x["kind"] == "transfer" else "",
                "%.1f" % (x.get("walk", 0) / 60.0) if x["kind"] == "transfer" else "",
            ])

    feats = []
    for x in reach:
        feats.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [round(x["lon"], 6), round(x["lat"], 6)]},
            "properties": {
                "name": x["stop"],
                "minutes": round(x["t"] / 60.0, 1),
                "type": KIND_EN.get(x["kind"], "transfer"),
                "leg1": x["legs"][0],
                "leg2": x["legs"][1] if len(x["legs"]) > 1 else "",
                "via": x.get("via") or "",
                "n_lines": x.get("n_lines", 0),
            },
        })
    gj = {"type": "FeatureCollection",
          "name": origin_name(),
          "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
          "features": feats}
    with io.open(os.path.join(HERE, "60分钟可达站点.geojson"), "w", encoding="utf-8") as f:
        f.write(json.dumps(gj, ensure_ascii=False))

    # compact version for arcpy (ascii-safe columns)
    with io.open(os.path.join(HERE, "for_arcpy.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["NAME", "LON", "LAT", "MINUTES", "TYPE", "LEG1", "LEG2", "VIA", "NLINES"])
        for x in reach:
            w.writerow([x["stop"], "%.6f" % x["lon"], "%.6f" % x["lat"], "%.1f" % (x["t"] / 60.0),
                        KIND_EN.get(x["kind"], "transfer"),
                        x["legs"][0], x["legs"][1] if len(x["legs"]) > 1 else "",
                        x.get("via") or "", x.get("n_lines", 0)])
    print("stops:", len(reach))


if __name__ == "__main__":
    main()
