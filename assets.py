"""
assets.py - loads every image, font and sound exactly once.

Two image sources
-----------------
1. The original project art (tiles 0-17, buttons, hearts, fireball, ...)
   in assets/images/<folder>/.
2. The 0x72 DungeonTileset II, packed into assets/images/atlas/atlas.png by
   tools/build_atlas.py. Frames are addressed by their original file name
   without ".png", e.g. "knight_m_run_anim_f2" or "weapon_katana".

Animation lookup convention (matches the 0x72 naming):
    <name>_idle_anim_f<N>   + <name>_run_anim_f<N>    (most characters)
    <name>_anim_f<N>                                  (slug, necromancer, ...)
    <name>_hit_anim_f0                                (heroes only, optional)

Everything that is derived (scaled, tinted, rotated) is cached in a dict
keyed by its parameters, so asking for the same variant twice is free.
"""
import json
import re
import pygame
import constants


def scale_img(image, scale):
    w, h = image.get_width(), image.get_height()
    return pygame.transform.scale(image, (max(1, int(w * scale)), max(1, int(h * scale))))


def tint_img(image, rgb):
    """Multiply-tint a copy of `image` (alpha preserved)."""
    out = image.copy()
    out.fill(tuple(rgb) + (255,), special_flags=pygame.BLEND_RGBA_MULT)
    return out


def recolour_img(image, rgb):
    """
    Grey-scale the image, brighten it, then multiply by `rgb`. Multiplying an
    orange fireball directly by blue gives mud; going through grey first lets
    us produce any hue from the single fireball sprite.
    """
    grey = pygame.transform.grayscale(image)
    grey.fill((90, 90, 90, 0), special_flags=pygame.BLEND_RGBA_ADD)
    return tint_img(grey, rgb)


def _natural_key(name):
    # "f10" must come after "f9": compare digit runs as integers.
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


class Assets:
    def __init__(self, audio=True, sound_bank=None):
        # All audio goes through sounds.SoundBank (volume settings, fallbacks,
        # throttling). `audio` is kept for backwards compatibility; with no
        # bank the game is simply silent (used by the headless tests).
        self.sound_bank = sound_bank if audio else None
        img = lambda *p: pygame.image.load(constants.asset_path("images", *p)).convert_alpha()

        # ---- fonts --------------------------------------------------------
        font_file = constants.asset_path("fonts", "AtariClassic.ttf")
        self.font = pygame.font.Font(font_file, 20)
        self.font_small = pygame.font.Font(font_file, 10)
        self.font_tiny = pygame.font.Font(font_file, 8)
        self.font_med = pygame.font.Font(font_file, 14)
        self.font_big = pygame.font.Font(font_file, 32)

        # ---- atlas ----------------------------------------------------------
        self.atlas = img("atlas", "atlas.png")
        with open(constants.asset_path("images", "atlas", "atlas.json")) as f:
            self.atlas_index = json.load(f)
        self._cache = {}

        # ---- original art ---------------------------------------------------
        self.buttons = {n: scale_img(img("buttons", f"button_{n}.png"), constants.BUTTON_SCALE)
                        for n in ("start", "exit", "restart", "resume", "settings")}
        self.heart_empty = scale_img(img("items", "heart_empty.png"), constants.ITEM_SCALE)
        self.heart_half = scale_img(img("items", "heart_half.png"), constants.ITEM_SCALE)
        self.heart_full = scale_img(img("items", "heart_full.png"), constants.ITEM_SCALE)
        self.coin_frames = [scale_img(img("items", f"coin_f{i}.png"), constants.ITEM_SCALE) for i in range(4)]
        fireball = scale_img(img("weapons", "fireball.png"), constants.FIREBALL_SCALE)

        # Act I tiles (original project)
        self.tiles = [pygame.transform.scale(img("tiles", f"{i}.png"), (constants.TILE_SIZE,) * 2)
                      for i in range(constants.TILE_TYPES)]
        # Act II tiles (0x72) - see world.World.draw for how they are used
        T = constants.TILE_SIZE
        tile = lambda n: pygame.transform.scale(self.raw(n), (T, T))
        self.act2 = {
            "floors": [tile(f"floor_{i}") for i in range(1, 9)],
            "wall": tile("wall_mid"),
            "wall_top": tile("wall_top_mid"),
            "ladder": tile("floor_ladder"),
            "decor": [tile(n) for n in ("wall_banner_red", "wall_banner_blue", "wall_banner_green",
                                        "wall_banner_yellow", "wall_hole_1", "wall_hole_2", "wall_goo")],
            "fountain": [tile(f"wall_fountain_mid_red_anim_f{i}") for i in range(3)],
            "fountain_basin": [tile(f"wall_fountain_basin_red_anim_f{i}") for i in range(3)],
            "fountain_top": tile("wall_fountain_top_1"),
            "hole": tile("hole"),
            "stairs": tile("floor_stairs"),
            "column": scale_img(self.raw("column"), constants.SCALE),
        }

        # ---- props / items --------------------------------------------------
        self.spikes = [self.frame(f"floor_spikes_anim_f{i}") for i in range(4)]
        self.chest = {k: [self.frame(f"chest_{k}_open_anim_f{i}") for i in range(3)]
                      for k in ("full", "empty", "mimic")}
        self.crate = self.frame("crate")
        self.skull = self.frame("skull")
        self.bomb = [self.frame(f"bomb_f{i}") for i in range(3)]
        self.flasks = {}
        for colour in ("red", "blue", "green", "yellow"):
            self.flasks[colour] = self.frame(f"flask_{colour}", 2.4)
            self.flasks["big_" + colour] = self.frame(f"flask_big_{colour}", 2.4)
        self.potion = self.flasks["red"]

        # ---- projectiles ----------------------------------------------------
        arrow = self.frame("weapon_arrow", 2.0)
        self.projectiles = {
            "fireball": fireball,
            "ember": scale_img(fireball, 0.7),
            "bone": recolour_img(scale_img(fireball, 0.85), (240, 240, 230)),
            "orb": recolour_img(scale_img(fireball, 0.8), (170, 120, 255)),
            "poison": recolour_img(scale_img(fireball, 0.8), (120, 255, 110)),
            "ice": recolour_img(scale_img(fireball, 0.8), (130, 220, 255)),
            "holy": recolour_img(scale_img(fireball, 0.9), (255, 245, 170)),
            "goo": recolour_img(scale_img(fireball, 0.8), (150, 190, 90)),
            # player shots
            "arrow": arrow,
            "knife": self.frame("weapon_knife", 2.0),
            "throwing_axe": self.frame("weapon_throwing_axe", 2.4),
            "pyro": scale_img(fireball, 0.9),
            "frost": recolour_img(scale_img(fireball, 0.75), (140, 230, 255)),
        }


    # ------------------------------------------------------------------
    # Atlas access
    # ------------------------------------------------------------------
    def has(self, name):
        return name in self.atlas_index

    def raw(self, name):
        """Unscaled frame cut out of the atlas (a subsurface = no copy)."""
        x, y, w, h = self.atlas_index[name]
        return self.atlas.subsurface((x, y, w, h))

    def frame(self, name, scale=constants.SCALE):
        key = ("frame", name, scale)
        if key not in self._cache:
            self._cache[key] = scale_img(self.raw(name), scale)
        return self._cache[key]

    def frames_with_prefix(self, prefix):
        names = [n for n in self.atlas_index if n.startswith(prefix) and n[len(prefix):].isdigit()]
        return sorted(names, key=_natural_key)

    def animation(self, name, scale=1.0, tint=None):
        """
        Return [idle_frames, run_frames, hit_frames] for a character name such
        as "knight_f" or "slug". `scale` multiplies the global SCALE.
        """
        key = ("anim", name, scale, tint)
        if key in self._cache:
            return self._cache[key]
        idle = self.frames_with_prefix(f"{name}_idle_anim_f")
        run = self.frames_with_prefix(f"{name}_run_anim_f")
        if not idle:                                   # single-animation monsters
            idle = run = self.frames_with_prefix(f"{name}_anim_f")
        if not idle:
            raise KeyError(f"no animation frames for '{name}' in atlas")
        hit = self.frames_with_prefix(f"{name}_hit_anim_f") or idle[:1]

        def build(names):
            out = [self.frame(n, constants.SCALE * scale) for n in names]
            return [tint_img(f, tint) for f in out] if tint else out
        result = [build(idle), build(run), build(hit)]
        self._cache[key] = result
        return result

    def weapon(self, name, scale=constants.SCALE):
        return self.frame(f"weapon_{name}", scale)

    # ------------------------------------------------------------------
    def play(self, key, volume=1.0):
        if self.sound_bank:
            self.sound_bank.play(key, volume)
