# -*- coding: utf-8 -*-
from gcj import gcj2wgs
"""Parsing + travel-time model for bjbus data."""
import re

TIME_RE = re.compile(r"^(\d{1,2}):(\d{2}):(\d{2})")


def to_secs(t):
    m = TIME_RE.match(t.strip())
    if not m:
        return None
    h, mi, s = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if h > 30:          # 24h+ notation
        h -= 24
    return h * 3600 + mi * 60 + s


def parse_route_info(raw):
    """-> {name, stops:[{name, lon, lat, dist}]}"""
    stops = []
    for s in raw.get("stops", []):
        try:
            lon = float(s.get("longitude"))
            lat = float(s.get("latitude"))
            # the feed publishes GCJ-02; the basemap is WGS-84
            lon, lat = gcj2wgs(lon, lat)
        except (TypeError, ValueError):
            lon = lat = None
        try:
            d = float(s.get("distance_from_previous_stop") or 0)
        except (TypeError, ValueError):
            d = 0.0
        stops.append({"name": s.get("name"), "lon": lon, "lat": lat, "dist": d})
    return {"name": raw.get("name"), "stops": stops}


def _collapse(visits, tol=180):
    """Collapse the overlapping fragments of one run into a single visit.

    visits: [(time, vehicle)] at one stop.  Two observations are the same visit
    when they belong to the same vehicle and are within `tol` seconds; different
    vehicles are never merged, so a 2-minute urban headway survives intact.
    """
    visits = sorted(visits)
    out = []
    for t, v in visits:
        if out and abs(t - out[-1][0]) <= tol and (v == out[-1][1] or v is None):
            continue
        out.append((t, v))
    return [t for t, _v in out]


def peak_only_from_schedules(sched):
    """True when the line only runs in the morning and evening peaks."""
    if not isinstance(sched, list) or not sched:
        return False
    per_day = {}
    for s in sched:
        try:
            stamp = s["depart"]["time"]
            day, hms = stamp[:10], stamp[11:19]
        except Exception:
            continue
        t = to_secs(hms)
        if t is None:
            continue
        per_day.setdefault(day, {}).setdefault(t // 3600, 0)
        per_day[day][t // 3600] += 1
    if not per_day:
        return False
    # judge a single service day: pooling days makes "1 morning + 1 evening"
    # look like "2 morning + 2 evening"
    best = max(per_day.values(), key=lambda h: sum(h.values()))
    mid = sum(v for hr, v in best.items() if 10 <= hr <= 15)
    am = sum(v for hr, v in best.items() if 6 <= hr <= 9)
    pm = sum(v for hr, v in best.items() if 16 <= hr <= 19)
    return mid == 0 and am >= 2 and pm >= 2


def headway_from_schedules(sched):
    """(runs on the busiest day, median gap within a day) from dated departures.

    Returns (None, None) when the payload is unusable.
    """
    if not isinstance(sched, list) or not sched:
        return None, None
    by_day = {}
    for s in sched:
        try:
            dep = s["depart"]["time"]
            day, hms = dep[:10], dep[11:19]
        except Exception:
            continue
        t = to_secs(hms)
        if t is None:
            continue
        by_day.setdefault(day, []).append(t)
    if not by_day:
        return None, None
    best_n, best_day = 0, None
    for day, times in by_day.items():
        if len(times) > best_n:
            best_n, best_day = len(times), day
    # mean gap of the busiest day, after collapsing the duplicated rows
    per_day = []
    for day, times in by_day.items():
        raw = sorted(times)
        tol = 1200 if len(raw) < 20 else 120
        v = []
        for t in raw:
            if v and t - v[-1] <= tol:
                continue
            v.append(t)
        if len(v) < 2:
            continue
        span = v[-1] - v[0]
        if span > 0:
            per_day.append((len(v), span / float(len(v) - 1)))
    if not per_day:
        return best_n, None
    per_day.sort(key=lambda t: -t[0])
    return per_day[0][0], per_day[0][1]


def parse_timetable(text, nstops):
    """Return (seg_secs list[n-1] or None, headway_sec or None, nruns).

    seg_secs[i] = typical time from stop i to i+1 (median over runs recording
    both).  nruns counts *departures*, not fragment rows: the feed splits one
    run into several rolling windows that overlap in time.
    """
    lines = [l for l in text.replace("\r\n", "\n").split("\n") if l.strip()]
    if not lines:
        return None, None, 0
    rows = lines[1:]
    seg_samples = [[] for _ in range(max(0, nstops - 1))]
    visits = {}
    for line in rows:
        cells = line.split("\t")
        if len(cells) < 2:
            continue
        veh = (cells[0] or "").strip() or None
        vals = cells[1:]
        times = []
        for c in vals:
            c = c.strip()
            if not c:
                times.append(None)
                continue
            times.append(to_secs(c.split(",")[0]))
        prev = None
        for i in range(len(times)):
            if times[i] is None:
                continue
            if prev is not None and times[i] < prev - 600:
                times[i] += 86400
            prev = times[i]
        for i in range(min(len(times) - 1, nstops - 1)):
            a, b = times[i], times[i + 1]
            if a is None or b is None:
                continue
            d = b - a
            if 20 <= d <= 7200:      # a motorway hop can legitimately take 1-2 h
                seg_samples[i].append(d)
        for i, t in enumerate(times):
            if t is not None:
                visits.setdefault(i, []).append((t % 86400, veh))

    seg = []
    for samples in seg_samples:
        if not samples:
            seg.append(None)
        else:
            samples.sort()
            seg.append(samples[len(samples) // 2])

    collapsed = {i: _collapse(v) for i, v in visits.items()}
    nruns = max((len(v) for v in collapsed.values()), default=0)
    headway = estimate_headway(collapsed)
    return seg, headway, nruns


def estimate_headway(collapsed, lo=60, hi=14400, dense=15):
    """Median gap between consecutive departures, pooled over stops.

    Two regimes, because the feed records each departure more than once:
      * a busy stop (>= `dense` observations) -> median of the gaps, which is
        robust to the odd duplicated row;
      * a sparse stop -> average gap over the observed span, because there the
        duplicates outnumber the real departures and would drag the median down
        (F25 at 堂上村: real service 3 times a day, median gap said 9 minutes).
    """
    gaps = []
    for idx, vals in collapsed.items():
        v = sorted(vals)
        if len(v) < 2:
            continue
        if len(v) >= dense:
            g = [v[i + 1] - v[i] for i in range(len(v) - 1)]
            g = [x for x in g if lo <= x <= hi]
            if g:
                g.sort()
                gaps.append(g[len(g) // 2])
        else:
            span = v[-1] - v[0]
            if span > 0:
                gaps.append(span / float(len(v) - 1))
    if not gaps:
        return None
    gaps.sort()
    return gaps[len(gaps) // 2]


def cumulative(seg, dists=None, v_missing=14.0, fallback_speed=4.5):
    """Turn per-segment seconds (may have None holes) into cumulative offsets.

    A missing segment (the feed recorded no arrival time) is estimated from the
    segment length at `v_missing` m/s (~50 km/h).  Filling it with the median of
    the route's other segments is wrong for express lines: 919快 was credited
    3 minutes for a 61 km motorway hop.
    """
    if not seg:
        return [0]
    cum = [0]
    for i, s in enumerate(seg):
        if s is None:
            d = 0.0
            if dists is not None and i + 1 < len(dists):
                d = dists[i + 1] or 0.0
            if d > 0:
                s = max(d / v_missing, 30.0)
            else:
                s = seg_fallback(seg, i, fallback_speed)
        cum.append(cum[-1] + s)
    return cum


def seg_fallback(seg, i, fallback_speed):
    vals = [v for v in seg if v]
    if vals:
        vals.sort()
        return vals[len(vals) // 2]
    return 120


# ---- service-level filter -------------------------------------------------
import os as _os
MIN_RUNS = int(_os.environ.get("BJ_MIN_RUNS", "3"))

WAIT_MODE = _os.environ.get("BJ_WAIT_MODE", "average")


PLANNED_FROM = 20 * 60.0     # at or above this headway people read the timetable


def wait_for(headway, default=480.0):
    """Expected wait, by how the line is actually used.

    frequent service -> you turn up and wait half a headway on average
    timetabled service (headway >= PLANNED_FROM) -> you plan the trip, so ~0
    """
    if headway:
        if WAIT_MODE == "best":
            return 0.0
        if WAIT_MODE == "worst":
            return float(headway)
        if headway >= PLANNED_FROM:
            return 0.0
        return headway / 2.0
    return default


   # 3 keeps rural scheduled lines, 12 keeps only dense urban ones          # runs observed in the feed window (a normal route: 100+)
EXPRESS = (u"快速直达专线",)


def service_ok(route_number, nruns, headway):
    """Keep ordinary all-day lines; drop night lines and reservation express lines."""
    if not route_number:
        return False
    if route_number.startswith(u"夜"):
        return False
    for p in EXPRESS:
        if route_number.startswith(p):
            return False
    if nruns is not None and nruns < MIN_RUNS:
        return False
    if headway is None:
        return False
    return True

