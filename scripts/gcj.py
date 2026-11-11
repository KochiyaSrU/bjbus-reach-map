# -*- coding: utf-8 -*-
"""GCJ-02 <-> WGS-84 conversion (standard public algorithm)."""
import math

A = 6378245.0
EE = 0.00669342162296594323


def _out_of_china(lon, lat):
    return not (73.66 < lon < 135.05 and 3.86 < lat < 53.55)


def _d_lat(x, y):
    ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(y * math.pi) + 40.0 * math.sin(y / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (160.0 * math.sin(y / 12.0 * math.pi) + 320 * math.sin(y * math.pi / 30.0)) * 2.0 / 3.0
    return ret


def _d_lon(x, y):
    ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(x * math.pi) + 40.0 * math.sin(x / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (150.0 * math.sin(x / 12.0 * math.pi) + 300.0 * math.sin(x / 30.0 * math.pi)) * 2.0 / 3.0
    return ret


def wgs2gcj(lon, lat):
    if _out_of_china(lon, lat):
        return lon, lat
    dlat = _d_lat(lon - 105.0, lat - 35.0)
    dlon = _d_lon(lon - 105.0, lat - 35.0)
    rad = math.radians(lat)
    magic = 1 - EE * math.sin(rad) ** 2
    sq = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((A * (1 - EE)) / (magic * sq) * math.pi)
    dlon = (dlon * 180.0) / (A / sq * math.cos(rad) * math.pi)
    return lon + dlon, lat + dlat


def gcj2wgs(lon, lat, iters=6):
    """Iterative inverse of wgs2gcj."""
    if _out_of_china(lon, lat):
        return lon, lat
    wlon, wlat = lon, lat
    for _ in range(iters):
        glon, glat = wgs2gcj(wlon, wlat)
        wlon -= (glon - lon)
        wlat -= (glat - lat)
    return wlon, wlat


if __name__ == "__main__":
    for lon, lat in ((116.353, 39.9975), (116.3975, 39.9075)):
        g = wgs2gcj(lon, lat)
        w = gcj2wgs(g[0], g[1])
        print("%.6f %.6f -> gcj %.6f %.6f (d=%.0f m, %.0f m) -> back %.6f %.6f"
              % (lon, lat, g[0], g[1], (g[0] - lon) * 85200, (g[1] - lat) * 111000, w[0], w[1]))
