# build_highways_fgb.py  (progress + tiling + NEU: signals-Layer)
import argparse, os, time, math
import numpy as np, pandas as pd, pyogrio

def parse_bounds_arg(s: str):
    vals = [float(x) for x in s.split(",")]
    if len(vals) != 4: raise ValueError("--bounds erwartet minx,miny,maxx,maxy")
    minx,miny,maxx,maxy = vals
    if not (minx < maxx and miny < maxy):
        raise ValueError("Ungültige --bounds Reihenfolge/Größe")
    return minx,miny,maxx,maxy

def _compute_highway_bounds_osmium(in_pbf, progress_every=20000):
    import osmium as osm, time as _time
    class BboxCollector(osm.SimpleHandler):
        def __init__(self):
            super().__init__()
            self.minx = float('inf'); self.miny = float('inf')
            self.maxx = float('-inf'); self.maxy = float('-inf')
            self.seen_ways = 0; self.used_ways = 0
            self.no_loc = 0; self.t_last = _time.time()
        def way(self, w):
            self.seen_ways += 1
            if 'highway' not in w.tags: return
            self.used_ways += 1
            any_valid = False
            for nd in w.nodes:
                loc = nd.location
                if loc and loc.valid():
                    lon, lat = float(loc.lon), float(loc.lat)
                    if lon < self.minx: self.minx = lon
                    if lon > self.maxx: self.maxx = lon
                    if lat < self.miny: self.miny = lat
                    if lat > self.maxy: self.maxy = lat
                    any_valid = True
            if not any_valid: self.no_loc += 1
            if (self.seen_ways % progress_every) == 0:
                dt = _time.time() - self.t_last; self.t_last = _time.time()
                print(f"[SCAN] ways_seen={self.seen_ways:,} hw_used={self.used_ways:,} "
                      f"bbox=({self.minx:.5f},{self.miny:.5f},{self.maxx:.5f},{self.maxy:.5f}) "
                      f"+{progress_every} in {dt:.1f}s")
    idx_map = osm.index.create_map("flex_mem")
    locator = osm.NodeLocationsForWays(idx_map); locator.ignore_errors()
    h = BboxCollector()
    print("[SCAN] Auto-Bounds: starte highway-Scan …")
    osm.apply(osm.io.Reader(in_pbf), locator, h)
    if not (h.minx < h.maxx and h.miny < h.maxy) or h.used_ways == 0:
        return None
    print(f"[SCAN] Fertig: hw_used={h.used_ways:,}  "
          f"Bounds=({h.minx:.5f},{h.miny:.5f},{h.maxx:.5f},{h.maxy:.5f})")
    return (h.minx, h.miny, h.maxx, h.maxy)

def detect_bounds(in_pbf, user_bounds=None):
    if user_bounds:
        return parse_bounds_arg(user_bounds)
    try:
        import osmium as osm
        r = osm.io.Reader(in_pbf)
        h = r.header(); b = h.bounds()
        if b and b.valid():
            bl = b.bottom_left(); tr = b.top_right()
            return float(bl.lon), float(bl.lat), float(tr.lon), float(tr.lat)
    except Exception:
        pass
    try:
        import numpy as _np
        b = pyogrio.read_bounds(in_pbf, layer="lines")
        arr = _np.asarray(b).reshape(-1)
        if arr.size == 4:
            minx, miny, maxx, maxy = arr.tolist()
            return float(minx), float(miny), float(maxx), float(maxy)
        if len(b) == 2 and all(hasattr(bi, "__len__") and len(bi) == 2 for bi in b):
            (minx, miny), (maxx, maxy) = b
            return float(minx), float(miny), float(maxx), float(maxy)
    except Exception:
        pass
    bbox = _compute_highway_bounds_osmium(in_pbf, progress_every=20000)
    if bbox: return bbox
    return (-180.0, -90.0, 180.0, 90.0)

def normalize_maxspeed(val):
    if val is None:
        return np.nan
    s = str(val).strip().lower().replace(" ", "")
    try:
        if s.endswith("mph"):
            return float(s[:-3]) * 1.609344
        for suf in ("km/h","kph","kmh"):
            if s.endswith(suf):
                return float(s[:-len(suf)])
        return float(s)
    except Exception:
        return np.nan

def parse_tiles(s: str):
    if "x" in s.lower():
        a,b = s.lower().split("x")
        return max(1,int(a)), max(1,int(b))
    n = max(1,int(s))
    return n,n

def pick_maxspeed_series(df):
    import pandas as pd
    if "maxspeed_kmh" in df.columns and str(df["maxspeed_kmh"].dtype) != "object":
        return df["maxspeed_kmh"]
    candidates = [
        "maxspeed",
        "maxspeed_forward", "maxspeed_backward",
        "maxspeed:forward", "maxspeed:backward",
        "maxspeed_forward", "maxspeed_backward",
    ]
    for c in candidates:
        if c in df.columns:
            return df[c]
    return pd.Series(np.nan, index=df.index)

def _read_lines_df(in_pbf, where, bbox):
    try:
        return pyogrio.read_dataframe(
            in_pbf, layer="lines", where=where, bbox=bbox,
            use_arrow=True, force_2d=True
        )
    except Exception:
        try:
            return pyogrio.read_dataframe(
                in_pbf, layer="lines", where=where, bbox=bbox, force_2d=True
            )
        except TypeError:
            return pyogrio.read_dataframe(
                in_pbf, layer="lines", where=where, bbox=bbox
            )

def _read_points_df(in_pbf, where, bbox):
    try:
        return pyogrio.read_dataframe(
            in_pbf, layer="points", where=where, bbox=bbox,
            use_arrow=True, force_2d=True
        )
    except Exception:
        try:
            return pyogrio.read_dataframe(
                in_pbf, layer="points", where=where, bbox=bbox, force_2d=True
            )
        except TypeError:
            return pyogrio.read_dataframe(
                in_pbf, layer="points", where=where, bbox=bbox
            )

def _dedup_by(df, subset_cols):
    if df is None or len(df) == 0:
        return df
    if not subset_cols or not all(c in df.columns for c in subset_cols):
        before = len(df)
        df["__wkb__"] = df.geometry.apply(lambda g: g.wkb if g is not None else None)
        df = df.drop_duplicates(subset=["__wkb__"]).drop(columns=["__wkb__"])
        print(f"[DEDUP] wkb: {before:,} -> {len(df):,}")
        return df
    before = len(df)
    df = df.drop_duplicates(subset=subset_cols)
    print(f"[DEDUP] {','.join(subset_cols)}: {before:,} -> {len(df):,}")
    return df

def main():
    ap = argparse.ArgumentParser(
        description="Convert OSM .pbf to FlatGeobuf (.fgb) with only highways (+signals), with progress")
    ap.add_argument("--in_pbf", required=True)
    ap.add_argument("--out_fgb", required=True)
    ap.add_argument("--keep_all", action="store_true",
                    help="Keep all highway types (otherwise exclude footways/cycleways/...)")
    ap.add_argument("--simplify", type=float, default=0.0,
                    help="Simplify tolerance in degrees (e.g. 0.0005 ~ 55 m). 0 = off.")
    ap.add_argument("--bounds", type=str, default=None,
                    help="Override bounds as 'minx,miny,maxx,maxy' (lon/lat)")
    ap.add_argument("--tiles", type=str, default="8x8",
                    help="Tile grid as NxM (default 8x8)")
    ap.add_argument("--single_read", action="store_true",
                    help="Einmaliges bbox-Read statt Tiling (schneller, braucht mehr RAM)")
    args = ap.parse_args()

    in_pbf  = os.path.abspath(args.in_pbf)
    out_fgb = os.path.abspath(args.out_fgb)
    os.makedirs(os.path.dirname(out_fgb), exist_ok=True)

    minx, miny, maxx, maxy = detect_bounds(in_pbf, args.bounds)
    print(f"[INFO] Bounds: W={minx:.6f}, S={miny:.6f}, E={maxx:.6f}, N={maxy:.6f}")

    ALLOWED_CAR = {
        "motorway","motorway_link",
        "trunk","trunk_link",
        "primary","primary_link",
        "secondary","secondary_link",
        "tertiary","tertiary_link",
        "unclassified","residential","service"
    }

    if args.keep_all:
        where_lines = "highway IS NOT NULL"
    else:
        where_lines = "highway IN ({})".format(",".join(f"'{t}'" for t in sorted(ALLOWED_CAR)))
    where_points = "highway = 'traffic_signals'"

    if args.single_read:
        print("[READ] single bbox read …")
        df = _read_lines_df(in_pbf, where_lines, (minx, miny, maxx, maxy))
        df_sig = _read_points_df(in_pbf, where_points, (minx, miny, maxx, maxy))

        # Lines -> highways
        src = pick_maxspeed_series(df)                            # <— einheitlich!
        df["maxspeed_kmh"] = src.apply(normalize_maxspeed)

        # optional: alte maxspeed-Varianten löschen (aufgeräumtes Schema)
        for dropcol in ("maxspeed","maxspeed_forward","maxspeed_backward",
                        "maxspeed:forward","maxspeed:backward"):
            if dropcol in df.columns:
                df = df.drop(columns=[dropcol])

        if args.simplify > 0.0:
            df["geometry"] = df.geometry.apply(
                lambda g: g.simplify(args.simplify, preserve_topology=False) if g is not None else g
            )
        df = _dedup_by(df, ["osm_id"] if "osm_id" in df.columns else None)
        pyogrio.write_dataframe(df, out_fgb, driver="FlatGeobuf")   # <— kein layer= bei FGB


        # Points -> signals
        if df_sig is None or len(df_sig) == 0:
            import pandas as _pd
            df_sig = _pd.DataFrame({"geometry": _pd.Series(dtype="object")})
        else:
            df_sig = _dedup_by(df_sig, ["osm_id"] if "osm_id" in df_sig.columns else None)
        pyogrio.write_dataframe(df_sig, out_fgb, driver="FlatGeobuf", layer="signals")
        print(f"[DONE] {out_fgb} | features highways={len(df):,} signals={len(df_sig):,}")
        return

    # --- Tiling ---
    nx, ny = parse_tiles(args.tiles)
    total_tiles = nx * ny
    print(f"[INFO] Bounds: W={minx:.6f}, S={miny:.6f}, E={maxx:.6f}, N={maxy:.6f} | tiles={nx}x{ny}")

    t0 = time.time()
    dfs_lines, dfs_points = [], []
    feat_total = 0; feat_sig_total = 0
    t_start = time.time()

    for iy in range(ny):
        y0 = miny + (maxy - miny) * (iy / ny)
        y1 = miny + (maxy - miny) * ((iy + 1) / ny)
        for ix in range(nx):
            x0 = minx + (maxx - minx) * (ix / nx)
            x1 = minx + (maxx - minx) * ((ix + 1) / nx)

            tile_idx = iy * nx + ix + 1
            t_tile = time.time()
            try:
                df_tile = _read_lines_df(in_pbf, where_lines, (x0, y0, x1, y1))
                df_pts  = _read_points_df(in_pbf, where_points, (x0, y0, x1, y1))
            except Exception as e:
                print(f"[WARN] Tile {tile_idx}/{total_tiles} read failed: {e}")
                continue

            if len(df_tile):
                src = pick_maxspeed_series(df_tile)
                df_tile["maxspeed_kmh"] = src.apply(normalize_maxspeed)
                for dropcol in ("maxspeed","maxspeed_forward","maxspeed_backward","maxspeed:forward","maxspeed:backward"):
                    if dropcol in df_tile.columns:
                        df_tile = df_tile.drop(columns=[dropcol])
                if args.simplify > 0.0:
                    df_tile["geometry"] = df_tile.geometry.apply(
                        lambda g: g.simplify(args.simplify, preserve_topology=False) if g is not None else g
                    )
                if "osm_id" in df_tile.columns:
                    df_tile = df_tile.drop_duplicates(subset=["osm_id"])
                dfs_lines.append(df_tile)
                feat_total += len(df_tile)

            if len(df_pts):
                if "osm_id" in df_pts.columns:
                    df_pts = df_pts.drop_duplicates(subset=["osm_id"])
                dfs_points.append(df_pts)
                feat_sig_total += len(df_pts)

            dt = time.time() - t_tile
            done = tile_idx / total_tiles
            elapsed = time.time() - t_start
            eta = (elapsed / done - elapsed) if done > 0 else float("inf")
            print(f"[{tile_idx:>3}/{total_tiles}] +{len(df_tile):,}/{len(df_pts):,} (cum {feat_total:,}/{feat_sig_total:,}) "
                  f"| {done*100:5.1f}% | {dt:4.1f}s | ETA {eta/60:5.1f} min")

    if not dfs_lines:
        df = pd.DataFrame({"geometry": pd.Series(dtype="object")})
    else:
        df = pd.concat(dfs_lines, ignore_index=True)
    df = _dedup_by(df, ["osm_id"] if "osm_id" in df.columns else None)

    if not dfs_points:
        df_sig = pd.DataFrame({"geometry": pd.Series(dtype="object")})
    else:
        df_sig = pd.concat(dfs_points, ignore_index=True)
    df_sig = _dedup_by(df_sig, ["osm_id"] if "osm_id" in df_sig.columns else None)

    pyogrio.write_dataframe(df, out_fgb, driver="FlatGeobuf", layer="highways")
    pyogrio.write_dataframe(df_sig, out_fgb, driver="FlatGeobuf", layer="signals")
    print(f"[DONE] {out_fgb} | features highways={len(df):,} signals={len(df_sig):,} | total_time={time.time()-t0:.1f}s")

if __name__ == "__main__":
    main()
