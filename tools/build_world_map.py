"""
Build assets/world-map.json: one SVG path per country (keyed by ISO 3166-1 alpha-2), in an
Equal Earth projection, for the admin "Global reach" map.

    python tools/build_world_map.py <countries-50m.json> <iso-codes.csv> <india-composite.geojson>

Needs shapely (pip install shapely) for the India boundary.

India is drawn per the official boundary (Survey of India): the whole of Jammu & Kashmir and
Ladakh, including PoK, Gilgit-Baltistan and Aksai Chin. Natural Earth alone draws the de facto
lines, so the third input replaces India's shape and is cut out of Pakistan and China.

Inputs (download once, not committed):
  india-composite.geojson
                      https://raw.githubusercontent.com/datameet/maps/master/Country/india-composite.geojson
                      (DataMeet, CC0; official boundary of India incl. disputed territories)
  countries-50m.json  https://cdn.jsdelivr.net/npm/world-atlas@2.0.2/countries-50m.json
                      (Natural Earth 1:50m, public domain; world-atlas is ISC licensed)
  iso-codes.csv       https://raw.githubusercontent.com/lukes/ISO-3166-Countries-with-Regional-Codes/master/all/all.csv

Output: {"w": 1000, "h": ..., "paths": {"IN": "M…Z", ...}, "dots": {"SG": [x, y], ...}}
`dots` gives a marker position for every country in backend/services/countries.py, so places
too small to see as a shape (Singapore, Bahrain, Maldives…) still show on the map.
Antarctica is left out.
"""
import csv
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets", "world-map.json")
WIDTH = 1000
TOLERANCE = 0.35     # simplification, in output pixels
MIN_RING_AREA = 0.6  # drop islands smaller than this (px²) unless they are a country's only shape

# Natural Earth shapes without an ISO numeric code.
UNCODED = {"Kosovo": "XK", "Somaliland": "SO", "N. Cyprus": "CY", "Siachen Glacier": "IN"}

# Marker positions (lon, lat) for countries/territories missing from the 1:50m shapes.
EXTRA_LONLAT = {
    "BH": (50.55, 26.07), "MV": (73.5, 4.2), "MU": (57.55, -20.25), "SG": (103.82, 1.35), "MT": (14.45, 35.9),
    "HK": (114.17, 22.32), "MO": (113.55, 22.17), "AD": (1.52, 42.51), "MC": (7.42, 43.74), "SM": (12.46, 43.94),
    "VA": (12.45, 41.9), "LI": (9.55, 47.15), "GI": (-5.35, 36.14), "TV": (179.2, -8.5), "NR": (166.93, -0.53),
    "MH": (171.0, 7.1), "PW": (134.5, 7.5), "FM": (158.2, 6.9), "KI": (-157.4, 1.9), "TO": (-175.2, -21.2),
    "WS": (-172.1, -13.75), "SC": (55.45, -4.65), "KM": (43.3, -11.7), "ST": (6.6, 0.25), "CV": (-23.6, 15.1),
    "BB": (-59.55, 13.15), "AG": (-61.8, 17.1), "DM": (-61.35, 15.42), "GD": (-61.68, 12.12), "KN": (-62.75, 17.3),
    "LC": (-60.97, 13.9), "VC": (-61.2, 13.25), "AW": (-69.97, 12.52), "CW": (-68.95, 12.17), "SX": (-63.05, 18.04),
    "BQ": (-68.26, 12.15), "AI": (-63.06, 18.22), "MS": (-62.19, 16.74), "VG": (-64.62, 18.42), "VI": (-64.8, 18.34),
    "KY": (-81.25, 19.31), "BM": (-64.75, 32.31), "TC": (-71.8, 21.8), "GP": (-61.55, 16.25), "MQ": (-61.02, 14.64),
    "BL": (-62.83, 17.9), "MF": (-63.07, 18.07), "PM": (-56.3, 46.9), "RE": (55.53, -21.12), "YT": (45.15, -12.82),
    "GF": (-53.1, 3.95), "IO": (72.4, -7.3), "CX": (105.69, -10.45), "CC": (96.87, -12.17), "NF": (167.95, -29.03),
    "CK": (-159.78, -21.23), "NU": (-169.87, -19.05), "TK": (-171.85, -9.2), "WF": (-176.2, -13.3), "AS": (-170.7, -14.3),
    "GU": (144.79, 13.44), "MP": (145.75, 15.18), "PF": (-149.45, -17.65), "SH": (-5.7, -15.95), "FO": (-6.9, 62.0),
    "GG": (-2.58, 49.45), "JE": (-2.13, 49.21), "IM": (-4.55, 54.23), "AX": (19.95, 60.2), "SJ": (16.0, 78.5),
    "PR": (-66.5, 18.22), "FK": (-59.5, -51.75), "NC": (165.6, -21.3), "TL": (125.7, -8.8), "BN": (114.7, 4.5),
}


def equal_earth(lon, lat):
    a1, a2, a3, a4 = 1.340264, -0.081106, 0.000893, 0.003796
    m = math.sqrt(3) / 2
    lam, phi = math.radians(lon), math.radians(lat)
    theta = math.asin(m * math.sin(phi))
    t2 = theta * theta
    t6 = t2 * t2 * t2
    x = lam * math.cos(theta) / (m * (a1 + 3 * a2 * t2 + t6 * (7 * a3 + 9 * a4 * t2)))
    y = theta * (a1 + a2 * t2 + t6 * (a3 + a4 * t2))
    return x, y


# Full extent of the projection, so the map is framed the same whatever data is drawn.
_XMAX = equal_earth(180, 0)[0]
_YMAX = equal_earth(0, 90)[1]
_YTOP = equal_earth(0, 85)[1]    # crop the empty Arctic
_YBOT = equal_earth(0, -58)[1]   # and below Tierra del Fuego (no Antarctica)
SCALE = WIDTH / (2 * _XMAX)
HEIGHT = round((_YTOP - _YBOT) * SCALE, 1)


def project(lon, lat):
    x, y = equal_earth(lon, lat)
    return (x + _XMAX) * SCALE, (_YTOP - y) * SCALE


def decode_arcs(topo):
    sx, sy = topo["transform"]["scale"]
    tx, ty = topo["transform"]["translate"]
    arcs = []
    for arc in topo["arcs"]:
        x = y = 0
        pts = []
        for dx, dy in arc:
            x += dx
            y += dy
            pts.append((x * sx + tx, y * sy + ty))  # lon, lat; projected later
        arcs.append(pts)
    return arcs


def ring_points(ring, arcs):
    """Projected ring(s) for one topojson ring. A ring that crosses the date line (Russia's
    Chukotka) is split into its eastern and western parts so no band is drawn across the map."""
    pts = []
    for i in ring:
        seg = arcs[i] if i >= 0 else arcs[~i][::-1]
        pts.extend(seg if not pts else seg[1:])
    crosses = any(abs(pts[k][0] - pts[k - 1][0]) > 180 for k in range(1, len(pts)))
    parts = [[p for p in pts if p[0] >= 0], [p for p in pts if p[0] < 0]] if crosses else [pts]
    out = []
    for part in parts:
        if len(part) >= 3:
            if part[0] != part[-1]:
                part.append(part[0])
            out.append(part)
    return out  # lon/lat rings; projected in main()


def apply_india_boundary(rings_by_iso, path):
    """Draw India as the Government of India / Survey of India boundary: all of Jammu & Kashmir
    and Ladakh, including PoK, Gilgit-Baltistan, Aksai Chin and the Shaksgam Valley.

    India = official outline ∪ Natural Earth India (so coasts and islands match the rest of the
    map), and that whole shape is cut out of every neighbour, so Pakistan and China no longer
    cover those areas and no gap opens along the borders."""
    from shapely.geometry import Polygon, shape
    from shapely.ops import unary_union

    gj = json.load(open(path, encoding="utf-8"))
    feats = gj.get("features") or [gj]
    official = unary_union([shape(f["geometry"]).buffer(0) for f in feats]).simplify(0.005)
    natural = [Polygon(r).buffer(0) for r in rings_by_iso.get("IN", [])]
    india = unary_union([official, *natural]).buffer(0)
    minx, miny, maxx, maxy = india.bounds

    def parts(geom):
        return [g for g in getattr(geom, "geoms", [geom]) if g.geom_type == "Polygon" and not g.is_empty]

    for iso, rings in rings_by_iso.items():
        if iso == "IN":
            continue
        out = []
        for r in rings:
            xs, ys = [p[0] for p in r], [p[1] for p in r]
            if max(xs) < minx or min(xs) > maxx or max(ys) < miny or min(ys) > maxy:
                out.append(r)
                continue
            poly = Polygon(r).buffer(0)
            if not poly.intersects(india):
                out.append(r)
                continue
            pieces = sorted(parts(poly.difference(india)), key=lambda g: -g.area)
            # Keep the main body; drop hairline slivers left where the two border sources differ.
            out.extend(list(g.exterior.coords) for k, g in enumerate(pieces) if k == 0 or not g.buffer(-0.03).is_empty)
        rings_by_iso[iso] = out
    rings_by_iso["IN"] = [list(g.exterior.coords) for g in parts(india)]
    return rings_by_iso


def simplify(pts, tol):
    """Douglas-Peucker. A closed ring (first point == last) is split at its farthest point,
    since a segment from a point to itself measures nothing."""
    if len(pts) < 4:
        return pts
    if pts[0] == pts[-1]:
        x0, y0 = pts[0]
        far = max(range(len(pts)), key=lambda i: (pts[i][0] - x0) ** 2 + (pts[i][1] - y0) ** 2)
        if 0 < far < len(pts) - 1:
            return _dp(pts[:far + 1], tol) + _dp(pts[far:], tol)[1:]
    return _dp(pts, tol)


def _dp(pts, tol):
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        ax, ay = pts[a]
        bx, by = pts[b]
        dx, dy = bx - ax, by - ay
        norm = math.hypot(dx, dy) or 1e-9
        best, idx = 0.0, -1
        for i in range(a + 1, b):
            px, py = pts[i]
            d = abs(dy * px - dx * py + bx * ay - by * ax) / norm
            if d > best:
                best, idx = d, i
        if best > tol and idx > 0:
            keep[idx] = True
            stack.append((a, idx))
            stack.append((idx, b))
    return [p for p, k in zip(pts, keep) if k]


def area(pts):
    return abs(sum(pts[i][0] * pts[i - 1][1] - pts[i - 1][0] * pts[i][1] for i in range(len(pts)))) / 2


def centroid(pts):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return [round((min(xs) + max(xs)) / 2, 1), round((min(ys) + max(ys)) / 2, 1)]


def fmt(v):
    s = f"{v:.1f}"
    return s[:-2] if s.endswith(".0") else s


def path_d(rings):
    out = []
    for pts in rings:
        out.append("M" + "L".join(f"{fmt(x)},{fmt(y)}" for x, y in pts) + "Z")
    return "".join(out)


def main():
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)
    topo = json.load(open(sys.argv[1], encoding="utf-8"))
    numeric_to_iso = {}
    with open(sys.argv[2], encoding="utf-8") as f:
        for row in csv.DictReader(f):
            numeric_to_iso[row["country-code"].lstrip("0") or "0"] = row["alpha-2"]

    sys.path.insert(0, os.path.join(ROOT, "backend"))
    from services.countries import COUNTRIES  # noqa: E402
    known = {c[0] for c in COUNTRIES}

    arcs = decode_arcs(topo)
    rings_by_iso: dict[str, list] = {}
    skipped = []
    for g in topo["objects"]["countries"]["geometries"]:
        name = g.get("properties", {}).get("name", "")
        iso = UNCODED.get(name) or numeric_to_iso.get(str(g.get("id", "")).lstrip("0"))
        if not iso or iso == "AQ" or iso not in known:
            skipped.append(name)
            continue
        polys = g["arcs"] if g["type"] == "MultiPolygon" else [g["arcs"]] if g["type"] == "Polygon" else []
        for poly in polys:
            for k, ring in enumerate(poly):
                if k > 0:
                    continue  # holes (e.g. Lesotho inside South Africa) are their own country
                rings_by_iso.setdefault(iso, []).extend(ring_points(ring, arcs))

    rings_by_iso = apply_india_boundary(rings_by_iso, sys.argv[3])

    paths, dots = {}, {}
    for iso, rings in rings_by_iso.items():
        rings = [[project(lon, lat) for lon, lat in r] for r in rings]
        simple = [simplify(r, TOLERANCE) for r in rings]
        simple = [r for r in simple if len(r) >= 3]
        biggest = max(simple, key=area) if simple else None
        kept = [r for r in simple if area(r) >= MIN_RING_AREA] or ([biggest] if biggest else [])
        if kept:
            paths[iso] = path_d(kept)
            dots[iso] = centroid(max(kept, key=area))
    for iso, (lon, lat) in EXTRA_LONLAT.items():
        if iso not in dots:
            x, y = project(lon, lat)
            dots[iso] = [round(x, 1), round(y, 1)]

    missing = sorted(known - set(dots))
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"w": WIDTH, "h": HEIGHT, "paths": dict(sorted(paths.items())), "dots": dict(sorted(dots.items()))},
                  f, separators=(",", ":"))
    print(f"Wrote {OUT}: {len(paths)} shapes, {len(dots)} markers, {os.path.getsize(OUT) // 1024} KB")
    if skipped:
        print("Skipped (no ISO / not in country list):", ", ".join(sorted(set(skipped))))
    if missing:
        print("No marker position for:", ", ".join(missing))


if __name__ == "__main__":
    main()
