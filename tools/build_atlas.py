"""
tools/build_atlas.py - pack the 0x72 "frames" folder into one texture atlas.

Usage:
    python tools/build_atlas.py "C:/path/to/0x72_DungeonTilesetII_v1.7/frames"

Why an atlas?
-------------
The 0x72 pack ships ~330 tiny PNGs. Loading 330 files at start-up is slow-ish
and copying them around is clumsy. A texture atlas is ONE PNG holding every
frame plus a JSON index  {name: [x, y, w, h]}. assets.py loads the PNG once
and cuts frames out with Surface.subsurface() - zero extra file I/O.

Packing algorithm: "shelf" packing. Sort frames by height (tallest first),
fill rows left-to-right; when a row is full, start a new shelf below the
tallest item of the previous one. Not optimal, but simple, deterministic and
more than good enough for a few hundred 16x16..32x48 sprites.
"""
import json
import os
import sys

import pygame

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "assets", "images", "atlas")
ATLAS_W = 512
PAD = 1   # 1px gap avoids texture bleeding if frames are ever scaled smoothly

# Frames that the game does not use (UI buttons, wall edge pieces, ...)
SKIP_PREFIXES = ("button_", "wall_edge", "wall_outer", "doors_", "lever_", "edge_",
                 "wall_fountain_mid_blue", "wall_fountain_basin_blue")


def build(src):
    pygame.init()
    pygame.display.set_mode((1, 1), pygame.HIDDEN if hasattr(pygame, "HIDDEN") else 0)
    files = sorted(f for f in os.listdir(src) if f.lower().endswith(".png")
                   and not f.startswith(SKIP_PREFIXES))
    imgs = [(f[:-4], pygame.image.load(os.path.join(src, f)).convert_alpha()) for f in files]
    imgs.sort(key=lambda t: (-t[1].get_height(), t[0]))

    index, x, y, shelf_h = {}, PAD, PAD, 0
    for name, img in imgs:
        w, h = img.get_size()
        if x + w + PAD > ATLAS_W:            # start a new shelf
            x, y, shelf_h = PAD, y + shelf_h + PAD, 0
        index[name] = [x, y, w, h]
        x += w + PAD
        shelf_h = max(shelf_h, h)
    height = y + shelf_h + PAD

    atlas = pygame.Surface((ATLAS_W, height), pygame.SRCALPHA)
    for name, img in imgs:
        atlas.blit(img, index[name][:2])
    os.makedirs(OUT_DIR, exist_ok=True)
    pygame.image.save(atlas, os.path.join(OUT_DIR, "atlas.png"))
    with open(os.path.join(OUT_DIR, "atlas.json"), "w") as f:
        json.dump(index, f, indent=0, sort_keys=True)
    print(f"packed {len(index)} frames into {ATLAS_W}x{height} atlas")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    build(sys.argv[1])
