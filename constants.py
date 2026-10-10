"""
constants.py - global tuning knobs and shared configuration.

Engineering notes
-----------------
* Every number that a designer might want to tweak lives here so that gameplay
  balancing never requires digging through logic code.
* Paths are resolved relative to THIS file (BASE_DIR), not to the current
  working directory. The original project used bare relative paths such as
  "assets/fonts/...", which crash with FileNotFoundError when the game is
  launched from an IDE or a shortcut whose working directory differs from the
  project folder. Anchoring on __file__ removes that whole class of bugs.
"""
import os

# --------------------------------------------------------------------------
# File system
# --------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSET_DIR = os.path.join(BASE_DIR, "assets")
LEVEL_DIR = os.path.join(BASE_DIR, "levels")


def asset_path(*parts):
    """Build an absolute path inside the assets folder."""
    return os.path.join(ASSET_DIR, *parts)


# --------------------------------------------------------------------------
# Display / timing
# --------------------------------------------------------------------------
FPS = 60
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
HUD_HEIGHT = 50                 # height of the top information panel (px)

# --------------------------------------------------------------------------
# Sprite scaling (source art is 16x16 pixel art, scaled up 3x)
# --------------------------------------------------------------------------
SCALE = 3
BUTTON_SCALE = 1
WEAPON_SCALE = 1.5
ITEM_SCALE = 3
POTION_SCALE = 2
FIREBALL_SCALE = 1

# --------------------------------------------------------------------------
# World grid
# --------------------------------------------------------------------------
TILE_SIZE = 16 * SCALE          # 48 px per tile on screen
TILE_TYPES = 18                 # number of tile images in assets/images/tiles
ROWS = 150
COLS = 150
MAX_LEVELS = 20

# Tile ids used in the CSV level files. Keeping them named avoids "magic
# numbers" sprinkled through world.py.
TILE_FLOOR = 0
TILE_WALL = 7
TILE_EXIT = 8
TILE_COIN = 9
TILE_POTION = 10
TILE_PLAYER = 11
TILE_BOSS = 17                  # boss marker; WHICH boss is decided per level
TILE_RANDOM_ENEMY = 23          # generated levels: "pick from this level's pool"
TILE_SPIKES = 24                # spike trap
TILE_CHEST = 25                 # treasure chest (may be a mimic!)
TILE_CRATE = 26                 # breakable crate
# 12..16 are fixed enemy types (see monsters.TILE_TO_MONSTER)

# --------------------------------------------------------------------------
# Player tuning
# --------------------------------------------------------------------------
PLAYER_SPEED = 5.0
PLAYER_START_HP = 100
PLAYER_HITBOX = 34              # square collision box (px); smaller than a
                                # tile so 1-tile gaps are comfortable to walk
PLAYER_INVULN_MS = 800          # i-frames after being hit
DASH_SPEED_MULT = 3.2
DASH_DURATION_MS = 170
DASH_COOLDOWN_MS = 1200

# --------------------------------------------------------------------------
# Weapon tuning
# --------------------------------------------------------------------------
ARROW_SPEED = 11
ARROW_BASE_DAMAGE = 12
ARROW_DAMAGE_SPREAD = 4         # damage = base +/- spread
ARROW_MAX_RANGE = 900           # px travelled before the arrow despawns
SHOT_COOLDOWN_MS = 330
CRIT_CHANCE = 0.10
CRIT_MULT = 2.0
AUTO_AIM_RANGE = 520            # max distance for SPACE / auto-fire targeting

# --------------------------------------------------------------------------
# Enemy tuning
# --------------------------------------------------------------------------
ENEMY_AGGRO_RANGE = 480         # enemies wake up when the player is this close
ENEMY_STOP_RANGE = 40           # melee enemies stop pushing at this distance
ENEMY_STUN_MS = 110             # brief flinch after being hit
ENEMY_KNOCKBACK = 9             # px pushed back per arrow hit

# Balance: ranged heroes used to stun-lock everything from a safe distance,
# because every projectile hit also flinched the enemy (ENEMY_STUN_MS) and
# pushed it back. Now ranged hits don't flinch, push much less, and do a bit
# less damage, so monsters can actually reach a ranged hero.
RANGED_DAMAGE_MULT = 0.85
RANGED_KNOCKBACK_MULT = 0.35

# Balance: bosses
BOSS_HP_MULT = 1.15             # all bosses have 15% more health
BOSS_BULLET_SPEED = 1.15        # boss projectiles fly 15% faster
BOSS_BULLET_DAMAGE = 0.85       # boss projectile damage as a share of contact damage (was 0.7)
BOSS_COOLDOWN_MULT = 0.85       # attack patterns come back 15% sooner
BOSS_GLOBAL_GAP_MS = 400        # minimum time between two patterns (was 450)
BOSS_AIM_LEAD = 0.6             # aimed shots partly lead a moving player (0 = no lead)
BOSS_PURSUIT_RANGE = 360        # beyond this the boss hurries to close in
BOSS_PURSUIT_MULT = 1.3
PROJECTILE_SPEED = 4.5
ELITE_CHANCE = 0.10             # chance a normal enemy spawns as an "elite"
CONTACT_WINDUP_MS = 260         # enemy must touch the player this long before biting
CONTACT_COOLDOWN_MS = 900       # then it waits this long before the next bite
MELEE_KNOCKBACK = 2.4           # melee hits shove enemies this many times harder
MELEE_STAGGER_MS = 380          # ...and stun them this long (no moving / biting)

# --------------------------------------------------------------------------
# Camera
# --------------------------------------------------------------------------
CAMERA_LERP = 0.18              # 0..1, how quickly the camera follows

# --------------------------------------------------------------------------
# Colours
# --------------------------------------------------------------------------
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
PINK = (235, 65, 54)
RED = (255, 0, 0)
YELLOW = (255, 215, 0)
GREEN = (80, 220, 100)
CYAN = (90, 200, 255)
GREY = (140, 140, 140)
DARK_GREY = (70, 70, 70)
BG = (40, 25, 25)
MENU_BG = (130, 0, 0)
PANEL = (50, 50, 50)
SHOP_BG = (28, 20, 34)
