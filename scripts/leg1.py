# -*- coding: utf-8 -*-
"""Stage 1: everything reachable from 学院路北口 with a single bus ride."""
import io
import json

from q import call
from net import fetch_many
from model import peak_only_from_schedules, headway_from_schedules, wait_for, parse_route_info, parse_timetable, cumulative, service_ok

ORIGIN = u"学院路北口"


def dump(obj, name):
    with io.open(name, "w", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False, indent=1))


def main():
    try:
        routes = call("query_routes_at_stop", {"stop_name": ORIGIN})
    except RuntimeError as e:
        print("[leg1] 站名查询失败：%s" % e)
        print("[leg1] 该站名在数据里不存在（或接口异常），先用 "
              "query_routes_at_stop 核对站名再重试。")
        raise SystemExit(2)
    dump(routes, "out_routes_at_stop.json")
    print("routes at origin:", len(routes))
    ids = [(r["route_id"], r["route_number"], int(r["current_stop_number"])) for r in routes]

    info_tasks = [("info:" + rid, "query_route_info_by_route_id", {"route_id": rid}) for rid, _, _ in ids]
    infos = fetch_many(info_tasks, nthreads=6)

    tt_tasks = [("tt:" + rid, "query_route_timetable", {"route_id": rid}) for rid, _, _ in ids]
    tts = fetch_many(tt_tasks, nthreads=6)
    # dated departures: the timetable pools several service days
    sc_tasks = [("sc:" + rid, "query_schedules_by_route_id", {"route_id": rid}) for rid, _, _ in ids]
    scs = fetch_many(sc_tasks, nthreads=6)

    lines = []
    leg1 = []
    for rid, rnum, oidx in ids:
        raw, err = infos.get("info:" + rid, (None, "missing"))
        if err or raw is None:
            lines.append("route %s (%s): INFO ERROR %s" % (rid, rnum, err))
            continue
        # the tool reports a failure as {"_raw_text": ..., "_isError": True}, not as an
        # exception, so check the payload too -- otherwise stops=[] crashes below.
        if raw.get("_isError") or not raw.get("stops"):
            lines.append("route %s (%s): INFO ERROR %s"
                         % (rid, rnum, (raw.get("_raw_text") or "no stops")[:70]))
            continue
        info = parse_route_info(raw)
        stops = info["stops"]
        n = len(stops)
        oi = oidx - 1
        if not 0 <= oi < n:
            lines.append("route %s (%s): INDEX ERROR origin_idx=%d nstops=%d"
                         % (rid, rnum, oi, n))
            continue
        traw, terr = tts.get("tt:" + rid, (None, "missing"))
        text = ""
        if traw is not None:
            text = traw.get("_raw_text") or ""
        seg, headway, nruns = parse_timetable(text, n)
        sraw, _serr = scs.get("sc:" + rid, (None, None))
        peak = False
        if sraw is not None:
            peak = peak_only_from_schedules(sraw)
            s_n, s_hw = headway_from_schedules(sraw)
            if s_n:
                nruns = s_n
            if s_hw:
                headway = s_hw
        if peak:
            nruns = 0          # peak-only: not available at an arbitrary hour
        cum = cumulative(seg, [s["dist"] for s in stops]) if n else [0]
        wait = wait_for(headway)
        keep = service_ok(rnum, nruns, headway)
        lines.append("route %s %-10s n=%2d origin_idx=%2d headway=%s nruns=%d seg_none=%d %s"
                     % (rid, rnum, n, oi, ("%dm" % (headway // 60)) if headway else "?", nruns,
                        sum(1 for s in seg if s is None), "" if keep else "EXCLUDED"))
        for j in range(oi, n):
            ride = cum[j] - cum[oi]
            leg1.append({
                "stop": stops[j]["name"], "lon": stops[j]["lon"], "lat": stops[j]["lat"],
                "t": wait + ride, "ride": ride, "wait": wait,
                "route_id": rid, "route_number": rnum,
                "origin_rank": j - oi, "ok": keep,
            })
        # terminal info for the report
        lines.append("    %s -> %s   ride(origin->%s)=%.0fmin  stops_left=%d"
                     % (stops[oi]["name"], stops[n - 1]["name"], stops[n - 1]["name"],
                        (cum[n - 1] - cum[oi]) / 60.0, n - 1 - oi))

    with io.open("out_origin.txt", "w", encoding="utf-8") as f:
        f.write(ORIGIN)
    dump({"leg1": leg1}, "out_leg1.json")
    with io.open("out_leg1_report.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
