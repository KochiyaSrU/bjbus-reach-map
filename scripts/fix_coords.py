# -*- coding: utf-8 -*-
"""Consolidate stop coordinates: one canonical point per physical stop.

The feed carries several slightly different coordinates for the same stop name
(different bay / direction / data versions, up to ~250 m apart).  On a map that
reads as 'the stop is misplaced', so we cluster each name and snap every
occurrence to the count-weighted centroid of its cluster.
"""
import io
import json
import math
import os
import collections
from model import parse_route_info

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = r"D:\Workspace\bjbus\cache"
CLUSTER_M = 260.0


def merc_d(lon1, lat1, lon2, lat2):
    dx = (lon2 - lon1) * 111320.0 * math.cos(math.radians((lat1 + lat2) / 2.0))
    dy = (lat2 - lat1) * 110540.0
    return math.hypot(dx, dy)


def build_registry():
    """name -> Counter[(lon, lat)] over every cached route (WGS-84 after parsing)."""
    pos = collections.defaultdict(collections.Counter)
    n = 0
    for fn in os.listdir(CACHE):
        if not fn.startswith("query_route_info_by_route_id_"):
            continue
        try:
            raw = json.load(io.open(os.path.join(CACHE, fn), encoding="utf-8"))
        except Exception:
            continue
        n += 1
        for s in parse_route_info(raw)["stops"]:
            if s["lon"] is None:
                continue
            pos[s["name"]][(round(s["lon"], 5), round(s["lat"], 5))] += 1
    print("routes scanned:", n, "unique names:", len(pos))
    return pos


def canonical_map(pos):
    """(name, lon, lat) -> (canonical_lon, canonical_lat)."""
    canon = {}
    n_clusters = 0
    for name, cnt in pos.items():
        items = sorted(cnt.items(), key=lambda kv: -kv[1])
        clusters = []          # list of [sumlon*w, sumlat*w, sumw, members]
        for (lon, lat), w in items:
            placed = False
            for c in clusters:
                cx, cy = c[0] / c[2], c[1] / c[2]
                if merc_d(lon, lat, cx, cy) <= CLUSTER_M:
                    c[0] += lon * w
                    c[1] += lat * w
                    c[2] += w
                    placed = True
                    break
            if not placed:
                clusters.append([lon * w, lat * w, float(w)])
        n_clusters += len(clusters)
        # merge pass: single-pass greedy clustering leaves neighbours split when
        # the seed order is unlucky, so merge until stable
        merged = True
        while merged and len(clusters) > 1:
            merged = False
            for i in range(len(clusters)):
                for j in range(i + 1, len(clusters)):
                    if clusters[j][2] <= 0:
                        continue
                    cx1, cy1 = clusters[i][0] / clusters[i][2], clusters[i][1] / clusters[i][2]
                    cx2, cy2 = clusters[j][0] / clusters[j][2], clusters[j][1] / clusters[j][2]
                    if merc_d(cx1, cy1, cx2, cy2) <= CLUSTER_M:
                        clusters[i][0] += clusters[j][0]
                        clusters[i][1] += clusters[j][1]
                        clusters[i][2] += clusters[j][2]
                        clusters[j][2] = 0.0
                        merged = True
            clusters = [c for c in clusters if c[2] > 0]

        # pick a medoid (a real observed coordinate), never a point between bays
        for c in clusters:
            cx, cy = c[0] / c[2], c[1] / c[2]
            members = [(lon, lat, w) for (lon, lat), w in items
                       if merc_d(lon, lat, cx, cy) <= CLUSTER_M * 1.6]
            if not members:
                continue
            best = None
            for (la, lb, lw) in members:
                s = sum(w2 * merc_d(la, lb, a2, b2) for (a2, b2, w2) in members)
                if best is None or s < best[0]:
                    best = (s, la, lb)
            c.append(best[1])
            c.append(best[2])
        for (lon, lat), w in items:
            best = None
            for c in clusters:
                cx, cy = c[0] / c[2], c[1] / c[2]
                d = merc_d(lon, lat, cx, cy)
                if d <= CLUSTER_M * 1.6 and (best is None or d < best[0]):
                    best = (d, c[-2] if len(c) > 3 else cx, c[-1] if len(c) > 3 else cy)
            if best:
                canon[(name, round(lon, 5), round(lat, 5))] = (best[1], best[2])
    print("clusters:", n_clusters, "canonical entries:", len(canon))
    return canon


def snap(name, lon, lat, canon):
    k = (name, round(lon, 5), round(lat, 5))
    if k in canon:
        return canon[k]
    best = None
    for (nm, a, b), v in canon.items():
        if nm != name:
            continue
        d = merc_d(lon, lat, a, b)
        if best is None or d < best[0]:
            best = (d, v[0], v[1])
    if best and best[0] < 600:
        return (best[1], best[2])
    return (lon, lat)


def main():
    pos = build_registry()
    canon = canonical_map(pos)
    with io.open(os.path.join(HERE, "canon.json"), "w", encoding="utf-8") as f:
        f.write(json.dumps(dict((u"%s|%.5f|%.5f" % k, v) for k, v in canon.items()),
                           ensure_ascii=False))

    reach = json.load(io.open(os.path.join(HERE, "out_reach.json"), encoding="utf-8"))
    rows = reach["reach"]
    best = {}
    moved = 0
    for x in rows:
        if x["stop"] == u"学院路北口":
            continue          # the origin is not a destination
        lon, lat = snap(x["stop"], x["lon"], x["lat"], canon)
        if abs(lon - x["lon"]) > 1e-5 or abs(lat - x["lat"]) > 1e-5:
            moved += 1
        k = (x["stop"], round(lon, 5), round(lat, 5))
        x2 = dict(x)
        x2["lon"], x2["lat"] = lon, lat
        cur = best.get(k)
        if cur is None or x2["t"] < cur["t"]:
            best[k] = x2
    print("reach: %d -> %d unique points (moved %d)" % (len(rows), len(best), moved))

    geoms = {}
    for rid, pts in reach.get("geoms", {}).items():
        # geoms only carry coordinates, no names: snap by nearest same-name is not
        # possible here, so leave them (route lines are context only)
        geoms[rid] = pts

    # ---- walking overlay -------------------------------------------------
    # You can simply walk to stops near the origin; the bus model alone makes a
    # stop 300 m away look like 30 minutes.
    import math as _m
    WALK_R = 1200.0
    WALK_V = 1.1
    try:
        leg1 = json.load(io.open(os.path.join(HERE, "out_leg1.json"), encoding="utf-8"))["leg1"]
        oc = [(e["lon"], e["lat"]) for e in leg1 if e.get("origin_rank") == 0 and e["lon"]]
        ox = sum(p[0] for p in oc) / len(oc)
        oy = sum(p[1] for p in oc) / len(oc)
    except Exception:
        ox = oy = None
    n_walk = 0
    if ox is not None:
        for k, v in best.items():
            d = _m.hypot((v["lon"] - ox) * 85200.0, (v["lat"] - oy) * 111000.0)
            if d > WALK_R:
                continue
            tw = d / WALK_V
            if tw < v["t"]:
                v = dict(v)
                v["t"] = tw
                v["kind"] = "walk"
                v["legs"] = [u"步行"]
                v["via"] = u"步行 %.0f m" % d
                best[k] = v
                n_walk += 1
    print("walking overlay: %d stops" % n_walk)

    out = {"reach": list(best.values()), "geoms": geoms}
    with io.open(os.path.join(HERE, "out_reach_geo.json"), "w", encoding="utf-8") as f:
        f.write(json.dumps(out, ensure_ascii=False))

    with io.open(os.path.join(HERE, "out_reach.json"), "w", encoding="utf-8") as f:
        f.write(json.dumps({"reach": list(best.values())}, ensure_ascii=False))

    # QA dump for the stops the user reported
    probes = [u"邮政研究院", u"育新小区北口", u"惠新东桥西", u"惠新东桥东", u"西三旗桥东",
              u"四拨子", u"安宁里", u"学院路北口"]
    lines = []
    for p in probes:
        hits = sorted([v for v in best.values() if v["stop"] == p], key=lambda z: z["t"])
        lines.append(u"%-8s %s" % (p, u" | ".join(u"%.5f,%.5f %.1fmin" % (h["lon"], h["lat"], h["t"] / 60.0)
                                                   for h in hits)))
    with io.open(os.path.join(HERE, "out_coord_fixed.txt"), "w", encoding="utf-8") as f:
        f.write(u"\n".join(lines))


if __name__ == "__main__":
    main()

