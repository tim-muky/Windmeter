#!/usr/bin/env python3
"""
Offline Tile Pre-Downloader
============================
Downloads OSM + OpenSeaMap tiles for the Berlin waterway region so the
map works on the boat when the iPad is connected only to the Pi's hotspot.

Run this ONCE at home while the Pi has a normal internet connection:
  python3 scripts/download_tiles.py

Default area covers all Berlin waterways (Havel, Spree, Dahme, Oder-Spree
canal) plus the Müggelsee and Wannsee.  Adjust BBOX if you sail elsewhere.

Tile counts by zoom level (approx):
  z10  →     4 tiles each layer
  z12  →    16 tiles
  z14  →   256 tiles
  z16  → 4 096 tiles
  Total ≈ 4 500 tiles × 2 layers ≈ ~25 MB
"""

import math
import os
import sys
import time
import urllib.request

# ── Configurable area (lat/lon bounding box) ──────────────────────────────────
# Covers Berlin + ~30 km around (includes most Brandenburg waterways)
BBOX = {
    "lat_min": 52.25,
    "lat_max": 52.75,
    "lon_min": 13.00,
    "lon_max": 13.80,
}

ZOOM_LEVELS = range(10, 17)   # z10..z16 inclusive

LAYERS = {
    "osm":      "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    "opensea":  "https://tiles.openseamap.org/seamark/{z}/{x}/{y}.png",
}

# Project root (one level up from scripts/)
ROOT      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(ROOT, "data", "tiles")

HEADERS = {
    "User-Agent": "SailMon/1.0 tile pre-downloader (private use)",
}

DELAY_S = 0.05   # seconds between requests (be polite to tile servers)

# ── Tile math ─────────────────────────────────────────────────────────────────

def deg2tile(lat_deg: float, lon_deg: float, zoom: int) -> tuple[int, int]:
    lat_r = math.radians(lat_deg)
    n     = 2 ** zoom
    x = int((lon_deg + 180) / 360 * n)
    y = int((1 - math.log(math.tan(lat_r) + 1 / math.cos(lat_r)) / math.pi) / 2 * n)
    return x, y


def tile_range(bbox: dict, zoom: int):
    x0, y0 = deg2tile(bbox["lat_max"], bbox["lon_min"], zoom)
    x1, y1 = deg2tile(bbox["lat_min"], bbox["lon_max"], zoom)
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            yield x, y


def count_tiles(bbox: dict, zooms) -> int:
    return sum(
        sum(1 for _ in tile_range(bbox, z)) * len(LAYERS)
        for z in zooms
    )


# ── Downloader ────────────────────────────────────────────────────────────────

def download_tile(layer: str, url_tpl: str, z: int, x: int, y: int) -> bool:
    """Return True if tile was downloaded, False if already cached."""
    path = os.path.join(CACHE_DIR, layer, str(z), str(x), f"{y}.png")
    if os.path.exists(path):
        return False  # already cached

    url = url_tpl.format(z=z, x=x, y=y)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
        with open(path, "wb") as f:
            f.write(data)
        return True
    except Exception as e:
        print(f"\n  ⚠ Failed {url}: {e}", file=sys.stderr)
        return False


def main():
    total    = count_tiles(BBOX, ZOOM_LEVELS)
    done     = 0
    fetched  = 0
    skipped  = 0
    t_start  = time.time()

    print(f"SailMon Tile Downloader")
    print(f"Area:   lat {BBOX['lat_min']}–{BBOX['lat_max']}, "
          f"lon {BBOX['lon_min']}–{BBOX['lon_max']}")
    print(f"Layers: {', '.join(LAYERS)}")
    print(f"Zoom:   {min(ZOOM_LEVELS)}–{max(ZOOM_LEVELS)}")
    print(f"Tiles:  ~{total} total\n")

    for z in ZOOM_LEVELS:
        for x, y in tile_range(BBOX, z):
            for layer, url_tpl in LAYERS.items():
                new = download_tile(layer, url_tpl, z, x, y)
                if new:
                    fetched += 1
                    time.sleep(DELAY_S)
                else:
                    skipped += 1
                done += 1

            # Progress bar
            pct = done / total * 100
            bar = '█' * int(pct / 2) + '░' * (50 - int(pct / 2))
            elapsed = time.time() - t_start
            eta     = (elapsed / done * (total - done)) if done > 0 else 0
            print(f"\r  [{bar}] {pct:5.1f}%  "
                  f"{fetched} new  {skipped} cached  "
                  f"ETA {int(eta//60)}:{int(eta%60):02d}", end="", flush=True)

    elapsed = time.time() - t_start
    print(f"\n\nDone! {fetched} tiles downloaded, {skipped} already cached. "
          f"Total time: {int(elapsed//60)}m {int(elapsed%60)}s")
    print(f"Cache directory: {CACHE_DIR}")


if __name__ == "__main__":
    main()
