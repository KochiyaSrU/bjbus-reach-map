# -*- coding: utf-8 -*-
"""One-command builder for a Beijing bus 60-minute reachability map.

    python make_map.py --origin "西苑" --out "D:\\out\\西苑60分钟可达" --shp xiyuan_60min

It clones the pipeline into a working directory, fetches what it needs, computes
the reachable set, draws both maps and exports CSV / GeoJSON / shapefile.

Working directory defaults to <this skill>/work/<slug>; the download cache is
shared between runs, so a second map in the same area is much faster.
"""
import argparse
import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "scripts")
POI = json.load(io.open(os.path.join(HERE, "poi.json"), encoding="utf-8"))

PY = sys.executable
ARC = r"C:\Python27\ArcGIS10.8\python.exe"      # arcpy 10.8 (Python 2.7), optional
ENGINE = r"D:\Workspace\bjbus"                   # shared cache + tile directory

COPY = ["mcp_client.py", "q.py", "net.py", "model.py", "gcj.py", "basemap.py",
        "tiles_core.py", "leg1.py", "leg2a.py", "leg2b.py", "fix_coords.py",
        "export.py", "deliver.py", "make_shp.py", "render.py", "fill_gentle.py",
        "qa_offset.py"]


try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def log(msg):
    print("[make_map] " + msg, flush=True)


def run(args, cwd, optional=False, quiet=False):
    """Run a pipeline step, streaming its output (a long fetch can take minutes)."""
    t0 = time.time()
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    proc = subprocess.Popen([PY] + args, cwd=cwd, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, env=env)
    tail = []
    for raw in proc.stdout:
        line = raw.decode("utf-8", "replace").rstrip()
        if not line:
            continue
        tail.append(line)
        if not quiet and (line.startswith("[fetch]") or "[make_map]" in line):
            log("    " + line[:120])
    proc.wait()
    log("  %-16s rc=%d  %.0fs  %s" % (args[0], proc.returncode, time.time() - t0,
                                      (tail[-1] if tail else "")[:90]))
    if proc.returncode and not optional:
        raise SystemExit("step failed: %s" % args[0])
    return "\n".join(tail)


def patch(path, pairs, must=True):
    s = io.open(path, encoding="utf-8").read()
    for old, new in pairs:
        if old not in s:
            if must:
                raise SystemExit("pattern missing in %s: %r" % (os.path.basename(path), old[:60]))
            continue
        s = s.replace(old, new, 1)
    io.open(path, "w", encoding="utf-8").write(s)


def set_line(path, prefix, newline):
    """Replace the first line starting with `prefix`."""
    lines = io.open(path, encoding="utf-8").read().split("\n")
    hit = False
    for i, ln in enumerate(lines):
        if ln.startswith(prefix):
            lines[i] = newline
            hit = True
            break
    if not hit:
        raise SystemExit("line not found in %s: %s" % (os.path.basename(path), prefix))
    io.open(path, "w", encoding="utf-8").write("\n".join(lines))


def slug(name):
    keep = re.sub(r"[^\w]", "", name)
    return keep or "origin"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--origin", required=True, help="exact bus stop name, e.g. 西苑")
    ap.add_argument("--out", required=True, help="deliverable folder")
    ap.add_argument("--shp", default=None, help="shapefile base name (ascii)")
    ap.add_argument("--work", default=None, help="working directory")
    ap.add_argument("--core-km", type=float, default=4.6, help="half-size of the detail map")
    ap.add_argument("--scale-km", type=float, default=5.0)
    ap.add_argument("--wait-mode", default="average",
                    choices=["average", "best", "worst"],
                    help="average: wait = headway/2; best: you time your trip; "
                         "worst: you just missed one")
    ap.add_argument("--skip-fetch", action="store_true", help="reuse an existing work dir")
    a = ap.parse_args()
    os.environ["BJ_WAIT_MODE"] = a.wait_mode

    origin = a.origin
    work = a.work or os.path.join(HERE, "work", slug(origin))
    shp = a.shp or "reach60"          # keep it ascii for ESRI compatibility
    os.makedirs(work, exist_ok=True)
    os.makedirs(a.out, exist_ok=True)
    log("origin=%s" % origin)
    log("work=%s" % work)

    for f in COPY:
        shutil.copy(os.path.join(SCRIPTS, f), os.path.join(work, f))

    # --- wire the clone to the shared cache and this origin -------------------
    set_line(os.path.join(work, "q.py"), "CACHE =", 'CACHE = r"%s\\cache"' % ENGINE)
    set_line(os.path.join(work, "fix_coords.py"), "CACHE =", 'CACHE = r"%s\\cache"' % ENGINE)
    set_line(os.path.join(work, "basemap.py"), "TILE_DIR =", 'TILE_DIR = r"%s\\tiles"' % ENGINE)
    patch(os.path.join(work, "fix_coords.py"),
          [(u'if x["stop"] == u"学院路北口":', u'if x["stop"] == u"%s":' % origin)])
    patch(os.path.join(work, "leg1.py"),
          [(u'ORIGIN = u"学院路北口"', u'ORIGIN = u"%s"' % origin)])
    patch(os.path.join(work, "make_shp.py"),
          [(u'shp_name = "xueyuanlubeikou_60min.shp"', u'shp_name = "%s.shp"' % shp)])

    # --- 1. origin routes ----------------------------------------------------
    run(["leg1.py"], work)
    leg1 = json.load(io.open(os.path.join(work, "out_leg1.json"), encoding="utf-8"))["leg1"]
    pts = [(e["lon"], e["lat"]) for e in leg1 if e.get("origin_rank") == 0 and e["lon"]]
    ox = sum(p[0] for p in pts) / len(pts)
    oy = sum(p[1] for p in pts) / len(pts)
    log("origin coordinates %.5f, %.5f  (%d route directions)" % (ox, oy, len(set(e["route_id"] for e in leg1))))

    # --- 2. one-transfer expansion ------------------------------------------
    run(["leg2a.py"], work)
    # leg2a records per-stop failures instead of raising: retry, then refuse
    for attempt in range(2):
        stage = json.load(io.open(os.path.join(work, "out_leg2_stage_a.json"), encoding="utf-8"))
        errs = stage.get("stop_route_errors") or {}
        if not errs:
            break
        log("  !! leg2a lost %d transfer stop(s), retrying%s"
            % (len(errs), " again" if attempt else ""))
        for k in list(errs)[:3]:
            log("     %s: %s" % (k, str(errs[k])[:80]))
        run(["leg2a.py"], work)
    else:
        stage = json.load(io.open(os.path.join(work, "out_leg2_stage_a.json"), encoding="utf-8"))
        errs = stage.get("stop_route_errors") or {}
        if errs:
            raise SystemExit(
                "leg2a still has %d failed transfer stops - the map would be wrong. "
                "Check the network / retry later. Details: %s"
                % (len(errs), os.path.join(work, "out_leg2_stage_a.json")))
    run(["fill_gentle.py"], work, optional=True)     # gentle retry for 503s
    stage = json.load(io.open(os.path.join(work, "out_leg2_stage_a.json"), encoding="utf-8"))
    if stage.get("stop_route_errors"):
        raise SystemExit("aborting: transfer expansion is incomplete")
    run(["leg2b.py"], work)
    run(["fix_coords.py"], work)
    run(["export.py"], work)

    reach = json.load(io.open(os.path.join(work, "out_reach_geo.json"), encoding="utf-8"))["reach"]
    log("reachable stops: %d" % len(reach))

    if not reach:
        log("")
        log("NO REACHABLE STOPS within the time budget.")
        log("This is a data limitation, not a bug. Usual causes:")
        log("  * the stop is served by only one or two village lines")
        log("  * those lines have no usable timetable (nruns = 0), so they are filtered out")
        log("  * every ride from here is longer than the budget")
        report = os.path.join(work, "out_leg1_report.txt")
        if os.path.exists(report):
            log("route-by-route evidence: %s" % report)
            for line in io.open(report, encoding="utf-8").read().splitlines()[:12]:
                log("    " + line.strip())
        lines = [u"# %s —— 60 分钟内没有可达站点" % origin, u"",
                 u"这不是脚本失败，是数据侧的结果。原因通常是：", u"",
                 u"1. 该站只有 1–2 条村/山区线路（F、H、Y 字头居多）；",
                 u"2. 这些线路的时刻表接口没有返回任何班次（nruns = 0），被服务水平过滤剔除；",
                 u"3. 或者线路本身的行程就超过了 60 分钟预算。", u"",
                 u"## 线路逐条证据", u""]
        rep = os.path.join(work, "out_leg1_report.txt")
        if os.path.exists(rep):
            for ln in io.open(rep, encoding="utf-8").read().splitlines():
                lines.append("    " + ln)
        lines += [u"", u"## 怎么复查", u"",
                  u"- 原始数据：" + rep,
                  u"- 若怀疑是接口报错而不是没班次，用 `call(tool, args, use_cache=False)` 重取一次对比；",
                  u"- 接口恢复后删掉对应缓存条目（cache/query_route_timetable_*.json）重跑即可。"]
        with io.open(os.path.join(a.out, u"结果说明.md"), "w", encoding="utf-8") as f:
            f.write(u"\n".join(lines))
        log("wrote an explanation to %s" % os.path.join(a.out, u"结果说明.md"))
        log("")
        log("DONE  %s : 0 stops (nothing to map)" % origin)
        return

    # --- 3. adapt the renderer ----------------------------------------------
    dlon = a.core_km / 85.2
    dlat = a.core_km / 111.0
    areas = "".join(u'    (u"%s", %.4f, %.4f),\n' % (n, lo, la) for n, lo, la in POI["areas"])
    marks = "".join(u'    u"%s": 1,\n' % n for n in POI["landmarks"])
    rp = os.path.join(work, "render.py")
    s = io.open(rp, encoding="utf-8").read()
    s = s.replace("x0, _ = merc(116.3110, 39.9410)", "x0, _ = merc(%.5f, %.5f)" % (ox - dlon, oy - dlat))
    s = s.replace("x1, _ = merc(116.3960, 39.9410)", "x1, _ = merc(%.5f, %.5f)" % (ox + dlon, oy - dlat))
    s = s.replace("_, y0 = merc(0, 39.9410)", "_, y0 = merc(0, %.5f)" % (oy - dlat))
    s = s.replace("_, y1 = merc(0, 40.0310)", "_, y1 = merc(0, %.5f)" % (oy + dlat))
    s = s.replace(u'u"核心区放大：学院路—中关村—清河—亚运村"',
                  u'u"核心区放大：%s 周边 %.1f km"' % (origin, a.core_km))
    s = s.replace("AREAS = [", "AREAS_EXTRA = [\n" + areas + "]\n\nAREAS = [", 1)
    s = s.replace("def area_labels(reach, X, Y, snap_km=3.0, keep_km=0.85):",
                  "def area_labels(reach, X, Y, snap_km=3.0, keep_km=0.85):\n    all_areas = AREAS_EXTRA + AREAS")
    s = s.replace("    names = [(x[\"stop\"], X[i], Y[i]) for i, x in enumerate(reach)]\n    out = []",
                  "    names = [(x[\"stop\"], X[i], Y[i]) for i, x in enumerate(reach)]\n    out = []\n    seen = set()")
    s = s.replace("    for nm, lon, lat in AREAS:\n        ax0, ay0 = merc(lon, lat)",
                  "    for nm, lon, lat in all_areas:\n        if nm in seen:\n            continue\n        seen.add(nm)\n        ax0, ay0 = merc(lon, lat)")
    s = s.replace(u'    u"前门": 1, u"崇文门": 1, u"王府井": 1,',
                  u'    u"前门": 1, u"崇文门": 1, u"王府井": 1,\n' + marks)
    s = s.replace(u'reserved_names=(u"学院路北口",), time_anchor',
                  u'reserved_names=(u"%s",), time_anchor' % origin)
    s = s.replace(u'reserved_names=(u"学院路北口",),', u'reserved_names=(u"%s",),' % origin)
    s = s.replace(u'自「学院路北口」公交站出发 · 最多换乘一次 · 含候车与换乘步行',
                  u'自「%s」公交站出发 · 最多换乘一次 · 含候车与换乘步行' % origin)
    s = s.replace(u'def origin_callout(ax, origin, text=u"起点  学院路北口"',
                  u'def origin_callout(ax, origin, text=u"起点  %s"' % origin)
    s = s.replace(u'label=u"起点 学院路北口"', u'label=u"起点 %s"' % origin)
    s = s.replace("cfg.update(scale_km=5,", "cfg.update(scale_km=%g," % a.scale_km)
    io.open(rp, "w", encoding="utf-8").write(s)
    log("renderer adapted (core window %.1f km, scale %g km)" % (a.core_km, a.scale_km))

    # --- 4. basemaps ---------------------------------------------------------
    n_reach = len(reach)
    lon_span = max(x["lon"] for x in reach) - min(x["lon"] for x in reach)
    bm = os.path.join(work, "basemap.py")
    patch(bm, [('build("light", 14', 'build("light", 13'), ('build("ref", 14', 'build("ref", 13')],
          must=False)
    if lon_span < 0.20:      # small extent: keep z14 for crispness
        patch(bm, [('build("light", 13', 'build("light", 14'), ('build("ref", 13', 'build("ref", 14')],
              must=False)
    run(["basemap.py"], work)
    tc = os.path.join(work, "tiles_core.py")
    patch(tc, [("116.3110, 39.9410, 116.3960, 40.0310",
                "%.5f, %.5f, %.5f, %.5f" % (ox - dlon, oy - dlat, ox + dlon, oy + dlat))], must=False)
    run(["tiles_core.py"], work)

    # --- 5. draw -------------------------------------------------------------
    run(["render.py", "all"], work)
    run(["deliver.py"], work)
    if os.path.exists(ARC):
        t_shp = time.time()
        r = subprocess.run([ARC, "make_shp.py"], cwd=work, capture_output=True)
        log("  make_shp.py      rc=%d  %.0fs" % (r.returncode, time.time() - t_shp))
    else:
        log("  arcpy not found - skipping shapefile")

    # --- 6. deliver ----------------------------------------------------------
    copied = 0
    for src, name in (("bjbus_reach60.png", u"公交60分钟可达范围_总图.png"),
                      ("bjbus_reach60_core.png", u"公交60分钟可达范围_核心区放大.png"),
                      (u"60分钟可达站点明细.csv", u"60分钟可达站点明细.csv"),
                      (u"60分钟可达站点.geojson", u"60分钟可达站点.geojson")):
        p = os.path.join(work, src)
        if os.path.exists(p):
            shutil.copy(p, os.path.join(a.out, name))
            copied += 1
    for ext in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
        p = os.path.join(work, shp + ext)
        if os.path.exists(p):
            shutil.copy(p, os.path.join(a.out, shp + ext))
            copied += 1
    log("delivered %d files to %s" % (copied, a.out))
    log("DONE  %s : %d stops" % (origin, n_reach))


if __name__ == "__main__":
    main()
