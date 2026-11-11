# -*- coding: utf-8 -*-

"""Draw the 60-minute one-transfer reachability map (overview + core detail)."""

import io

import json

import math

import os

import sys

import time



import numpy as np

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt

import matplotlib.patheffects as pe

from matplotlib import font_manager as fm

from matplotlib.colors import LinearSegmentedColormap, to_rgb

from matplotlib.collections import LineCollection

from matplotlib.lines import Line2D

from matplotlib.patches import Rectangle, Patch

from scipy.spatial import cKDTree



HERE = os.path.dirname(os.path.abspath(__file__))

R = 6378137.0



C_BAND = [(0, 15, "#2b6ca3"), (15, 30, "#3d9e93"), (30, 45, "#dfa33a"), (45, 60, "#c4435b")]

LEVELS = [0, 15, 30, 45, 60]



LANDMARKS = {

    u"西直门": 1, u"中关村南": 1, u"五道口": 1, u"清河": 1, u"上地桥东": 1,

    u"地铁西二旗站": 1, u"霍营": 1, u"立水桥": 1, u"北苑": 1, u"望京街西口": 1,

    u"三元桥南": 1, u"惠新西街": 1, u"安贞桥西": 1, u"马甸桥东": 1, u"德胜门": 1,

    u"积水潭桥东": 1, u"复兴门南": 1, u"北京西站": 1, u"六里桥北里": 1, u"公主坟南": 1,

    u"紫竹桥": 1, u"魏公村": 1, u"人民大学": 1, u"苏州桥南": 1, u"学院桥": 1,

    u"健翔桥东": 1, u"亚运村": 1, u"颐和园": 1, u"北京大学西门": 1, u"百望山森林公园": 1,

    u"地铁霍营站": 1, u"地铁立水桥站": 1, u"清河火车站": 1, u"四惠枢纽站": 1,

    u"大钟寺": 1, u"阜成门": 1, u"动物园": 1, u"国家图书馆": 1, u"鸟巢": 1,

    u"北京航空航天大学": 1, u"成府路口南": 1, u"蓟门桥北": 1, u"北太平桥西": 1,

    u"中国农业大学东校区": 1, u"二里庄": 1, u"北沙滩桥东": 1, u"奥运村西": 1,

    u"地铁林萃桥站": 1, u"黄土店火车站": 1, u"地铁回龙观东大街站": 1, u"地铁生命科学园站西": 1,

    u"上地五街": 1, u"地铁上地站": 1, u"地铁望京站": 1, u"安贞桥东": 1, u"西坝河": 1,

    u"三元桥西站": 1, u"蓟门桥西": 1, u"明光桥南": 1, u"学知桥南": 1, u"北沙滩桥东": 1,

    u"健翔桥西": 1, u"牡丹园": 1, u"北太平庄": 1, u"积水潭桥北": 1, u"德胜门外": 1,

    u"前门": 1, u"崇文门": 1, u"王府井": 1,

}





def merc(lon, lat):

    lon = np.asarray(lon, dtype=float)

    lat = np.asarray(lat, dtype=float)

    return np.radians(lon) * R, np.log(np.tan(np.pi / 4.0 + np.radians(lat) / 2.0)) * R





def load(name):

    with io.open(os.path.join(HERE, name), encoding="utf-8") as f:

        return json.load(f)





def setup_font():

    for cand in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyhbd.ttc"):

        if os.path.exists(cand):

            fm.fontManager.addfont(cand)

    plt.rcParams["font.family"] = ["Microsoft YaHei", "DejaVu Sans"]

    plt.rcParams["axes.unicode_minus"] = False





def cmap_time():

    pts = [(0.0, C_BAND[0][2])]

    for lo, hi, c in C_BAND:

        pts.append((hi / 60.0, c))

    return LinearSegmentedColormap.from_list("reach", pts)





def build_field(xy, tt, xmin, xmax, ymin, ymax, nx=560, ny=760,

                max_access_m=800.0, k=9, power=2.0, seed=None):

    """IDW travel-time surface.  `seed` = (x, y, minutes) added as a sample,

    normally the origin at 0 min so the near-zero core is anchored there."""

    if seed is not None:

        xy = np.vstack([xy, [seed[0], seed[1]]])

        tt = np.concatenate([tt, [seed[2]]])

    xs = np.linspace(xmin, xmax, nx)

    ys = np.linspace(ymin, ymax, ny)

    gx, gy = np.meshgrid(xs, ys)

    pts = np.column_stack([gx.ravel(), gy.ravel()])

    tree = cKDTree(xy)

    dist, idx = tree.query(pts, k=min(k, len(xy)))

    d0 = dist[:, 0]

    w = 1.0 / np.maximum(dist, 22.0) ** power

    t = (tt[idx] * w).sum(axis=1) / w.sum(axis=1)

    t = t.reshape(gx.shape)

    return xs, ys, t, d0.reshape(gx.shape)





WAIT_NOTE = {"average": u"\u5019\u8f66\uff1a\u5bc6\u96c6\u7ebf\u8def\u6309\u95f4\u9694\u00f72\uff0c\u73ed\u6b21\u758f\u7684\u6309\u5361\u70b9",

             "best": u"\u5019\u8f66\u6309\u5361\u70b9\u53e3\u5f84\uff08\u5047\u8bbe\u4f60\u6309\u65f6\u523b\u8868\u8d76\u8f66\uff09",

             "worst": u"\u5019\u8f66\u6309\u6700\u5dee\u53e3\u5f84\uff08\u521a\u8d70\u4e00\u8f86\uff09"}





def fit_texts(fig, margin=8.0):
    """Shrink footer/legend text until it fits inside the canvas.

    The footer lines are long single strings; on a narrow canvas they used to be
    cut off at the right edge (长辛店: 5 characters lost).
    """
    try:
        fig.canvas.draw()
        r = fig.canvas.get_renderer()
        W = fig.get_window_extent().width
        for t in list(fig.texts):
            for _ in range(8):
                bb = t.get_window_extent(renderer=r)
                if bb.x1 <= W - margin:
                    break
                fs = t.get_fontsize()
                if fs <= 5.0:
                    break
                t.set_fontsize(fs * 0.93)
                fig.canvas.draw()
    except Exception:
        pass


def wait_note():

    return WAIT_NOTE.get(os.environ.get("BJ_WAIT_MODE", "average"), "")





MAX_LABEL_OFFSET_PT = 11.0     # a label further than this from its dot is dropped





class Placer(object):

    def __init__(self, ax, fig, dot_px=None):

        self.ax = ax

        self.fig = fig

        self.boxes = []

        self.dots = []

        self.dot_px = dot_px            # (N,2) display coords of every stop

        self._tree = None

        if dot_px is not None and len(dot_px):

            try:

                from scipy.spatial import cKDTree

                self._tree = cKDTree(dot_px)

            except Exception:

                self._tree = None



    def owns(self, box, own_x, own_y, slack=6.0):

        """True if the label's centre is nearest to its own stop."""

        if self._tree is None:

            return True

        cx, cy = (box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0

        d, i = self._tree.query([cx, cy], k=1)

        own = math.hypot(cx - own_x, cy - own_y)

        return d >= own - slack



    def covers_dot(self, box, r=3.0):

        if self._tree is None:

            return False

        x0, y0, x1, y1 = box

        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0

        rad = 0.5 * math.hypot(x1 - x0, y1 - y0) + r

        idx = self._tree.query_ball_point([cx, cy], rad)

        for i in idx:

            px, py = self.dot_px[i]

            if x0 - r <= px <= x1 + r and y0 - r <= py <= y1 + r:

                return True

        return False



    def add_dot(self, px, py, r=3.0):

        self.dots.append((px, py, r))



    def add_rect(self, x0, y0, x1, y1):

        """Reserve an area (e.g. under the origin callout)."""

        self.boxes.append((x0, y0, x1, y1))



    def place(self, x, y, text, fontsize, color, weight="normal", halo=2.0, pad=2.0,

              plate=False, spacing=False, leash=4.0, gaps=(2.5, 4.5, 7.0), min_gap_px=0.0,

              avoid_dots=True, max_off=None):

        cfg_leash = leash

        ax = self.ax

        dpi = self.fig.dpi

        shown = u"\u2009".join(list(text)) if spacing else text

        tw = len(shown) * fontsize * 1.03 * dpi / 72.0

        th = fontsize * 1.18 * dpi / 72.0

        if plate:

            tw += th * 0.9

            th += th * 0.55

        px, py = ax.transData.transform((x, y))

        bb = ax.get_window_extent()

        gaps = list(gaps)

        offs = []

        for g in gaps:

            offs += [(g, 0, "left", "center"),

                     (0, g + th * 0.5, "center", "bottom"),

                     (0, -g - th * 0.5, "center", "top"),

                     (-g, 0, "right", "center")]

        for g in gaps:

            offs += [(g * 0.72, g * 0.72, "left", "bottom"),

                     (-g * 0.72, g * 0.72, "right", "bottom"),

                     (g * 0.72, -g * 0.72, "left", "top"),

                     (-g * 0.72, -g * 0.72, "right", "top")]

        cands = []

        for dx, dy, ha, va in offs:

            if min_gap_px and math.hypot(dx, dy) < min_gap_px:

                continue

            k = self.fig.dpi / 72.0            # offset points -> pixels

            tx, ty = px + dx * k, py + dy * k

            if ha == "left":

                x0, x1 = tx, tx + tw

            elif ha == "right":

                x0, x1 = tx - tw, tx

            else:

                x0, x1 = tx - tw / 2, tx + tw / 2

            if va == "bottom":

                y0, y1 = ty, ty + th

            elif va == "top":

                y0, y1 = ty - th, ty

            else:

                y0, y1 = ty - th / 2, ty + th / 2

            m = 12.0                       # halo + frame clearance

            if x0 < bb.x0 + m or x1 > bb.x1 - m or y0 < bb.y0 + m or y1 > bb.y1 - m:

                continue

            box = (x0, y0, x1, y1)

            if any(not (box[2] + pad < b[0] or b[2] + pad < box[0]

                        or box[3] + pad < b[1] or b[3] + pad < box[1]) for b in self.boxes):

                continue

            if any(box[0] - r < dx2 < box[2] + r and box[1] - r < dy2 < box[3] + r

                   for dx2, dy2, r in self.dots):

                continue

            if avoid_dots and self.covers_dot(box):

                continue

            # ownership: how much nearer is this label to its own stop than to

            # the nearest other one?  1.0 = tie, >1 = clearly its own.

            ratio = 1.0

            if avoid_dots and self._tree is not None:

                cx, cy = (box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0

                d, _i = self._tree.query([cx, cy], k=1)

                own = math.hypot(cx - px, cy - py)

                ratio = own / max(float(d), 1e-6)

            limit = MAX_LABEL_OFFSET_PT if max_off is None else max_off

            if math.hypot(dx, dy) > limit:      # too far to read as this stop

                continue

            cands.append((ratio, dx, dy, ha, va, box))

            if ratio >= 1.0:            # good enough, stop searching

                break

        if not cands:

            return None

        ratio, dx, dy, ha, va, box = max(cands, key=lambda t: t[0])

        if ratio < 0.72:                # clearly belongs to another stop: skip

            return None

        if True:

            self.boxes.append(box)

            kw = dict(fontsize=fontsize, color=color, ha=ha, va="center",

                      fontweight=weight, zorder=30, clip_on=True,

                      path_effects=[pe.withStroke(linewidth=halo, foreground="white", alpha=0.95)])

            if plate:

                kw["bbox"] = dict(boxstyle="round,pad=0.30,rounding_size=0.5",

                                  fc=(1.0, 1.0, 1.0, 0.90), ec="#123743", lw=0.6)

                kw["path_effects"] = []

            if math.hypot(dx, dy) > max(cfg_leash, 6.0):

                kw["arrowprops"] = dict(arrowstyle="-", color="#93a0ac", lw=0.4,

                                        shrinkA=2.5, shrinkB=3.0, alpha=0.75)

            ann = ax.annotate(shown, xy=(x, y), xytext=(dx, dy), textcoords="offset points", **kw)

            return ann

        return None





def prune_labels(ax, fig, items, pad=2.0, dots=None):

    """Delete labels whose *rendered* bounding box collides with a higher-priority one."""

    fig.canvas.draw()

    r = fig.canvas.get_renderer()

    kept, boxes = 0, []

    for prio, ann in sorted(items, key=lambda t: -t[0]):

        try:

            bb = ann.get_window_extent(renderer=r)

        except Exception:

            continue

        if bb.width <= 0 or bb.height <= 0:

            continue

        box = (bb.x0, bb.y0, bb.x1, bb.y1)

        bad = any(not (box[2] + pad < b[0] or b[2] + pad < box[0]

                       or box[3] + pad < b[1] or b[3] + pad < box[1]) for b in boxes)

        if not bad:

            # a label sitting right above/below another one reads as one block

            for b in boxes:

                xov = min(box[2], b[2]) - max(box[0], b[0])

                if xov > 0.45 * min(box[2] - box[0], b[2] - b[0]):

                    gap = max(box[1] - b[3], b[1] - box[3])

                    if 0.0 <= gap < 7.0:

                        bad = True

                        break

        if bad:

            ann.remove()

        else:

            boxes.append(box)

            kept += 1

    return kept





def fit_axes(fig, rect_x, rect_y, rect_w, rect_h, aspect):

    """Shrink a rect to match aspect = width/height (data units)."""

    W, H = fig.get_size_inches()

    w = rect_w * W

    h = rect_h * H

    if w / h > aspect:

        w = h * aspect

    else:

        h = w / aspect

    return [rect_x + (rect_w - w / W) / 2.0, rect_y + (rect_h - h / H) / 2.0,

            w / W, h / H]





def find_boundary(X, Y, ox, oy, hull_dist=330.0, nbin=36):

    """Stops on the outer edge of the reachable set: concave-hull boundary

    plus the farthest stop in each direction from the origin."""

    out = set()

    try:

        import shapely

        from shapely.geometry import MultiPoint

        mp = MultiPoint([(float(x), float(y)) for x, y in zip(X, Y)])

        hull = shapely.concave_hull(mp, ratio=0.12)

        bd = hull.exterior

        for i in range(len(X)):

            if bd.distance(shapely.geometry.Point(float(X[i]), float(Y[i]))) <= hull_dist:

                out.add(i)

    except Exception as e:

        print("hull failed:", e)

    # direction extremes

    import math as _m

    best = {}

    for i in range(len(X)):

        dx, dy = X[i] - ox, Y[i] - oy

        r = _m.hypot(dx, dy)

        if r < 1200:

            continue

        a = (_m.degrees(_m.atan2(dy, dx)) + 360.0) % 360.0

        b = int(a / (360.0 / nbin)) % nbin

        if b not in best or r > best[b][1]:

            best[b] = (i, r)

    for b, (i, r) in best.items():

        out.add(i)



    # spatial thinning: neighbouring stops on the same rim should not all be

    # ringed and labelled (木樨园桥西/桥/桥东 were three rings in 700 m)

    order = sorted(out, key=lambda i: -(_m.hypot(X[i] - ox, Y[i] - oy)))

    kept = []

    for i in order:

        if all(_m.hypot(X[i] - X[j], Y[i] - Y[j]) > 1200.0 for j in kept):

            kept.append(i)

    return set(kept)





AREAS = [

    (u"中关村", 116.3160, 39.9840), (u"五道口", 116.3380, 39.9925),

    (u"学院路", 116.3470, 39.9965), (u"知春路", 116.3340, 39.9770),

    (u"苏州街", 116.3060, 39.9770), (u"万柳", 116.2990, 39.9760),

    (u"北太平庄", 116.3660, 39.9670), (u"马甸", 116.3760, 39.9730),

    (u"牡丹园", 116.3720, 39.9810), (u"安贞", 116.4070, 39.9720),

    (u"亚运村", 116.4070, 39.9970), (u"健翔桥", 116.3600, 39.9950),

    (u"清河", 116.3350, 40.0300), (u"上地", 116.3050, 40.0300),

    (u"西二旗", 116.3000, 40.0500), (u"回龙观", 116.3400, 40.0750),

    (u"霍营", 116.3700, 40.0750), (u"西三旗", 116.3300, 40.0450),

    (u"立水桥", 116.4100, 40.0400), (u"北苑", 116.4150, 40.0300),

    (u"望京", 116.4700, 39.9960), (u"酒仙桥", 116.4850, 39.9750),

    (u"西直门", 116.3550, 39.9400), (u"动物园", 116.3400, 39.9380),

    (u"车公庄", 116.3520, 39.9330), (u"阜成门", 116.3560, 39.9230),

    (u"复兴门", 116.3570, 39.9080), (u"德胜门", 116.3790, 39.9490),

    (u"积水潭", 116.3720, 39.9420), (u"新街口", 116.3650, 39.9450),

    (u"三里河", 116.3480, 39.9120), (u"木樨地", 116.3300, 39.9100),

    (u"紫竹院", 116.3130, 39.9400), (u"花园桥", 116.3080, 39.9330),

    (u"航天桥", 116.3070, 39.9240), (u"公主坟", 116.3100, 39.9080),

    (u"五棵松", 116.2740, 39.9070), (u"定慧寺", 116.2830, 39.9300),

    (u"田村", 116.2530, 39.9300), (u"五路居", 116.2900, 39.9500),

    (u"四季青", 116.2700, 39.9600), (u"西苑", 116.2900, 40.0000),

    (u"圆明园", 116.3000, 40.0080), (u"颐和园", 116.2700, 39.9990),

    (u"香山", 116.1950, 39.9930), (u"百望山", 116.2700, 40.0300),

    (u"西北旺", 116.2600, 40.0450), (u"永丰", 116.2300, 40.0700),

    (u"六里桥", 116.3000, 39.8800), (u"北京西站", 116.3220, 39.8950),

    (u"广安门", 116.3500, 39.8850), (u"白纸坊", 116.3650, 39.8800),

    (u"天安门", 116.3970, 39.9080), (u"王府井", 116.4100, 39.9120),

    (u"东直门", 116.4350, 39.9460), (u"和平里", 116.4200, 39.9550),

    (u"安定门", 116.4100, 39.9480), (u"三里屯", 116.4550, 39.9400),

    (u"朝阳公园", 116.4750, 39.9450), (u"劲松", 116.4600, 39.8800),

    (u"双井", 116.4600, 39.8950), (u"四惠", 116.4950, 39.9070),

    (u"大望路", 116.4750, 39.9080), (u"国贸", 116.4600, 39.9080),

]





def area_labels(reach, X, Y, snap_km=3.0, keep_km=0.85):

    """Place area names on the actually-reachable stops of that area.



    An area is only labelled when the reachable network really covers it

    (a stop within keep_km), so no 'you cannot get here' names appear.

    """

    names = [(x["stop"], X[i], Y[i]) for i, x in enumerate(reach)]

    out = []

    for nm, lon, lat in AREAS:

        ax0, ay0 = merc(lon, lat)

        hit = [(x, y) for (s, x, y) in names

               if nm in s and math.hypot(x - ax0, y - ay0) < snap_km * 1000]

        if hit:

            cx = float(np.mean([p[0] for p in hit]))

            cy = float(np.mean([p[1] for p in hit]))

            if math.hypot(cx - ax0, cy - ay0) < 2.2 * 1000:

                out.append((nm, cx, cy))

            continue

        best = None

        for (s, x, y) in names:

            d = math.hypot(x - ax0, y - ay0)

            if (best is None or d < best[0]):

                best = (d, x, y)

        if best and best[0] < keep_km * 1000:

            out.append((nm, best[1], best[2]))

    return out





def pick_empty_spot(X, Y, xmin, xmax, ymin, ymax, w, h, pad=450.0):

    """Anchor of the scale bar: prefers the bottom, but avoids stops."""

    best = None

    for fy in (0.045, 0.075, 0.11, 0.15, 0.20, 0.27):

        y = ymin + fy * (ymax - ymin)

        for fx in [0.03 + 0.039 * k for k in range(0, 25)]:

            x = xmin + fx * (xmax - xmin)

            if x + w > xmin + 0.975 * (xmax - xmin):

                continue

            x0, x1 = x - pad, x + w + pad

            y0, y1 = y - pad, y + h + pad

            n = int(((X >= x0) & (X <= x1) & (Y >= y0) & (Y <= y1)).sum())

            score = n * 1000.0 + fy * 40.0 + abs(fx - 0.5) * 6.0

            if best is None or score < best[0]:

                best = (score, x, y)

    return (best[1], best[2]) if best else (xmin + 0.6 * (xmax - xmin), ymin + 0.05 * (ymax - ymin))





def pick_empty_corner(X, Y, xmin, xmax, ymin, ymax):

    """North arrow: the top corner with the fewest stops around it."""

    dx, dy = (xmax - xmin) * 0.10, (ymax - ymin) * 0.07

    best = None

    for cx, cy, fx, fy in ((xmax - 0.06 * (xmax - xmin), ymax - 0.10 * (ymax - ymin), 1, 1),

                           (xmin + 0.06 * (xmax - xmin), ymax - 0.10 * (ymax - ymin), -1, 1),

                           (xmax - 0.06 * (xmax - xmin), ymin + 0.22 * (ymax - ymin), 1, -1),

                           (xmin + 0.06 * (xmax - xmin), ymin + 0.22 * (ymax - ymin), -1, -1)):

        n = int(((X >= cx - dx) & (X <= cx + dx) & (Y >= cy - dy) & (Y <= cy + dy)).sum())

        if best is None or n < best[0]:

            best = (n, cx, cy)

    return best[1], best[2]





def draw(fig, ax, reach, geoms, base, extent, origin, cfg):

    lons = np.array([x["lon"] for x in reach], dtype=float)

    lats = np.array([x["lat"] for x in reach], dtype=float)

    X, Y = merc(lons, lats)

    T = np.array([x["t"] / 60.0 for x in reach], dtype=float)

    direct = np.array([x["kind"] in ("direct", "walk") for x in reach])



    view = cfg["view"]

    xmin, xmax, ymin, ymax = view



    ax.imshow(base, extent=(extent["xmin"], extent["xmax"], extent["ymin"], extent["ymax"]),

              origin="upper", zorder=0, interpolation="bilinear")

    ax.set_xlim(xmin, xmax)

    ax.set_ylim(ymin, ymax)

    ax.set_aspect("equal")

    ax.set_xticks([])

    ax.set_yticks([])

    for sp in ax.spines.values():

        sp.set_color("#9aa7b3")

        sp.set_linewidth(1.0)



    # network fabric

    if cfg.get("fabric", True):

        segs = []

        maxseg = cfg.get("fabric_max_seg", 900.0)

        for rid, pts in geoms.items():

            if len(pts) < 2:

                continue

            gx, gy = merc([p[0] for p in pts], [p[1] for p in pts])

            for i in range(len(gx) - 1):

                if math.hypot(gx[i + 1] - gx[i], gy[i + 1] - gy[i]) > maxseg:

                    continue

                segs.append([(gx[i], gy[i]), (gx[i + 1], gy[i + 1])])

        ax.add_collection(LineCollection(segs, colors="#7d93ab", linewidths=cfg.get("fabric_lw", 0.45),

                                         alpha=cfg.get("fabric_alpha", 0.15), zorder=2,

                                         capstyle="round"))



    # time field: discrete bands, the origin is seeded at 0 min

    xs, ys, field, d0 = build_field(np.column_stack([X, Y]), T, xmin, xmax, ymin, ymax,

                                    nx=cfg.get("nx", 560), ny=cfg.get("ny", 760),

                                    seed=(origin[0], origin[1], 0.0))

    hole_mask = d0 > cfg.get("access", 800.0)

    try:                      # fill only holes enclosed by coloured area

        from scipy.ndimage import binary_fill_holes

        hole_mask = ~binary_fill_holes(~hole_mask)

    except Exception:

        pass

    masked = np.ma.array(field, mask=hole_mask)

    band_alpha = cfg.get("band_alpha", [0.52, 0.49, 0.44, 0.36])

    if any(a > 0 for a in band_alpha):

        for (lo, hi, c), a in zip(C_BAND, band_alpha):

            ax.contourf(xs, ys, masked, levels=[lo, hi], colors=[c], alpha=a,

                        zorder=3, antialiased=True)

    if cfg.get("iso_lines", True):

        ax.contour(xs, ys, masked, levels=[15, 30, 45], colors="white",

                   linewidths=cfg.get("iso_lw", 1.0), alpha=0.9, zorder=4)

        ax.contour(xs, ys, masked, levels=[60], colors=["#7d1f31"],

                   linewidths=cfg.get("b60_lw", 2.0), alpha=0.95, zorder=5)



    # stops (discrete time bands, matching the legend exactly)

    def band_rgb(t):

        for lo, hi, c in C_BAND:

            if t <= hi:

                return to_rgb(c)

        return to_rgb(C_BAND[-1][2])



    cols = [band_rgb(t) for t in T]

    tr = ~direct

    ax.scatter(X[tr], Y[tr], s=cfg.get("s_tr", 7.0), c=[cols[i] for i in np.where(tr)[0]],

               marker="o", linewidths=0.35, edgecolors="white", alpha=0.95, zorder=6)

    ax.scatter(X[direct], Y[direct], s=cfg.get("s_dir", 18.0), c=[cols[i] for i in np.where(direct)[0]],

               marker="o", linewidths=0.6, edgecolors="#17242f", alpha=1.0, zorder=7)



    # outer boundary of the reachable set

    bound = find_boundary(X, Y, origin[0], origin[1],

                          hull_dist=cfg.get("hull_dist", 330.0), nbin=cfg.get("nbin", 36))

    if bound:

        bi = np.array(sorted(bound))

        ax.scatter(X[bi], Y[bi], s=cfg.get("s_bound", 46), marker="o", facecolors="none",

                   edgecolors="#7d1f31", linewidths=1.1, alpha=0.9, zorder=8)



    # origin

    ax.scatter([origin[0]], [origin[1]], s=cfg.get("star", 300), marker="*", c="#101010",

               edgecolors="white", linewidths=1.2, zorder=12)

    ax.scatter([origin[0]], [origin[1]], s=cfg.get("ring", 760), marker="o", facecolors="none",

               edgecolors="#101010", linewidths=1.0, alpha=0.5, zorder=11)



    # labels

    fig.canvas.draw()

    pl = Placer(ax, fig, ax.transData.transform(np.column_stack([X, Y])))

    # the origin marker is the only thing a label may never cover

    pl.add_dot(*ax.transData.transform(origin), r=cfg.get("star_px", 15))

    # scale bar + north arrow, auto-placed in the emptiest part of the map

    if cfg.get("scale", True):

        span_m = (xmax - xmin)

        km = cfg.get("scale_km", 5)

        for cand in (0.1, 0.2, 0.5, 1, 2, 3, 5, 10, 20, 50):

            if cand * 1000.0 <= span_m / 4.2:

                km = cand

        km = min(km, cfg.get("scale_km", 5))

        w = km * 1000.0 * math.cos(math.radians(40.0))

        h = (ymax - ymin) * 0.055

        bx, by = pick_empty_spot(X, Y, xmin, xmax, ymin, ymax, w, h)

        scale_bar(ax, pl, bx, by, km)

        ax_, ay_ = pick_empty_corner(X, Y, xmin, xmax, ymin, ymax)

        north_arrow(ax, pl, ax_, ay_, (ymax - ymin) * 0.042)



    # draw the origin callout here and reserve its measured box, so no label

    # can ever be placed underneath it

    if cfg.get("callout", True):

        ann = origin_callout(ax, origin, dx=cfg.get("callout_dx", 26),

                             dy=cfg.get("callout_dy", 18), fs=cfg.get("callout_fs", 12.5))

        fig.canvas.draw()

        try:

            r0 = fig.canvas.get_renderer()

            b2 = ann.get_window_extent(renderer=r0)

            pl.add_rect(b2.x0 - 5, b2.y0 - 5, b2.x1 + 5, b2.y1 + 5)

        except Exception:

            px, py = ax.transData.transform(origin)

            pl.add_rect(px - 40, py - 20, px + 340, py + 80)



    vis = (X > xmin) & (X < xmax) & (Y > ymin) & (Y < ymax)



    names_seen = set(cfg.get("reserved_names", ()))

    visidx = list(np.where(vis)[0])

    placed = {"area": 0, "bound": 0, "hub": 0, "land": 0, "periph": 0}

    items = []          # (priority, annotation) for the final collision pass

    area_pts = []       # (name, x, y) of district labels, for redundancy filtering



    # ---- pass 1: district / area names (orientation layer) ----

    if cfg.get("show_areas", True):

        for nm, ax0, ay0 in area_labels(reach, X, Y):

            if not (xmin < ax0 < xmax and ymin < ay0 < ymax):

                continue

            ann = pl.place(ax0, ay0, nm, cfg.get("area_fs", 15.0), "#546a7b",

                           weight="normal", halo=cfg.get("area_halo", 4.2), pad=7.0,

                           spacing=True, leash=1e9, gaps=(0, 6, 12), avoid_dots=False)

            if ann is not None:

                placed["area"] += 1

                items.append((9000, ann))

                area_pts.append((nm, ax0, ay0))



    def near_area(stop, x, y, r=1900.0):

        """True if a stop name repeats an already-labelled district name nearby."""

        for nm, ax0, ay0 in area_pts:

            if nm in stop and math.hypot(x - ax0, y - ay0) < r:

                return True

        return False



    # ---- pass 2: outer boundary stops ----

    if bound:

        bcap = cfg.get("bound_cap", 90)



        def bkey(i):

            r = math.hypot(X[i] - origin[0], Y[i] - origin[1])

            return -(r / 1000.0 * 6.0 + reach[i].get("n_lines", 0))

        nb_done = 0

        for i in sorted(bound, key=bkey):

            if nb_done >= bcap:

                break

            st = reach[i]["stop"]

            if st in names_seen or not vis[i]:

                continue

            _x, _y = X[i], Y[i]

            if near_area(st, _x, _y, r=1300.0):

                continue          # the district name already covers this spot

            ann = pl.place(_x, _y, st, cfg.get("fs_bound", 7.1), "#6d1a2b",

                           weight="bold", halo=2.2)

            if ann is not None:

                names_seen.add(st)

                placed["bound"] += 1

                nb_done += 1

                items.append((7000 + i, ann))



    # ---- pass 3: big interchanges (many lines) ----

    hub_thr = cfg.get("hub_thr", 10)

    hubs = [i for i in visidx

            if reach[i].get("n_lines", 0) >= hub_thr and reach[i]["stop"] not in names_seen]

    hubs.sort(key=lambda i: -reach[i].get("n_lines", 0))

    for i in hubs:

        st = reach[i]["stop"]

        if st in names_seen:

            continue

        _x, _y = X[i], Y[i]

        if near_area(st, _x, _y):

            continue

        fs = cfg.get("fs_hub", 8.0) if reach[i].get("n_lines", 0) >= hub_thr + 3 else cfg.get("fs_hub2", 7.2)

        ann = pl.place(_x, _y, st, fs, "#0d2a35", weight="bold", halo=2.3, plate=True,

                       min_gap_px=12.0, gaps=(12.0, 14.5, 17.0), max_off=17.0)

        if ann is not None:

            names_seen.add(st)

            placed["hub"] += 1

            items.append((6000 + reach[i].get("n_lines", 0), ann))



    # ---- pass 4: curated landmarks ----

    for i in visidx:

        st = reach[i]["stop"]

        _x, _y = X[i], Y[i]

        if not LANDMARKS.get(st) or st in names_seen:

            continue

        if near_area(st, _x, _y):

            continue

        ann = pl.place(_x, _y, st, cfg.get("fs_land", 8.4), "#0f1c26", weight="bold", halo=2.3)

        if ann is not None:

            names_seen.add(st)

            placed["land"] += 1

            items.append((5000, ann))



    # ---- pass 5: remaining stops, picked on a regular grid so that the

    #              labels are spread evenly over the whole map ----

    if cfg.get("periph", True):

        cell = cfg.get("cell_m", 1300.0)

        minr = cfg.get("min_routes", 2)

        clean_r = cfg.get("clean_r", 5200)

        cand = [i for i in visidx

                if reach[i]["stop"] not in names_seen

                and reach[i].get("n_routes", 0) >= minr

                and math.hypot(X[i] - origin[0], Y[i] - origin[1]) >= clean_r]

        buckets = {}

        for i in cand:

            k = (int((X[i] - xmin) // cell), int((Y[i] - ymin) // cell))

            buckets.setdefault(k, []).append(i)

        for v in buckets.values():

            v.sort(key=lambda j: -(reach[j].get("n_routes", 0) * 2

                                   + min(reach[j].get("terminal", 0), 3)))

        maxr = max((len(v) for v in buckets.values()), default=0)

        quota = cfg.get("cell_quota", 3)

        seq = []

        for r in range(maxr):

            if r >= quota:

                break

            for k in sorted(buckets):

                if r < len(buckets[k]):

                    seq.append(buckets[k][r])

        for i in seq:

            if len(items) >= cfg.get("max_labels", 720):

                break

            _x, _y = X[i], Y[i]

            if reach[i]["stop"] in names_seen or near_area(reach[i]["stop"], _x, _y):

                continue

            ann = pl.place(_x, _y, reach[i]["stop"],

                           cfg.get("fs_minor", 6.0) if reach[i].get("n_routes", 0) >= 3

                           else cfg.get("fs_minor2", 5.6), "#2c3e4d", halo=1.9)

            if ann is not None:

                names_seen.add(reach[i]["stop"])

                placed["periph"] += 1

                items.append((1000 + reach[i].get("n_routes", 0), ann))



    kept = prune_labels(ax, fig, items, pad=cfg.get("prune_pad", 2.6))

    print("  labels: placed=%d kept=%d %s" % (len(items), kept, placed))



    n = kept

    return n, (xmin, xmax, ymin, ymax), len(bound), placed





def legend(fig, ax, cfg):

    """discrete time-band swatches + symbol legend (no continuous ramp: the map

    itself only uses these four colours)."""

    hs = [Patch(facecolor=c, edgecolor="white", linewidth=0.6,

                label=u"%d–%d 分钟" % (lo, hi)) for lo, hi, c in C_BAND]

    l1 = fig.legend(handles=hs, loc="lower left",

                    bbox_to_anchor=cfg.get("time_anchor", (0.044, 0.0475)),

                    fontsize=cfg.get("time_fs", 8.8), frameon=False,

                    ncol=4, handlelength=1.5, handleheight=0.9,

                    columnspacing=1.1, handletextpad=0.45, borderpad=0.1)



    h = [Line2D([], [], marker="o", linestyle="none", markersize=8, markerfacecolor="#5b6b7a",

                markeredgecolor="#17242f", markeredgewidth=0.7, label=u"直达站点"),

         Line2D([], [], marker="o", linestyle="none", markersize=5.4, markerfacecolor="#8fa3b5",

                markeredgecolor="white", markeredgewidth=0.6, label=u"换乘一次可达"),

         Line2D([], [], marker="s", linestyle="none", markersize=8, markerfacecolor="white",

                markeredgecolor="#123743", markeredgewidth=0.8, label=u"大型换乘枢纽")]

    if cfg.get("show_bound", True):

        h.append(Line2D([], [], marker="o", linestyle="none", markersize=9, markerfacecolor="none",

                        markeredgecolor="#7d1f31", markeredgewidth=1.3, label=u"可达边界站点"))

    h.append(Line2D([], [], marker="*", linestyle="none", markersize=15, markerfacecolor="#101010",

                    markeredgecolor="white", label=u"起点 学院路北口"))

    l2 = fig.legend(handles=h, loc="lower left",

                    bbox_to_anchor=cfg.get("sym_anchor", (0.50, 0.0405)),

                    fontsize=cfg.get("sym_fs", 8.2), frameon=False,

                    labelspacing=0.32, handletextpad=0.8, borderpad=0.1,

                    ncol=cfg.get("sym_cols", 2), columnspacing=1.4)

    return l1, l2





def scale_bar(ax, pl, x, y, km, fs=9.5, color="#1b2832"):

    """Bar length corrected for the Mercator scale factor, drawn above the labels,

    with a white casing, and the area is reserved so no label is placed there."""

    lat = math.degrees(2.0 * math.atan(math.exp(y / R)) - math.pi / 2.0)

    seg = km * 1000.0 * math.cos(math.radians(lat))

    ax.plot([x, x + seg], [y, y], lw=8.0, color="white", solid_capstyle="butt", zorder=4.5)

    ax.plot([x, x + seg], [y, y], lw=3.8, color=color, solid_capstyle="butt", zorder=4.6)

    for xx in (x, x + seg):

        ax.plot([xx, xx], [y - 160, y + 160], lw=6.5, color="white", zorder=4.5)

        ax.plot([xx, xx], [y - 160, y + 160], lw=1.7, color=color, zorder=4.6)

    ax.plot([x + seg / 2, x + seg / 2], [y - 105, y + 105], lw=1.1, color=color, zorder=4.6)

    ax.text(x + seg / 2, y + 300, u"%d km" % km, ha="center", va="bottom", fontsize=fs,

            color=color, zorder=4.6,

            bbox=dict(boxstyle="square,pad=0.18", fc="white", ec="none", alpha=0.9))

    if pl is not None:

        px0, py0 = ax.transData.transform((x, y - 320))

        px1, py1 = ax.transData.transform((x + seg, y + 620))

        pl.add_rect(min(px0, px1) - 8, min(py0, py1) - 8, max(px0, px1) + 8, max(py0, py1) + 8)





def north_arrow(ax, pl, cx, cy, h):

    ax.annotate("", xy=(cx, cy + h), xytext=(cx, cy),

                arrowprops=dict(arrowstyle="-|>", color="#1b2832", lw=1.9, mutation_scale=17,

                                shrinkA=0, shrinkB=0,

                                path_effects=[pe.withStroke(linewidth=4.5, foreground="white")]),

                zorder=4.6)

    ax.text(cx, cy + h * 1.10, u"北", ha="center", va="bottom", fontsize=11, color="#1b2832",

            zorder=4.6, path_effects=[pe.withStroke(linewidth=3.2, foreground="white")])

    if pl is not None:

        px0, py0 = ax.transData.transform((cx - h * 0.5, cy - h * 0.15))

        px1, py1 = ax.transData.transform((cx + h * 0.5, cy + h * 1.45))

        pl.add_rect(min(px0, px1) - 6, min(py0, py1) - 6, max(px0, px1) + 6, max(py0, py1) + 6)





def origin_callout(ax, origin, text=u"起点  学院路北口", dx=26, dy=18, fs=12.5):

    """Place the label on whichever side has room, and keep it inside the axes."""

    x0, x1 = ax.get_xlim()

    px = ax.transData.transform(origin)[0]

    bb = ax.get_window_extent()

    # rough label width in points -> pixels

    w_px = (len(text) * fs * 1.05 + 16) * ax.figure.dpi / 72.0

    if px + dx * ax.figure.dpi / 72.0 + w_px > bb.x1 - 4:

        dx = -dx - (w_px * 72.0 / ax.figure.dpi)     # flip to the left of the dot

        ha = "right"

    else:

        ha = "left"

    ann = ax.annotate(text, xy=origin, xytext=(dx, dy), textcoords="offset points",

                      ha=ha, fontsize=fs, fontweight="bold", color="#101010", zorder=40,

                      bbox=dict(boxstyle="round,pad=0.45", fc="#fff4c2", ec="#8f7f33",

                                lw=1.1, alpha=0.98),

                      arrowprops=dict(arrowstyle="-", color="#101010", lw=1.3,

                                      shrinkA=0, shrinkB=6))





def origin_xy():

    try:

        leg1 = load("out_leg1.json")["leg1"]

        o = [(e["lon"], e["lat"]) for e in leg1 if e.get("origin_rank") == 0 and e["lon"]]

        if o:

            return merc(np.mean([p[0] for p in o]), np.mean([p[1] for p in o]))

    except Exception:

        pass

    return merc(116.3479, 39.9852)





def overview():

    setup_font()

    reach = load("out_reach_geo.json")["reach"]

    geoms = load("out_reach_geo.json")["geoms"]

    extent = load("base_extent.json")

    from PIL import Image

    base = np.asarray(Image.open(os.path.join(HERE, "base_light.png")).convert("RGB"))



    X, Y = merc([x["lon"] for x in reach], [x["lat"] for x in reach])

    ox, oy = origin_xy()

    pad = 700

    view = (X.min() - pad, X.max() + pad, Y.min() - pad, Y.max() + pad)



    aspect = (view[1] - view[0]) / (view[3] - view[2])

    if aspect >= 0.85:                     # square-ish / wide: adaptive canvas

        figh = 11.6

        figw = figh * aspect / 1.10

        if figw > 19.0:

            figw = 19.0

            figh = figw * 1.14 / aspect

        figsize = (figw, figh)

    else:

        figsize = (11.4, 17.6)

    fig = plt.figure(figsize=figsize, dpi=200, facecolor="white")

    H = figsize[1]

    BOTTOM = 1.62 / H

    TOP = 1.02 / H

    rect = fit_axes(fig, 0.045, BOTTOM, 0.91, 1.0 - TOP - BOTTOM, aspect)

    ax = fig.add_axes(rect)



    cfg = dict(view=view, access=780, nx=620, ny=900,

               hub_thr=10, max_labels=760, min_routes=2, clean_r=5400, cell_m=1250, cell_quota=2,

               fs_hub=7.8, fs_hub2=7.0, fs_bound=7.0, fs_land=8.2, fs_minor=6.0, fs_minor2=5.6,

               area_fs=12.2, area_halo=3.4, reserved_names=(u"学院路北口",), time_anchor=(0.044, 1.06 / H), sym_anchor=(0.50, 0.94 / H))

    cfg.update(scale_km=5, scale_x=0.66, scale_y=0.050,

               arrow_x=0.052, arrow_y=0.140, arrow_h=0.042)

    n, view, nb, placed = draw(fig, ax, reach, geoms, base, extent, (ox, oy), cfg)

    legend(fig, ax, cfg)





    n_direct = sum(1 for x in reach if x["kind"] in ("direct", "walk"))

    n_walk = sum(1 for x in reach if x["kind"] == "walk")

    fig.text(0.045, 1.0 - 0.16 / H, u"北京公交 60 分钟可达范围", fontsize=28, fontweight="bold", color="#0d1720", va="top")

    fig.text(0.045, 1.0 - 0.62 / H, u"自「学院路北口」公交站出发 · 最多换乘一次 · 含候车与换乘步行、" + wait_note(),

             fontsize=13.5, color="#3a4b5a", va="top")

    fig.text(0.955, 1.0 - 0.32 / H, time.strftime("%Y-%m-%d"), fontsize=11, color="#6b7a88", ha="right", va="top")



    # bottom info strip: discrete time-band key + label key

    fig.text(0.045, 1.42 / H, u"预计总耗时（分钟，含候车与换乘步行）", fontsize=9, color="#33434f")



    fig.text(0.045, 0.82 / H,

             u"可达公交站点 %d 个（直达 %d · 步行 %d · 换乘一次 %d）· 可达边界站点 %d 个 · 图上标注 %d 个站名 · 灰色大字为片区名"

             % (len(reach), n_direct - n_walk, n_walk, len(reach) - n_direct, nb, n), fontsize=9, color="#33434f")

    fig.text(0.045, 0.54 / H,

             u"时间模型：候车＝密集线路取发车间隔÷2、班次疏（≥20 min）的线路按掐点 0 分钟；乘车＝各分段行程时间中位数；"

             u"换乘步行＝90 m ＋ 直线距离/1.1 m·s⁻¹（同名站点 700 m 内）；起点 1.2 km 内按步行计",

             fontsize=8.0, color="#5b6b7a")

    fig.text(0.045, 0.26 / H,

             u"已剔除夜间线路与快速直达专线 · 范围约 %.0f × %.0f km · 底图 © Esri, HERE, Garmin, "

             u"© OpenStreetMap contributors · 公交数据 bjbus.jinzihao.me"

             % ((view[1] - view[0]) / 1000.0 * math.cos(math.radians(40)),

                (view[3] - view[2]) / 1000.0 * math.cos(math.radians(40))),

             fontsize=7.8, color="#7b8894")

    out = os.path.join(HERE, "bjbus_reach60.png")

    fit_texts(fig)
    fig.savefig(out, dpi=200, facecolor="white")

    print("overview:", out, os.path.getsize(out), "labels", n, "size", fig.get_size_inches())





def core():

    setup_font()

    reach = load("out_reach_geo.json")["reach"]

    geoms = load("out_reach_geo.json")["geoms"]

    extent = load("base_core_extent.json")

    from PIL import Image

    base = np.asarray(Image.open(os.path.join(HERE, "base_core.png")).convert("RGB"))



    ox, oy = origin_xy()

    x0, _ = merc(116.3110, 39.9410)

    x1, _ = merc(116.3960, 39.9410)

    _, y0 = merc(0, 39.9410)

    _, y1 = merc(0, 40.0310)

    view = (x0, x1, y0, y1)



    aspect = (view[1] - view[0]) / (view[3] - view[2])

    if aspect >= 1.05:

        figh = 11.5

        figw = figh * aspect / 1.12

        if figw > 18.0:

            figw = 18.0

            figh = figw * 1.12 / aspect

        figsize = (figw, figh)

    else:

        figsize = (11.6, 15.4)

    fig = plt.figure(figsize=figsize, dpi=200, facecolor="white")

    rect = fit_axes(fig, 0.04, 0.105, 0.92, 0.83, aspect)

    ax = fig.add_axes(rect)



    cfg = dict(view=view, access=520, nx=620, ny=860, max_labels=760,

               min_routes=1, fs_hub=8.4, fs_hub2=7.6, fs_bound=7.0, fs_land=8.4,

               fs_minor=6.2, fs_minor2=5.8, show_areas=False, show_bound=False, periph=True,

               clean_r=0, cell_m=700, cell_quota=6, prune_pad=3.2, fabric=False,

               reserved_names=(u"学院路北口",),

               band_alpha=[0.24, 0.22, 0.18, 0.12], iso_lines=False, access_mask=520,

               s_tr=15, s_dir=26, star=360, ring=900,

               time_anchor=(0.045, 0.044), sym_anchor=(0.47, 0.040), sym_cols=2)

    cfg.update(scale_km=2, scale_x=0.60, scale_y=0.036,

               arrow_x=0.055, arrow_y=0.100, arrow_h=0.036)

    cfg.update(callout_dx=26, callout_dy=20, callout_fs=13)

    n, view, nb, placed = draw(fig, ax, reach, geoms, base, extent, (ox, oy), cfg)

    legend(fig, ax, cfg)





    fig.text(0.04, 0.968, u"核心区放大：学院路—中关村—清河—亚运村", fontsize=24, fontweight="bold", color="#0d1720")

    fig.text(0.04, 0.9485, u"与总图同一时间模型 · 标注 %d 个站点（过密处自动避让，未标注的站点仍以圆点表示）" % n,

             fontsize=12.0, color="#3a4b5a")

    fig.text(0.04, 0.020,

             u"底图 © Esri, HERE, Garmin, © OpenStreetMap contributors · 公交数据 bjbus.jinzihao.me",

             fontsize=8.2, color="#7b8894")

    out = os.path.join(HERE, "bjbus_reach60_core.png")

    fit_texts(fig)
    fig.savefig(out, dpi=200, facecolor="white")

    print("core:", out, os.path.getsize(out), "labels", n)





def window(lon0, lon1, lat0, lat1, out, figw=11.0):

    """Render an arbitrary lon/lat window (QA or detail view)."""

    setup_font()

    reach = load("out_reach_geo.json")["reach"]

    geoms = load("out_reach_geo.json")["geoms"]

    extent = load("base_extent.json")

    from PIL import Image

    baseimg = np.asarray(Image.open(os.path.join(HERE, "base_light.png")).convert("RGB"))

    ox, oy = origin_xy()

    x0, _ = merc(lon0, lat0)

    x1, _ = merc(lon1, lat0)

    _, y0 = merc(lon0, lat0)

    _, y1 = merc(lon0, lat1)

    view = (x0, x1, y0, y1)

    aspect = (x1 - x0) / (y1 - y0)

    figh = figw / aspect * 1.12

    fig = plt.figure(figsize=(figw, figh), dpi=200, facecolor="white")

    rect = fit_axes(fig, 0.03, 0.06, 0.94, 0.90, aspect)

    ax = fig.add_axes(rect)

    cfg = dict(view=view, access=400, nx=700, ny=780, max_labels=420, min_routes=1,

               fs_hub=9.0, fs_hub2=8.0, fs_bound=8.0, fs_land=9.0, fs_minor=7.0, fs_minor2=6.6,

               show_areas=True, show_bound=True, periph=True, clean_r=0, cell_m=300, cell_quota=8,

               prune_pad=1.4, band_alpha=[0.30, 0.28, 0.24, 0.15], iso_lines=False,

               fabric=True, fabric_lw=0.6, fabric_alpha=0.25, fabric_max_seg=1200,

               s_tr=16, s_dir=26, star=340, ring=900, area_fs=15.0,

               time_anchor=(0.03, 0.014), sym_anchor=(0.42, 0.008))

    cfg.update(callout_dx=22, callout_dy=14, callout_fs=11)

    n, view, nb, placed = draw(fig, ax, reach, geoms, baseimg, extent, (ox, oy), cfg)

    legend(fig, ax, cfg)

    out_path = os.path.join(HERE, out)

    fit_texts(fig)
    fig.savefig(out_path, dpi=200, facecolor="white")

    print("window:", out_path, "labels", n)





if __name__ == "__main__":

    which = sys.argv[1] if len(sys.argv) > 1 else "all"

    if which == "window":

        window(float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4]),

               float(sys.argv[5]), sys.argv[6])

    else:

        if which in ("all", "overview"):

            overview()

        if which in ("all", "core"):

            core()









