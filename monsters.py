"""
monsters.py - DATA for every monster, boss and level.

Every character in the 0x72 DungeonTileset II is used:
  heroes (10)  -> heroes.py
  monsters     -> MONSTERS below (21 + the mimic chest)
  bosses (8)   -> BOSSES below (ogre, skelet, big_zombie, big_demon, doc,
                  necromancer, pumpkin_dude, angel)

Adding a monster is a data change: give it a sprite name that exists in the
atlas, pick a behaviour, and list its key in some LEVELS[n]["pool"].

Behaviours (implemented in character.Enemy):
  chaser    walk at the player                    erratic   fast zig-zag
  ranged    keep distance, shoot                  charger   wind-up, rush
  splitter  splits into children on death         reviver   gets up once after dying
  berserk   speeds up below 50% HP                teleporter  blinks next to you
  leaper    crouches, then jumps at you           summoner  raises minions
  bomber    lobs bombs with a fuse                healer    heals nearby monsters
  freezer   attacks slow you                      poisoner  throws flasks -> poison puddles
  gooey     leaves slowing goo behind             armored   takes 50% damage
  mimic     disguised as a chest, leaps
"""
from dataclasses import dataclass, field


@dataclass
class MonsterType:
    name: str
    sprite: str                  # atlas animation name
    hp: int = 60
    speed: float = 3.0
    damage: int = 10
    behaviour: str = "chaser"
    hitbox: int = 38
    draw_scale: float = 1.0
    tint: tuple = None
    coins: tuple = (1, 2)
    shoot_cooldown_ms: int = 1800
    projectile: str = "fireball"
    preferred_range: int = 260
    split_into: str = None
    split_count: int = 2
    summon: str = None
    enabled: bool = True


MONSTERS = {
    # ---- swarm / basic --------------------------------------------------------
    "tiny_zombie": MonsterType("Tiny Zombie", "tiny_zombie", hp=26, speed=3.8, damage=6,
                               behaviour="erratic", hitbox=30, coins=(0, 1)),
    "goblin":      MonsterType("Goblin", "goblin", hp=38, speed=4.4, damage=8, behaviour="erratic",
                               coins=(1, 3)),
    "imp":         MonsterType("Imp", "imp", hp=40, speed=2.6, damage=8, behaviour="ranged",
                               projectile="ember", coins=(1, 2)),
    "skelet":      MonsterType("Skeleton", "skelet", hp=50, speed=3.2, damage=10, behaviour="reviver",
                               coins=(1, 2)),
    "zombie":      MonsterType("Zombie", "zombie", hp=85, speed=2.2, damage=12, behaviour="berserk",
                               coins=(1, 2)),
    "tiny_slug":   MonsterType("Slugling", "tiny_slug", hp=18, speed=3.6, damage=5, hitbox=28,
                               coins=(0, 1)),
    "slug":        MonsterType("Slug", "slug", hp=70, speed=2.0, damage=10, behaviour="splitter",
                               split_into="tiny_slug", split_count=3, coins=(1, 2)),
    "muddy":       MonsterType("Muddy", "muddy", hp=80, speed=2.2, damage=12, behaviour="splitter",
                               split_into="mudling", split_count=2, coins=(1, 2)),
    "mudling":     MonsterType("Mudling", "muddy", hp=22, speed=3.6, damage=6, hitbox=26,
                               draw_scale=0.65, coins=(0, 1)),
    # ---- demons ------------------------------------------------------------------
    "chort":       MonsterType("Chort", "chort", hp=55, speed=3.4, damage=11, behaviour="teleporter",
                               coins=(1, 3)),
    "wogol":       MonsterType("Wogol", "wogol", hp=60, speed=3.0, damage=12, behaviour="leaper",
                               coins=(1, 3)),
    # ---- orcs ----------------------------------------------------------------------
    "orc_warrior": MonsterType("Orc Warrior", "orc_warrior", hp=90, speed=2.6, damage=14,
                               behaviour="charger", coins=(2, 3)),
    "orc_shaman":  MonsterType("Orc Shaman", "orc_shaman", hp=55, speed=2.4, damage=8,
                               behaviour="healer", projectile="orb", coins=(2, 3)),
    "masked_orc":  MonsterType("Masked Orc", "masked_orc", hp=110, speed=2.6, damage=14,
                               behaviour="armored", coins=(2, 4)),
    # ---- swamp & ice ----------------------------------------------------------------
    "swampy":      MonsterType("Swampy", "swampy", hp=60, speed=2.8, damage=9, behaviour="gooey",
                               coins=(1, 2)),
    "ice_zombie":  MonsterType("Ice Zombie", "ice_zombie", hp=70, speed=2.6, damage=10,
                               behaviour="freezer", projectile="ice", shoot_cooldown_ms=2600,
                               coins=(1, 3)),
    # ---- casters ---------------------------------------------------------------------
    "necromancer": MonsterType("Necromancer", "necromancer", hp=65, speed=2.2, damage=8,
                               behaviour="summoner", summon="skelet", projectile="orb",
                               preferred_range=320, coins=(2, 4)),
    "doc":         MonsterType("Plague Doctor", "doc", hp=70, speed=2.4, damage=8, behaviour="poisoner",
                               projectile="poison", shoot_cooldown_ms=2600, coins=(2, 4)),
    "pumpkin_dude": MonsterType("Pumpkin Dude", "pumpkin_dude", hp=75, speed=2.4, damage=10,
                                behaviour="bomber", shoot_cooldown_ms=3200, coins=(2, 4)),
    # ---- heavies (late game) ---------------------------------------------------------
    "ogre":        MonsterType("Ogre", "ogre", hp=260, speed=2.2, damage=20, behaviour="charger",
                               hitbox=64, coins=(4, 7)),
    "big_zombie":  MonsterType("Big Zombie", "big_zombie", hp=300, speed=1.8, damage=20,
                               behaviour="berserk", hitbox=64, coins=(4, 7)),
    # ---- special -------------------------------------------------------------------------
    "mimic":       MonsterType("Mimic", "chest_mimic_open", hp=120, speed=3.2, damage=16,
                               behaviour="leaper", hitbox=40, coins=(8, 12)),
}

# Fixed enemy tiles found in the hand-made CSV levels 1-3.
TILE_TO_MONSTER = {12: "imp", 13: "skelet", 14: "goblin", 15: "muddy", 16: "tiny_zombie"}


# ==========================================================================
# Bosses
# ==========================================================================
@dataclass
class BossType:
    name: str
    sprite: str
    hp: int
    speed: float
    damage: int
    hitbox: int
    draw_scale: float
    tint: tuple = None
    coins: int = 20
    phases: list = field(default_factory=list)   # [(hp_ratio_threshold, [patterns]), ...]
    summon: list = field(default_factory=list)   # monster keys used by "summon"
    projectile: str = "fireball"
    title: str = ""


# Pattern names understood by character.Boss:
#   aimed spread3 spread5 ring spiral charge summon slam bombs poison
#   teleport homing cross judgement
BOSSES = {
    "ogre_chief": BossType("OGRE CHIEFTAIN", "ogre", hp=700, speed=2.4, damage=16, hitbox=90,
                           draw_scale=1.5, coins=20, summon=["goblin"], projectile="bone",
                           phases=[(0.5, ["charge", "slam", "summon", "spread3"]),
                                   (1.0, ["charge", "slam", "summon"])],
                           title="Lord of the Upper Halls"),
    "bone_lord":  BossType("BONE LORD", "skelet", hp=950, speed=2.2, damage=15, hitbox=84,
                           draw_scale=2.6, tint=(255, 235, 200), coins=28, summon=["skelet"],
                           projectile="bone",
                           phases=[(0.4, ["ring", "summon", "aimed", "spiral"]),
                                   (1.0, ["ring", "summon", "aimed"])],
                           title="Keeper of the Ossuary"),
    "colossus":   BossType("ROTTING COLOSSUS", "big_zombie", hp=1400, speed=1.9, damage=18, hitbox=100,
                           draw_scale=1.6, coins=34, summon=["tiny_zombie", "zombie"], projectile="goo",
                           phases=[(0.5, ["slam", "poison", "summon", "spread5"]),
                                   (1.0, ["slam", "poison", "summon"])],
                           title="The Hunger That Walks"),
    "demon_brute": BossType("DEMON BRUTE", "big_demon", hp=1800, speed=2.6, damage=20, hitbox=100,
                            draw_scale=1.5, coins=45, summon=["imp", "chort"],
                            phases=[(0.3, ["spiral", "ring", "charge", "summon", "spread5"]),
                                    (0.6, ["spiral", "spread5", "charge", "aimed"]),
                                    (1.0, ["aimed", "spread3", "charge"])],
                            title="Warden of the First Seal"),
    "plague_doc": BossType("DOCTOR MORBIUS", "doc", hp=2000, speed=2.4, damage=16, hitbox=84,
                           draw_scale=2.8, coins=50, summon=["slug", "swampy"], projectile="poison",
                           phases=[(0.5, ["poison", "teleport", "spread5", "summon", "homing"]),
                                   (1.0, ["poison", "teleport", "spread5", "summon"])],
                           title="Physician of Rot"),
    "necros":     BossType("ARCHMAGE NECROS", "necromancer", hp=2300, speed=2.0, damage=16, hitbox=84,
                           draw_scale=3.0, tint=(220, 200, 255), coins=55,
                           summon=["skelet", "necromancer"], projectile="orb",
                           phases=[(0.5, ["teleport", "homing", "ring", "summon", "spiral"]),
                                   (1.0, ["teleport", "homing", "summon", "aimed"])],
                           title="The Last Witness"),
    "pumpkin_king": BossType("THE PUMPKIN KING", "pumpkin_dude", hp=2600, speed=2.6, damage=18,
                             hitbox=84, draw_scale=3.0, tint=(255, 200, 150), coins=60,
                             summon=["pumpkin_dude", "wogol"],
                             phases=[(0.4, ["bombs", "ring", "charge", "spread5", "summon"]),
                                     (1.0, ["bombs", "charge", "spread5"])],
                             title="Gardener of Graves"),
    "seraph":     BossType("SERAPHIEL", "angel", hp=4200, speed=2.8, damage=22, hitbox=96,
                           draw_scale=3.6, coins=120, summon=["imp", "chort", "skelet"], projectile="holy",
                           phases=[(0.33, ["judgement", "spiral", "cross", "homing", "summon", "teleport"]),
                                   (0.66, ["spiral", "ring", "homing", "summon", "cross"]),
                                   (1.0, ["aimed", "cross", "teleport", "spread5"])],
                           title="The Fallen Seal"),
}


# ==========================================================================
# Levels
# ==========================================================================
# Each level: enemy pool (repeat a key to make it more common), boss and
# chances for props. hp/dmg multipliers grow smoothly with depth.
_POOLS = {
    1:  ["tiny_zombie", "goblin", "goblin"],
    2:  ["tiny_zombie", "goblin", "imp", "skelet"],
    3:  ["goblin", "imp"],
    4:  ["slug", "chort", "goblin", "imp"],
    5:  ["skelet", "skelet", "tiny_zombie"],
    6:  ["muddy", "wogol", "orc_warrior", "chort"],
    7:  ["zombie", "orc_shaman", "orc_warrior", "wogol", "imp"],
    8:  ["zombie", "tiny_zombie", "slug"],
    9:  ["masked_orc", "swampy", "ice_zombie", "orc_shaman", "orc_warrior"],
    10: ["imp", "chort", "imp"],
    11: ["necromancer", "ice_zombie", "wogol", "skelet", "chort"],
    12: ["doc", "masked_orc", "swampy", "orc_shaman", "goblin"],
    13: ["slug", "swampy", "doc"],
    14: ["pumpkin_dude", "ogre", "orc_warrior", "masked_orc", "imp"],
    15: ["skelet", "necromancer", "skelet"],
    16: ["big_zombie", "zombie", "ice_zombie", "doc", "chort", "orc_shaman"],
    17: ["ogre", "masked_orc", "pumpkin_dude", "necromancer", "wogol", "muddy"],
    18: ["pumpkin_dude", "wogol", "goblin"],
    19: ["ogre", "big_zombie", "necromancer", "doc", "pumpkin_dude", "masked_orc", "ice_zombie", "chort"],
    20: ["imp", "chort", "skelet"],
}
_BOSS_AT = {3: "ogre_chief", 5: "bone_lord", 8: "colossus", 10: "demon_brute",
            13: "plague_doc", 15: "necros", 18: "pumpkin_king", 20: "seraph"}

LEVELS = {
    n: dict(pool=_POOLS[n],
            hp_mult=round(1 + 0.09 * (n - 1), 2),
            dmg_mult=round(1 + 0.06 * (n - 1), 2),
            boss=_BOSS_AT.get(n),
            act=1 if n <= 10 else 2,
            mimic_chance=0.0 if n < 6 else 0.3)
    for n in range(1, 21)
}


def level_pool(level):
    return LEVELS[level]["pool"]
