# augment_gpx.py
import sys, time, math, argparse, os, io
from pathlib import Path
import numpy as np

import osmium as osm
from lxml import etree
from pyproj import Transformer

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
except Exception:
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
def log(msg): print(msg, flush=True)
def tick_every(n, i): return (i % n) == 0

SEARCH_RADIUS_M = 5.0
BBOX_MARGIN_M   = 10.0
VERBOSE         = True
SAMPLE_WAYS_PRINT = 5
PROGRESS_EVERY_WAYS = 2000
PROGRESS_EVERY_PTS  = 50

DEFAULTS = {
    "motorway":130,"trunk":100,"primary":70,"secondary":70,"tertiary":50,
    "unclassified":50,"residential":50,"motorway_link":80,"trunk_link":80,
    "primary_link":70,"secondary_link":60,
}
to_xy = Transformer.from_crs(4326, 3857, always_xy=True)

try:
    from rtree import index as rtree_index
    USE_RTREE = True
except Exception:
    USE_RTREE = False

def default_by_highway(hw): return float(DEFAULTS.get(hw or "", 50.0))

def meters_to_deglatlon(lat_deg, meters):
    lat_rad = math.radians(lat_deg)
    m_per_deg_lat = 111132.92 - 559.82*math.cos(2*lat_rad) + 1.175*math.cos(4*lat_rad)
    m_per_deg_lon = 111412.84*math.cos(lat_rad) - 93.5*math.cos(3*lat_rad)
    return meters/m_per_deg_lat, meters/max(m_per_deg_lon,1e-9)

def point_segment_distance(x,y,x1,y1,x2,y2):
    dx, dy = x2-x1, y2-y1
    seg_len2 = dx*dx+dy*dy
    if seg_len2 == 0.0:
        return math.hypot(x-x1,y-y1), 0.0
    t = ((x-x1)*dx+(y-y1)*dy)/seg_len2
    t = max(0.0, min(1.0, t))
    px, py = x1+t*dx, y1+t*dy
    return math.hypot(x-px,y-py), t

def assign_maxspeed_to_point(lat, lon, segs, idx=None, radius=SEARCH_RADIUS_M):
    x, y = to_xy.transform(lon, lat)
    best_d = float("inf"); best_v=None; best_hi=None; best_i=-1; best_t=0.0
    cand_ids = range(len(segs))
    if idx is not None:
        cand_ids = idx.intersection((x-radius, y-radius, x+radius, y+radius))
    for i in cand_ids:
        s = segs[i]
        d, t = point_segment_distance(x,y,s["x1"],s["y1"],s["x2"],s["y2"])
        if d < best_d:
            vmax = s["vmax_kmh"] if s["vmax_kmh"] is not None else default_by_highway(s["highway"])
            best_d, best_v, best_hi, best_i, best_t = d, vmax, s["highway"], i, t
    if best_d > radius and idx is not None:
        for i, s in enumerate(segs):
            d, t = point_segment_distance(x,y,s["x1"],s["y1"],s["x2"],s["y2"])
            if d < best_d:
                vmax = s["vmax_kmh"] if s["vmax_kmh"] is not None else default_by_highway(s["highway"])
                best_d, best_v, best_hi, best_i, best_t = d, vmax, s["highway"], i, t
    return best_v, best_d, best_hi, best_i, best_t

def read_gpx_points_and_bbox(gpx_path, bbox_margin):
    parser = etree.XMLParser(remove_blank_text=False, recover=True)
    tree = etree.parse(str(gpx_path), parser)
    root = tree.getroot()
    gpx_ns = root.nsmap.get(None); GPX = f"{{{gpx_ns}}}" if gpx_ns else ""
    lats, lons, trkpts = [], [], []
    for trkpt in root.iter(f"{GPX}trkpt"):
        lat = float(trkpt.get("lat")); lon = float(trkpt.get("lon"))
        lats.append(lat); lons.append(lon); trkpts.append(trkpt)
    if not lats: raise RuntimeError("Keine <trkpt> in GPX gefunden.")
    minlat, maxlat = min(lats), max(lats); minlon, maxlon = min(lons), max(lons)
    lat0 = 0.5*(minlat+maxlat)
    dlat, dlon = meters_to_deglatlon(lat0, bbox_margin)
    bbox = (minlat - dlat, minlon - dlon, maxlat + dlat, maxlon + dlon)  # (S,W,N,E)
    if VERBOSE:
        log(f"[GPX] Punkte: {len(lats)}")
        log(f"[GPX] BBox: S={bbox[0]:.6f}, W={bbox[1]:.6f}, N={bbox[2]:.6f}, E={bbox[3]:.6f}")
    return tree, root, GPX, trkpts, bbox

def bbox_south_west_north_east_to_minmax(bbox_s_w_n_e):
    S,W,N,E = bbox_s_w_n_e
    return (W, S, E, N)

def normalize_maxspeed(val):
    if val is None:
        return np.nan
    s = str(val).strip().lower().replace(" ", "")
    try:
        if s.endswith("mph"): return float(s[:-3]) * 1.609344
        for suf in ("km/h","kph","kmh"):
            if s.endswith(suf): return float(s[:-len(suf)])
        return float(s)
    except Exception:
        return np.nan

def pick_maxspeed_series_like(df):
    cand = ["maxspeed_kmh","maxspeed","maxspeed_forward","maxspeed_backward","maxspeed:forward","maxspeed:backward"]
    for c in cand:
        if c in df.columns:
            return df[c]
    import pandas as pd
    return pd.Series(np.nan, index=df.index)

def load_segments_from_fgb(fgb_path, bbox_s_w_n_e):
    import pyogrio
    (minx, miny, maxx, maxy) = bbox_south_west_north_east_to_minmax(bbox_s_w_n_e)
    cols = ["geometry","highway","maxspeed_kmh","maxspeed","maxspeed_forward","maxspeed_backward",
            "name","ref","oneway","bridge","tunnel"]
    try:
        df = pyogrio.read_dataframe(
            fgb_path, layer="highways",
            bbox=(minx, miny, maxx, maxy),
            columns=[c for c in cols if c != "geometry"]
        )
        src = pick_maxspeed_series_like(df)
        df["maxspeed_kmh"] = src.apply(normalize_maxspeed)
    except Exception as e:
        raise RuntimeError(f"FGB lesen fehlgeschlagen: {e}")

    segs = []
    for geom, hw, vmax in zip(df.geometry.values, df.get("highway", []), df.get("maxspeed_kmh", [])):
        if geom is None: continue
        gtype = getattr(geom, "geom_type", None)
        if gtype == "LineString":
            coords = list(geom.coords)
            for (x1,y1),(x2,y2) in zip(coords[:-1], coords[1:]):
                X1,Y1 = to_xy.transform(x1, y1)  # lon,lat -> 3857
                X2,Y2 = to_xy.transform(x2, y2)
                segs.append({"x1":X1,"y1":Y1,"x2":X2,"y2":Y2,"highway":hw,
                             "vmax_kmh":(None if (vmax is None or (isinstance(vmax,float) and math.isnan(vmax))) else float(vmax))})
        elif gtype == "MultiLineString":
            for ls in geom.geoms:
                coords = list(ls.coords)
                for (x1,y1),(x2,y2) in zip(coords[:-1], coords[1:]):
                    X1,Y1 = to_xy.transform(x1, y1)
                    X2,Y2 = to_xy.transform(x2, y2)
                    segs.append({"x1":X1,"y1":Y1,"x2":X2,"y2":Y2,"highway":hw,
                                 "vmax_kmh":(None if (vmax is None or (isinstance(vmax,float) and math.isnan(vmax))) else float(vmax))})
    return segs

# ---- Signals (optional) ----
def load_signals_from_fgb(fgb_path, bbox_s_w_n_e):
    import pyogrio
    (minx, miny, maxx, maxy) = bbox_south_west_north_east_to_minmax(bbox_s_w_n_e)
    try:
        df = pyogrio.read_dataframe(
            fgb_path, layer="signals",
            bbox=(minx, miny, maxx, maxy),
            columns=[]
        )
    except Exception:
        return []
    pts = []
    for geom in getattr(df, "geometry", []):
        if geom is None: continue
        if getattr(geom, "geom_type", "") == "Point":
            x, y = geom.x, geom.y
            X, Y = to_xy.transform(x, y)
            pts.append((X, Y))
    return pts

class SignalCollector(osm.SimpleHandler):
    def __init__(self, bbox):
        super().__init__()
        self.S,self.W,self.N,self.E = bbox
        self.points = []
    def in_bbox(self, lat, lon): return (self.S<=lat<=self.N) and (self.W<=lon<=self.E)
    def node(self, n):
        if 'highway' in n.tags and n.tags.get('highway') == 'traffic_signals':
            loc = n.location
            if loc and loc.valid() and self.in_bbox(float(loc.lat), float(loc.lon)):
                X,Y = to_xy.transform(float(loc.lon), float(loc.lat))
                self.points.append((X,Y))

def load_signals_from_pbf(pbf_path, bbox_s_w_n_e):
    S,W,N,E = bbox_s_w_n_e
    coll = SignalCollector((S,W,N,E))
    osm.apply(osm.io.Reader(pbf_path), coll)
    return coll.points

def build_rtree_segments(segs):
    from rtree import index as rtree_index
    p = rtree_index.Property(); p.interleaved = True
    idx = rtree_index.Index(properties=p)
    for i,s in enumerate(segs):
        x1,y1,x2,y2 = s["x1"],s["y1"],s["x2"],s["y2"]
        xmin,xmax = (x1,x2) if x1<=x2 else (x2,x1)
        ymin,ymax = (y1,y2) if y1<=y2 else (y2,y1)
        idx.insert(i,(xmin,ymin,xmax,ymax))
    return idx

def build_rtree_points(points):
    from rtree import index as rtree_index
    p = rtree_index.Property(); p.interleaved = True
    idx = rtree_index.Index(properties=p)
    for i,(X,Y) in enumerate(points):
        idx.insert(i, (X, Y, X, Y))
    return idx

def snap_signals_to_gpx_pts(gpx_xy, signals_xy, snap_radius_m=12.0):
    snapped = set()
    if not signals_xy: return snapped
    try:
        idx = build_rtree_points(gpx_xy)
    except Exception:
        idx = None
    for (Xs, Ys) in signals_xy:
        nearest_i = None; best_d2 = float("inf")
        candidates = idx.intersection((Xs-snap_radius_m, Ys-snap_radius_m, Xs+snap_radius_m, Ys+snap_radius_m)) if idx else range(len(gpx_xy))
        for i in candidates:
            Xg,Yg = gpx_xy[i]; d2 = (Xg-Xs)**2 + (Yg-Ys)**2
            if d2 < best_d2: best_d2, nearest_i = d2, i
        if nearest_i is not None and best_d2 <= (snap_radius_m**2):
            snapped.add(nearest_i)
    return snapped

class WayCollector(osm.SimpleHandler):
    def __init__(self, bbox, sample_print=SAMPLE_WAYS_PRINT, progress_every=PROGRESS_EVERY_WAYS):
        super().__init__()
        self.S,self.W,self.N,self.E = bbox
        self.segments = []
        self.count_seen=self.count_hw=self.count_used=0
        self.count_no_loc=self.count_too_short=self.count_no_bbox_hit=0
        self.sample_left = sample_print
        self.progress_every = progress_every
        self.t_last = time.time()
    def in_bbox(self, lat, lon): return (self.S<=lat<=self.N) and (self.W<=lon<=self.E)
    def way(self, w):
        self.count_seen += 1
        if tick_every(self.progress_every, self.count_seen):
            dt = time.time()-self.t_last; self.t_last=time.time()
            log(f"[PBF] ways_seen={self.count_seen:,} (+{self.progress_every}) | segs={len(self.segments):,} | dt={dt:.1f}s")
        if "highway" not in w.tags: return
        self.count_hw += 1
        highway = w.tags.get("highway"); vmax_raw = w.tags.get("maxspeed")
        vmax=None
        if vmax_raw:
            txt=vmax_raw.strip().lower()
            try:
                if txt.endswith("mph"): vmax=float(txt[:-3].strip())*1.609344
                elif txt.endswith("km/h"): vmax=float(txt[:-4].strip())
                else: vmax=float(txt)
            except Exception: vmax=None
        coords=[]
        for nd in w.nodes:
            loc = nd.location
            if not loc or not loc.valid():
                self.count_no_loc += 1; return
            coords.append((loc.lat, loc.lon))
        if len(coords)<2: self.count_too_short+=1; return
        if not any(self.in_bbox(lat,lon) for (lat,lon) in coords):
            self.count_no_bbox_hit += 1; return
        for (lat1,lon1),(lat2,lon2) in zip(coords[:-1], coords[1:]):
            x1,y1 = to_xy.transform(lon1,lat1); x2,y2 = to_xy.transform(lon2,lat2)
            self.segments.append({"x1":x1,"y1":y1,"x2":x2,"y2":y2,"highway":highway,"vmax_kmh":vmax})
        self.count_used += 1
        if VERBOSE and self.sample_left>0:
            self.sample_left -= 1
            log(f"[PBF] Way {w.id}: highway={highway}, maxspeed(raw)={vmax_raw}, segs+={len(coords)-1}")

def main():
    ap = argparse.ArgumentParser(description="Augment GPX with maxspeed + highway tag (+ signals)")
    ap.add_argument("--highways_fgb", required=False, help="FlatGeobuf mit highways/signals (empfohlen)")
    ap.add_argument("--pbf", required=False, help="Pfad zu (voller) OSM PBF")
    ap.add_argument("--pbf_highways", required=False, help="Pfad zu highways-only PBF (falls vorhanden)")
    ap.add_argument("--gpx_in", required=True)
    ap.add_argument("--gpx_out", required=True)
    ap.add_argument("--radius", type=float, default=SEARCH_RADIUS_M)
    ap.add_argument("--bbox_margin", type=float, default=BBOX_MARGIN_M)
    ap.add_argument("--no_rtree", action="store_true")
    ap.add_argument("--signal_snap_radius", type=float, default=12.0)
    args = ap.parse_args()

    if not (args.highways_fgb or args.pbf or args.pbf_highways):
        ap.error("Bitte Quelle angeben: --highways_fgb ODER --pbf/--pbf_highways")

    fgb_path = os.path.abspath(args.highways_fgb) if args.highways_fgb else None
    if fgb_path and not os.path.isfile(fgb_path):
        raise FileNotFoundError(f"FGB not found: {fgb_path}")

    pbf_for_spatial = args.pbf_highways or args.pbf
    pbf_path    = os.path.abspath(pbf_for_spatial) if pbf_for_spatial else None
    pbf_hw_path = os.path.abspath(args.pbf_highways) if args.pbf_highways else None
    if not fgb_path:
        if not pbf_path or not os.path.isfile(pbf_path):
            raise FileNotFoundError(f"PBF not found: {pbf_path}")
        if pbf_hw_path and not os.path.isfile(pbf_hw_path):
            raise FileNotFoundError(f"Highways PBF not found: {pbf_hw_path}")

    gpx_in      = os.path.abspath(args.gpx_in)
    gpx_out     = os.path.abspath(args.gpx_out)
    radius_m    = float(args.radius)
    bbox_margin = float(args.bbox_margin)
    use_rtree   = not args.no_rtree
    snap_radius = float(args.signal_snap_radius)

    t0 = time.time()
    log(f"[SETUP] GPX_IN={gpx_in} | GPX_OUT={gpx_out}")

    tree, root, GPX, trkpts, bbox = read_gpx_points_and_bbox(gpx_in, bbox_margin)

    # Segmente laden
    if fgb_path:
        log(f"[SETUP] Using FGB: {fgb_path}")
        segments = load_segments_from_fgb(fgb_path, bbox)
    else:
        scan_pbf = pbf_hw_path or pbf_path
        idx_map = osm.index.create_map("flex_mem")
        locator = osm.NodeLocationsForWays(idx_map); locator.ignore_errors()
        collector = WayCollector(bbox)
        log("[PBF] Reader + Locator …")
        osm.apply(osm.io.Reader(scan_pbf), locator, collector)
        segments = collector.segments
        log(f"[PBF] Segmente gesamt: {len(segments):,}")

    if not segments:
        log("Keine Segmente gefunden.")
        Path(gpx_out).parent.mkdir(parents=True, exist_ok=True)
        tree.write(str(gpx_out), pretty_print=True, xml_declaration=True, encoding="utf-8")
        return

    # Ampeln laden (optional)
    if fgb_path:
        signals_xy = load_signals_from_fgb(fgb_path, bbox)
    else:
        scan_pbf = pbf_hw_path or pbf_path
        signals_xy = load_signals_from_pbf(scan_pbf, bbox)

    # R-Tree für Segmente
    idx = None
    if use_rtree and USE_RTREE:
        try:
            idx = build_rtree_segments(segments)
            log("[IDX] R-Tree aktiv")
        except Exception as e:
            log(f"[IDX] R-Tree nicht verfügbar ({e}); ohne fort")

    # GPX-XY
    gpx_xy = []
    for trkpt in trkpts:
        lat=float(trkpt.get("lat")); lon=float(trkpt.get("lon"))
        X,Y = to_xy.transform(lon, lat)
        gpx_xy.append((X,Y))

    # Ampeln snappen
    signal_idx = set()
    try:
        signal_idx = snap_signals_to_gpx_pts(gpx_xy, signals_xy, snap_radius)
    except Exception as e:
        log(f"[SIG] snapping error: {e}; continue without signals")
        signal_idx = set()
    log(f"[SIG] snapped signals to GPX points: {len(signal_idx)}")

    # GPX schreiben
    N = len(trkpts); count_assigned=0; count_signal=0
    for i,trkpt in enumerate(trkpts, start=0):
        lat=float(trkpt.get("lat")); lon=float(trkpt.get("lon"))
        vmax_kmh, dist_m, hi, seg_i, t_param = assign_maxspeed_to_point(lat,lon,segments,idx,radius_m)
        ext = trkpt.find(f"{GPX}extensions")
        if ext is None: ext = etree.SubElement(trkpt, f"{GPX}extensions")
        # maxspeed
        old = ext.find("maxspeed")
        if old is not None: ext.remove(old)
        if vmax_kmh is not None and math.isfinite(vmax_kmh):
            etree.SubElement(ext, "maxspeed").text = f"{float(vmax_kmh):.1f}"; count_assigned += 1
        # highway-Typ (NEU)
        oldh = ext.find("highway")
        if oldh is not None: ext.remove(oldh)
        if hi:
            etree.SubElement(ext, "highway").text = str(hi)
        # traffic_signal
        if i in signal_idx:
            if ext.find("traffic_signal") is None:
                etree.SubElement(ext, "traffic_signal").text = "true"
            count_signal += 1
        if VERBOSE and (i<5 or tick_every(PROGRESS_EVERY_PTS,i+1)):
            vtxt = ("%.1f" % vmax_kmh) if vmax_kmh is not None else "None"
            log(f"[GPX] {i+1}/{N} -> v={vtxt} | hw={hi or '-'} | sig={'1' if i in signal_idx else '0'} "
                f"(d~{dist_m:.1f} m, seg={seg_i}, t={t_param:.2f})")

    Path(gpx_out).parent.mkdir(parents=True, exist_ok=True)
    tree.write(str(gpx_out), pretty_print=True, xml_declaration=True, encoding="utf-8")
    log(f"[SAVE] {Path(gpx_out).resolve()}")
    log(f"[TIME] Gesamt: {time.time()-t0:.1f}s | maxspeed={count_assigned}/{N} | signals_marked={count_signal}")

if __name__ == "__main__":
    main()
