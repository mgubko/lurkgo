#!/usr/bin/env python3
"""Cut an OSM extract (.osm.pbf) into the static path-data tiles the LurkGo app reads from
https://lurkgo.app/osm/v1/ instead of asking the public Overpass servers (which rate-limit or
refuse phones). Same selection as the app's Overpass query (YouGo app/src/positioning/
PublicGround.ts, overpassQuery), only the tags the app looks at, compact geometry.

Tile = 0.01° × 0.01° (≈ 1.1 × 0.74 km here), named <floor(lat/0.01)>_<floor(lon/0.01)>.json.
An element goes into every tile its bounding box touches (the app splits further itself).
Element shapes:  node     {"t":"n","id":…,"tags":{…},"p":[lat,lon]}
                 way      {"t":"w","id":…,"tags":{…},"g":[lat,lon,lat,lon,…]}
                 relation {"t":"r","id":…,"tags":{…},"m":[[role,[lat,lon,…]],…]}   (multipolygons)
index.json lists the covered box, so the app falls back to Overpass outside it.

Usage: osm_tiles.py extract.osm.pbf OUTDIR S W N E
"""
import json, math, os, re, sys, datetime
import osmium

TILE = 0.01
KEEP_KEY = re.compile(r'^(highway|footway|path|cycleway|bridleway|sidewalk(:.*)?|foot|access|area|building|'
                      r'landuse|amenity|power|military|railway|tunnel|width|lanes|crossing|'
                      r'abandoned(:.*)?|disused(:.*)?)$')
AMENITY = re.compile(r'^(prison|school|kindergarten)$')

def way_selected(t):
    return any(k in t for k in ('highway', 'railway', 'building', 'landuse', 'access', 'military',
                                'abandoned', 'disused')) \
        or AMENITY.match(t.get('amenity', '')) is not None \
        or t.get('power') in ('substation', 'plant')

def node_selected(t):
    return t.get('highway') in ('crossing', 'traffic_signals') or 'crossing' in t

def rel_selected(t):
    return t.get('type') == 'multipolygon' and (
        any(k in t for k in ('landuse', 'building', 'access', 'military'))
        or AMENITY.match(t.get('amenity', '')) is not None)

def slim(tags):
    out = {k: v for k, v in tags if KEEP_KEY.match(k)}
    if 'building' in out:                      # the app only asks whether a building is there
        out['building'] = 'yes' if out['building'] != 'no' else 'no'
    return out

def tidx(deg):
    return math.floor(deg / TILE + 1e-9)

class Rels(osmium.SimpleHandler):
    def __init__(self):
        super().__init__(); self.rels = {}; self.member_ways = set()
    def relation(self, r):
        tags = {t.k: t.v for t in r.tags}
        if not rel_selected(tags): return
        mem = [(m.ref, m.role) for m in r.members if m.type == 'w']
        if not mem: return
        self.rels[r.id] = (slim(r.tags), mem)
        self.member_ways.update(ref for ref, _ in mem)

class Main(osmium.SimpleHandler):
    def __init__(self, member_ways, box):
        super().__init__(); self.member_ways = member_ways; self.box = box
        self.out = []; self.geom = {}
    def inbox(self, s, w, n, e):
        S, W, N, E = self.box
        return s <= N and n >= S and w <= E and e >= W
    def node(self, nd):
        tags = {t.k: t.v for t in nd.tags}
        if not tags or not node_selected(tags) or not nd.location.valid(): return
        lat, lon = round(nd.location.lat, 7), round(nd.location.lon, 7)
        if self.inbox(lat, lon, lat, lon):
            self.out.append(({'t': 'n', 'id': nd.id, 'tags': slim(nd.tags), 'p': [lat, lon]}, (lat, lon, lat, lon)))
    def way(self, w):
        tags = {t.k: t.v for t in w.tags}
        sel = way_selected(tags)
        if not sel and w.id not in self.member_ways: return
        try:
            pts = [(round(n.location.lat, 7), round(n.location.lon, 7)) for n in w.nodes]
        except osmium.InvalidLocationError:
            return
        if len(pts) < 2: return
        if w.id in self.member_ways: self.geom[w.id] = pts
        if not sel: return
        lats = [p[0] for p in pts]; lons = [p[1] for p in pts]
        bb = (min(lats), min(lons), max(lats), max(lons))
        if self.inbox(*bb):
            self.out.append(({'t': 'w', 'id': w.id, 'tags': slim(w.tags), 'g': [c for p in pts for c in p]}, bb))

def main():
    src, outdir = sys.argv[1], sys.argv[2]
    box = tuple(float(x) for x in sys.argv[3:7])
    rels = Rels(); rels.apply_file(src)
    h = Main(rels.member_ways, box); h.apply_file(src, locations=True, idx='flex_mem')
    for rid, (tags, mem) in rels.rels.items():
        members, allpts = [], []
        for ref, role in mem:
            g = h.geom.get(ref)
            if not g: continue
            members.append([role, [c for p in g for c in p]]); allpts += g
        if not members: continue
        lats = [p[0] for p in allpts]; lons = [p[1] for p in allpts]
        bb = (min(lats), min(lons), max(lats), max(lons))
        if h.inbox(*bb):
            h.out.append(({'t': 'r', 'id': rid, 'tags': tags, 'm': members}, bb))

    S, W, N, E = box
    tiles = {}
    for el, (s, w, n, e) in h.out:
        for i in range(max(tidx(s), tidx(S)), min(tidx(n), tidx(N)) + 1):
            for j in range(max(tidx(w), tidx(W)), min(tidx(e), tidx(E)) + 1):
                tiles.setdefault((i, j), []).append(el)
    os.makedirs(outdir, exist_ok=True)
    for f in os.listdir(outdir):
        if re.match(r'^-?\d+_-?\d+\.json$', f): os.remove(os.path.join(outdir, f))
    date = datetime.date.today().isoformat()
    total = 0
    for i in range(tidx(S), tidx(N) + 1):          # every tile of the box, empty ones too
        for j in range(tidx(W), tidx(E) + 1):
            text = json.dumps({'v': 1, 'elements': tiles.get((i, j), [])}, separators=(',', ':'), ensure_ascii=False)
            total += len(text)
            with open(os.path.join(outdir, f'{i}_{j}.json'), 'w', encoding='utf-8') as fh: fh.write(text)
    with open(os.path.join(outdir, 'index.json'), 'w') as fh:
        json.dump({'v': 1, 'tile': TILE, 'box': [tidx(S), tidx(W), tidx(N), tidx(E)], 'date': date,
                   'source': '© OpenStreetMap contributors, ODbL'}, fh)
    print(f'{len(h.out)} elements, {(tidx(N)-tidx(S)+1)*(tidx(E)-tidx(W)+1)} tiles, {total/1e6:.1f} MB')

if __name__ == '__main__':
    main()
