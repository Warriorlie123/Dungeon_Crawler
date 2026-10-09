"""
tools/level_generator.py - procedural generator for levels 4-10.

Usage (from the project folder):
    python tools/level_generator.py            # regenerate levels 4..10
    python tools/level_generator.py 7 --seed 99

Output is the same CSV format the hand-made levels 1-3 use (150 x 150 ints),
so generated maps can be opened and polished in any tile editor (e.g. Tiled)
afterwards. Generation is seeded => the same seed always produces the same
map, which makes bugs reproducible.

Algorithm ("room chain + corridors")
------------------------------------
1. Place a start room.
2. Repeatedly attach a new room to the previous one (or, sometimes, to a
   random earlier room to create side branches) in a random direction,
   rejecting placements that overlap existing rooms (with a 2-tile margin).
3. Join each new room to its parent with an L-shaped 3-tile-wide corridor.
4. Every empty cell touching a floor cell (8-neighbourhood) becomes a wall.
5. Large rooms get 2x2 pillars, kept >= 3 tiles from the room edge so they
   can never cut the room (and therefore the level) in two.
6. Populate: player in room 0, exit in the last room (behind the boss on
   boss levels), enemies/coins/potions in the other rooms.
7. The exit goes in the room that is FARTHEST TO WALK from the spawn (BFS
   distance), and the boss arena is attached to the deepest room. Layouts
   where the exit would still be close to the spawn are rejected.
8. Validate with a BFS flood fill that the exit and every spawn are reachable.
"""
import csv
import os
import random
import sys
from collections import deque

ROWS = COLS = 150
FLOOR, WALL, EXIT, COIN, POTION, PLAYER, BOSS, RANDOM_ENEMY = 0, 7, 8, 9, 10, 11, 17, 23
SPIKES, CHEST, CRATE = 24, 25, 26
DECOR = [1, 2, 3, 4, 5, 6]

# level: (number of normal rooms, (min, max) enemies per room, boss arena?)
# Boss levels (3, 5, 8, 10, 13, 15, 18, 20) end in a big arena. Level 3 is
# the original hand-made map, so it is not generated.
BOSS_LEVELS = {5, 8, 10, 13, 15, 18, 20}
LEVEL_PARAMS = {}
for _lv in range(4, 21):
    if _lv in BOSS_LEVELS:
        LEVEL_PARAMS[_lv] = (4 + _lv // 5, (2, 3 + _lv // 8), True)
    else:
        LEVEL_PARAMS[_lv] = (6 + _lv // 3, (2 + _lv // 7, 4 + _lv // 6), False)


class Room:
    def __init__(self, x, y, w, h):
        self.x, self.y, self.w, self.h = x, y, w, h

    @property
    def center(self):
        return self.x + self.w // 2, self.y + self.h // 2

    def overlaps(self, other, margin=2):
        return not (self.x + self.w + margin <= other.x or other.x + other.w + margin <= self.x or
                    self.y + self.h + margin <= other.y or other.y + other.h + margin <= self.y)

    def cells(self):
        for yy in range(self.y, self.y + self.h):
            for xx in range(self.x, self.x + self.w):
                yield xx, yy


def generate(level, seed=None):
    rng = random.Random(seed if seed is not None else 1000 + level * 7919)
    n_rooms, enemy_range, boss_level = LEVEL_PARAMS[level]
    floor = set()
    rooms = []
    links = []
    depth = {}          # room -> number of rooms between it and the start

    def carve_room(r):
        for c in r.cells():
            floor.add(c)

    def carve_corridor(a, b):
        (x1, y1), (x2, y2) = a, b
        # horizontal leg then vertical leg, 3 cells wide
        for x in range(min(x1, x2), max(x1, x2) + 1):
            for o in (-1, 0, 1):
                floor.add((x, y1 + o))
        for y in range(min(y1, y2), max(y1, y2) + 1):
            for o in (-1, 0, 1):
                floor.add((x2 + o, y))

    start = Room(8, 8, rng.randint(8, 10), rng.randint(7, 9))
    rooms.append(start)
    depth[id(start)] = 0
    carve_room(start)

    total = n_rooms + (1 if boss_level else 0)
    while len(rooms) < total:
        is_arena = boss_level and len(rooms) == total - 1
        placed = False
        for _ in range(400):
            # The boss arena always hangs off the DEEPEST room, so the fight
            # is at the far end of the level, never next to the spawn.
            if is_arena:
                parent = max(rooms, key=lambda r: depth[id(r)])
            else:
                parent = rooms[-1] if rng.random() < 0.75 else rng.choice(rooms)
            if is_arena:
                w, h = 22, 18
            else:
                w, h = rng.randint(8, 14), rng.randint(7, 12)
            # bias towards right/down so the map spreads away from the start
            direction = rng.choice(["right", "right", "down", "down", "left", "up"])
            gap = rng.randint(4, 8)
            px, py = parent.center
            if direction == "right":
                x, y = parent.x + parent.w + gap, py - h // 2 + rng.randint(-3, 3)
            elif direction == "left":
                x, y = parent.x - gap - w, py - h // 2 + rng.randint(-3, 3)
            elif direction == "down":
                x, y = px - w // 2 + rng.randint(-3, 3), parent.y + parent.h + gap
            else:
                x, y = px - w // 2 + rng.randint(-3, 3), parent.y - gap - h
            cand = Room(x, y, w, h)
            if x < 3 or y < 3 or x + w > COLS - 4 or y + h > ROWS - 4:
                continue
            if any(cand.overlaps(r) for r in rooms):
                continue
            rooms.append(cand)
            depth[id(cand)] = depth[id(parent)] + 1
            carve_room(cand)
            carve_corridor(parent.center, cand.center)
            links.append((parent, cand))
            placed = True
            break
        if not placed:
            # dead end: restart with a different seed to stay deterministic
            return generate(level, rng.randint(0, 10 ** 9))

    # ---- pillars (cover) in big rooms -------------------------------------
    pillars = set()
    for r in rooms[1:]:
        if r.w >= 11 and r.h >= 10:
            for _ in range(rng.randint(1, 3)):
                cx = rng.randint(r.x + 3, r.x + r.w - 5)
                cy = rng.randint(r.y + 3, r.y + r.h - 5)
                block = {(cx, cy), (cx + 1, cy), (cx, cy + 1), (cx + 1, cy + 1)}
                if not any((bx, by) == rr.center for rr in rooms for bx, by in block):
                    pillars |= block
    floor -= pillars

    # ---- build the grid ---------------------------------------------------
    grid = [[-1] * COLS for _ in range(ROWS)]
    for (x, y) in floor:
        grid[y][x] = rng.choice(DECOR) if rng.random() < 0.10 else FLOOR
    for (x, y) in floor | pillars:
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                nx, ny = x + dx, y + dy
                if (nx, ny) not in floor and 0 <= nx < COLS and 0 <= ny < ROWS:
                    grid[ny][nx] = WALL

    used = set()

    def free_cell(room, margin=1, avoid=None):
        for _ in range(200):
            x = rng.randint(room.x + margin, room.x + room.w - 1 - margin)
            y = rng.randint(room.y + margin, room.y + room.h - 1 - margin)
            if (x, y) in floor and (x, y) not in used:
                if avoid and abs(x - avoid[0]) + abs(y - avoid[1]) < 5:
                    continue
                used.add((x, y))
                return x, y
        return None

    def put(cell, tile):
        if cell:
            grid[cell[1]][cell[0]] = tile

    # Player
    sx, sy = start.center
    grid[sy][sx] = PLAYER
    used.add((sx, sy))

    # ---- choose the exit room by WALKING distance --------------------------
    # The chain can curl back towards the start, and L-shaped corridors can
    # cut through other rooms, so "the last room placed" may be right next
    # to the spawn (that was the level 17 bug). Instead we flood-fill from
    # the spawn and put the exit in the room that is farthest to WALK to.
    dist = walk_distances(floor, start.center)
    far = max(dist.values())
    if boss_level:
        last = rooms[-1]                               # the arena
    else:
        last = max(rooms[1:], key=lambda r: dist.get(r.center, 0))
    if dist.get(last.center, 0) < max(40, 0.75 * far):
        # exit would still be too close - try another layout (deterministic)
        return generate(level, rng.randint(0, 10 ** 9))
    if boss_level:
        bx, by = last.center
        grid[by][bx] = BOSS
        used.add((bx, by))
        # exit on the arena side opposite to where the corridor arrives
        parent = links[-1][0]
        ex = last.x + last.w - 3 if parent.center[0] < last.center[0] else last.x + 2
        ey = last.y + last.h - 3 if parent.center[1] < last.center[1] else last.y + 2
        grid[ey][ex] = EXIT
        used.add((ex, ey))
        for _ in range(4):
            put(free_cell(last, 2), COIN)
    else:
        ex, ey = last.center
        grid[ey][ex] = EXIT
        used.add((ex, ey))

    # Enemies / loot in the remaining rooms
    for i, r in enumerate(rooms[1:], start=1):
        if boss_level and r is last:
            continue
        lo, hi = enemy_range
        for _ in range(rng.randint(lo, hi)):
            put(free_cell(r, 1, avoid=start.center if i == 1 else None), RANDOM_ENEMY)
        for _ in range(rng.randint(1, 3)):
            put(free_cell(r), COIN)
        if rng.random() < 0.3:
            put(free_cell(r), POTION)
    # A couple of coins in the start room as a welcome
    for _ in range(2):
        put(free_cell(start), COIN)

    # ---- props: crates everywhere, chests sometimes, spike traps deeper ----
    for i, r in enumerate(rooms[1:], start=1):
        if boss_level and r is last:
            continue
        for _ in range(rng.randint(0, 2)):
            put(free_cell(r, 1), CRATE)
        if rng.random() < 0.25:
            put(free_cell(r, 2), CHEST)
        if level >= 6 and rng.random() < 0.5:
            # a short row of spikes across the room
            cell = free_cell(r, 2)
            if cell:
                horiz = rng.random() < 0.5
                for k in range(rng.randint(2, 4)):
                    c = (cell[0] + k, cell[1]) if horiz else (cell[0], cell[1] + k)
                    if c in floor and grid[c[1]][c[0]] in (FLOOR,) + tuple(DECOR):
                        grid[c[1]][c[0]] = SPIKES
                        used.add(c)

    validate(grid, (sx, sy))
    return grid


def walk_distances(floor, start):
    """BFS over floor cells: {cell: steps from start}."""
    dist = {start: 0}
    q = deque([start])
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (x + dx, y + dy)
            if n in floor and n not in dist:
                dist[n] = dist[(x, y)] + 1
                q.append(n)
    return dist


def validate(grid, start):
    """BFS from the player; every special tile must be reachable."""
    seen = {start}
    q = deque([start])
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if (nx, ny) not in seen and 0 <= nx < COLS and 0 <= ny < ROWS and \
                    grid[ny][nx] not in (-1, WALL):
                seen.add((nx, ny))
                q.append((nx, ny))
    for y in range(ROWS):
        for x in range(COLS):
            if grid[y][x] not in (-1, WALL) and (x, y) not in seen:
                raise AssertionError(f"unreachable tile {grid[y][x]} at {(x, y)}")


def save(grid, level):
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "levels", f"level{level}_data.csv")
    with open(out, "w", newline="") as f:
        csv.writer(f).writerows(grid)
    return out


if __name__ == "__main__":
    args = sys.argv[1:]
    seed = None
    if "--seed" in args:
        i = args.index("--seed")
        seed = int(args[i + 1])
        del args[i:i + 2]
    levels = [int(a) for a in args] or sorted(LEVEL_PARAMS)
    for lv in levels:
        print("wrote", save(generate(lv, seed), lv))
