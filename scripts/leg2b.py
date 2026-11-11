# -*- coding: utf-8 -*-
"""Stage 3: compute one-transfer reachability within 60 minutes."""
import io
import json
import math

from q import call, _key
from model import wait_for, peak_only_from_schedules, headway_from_schedules, parse_route_info, parse_timetable, cumulative, service_ok

BUDGET = 60 * 60
NIGHT = lambda r: r.startswith(u"夜")


def load(name):
    with io.open(name, encoding="utf-8") as f:
        return json.load(f)


def dump(obj, name):
    with io.open(name, "w", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False))


def cached(tool, args):
    kp = _key(tool, args)
    try:
        with io.open(kp, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def hyps(lon1, lat1, lon2, lat2):
    dx = (lon2 - lon1) * 111320.0 * math.cos(math.radians((lat1 + lat2) / 2.0))
    dy = (lat2 - lat1) * 110540.0
    return math.hypot(dx, dy)


class RouteCache(object):
    def __init__(self):
        self.info = {}
        self.tt = {}

    def get(self, rid):
        if rid not in self.info:
            raw = cached("query_route_info_by_route_id", {"route_id": rid})
            if raw is None:
                self.info[rid] = None
                self.tt[rid] = None
            else:
                info = parse_route_info(raw)
                n = len(info["stops"])
                traw = cached("query_route_timetable", {"route_id": rid}) or {}
                seg, headway, nruns = parse_timetable(traw.get("_raw_text") or "", n)
                sraw = cached("query_schedules_by_route_id", {"route_id": rid})
                if sraw is not None:
                    if peak_only_from_schedules(sraw):
                        nruns = 0
                    s_n, s_hw = headway_from_schedules(sraw)
                    if s_n:
                        nruns = 0 if nruns == 0 else s_n
                    if s_hw:
                        headway = s_hw
                info["seg"] = seg
                info["headway"] = headway
                info["cum"] = cumulative(seg, [s["dist"] for s in info["stops"]])
                info["nruns"] = nruns
                self.info[rid] = info
                self.tt[rid] = headway
        return self.info[rid]


def main():
    stage = load("out_leg2_stage_a.json")
    leg1 = load("out_leg1.json")["leg1"]
    rc = RouteCache()

    # ---- direct (0 transfer) destinations ----
    best = {}
    for x in leg1:
        if NIGHT(x["route_number"]) or x["origin_rank"] == 0 or x["lon"] is None:
            continue
        if not x.get("ok", True) or x["t"] > BUDGET:
            continue
        k = (x["stop"], round(x["lon"], 4), round(x["lat"], 4))
        cur = best.get(k)
        if cur is None or x["t"] < cur["t"]:
            best[k] = {"stop": x["stop"], "lon": x["lon"], "lat": x["lat"], "t": x["t"],
                       "kind": "direct", "legs": [x["route_number"]],
                       "via": None, "detail": [(x["route_id"], 0, x["origin_rank"])]}
    direct = dict(best)
    print("direct destinations (<=60min):", len(direct))

    # ---- one transfer ----
    n_transfer_ok = 0
    for name, instances in stage["cands"].items():
        routes = stage["stop_routes"].get(name)
        if not routes:
            continue
        for inst in instances:
            t1 = inst["t1"]
            if t1 > BUDGET - 240:          # same margin as leg2a's MAX_T1 (56 min)
                continue
            for r in routes:
                rid = r["route_id"]
                if r["route_number"] == inst["route_number"]:
                    continue          # same line -> not a real transfer
                if rid in [i["route_id"] for i in instances]:
                    continue
                info = rc.get(rid)
                if not info or not info["stops"]:
                    continue
                if not service_ok(r["route_number"], info["nruns"], info["headway"]):
                    continue
                wait2 = wait_for(info["headway"])
                cum = info["cum"]
                stops = info["stops"]
                # where does this route meet the transfer stop?
                idxs = [i for i, s in enumerate(stops)
                        if s["name"] == name and s["lon"] is not None
                        and hyps(inst["lon"], inst["lat"], s["lon"], s["lat"]) <= 700]
                for i in idxs:
                    s0 = stops[i]
                    walk = 90.0 + hyps(inst["lon"], inst["lat"], s0["lon"], s0["lat"]) / 1.1
                    base = t1 + walk + wait2
                    if base >= BUDGET:
                        continue
                    for j in range(i + 1, len(stops)):
                        tt = base + (cum[j] - cum[i])
                        if tt > BUDGET:
                            break
                        s = stops[j]
                        if s["lon"] is None:
                            continue
                        k = (s["name"], round(s["lon"], 4), round(s["lat"], 4))
                        cur = best.get(k)
                        if cur is None or tt < cur["t"]:
                            best[k] = {"stop": s["name"], "lon": s["lon"], "lat": s["lat"],
                                       "t": tt, "kind": "transfer",
                                       "legs": [inst["route_number"], r["route_number"]],
                                       "via": name,
                                       "detail": [(inst["route_id"], 0, 0), (rid, i, j)],
                                       "leg1_ride": inst["ride"], "leg2_ride": cum[j] - cum[i],
                                       "wait1": inst["wait"], "wait2": wait2, "walk": walk}
                            n_transfer_ok += 1

    transfer = dict((k, v) for k, v in best.items() if v["kind"] == "transfer")
    print("stops reached via transfer:", len(transfer))
    print("total reachable stops:", len(best))

    dump({"reach": list(best.values())}, "out_reach.json")
    # summary by kind
    kinds = {}
    for v in best.values():
        kinds[v["kind"]] = kinds.get(v["kind"], 0) + 1
    print(kinds)


if __name__ == "__main__":
    main()
