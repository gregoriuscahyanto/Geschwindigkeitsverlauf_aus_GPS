#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Merge multiple .osm.pbf files into one .osm.pbf using pyosmium only (no osmium CLI).
- Streaming-Verarbeitung: Dateien nacheinander, geringer RAM-Bedarf
- Deduplikation per ID: erste Sicht gewinnt (für Geofabrik-Nachbarregionen gleichen Datums passend)
"""

import argparse
import os
import sys
import osmium as osm


def human(n: int) -> str:
    return f"{n:,}".replace(",", " ")


class MergeHandler(osm.SimpleHandler):
    def __init__(self, writer: osm.SimpleWriter, seen_nodes, seen_ways, seen_rels, stats: dict):
        super().__init__()
        self.w = writer
        self.seen_nodes = seen_nodes
        self.seen_ways = seen_ways
        self.seen_rels = seen_rels
        self.s = stats  # zählt in/out/dup

    def node(self, n):
        self.s["nodes_in"] += 1
        nid = n.id
        if nid in self.seen_nodes:
            self.s["nodes_dup"] += 1
            return
        self.seen_nodes.add(nid)
        self.w.add_node(n)
        self.s["nodes_out"] += 1

    def way(self, w):
        self.s["ways_in"] += 1
        wid = w.id
        if wid in self.seen_ways:
            self.s["ways_dup"] += 1
            return
        self.seen_ways.add(wid)
        self.w.add_way(w)
        self.s["ways_out"] += 1

    def relation(self, r):
        self.s["rels_in"] += 1
        rid = r.id
        if rid in self.seen_rels:
            self.s["rels_dup"] += 1
            return
        self.seen_rels.add(rid)
        self.w.add_relation(r)
        self.s["rels_out"] += 1


def main():
    ap = argparse.ArgumentParser(description="Merge multiple OSM PBFs (pyosmium-based).")
    ap.add_argument("inputs", nargs="+", help="Input .osm.pbf files (>=2)")
    ap.add_argument("-o", "--out", required=True, help="Output .osm.pbf")
    ap.add_argument("--overwrite", action="store_true", help="Overwrite output if it exists")
    ap.add_argument("--force", action="store_true", help="Continue on read warnings (best-effort)")
    args = ap.parse_args()

    if len(args.inputs) < 2:
        ap.error("Need at least two input PBFs.")

    out = os.path.abspath(args.out)
    if os.path.exists(out) and not args.overwrite:
        print(f"[ERR] Output exists: {out} (use --overwrite)", file=sys.stderr)
        sys.exit(2)

    # Sanity check
    for p in args.inputs:
        if not os.path.isfile(p):
            print(f"[ERR] Not found: {p}", file=sys.stderr)
            sys.exit(2)

    # Writer anhand Zielendung: .pbf -> schreibt PBF
    w = osm.SimpleWriter(out)

    seen_nodes, seen_ways, seen_rels = set(), set(), set()

    total = {
        "nodes_in": 0, "ways_in": 0, "rels_in": 0,
        "nodes_out": 0, "ways_out": 0, "rels_out": 0,
        "nodes_dup": 0, "ways_dup": 0, "rels_dup": 0,
        "files": 0
    }

    try:
        for i, p in enumerate(args.inputs, start=1):
            stats = {k: 0 for k in total.keys() if k != "files"}
            print(f"[{i}/{len(args.inputs)}] Merging: {p}")
            h = MergeHandler(w, seen_nodes, seen_ways, seen_rels, stats)
            try:
                # locations=True: Node-Koordinaten beim Lesen verfügbar
                h.apply_file(p, locations=True)
            except Exception as e:
                if args.force:
                    print(f"[WARN] Problem while reading {p}: {e} — continuing (--force)", file=sys.stderr)
                else:
                    raise

            total["files"] += 1
            for k in stats:
                total[k] += stats[k]

            print(f"    nodes:  in {human(stats['nodes_in'])} → out {human(stats['nodes_out'])} "
                  f"(dup {human(stats['nodes_dup'])})")
            print(f"    ways:   in {human(stats['ways_in'])} → out {human(stats['ways_out'])} "
                  f"(dup {human(stats['ways_dup'])})")
            print(f"    rels:   in {human(stats['rels_in'])} → out {human(stats['rels_out'])} "
                  f"(dup {human(stats['rels_dup'])})")
    finally:
        w.close()

    print("\n[SUMMARY]")
    print(f"  files merged : {total['files']}")
    print(f"  nodes  in/out: {human(total['nodes_in'])} / {human(total['nodes_out'])} "
          f"(dup {human(total['nodes_dup'])})")
    print(f"  ways   in/out: {human(total['ways_in'])} / {human(total['ways_out'])} "
          f"(dup {human(total['ways_dup'])})")
    print(f"  rels   in/out: {human(total['rels_in'])} / {human(total['rels_out'])} "
          f"(dup {human(total['rels_dup'])})")
    print(f"[OK] Wrote: {out}")


if __name__ == "__main__":
    main()
