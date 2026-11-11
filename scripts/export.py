# -*- coding: utf-8 -*-
"""Export reach to CSV + build per-stop route counts (importance) and route geoms."""
import io
import json
import csv
import math
import os

from q import _key
from model import parse_route_info

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    with io.open(os.path.join(HERE, name), encoding="utf-8") as f:
        return json.load(f)


def cached(tool, args):
    kp = _key(tool, args)
    try:
        with io.open(kp, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def main():
    reach = load("out_reach.json")["reach"]
    stage = load("out_leg2_stage_a.json")
    leg1 = load("out_leg1.json")["leg1"]

    # canonical stop coordinates (one point per physical stop)
    canon = {}
    try:
        raw = load("canon.json")
        for k, v in raw.items():
            nm, lo, la = k.split("|")
            canon[(nm, round(float(lo), 4), round(float(la), 4))] = (v[0], v[1])
    except Exception as e:
        print("no canon.json:", e)

    def snap(name, lon, lat):
        k = (name, round(lon, 4), round(lat, 4))
        if k in canon:
            return canon[k]
        best = None
        for (nm, a, b), v in canon.items():
            if nm != name:
                continue
            d = math.hypot((lon - a) * 85000, (lat - b) * 111000)
            if best is None or d < best[0]:
                best = (d, v)
        if best and best[0] < 500:
            return best[1]
        return (lon, lat)

    route_ids = set()
    for x in leg1:
        route_ids.add(x["route_id"])
    route_ids |= set(stage["need_routes"])

    geoms = {}
    counts = {}
    lines_at = {}
    terminals = {}
    for rid in sorted(route_ids):
        raw = cached("query_route_info_by_route_id", {"route_id": rid})
        if not raw:
            continue
        info = parse_route_info(raw)
        pts = [snap(s["name"], s["lon"], s["lat"]) for s in info["stops"] if s["lon"] is not None]
        if len(pts) >= 2:
            geoms[rid] = pts
        num = (raw.get("name") or "").split(" ")[0]
        for s in info["stops"]:
            if s["lon"] is None:
                continue
            lon, lat = snap(s["name"], s["lon"], s["lat"])
            key = (s["name"], round(lon, 4), round(lat, 4))
            counts[key] = counts.get(key, 0) + 1
            lines_at.setdefault(key, set()).add(num)
        if info["stops"]:
            for nm in (info["stops"][0]["name"], info["stops"][-1]["name"]):
                terminals[nm] = terminals.get(nm, 0) + 1

    for x in reach:
        lon, lat = snap(x["stop"], x["lon"], x["lat"])
        x["lon"], x["lat"] = lon, lat
        key = (x["stop"], round(lon, 4), round(lat, 4))
        x["n_routes"] = counts.get(key, 0)
        x["n_lines"] = len(lines_at.get(key, ()))
        x["terminal"] = terminals.get(x["stop"], 0)

    with io.open("out_reach_geo.json", "w", encoding="utf-8") as f:
        f.write(json.dumps({"reach": reach, "geoms": geoms}, ensure_ascii=False))

    with io.open("out_reachable_stops.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["站点", "经度", "纬度", "预计分钟", "类型", "换乘站", "线路1", "线路2", "本站线路数"])
        for x in sorted(reach, key=lambda z: z["t"]):
            w.writerow([x["stop"], "%.6f" % x["lon"], "%.6f" % x["lat"], "%.1f" % (x["t"] / 60.0),
                        "直达" if x["kind"] == "direct" else "换乘一次", x.get("via") or "",
                        x["legs"][0], x["legs"][1] if len(x["legs"]) > 1 else "",
                        x["n_routes"]])
    print("stops=%d routes=%d" % (len(reach), len(geoms)))

    # notable names present?
    names = set(x["stop"] for x in reach)
    probes = [u"天安门东", u"天安门西", u"西直门", u"西直门南", u"回龙观", u"回龙观东大街", u"上地",
              u"上地桥东", u"奥林匹克公园", u"中关村南", u"中关村", u"五道口", u"国贸", u"望京",
              u"北京西站", u"六里桥北里", u"清河", u"苏州桥", u"牡丹园", u"北太平庄", u"健翔桥",
              u"亚运村", u"三元桥", u"芍药居", u"惠新西街", u"安贞桥", u"马甸桥", u"学院桥",
              u"人民大学", u"魏公村", u"紫竹桥", u"公主坟", u"复兴门", u"积水潭", u"德胜门",
              u"霍营", u"北苑", u"天通苑", u"立水桥", u"西二旗", u"上地信息产业基地"]
    with io.open("out_probe.txt", "w", encoding="utf-8") as f:
        for p in probes:
            hits = [n for n in names if p in n]
            f.write(u"%-10s %s\n" % (p, u" / ".join(sorted(hits)) if hits else u"--"))
    print("ok")


if __name__ == "__main__":
    main()

