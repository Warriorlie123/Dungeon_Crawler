"""
world.py - level loading, tile collision, line-of-sight and rendering.

Coordinate system (important change vs. the original code)
-----------------------------------------------------------
The original game kept everything in SCREEN coordinates and "scrolled the
world" by adding `screen_scroll` to every tile, enemy, item, arrow and damage
number each frame. That approach has three problems:
  1. Every new object type must remember to apply the scroll, or it drifts
     (a classic source of bugs).
  2. Collision used a linear scan over ALL wall tiles - O(walls) per move.
  3. Positions accumulate integer rounding errors over time.

Now every object lives in WORLD coordinates (pixels from the map's top-left)
and only the renderer subtracts a `Camera` offset. Walls are stored in a 2-D
boolean grid, so a collision test only inspects the handful of tiles that a
rectangle overlaps - O(1) regardless of map size.
"""
import csv
import math
import os
import random
import pygame
import constants
import monsters


class Camera:
    """Smoothly follows a target; converts world -> screen coordinates."""

    def __init__(self):
        self.x = 0.0
        self.y = 0.0
        self.shake_ms = 0
        self.shake_strength = 0

    def snap_to(self, rect):
        self.x = rect.centerx - constants.SCREEN_WIDTH / 2
        self.y = rect.centery - (constants.SCREEN_HEIGHT + constants.HUD_HEIGHT) / 2

    def follow(self, rect, dt_ms):
        tx = rect.centerx - constants.SCREEN_WIDTH / 2
        ty = rect.centery - (constants.SCREEN_HEIGHT + constants.HUD_HEIGHT) / 2
        # Linear interpolation ("lerp") gives a soft, lag-free follow.
        self.x += (tx - self.x) * constants.CAMERA_LERP
        self.y += (ty - self.y) * constants.CAMERA_LERP
        if self.shake_ms > 0:
            self.shake_ms -= dt_ms

    def shake(self, strength=6, ms=200):
        if not getattr(getattr(self, "settings", None), "screen_shake", True):
            return
        self.shake_strength = strength
        self.shake_ms = ms

    @property
    def offset(self):
        ox, oy = self.x, self.y
        if self.shake_ms > 0:
            ox += random.uniform(-self.shake_strength, self.shake_strength)
            oy += random.uniform(-self.shake_strength, self.shake_strength)
        return int(ox), int(oy)

    def apply(self, rect):
        ox, oy = self.offset
        return rect.move(-ox, -oy)


def load_level_csv(level):
    """Read levels/levelN_data.csv into a ROWS x COLS list of ints."""
    data = [[-1] * constants.COLS for _ in range(constants.ROWS)]
    path = os.path.join(constants.LEVEL_DIR, f"level{level}_data.csv")
    with open(path, newline="") as f:
        for y, row in enumerate(csv.reader(f)):
            if y >= constants.ROWS:
                break
            for x, tile in enumerate(row[:constants.COLS]):
                data[y][x] = int(tile)
    return data


class World:
    def __init__(self, level, assets):
        self.level = level
        self.assets = assets
        T = constants.TILE_SIZE
        self.tile_grid = [[-1] * constants.COLS for _ in range(constants.ROWS)]
        self.solid = [[False] * constants.COLS for _ in range(constants.ROWS)]
        self.exit_rect = None
        self.player_spawn = (0, 0)
        self.enemy_spawns = []   # list of (monster_key, x, y)
        self.boss_spawn = None   # (boss_key, x, y)
        self.item_spawns = []    # list of ("coin"|"potion", x, y)
        self.prop_spawns = []    # list of ("spikes"|"chest"|"crate", x, y)

        data = load_level_csv(level)
        cfg = monsters.LEVELS.get(level, {})
        pool = monsters.level_pool(level)
        self.act = cfg.get("act", 1)

        for y, row in enumerate(data):
            for x, tile in enumerate(row):
                if tile < 0:
                    continue
                cx, cy = x * T + T // 2, y * T + T // 2   # tile centre (world px)
                visual = tile
                if tile == constants.TILE_WALL:
                    self.solid[y][x] = True
                elif tile == constants.TILE_EXIT:
                    self.exit_rect = pygame.Rect(x * T, y * T, T, T)
                elif tile == constants.TILE_COIN:
                    self.item_spawns.append(("coin", cx, cy)); visual = 0
                elif tile == constants.TILE_POTION:
                    self.item_spawns.append(("potion", cx, cy)); visual = 0
                elif tile == constants.TILE_PLAYER:
                    self.player_spawn = (cx, cy); visual = 0
                elif tile in monsters.TILE_TO_MONSTER:
                    self.enemy_spawns.append((monsters.TILE_TO_MONSTER[tile], cx, cy)); visual = 0
                elif tile in (constants.TILE_SPIKES, constants.TILE_CHEST, constants.TILE_CRATE):
                    kind = {constants.TILE_SPIKES: "spikes", constants.TILE_CHEST: "chest",
                            constants.TILE_CRATE: "crate"}[tile]
                    self.prop_spawns.append((kind, cx, cy)); visual = 0
                elif tile == constants.TILE_RANDOM_ENEMY:
                    self.enemy_spawns.append((random.choice(pool), cx, cy)); visual = 0
                elif tile == constants.TILE_BOSS:
                    boss_key = cfg.get("boss") or "ogre_chief"
                    self.boss_spawn = (boss_key, cx, cy); visual = 0
                if visual >= constants.TILE_TYPES:
                    visual = 0
                self.tile_grid[y][x] = visual

        self._build_minimap()
        if self.act == 2:
            self._build_act2_cache()

    # ------------------------------------------------------------------
    # Collision helpers
    # ------------------------------------------------------------------
    def is_solid_px(self, px, py):
        T = constants.TILE_SIZE
        c, r = int(px // T), int(py // T)
        if r < 0 or c < 0 or r >= constants.ROWS or c >= constants.COLS:
            return True                       # outside the map counts as wall
        return self.solid[r][c] or self.tile_grid[r][c] < 0

    def rect_hits_wall(self, rect):
        """Check only the tiles the rectangle overlaps (fast)."""
        T = constants.TILE_SIZE
        c0, c1 = rect.left // T, (rect.right - 1) // T
        r0, r1 = rect.top // T, (rect.bottom - 1) // T
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                if r < 0 or c < 0 or r >= constants.ROWS or c >= constants.COLS:
                    return True
                if self.solid[r][c] or self.tile_grid[r][c] < 0:
                    return True
        return False

    def move_rect(self, rect, fx, fy, dx, dy):
        """
        Move a rect by (dx, dy) with wall sliding.

        `fx, fy` are float positions (the rect's centre) kept by the caller so
        sub-pixel speeds such as 2.2 px/frame accumulate correctly instead of
        being truncated to 2 every frame. Returns the new float centre and
        whether a wall was hit on each axis.

        Axis-separated resolution: move X, resolve; then move Y, resolve.
        This is what lets the player "slide" along walls diagonally.
        """
        hit_x = hit_y = False
        # --- X axis -------------------------------------------------------
        if dx:
            nx = fx + dx
            rect.centerx = round(nx)
            if self.rect_hits_wall(rect):
                hit_x = True
                step = 1 if dx > 0 else -1
                # back off pixel by pixel until free (max one tile)
                for _ in range(constants.TILE_SIZE):
                    rect.x -= step
                    if not self.rect_hits_wall(rect):
                        break
                nx = rect.centerx
            fx = nx
        # --- Y axis -------------------------------------------------------
        if dy:
            ny = fy + dy
            rect.centery = round(ny)
            if self.rect_hits_wall(rect):
                hit_y = True
                step = 1 if dy > 0 else -1
                for _ in range(constants.TILE_SIZE):
                    rect.y -= step
                    if not self.rect_hits_wall(rect):
                        break
                ny = rect.centery
            fy = ny
        return fx, fy, hit_x, hit_y

    def line_of_sight(self, a, b, step=12):
        """
        Ray-march from point a to b in `step`-px increments and report whether
        any wall tile blocks the segment. O(distance/step), independent of the
        number of walls (the original clipped the line against every wall).
        """
        ax, ay = a
        bx, by = b
        dist = math.hypot(bx - ax, by - ay)
        n = max(1, int(dist // step))
        for i in range(1, n):
            t = i / n
            if self.is_solid_px(ax + (bx - ax) * t, ay + (by - ay) * t):
                return False
        return True

    def random_floor_near(self, x, y, radius_tiles=3):
        """Find a walkable tile centre near (x, y) - used for summons."""
        T = constants.TILE_SIZE
        for _ in range(30):
            c = int(x // T) + random.randint(-radius_tiles, radius_tiles)
            r = int(y // T) + random.randint(-radius_tiles, radius_tiles)
            if 0 <= r < constants.ROWS and 0 <= c < constants.COLS and \
                    self.tile_grid[r][c] >= 0 and not self.solid[r][c]:
                return c * T + T // 2, r * T + T // 2
        return x, y

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def draw(self, surface, camera, exit_locked=False):
        """Draw only the tiles inside the viewport (culling)."""
        T = constants.TILE_SIZE
        ox, oy = camera.offset
        c0 = max(0, ox // T)
        c1 = min(constants.COLS - 1, (ox + constants.SCREEN_WIDTH) // T + 1)
        r0 = max(0, oy // T)
        r1 = min(constants.ROWS - 1, (oy + constants.SCREEN_HEIGHT) // T + 1)
        if self.act == 2:
            self._draw_act2(surface, ox, oy, c0, c1, r0, r1)
        else:
            tiles = self.assets.tiles
            for r in range(r0, r1 + 1):
                row = self.tile_grid[r]
                for c in range(c0, c1 + 1):
                    t = row[c]
                    if t >= 0:
                        surface.blit(tiles[t], (c * T - ox, r * T - oy))
        if self.exit_rect and exit_locked:
            # Red pulsing overlay tells the player the boss must die first.
            er = camera.apply(self.exit_rect)
            pulse = 90 + int(60 * math.sin(pygame.time.get_ticks() / 150))
            overlay = pygame.Surface((T, T), pygame.SRCALPHA)
            overlay.fill((255, 0, 0, pulse))
            surface.blit(overlay, er)

    def _build_act2_cache(self):
        """
        Act II uses the 0x72 tiles. Decide ONCE per tile which image it gets
        (floor variant, brick face, wall lip, decoration) and store it, so the
        per-frame draw loop is just a lookup + blit.
        """
        a = self.assets.act2
        rng = random.Random(self.level * 7717)
        R, C = constants.ROWS, constants.COLS
        self.act2_grid = [[None] * C for _ in range(R)]
        self.fountains = []

        def floorish(r, c):
            return 0 <= r < R and 0 <= c < C and self.tile_grid[r][c] >= 0 and not self.solid[r][c]
        for r in range(R):
            for c in range(C):
                t = self.tile_grid[r][c]
                if t < 0:
                    continue
                if not self.solid[r][c]:
                    if t == constants.TILE_EXIT:
                        img = a["ladder"]
                    elif t == 0:
                        img = a["floors"][0] if rng.random() < 0.8 else rng.choice(a["floors"][1:])
                    else:
                        img = a["floors"][t % 8]
                    self.act2_grid[r][c] = img
                    continue
                near_floor = any(floorish(r + dr, c + dc) for dr in (-1, 0, 1) for dc in (-1, 0, 1))
                if floorish(r + 1, c):              # brick face visible from the room
                    roll = rng.random()
                    if roll < 0.02 and floorish(r + 2, c):
                        self.fountains.append((r, c))
                        img = a["wall"]
                    elif roll < 0.10:
                        img = rng.choice(a["decor"])
                    else:
                        img = a["wall"]
                elif near_floor:
                    img = a["wall"]
                else:
                    img = None
                self.act2_grid[r][c] = img

    def _draw_act2(self, surface, ox, oy, c0, c1, r0, r1):
        T = constants.TILE_SIZE
        a = self.assets.act2
        top = a["wall_top"]
        for r in range(r0, r1 + 1):
            row = self.act2_grid[r]
            for c in range(c0, c1 + 1):
                img = row[c]
                if img is not None:
                    surface.blit(img, (c * T - ox, r * T - oy))
                    # lip on top of every wall that sits above a brick face
                    if self.solid[r][c] and r > 0 and self.act2_grid[r - 1][c] is None:
                        surface.blit(top, (c * T - ox, (r - 1) * T - oy))
        f = (pygame.time.get_ticks() // 160) % 3
        for (r, c) in self.fountains:
            if r0 - 1 <= r <= r1 and c0 <= c <= c1:
                surface.blit(a["fountain"][f], (c * T - ox, r * T - oy))
                surface.blit(a["fountain_basin"][f], (c * T - ox, (r + 1) * T - oy))

    # ------------------------------------------------------------------
    # Minimap with fog of war ("Dead Cells" style)
    # ------------------------------------------------------------------
    # The map starts black. Only tiles the player has actually SEEN are drawn,
    # so the minimap shows the paths you explored and nothing else: no enemy
    # dots, no spoiled exit location. Seen tiles are painted onto a persistent
    # surface the moment they are discovered, so drawing the minimap each
    # frame is still a single blit.
    MM_REVEAL_RADIUS = 6          # tiles

    def _build_minimap(self):
        rows = [r for r in range(constants.ROWS) if any(t >= 0 for t in self.tile_grid[r])]
        # ignore the stray full-floor row some original CSVs have at the bottom
        rows = [r for r in rows if sum(1 for t in self.tile_grid[r] if t >= 0) < constants.COLS]
        cols = [c for c in range(constants.COLS) if any(self.tile_grid[r][c] >= 0 for r in rows)]
        if not rows or not cols:
            self.minimap = None
            return
        self.mm_r0, self.mm_c0 = min(rows), min(cols)
        h, w = max(rows) - self.mm_r0 + 1, max(cols) - self.mm_c0 + 1
        self.mm_px = 4                       # fixed zoom; we show a window around the player
        self.minimap = pygame.Surface((w * self.mm_px, h * self.mm_px), pygame.SRCALPHA)
        self.minimap.fill((0, 0, 0, 0))     # unexplored = fully transparent
        self.explored = [[False] * constants.COLS for _ in range(constants.ROWS)]
        self._last_reveal_cell = None

    def _paint_mm(self, r, c):
        if self.explored[r][c]:
            return
        self.explored[r][c] = True
        if self.solid[r][c]:
            col = (150, 120, 95)
        elif self.tile_grid[r][c] == constants.TILE_EXIT:
            col = (255, 215, 0)
        else:
            col = (95, 85, 85)
        pygame.draw.rect(self.minimap, col, ((c - self.mm_c0) * self.mm_px, (r - self.mm_r0) * self.mm_px,
                                             self.mm_px, self.mm_px))

    def reveal(self, player_rect):
        """
        Mark tiles around the player as explored. Only floor tiles in line of
        sight are revealed (you can't see through walls), plus the walls that
        border them. Runs only when the player enters a new tile, so the
        ray-marching cost is paid a few times per second, not every frame.
        """
        if not self.minimap:
            return
        T = constants.TILE_SIZE
        pc, pr = player_rect.centerx // T, player_rect.centery // T
        if (pc, pr) == self._last_reveal_cell:
            return
        self._last_reveal_cell = (pc, pr)
        R = self.MM_REVEAL_RADIUS
        seen = []
        for r in range(max(0, pr - R), min(constants.ROWS, pr + R + 1)):
            for c in range(max(0, pc - R), min(constants.COLS, pc + R + 1)):
                if (r - pr) ** 2 + (c - pc) ** 2 > R * R:
                    continue
                if self.tile_grid[r][c] < 0 or self.solid[r][c] or self.explored[r][c]:
                    continue
                if self.line_of_sight(player_rect.center, (c * T + T // 2, r * T + T // 2), step=16):
                    seen.append((r, c))
        for r, c in seen:
            self._paint_mm(r, c)
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    rr, cc = r + dr, c + dc
                    if 0 <= rr < constants.ROWS and 0 <= cc < constants.COLS and self.solid[rr][cc]:
                        self._paint_mm(rr, cc)

    def reveal_exit(self):
        """Once the ladder unlocks, mark it on the map even if unexplored."""
        if self.minimap and self.exit_rect:
            T = constants.TILE_SIZE
            r, c = self.exit_rect.centery // T, self.exit_rect.centerx // T
            self.explored[r][c] = False
            self._paint_mm(r, c)
            self.exit_revealed = True

    def draw_minimap(self, surface, player_rect, hunted=None, now=0):
        """
        Enemies are normally NOT shown. `hunted` is the short list of the
        last few survivors (passed by the Game when only a handful remain);
        those pulse in red so the player can finish the floor.
        """
        if not self.minimap:
            return
        # A fixed-size window centred on the player (like Dead Cells): the
        # explored map scrolls underneath it, so the full level size is never
        # given away either.
        T = constants.TILE_SIZE
        vw, vh = 180, 130
        x0 = constants.SCREEN_WIDTH - vw - 8
        y0 = constants.HUD_HEIGHT + 8
        px = int((player_rect.centerx / T - self.mm_c0) * self.mm_px)
        py = int((player_rect.centery / T - self.mm_r0) * self.mm_px)
        panel = pygame.Surface((vw, vh), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 140))
        panel.blit(self.minimap, (vw // 2 - px, vh // 2 - py))
        surface.blit(panel, (x0, y0))
        pygame.draw.rect(surface, (110, 95, 120), (x0 - 1, y0 - 1, vw + 2, vh + 2), 1)
        cx, cy = x0 + vw // 2, y0 + vh // 2
        clip = surface.get_clip()
        surface.set_clip(pygame.Rect(x0, y0, vw, vh))
        if getattr(self, "exit_revealed", False) and self.exit_rect:
            ex = cx + int((self.exit_rect.centerx / T - self.mm_c0) * self.mm_px) - px
            ey = cy + int((self.exit_rect.centery / T - self.mm_r0) * self.mm_px) - py
            pygame.draw.circle(surface, constants.YELLOW, (ex, ey), 4)
        if hunted:
            rad = 3 + int(1.5 * (1 + math.sin(now / 150)))
            for e in hunted:
                hx = cx + int((e.rect.centerx / T - self.mm_c0) * self.mm_px) - px
                hy = cy + int((e.rect.centery / T - self.mm_r0) * self.mm_px) - py
                # far-away survivors stick to the minimap border (= direction)
                hx = max(x0 + 4, min(x0 + vw - 4, hx))
                hy = max(y0 + 4, min(y0 + vh - 4, hy))
                pygame.draw.circle(surface, constants.RED, (hx, hy), rad)
        surface.set_clip(clip)
        pygame.draw.circle(surface, constants.GREEN, (cx, cy), 3)
