# -*- coding: utf-8 -*-
"""Stage 2: gather transfer-stop route lists and fetch all needed route data."""
import io
import json
import math

from q import call
from net import fetch_many
from model import parse_timetable

NIGHT = lambda r: r.startswith(u"夜")
MAX_T1 = 56 * 60          # a transfer beyond this leaves <4 min for leg 2


def dump(obj, name):
    with io.open(name, "w", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False))


def load(name):
    with io.open(name, encoding="utf-8") as f:
        return json.load(f)


def hyps(lon1, lat1, lon2, lat2):
    dx = (lon2 - lon1) * 111320.0 * math.cos(math.radians((lat1 + lat2) / 2.0))
    dy = (lat2 - lat1) * 110540.0
    return math.hypot(dx, dy)


def main():
    leg1 = load("out_leg1.json")["leg1"]
    origin_routes = json.load(io.open("out_routes_at_stop.json", encoding="utf-8"))
    oids = set(r["route_id"] for r in origin_routes)

    cands = {}
    for x in leg1:
        if NIGHT(x["route_number"]) or x["origin_rank"] == 0:
            continue
        if not x.get("ok", True):        # route rejected by service_ok(): never a leg 1
            continue
        if x["lon"] is None or x["t"] > MAX_T1:
            continue
        cands.setdefault(x["stop"], []).append({
            "t1": x["t"], "lon": x["lon"], "lat": x["lat"],
            "route_id": x["route_id"], "route_number": x["route_number"],
            "ride": x["ride"], "wait": x["wait"],
        })
    print("candidate transfer stops:", len(cands))

    tasks = [("rs:" + n, "query_routes_at_stop", {"stop_name": n}) for n in cands]
    stop_routes = fetch_many(tasks, nthreads=8)

    ok = 0
    errs = []
    need = set()
    for name in cands:
        res, err = stop_routes.get("rs:" + name, (None, "missing"))
        if err or res is None:
            errs.append((name, err))
            continue
        ok += 1
        for r in res:
            if r["route_id"] in oids or NIGHT(r["route_number"]):
                continue
            need.add(r["route_id"])
    print("stops resolved: %d/%d, errors=%d, new route-directions: %d"
          % (ok, len(cands), len(errs), len(need)))

    store = {"cands": cands,
             "stop_routes": dict((k[3:], v[0]) for k, v in stop_routes.items() if v[0] is not None),
             "stop_route_errors": errs,
             "need_routes": sorted(need)}
    dump(store, "out_leg2_stage_a.json")

    tt_tasks = []
    for rid in sorted(need):
        tt_tasks.append(("info:" + rid, "query_route_info_by_route_id", {"route_id": rid}))
        tt_tasks.append(("tt:" + rid, "query_route_timetable", {"route_id": rid}))
    print("fetching %d calls ..." % len(tt_tasks))
    fetch_many(tt_tasks, nthreads=8)
    print("done")


if __name__ == "__main__":
    main()
