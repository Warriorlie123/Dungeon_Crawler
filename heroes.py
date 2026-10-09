"""
heroes.py - the ten playable heroes (5 classes x female/male).

Every hero is pure DATA: sprite name, base stats, a weapon family with
upgrade tiers (the Forge in the shop moves you up a tier), an active ability
(E / right-click) and a passive. The behaviour lives in:
    weapon.py     - how each weapon KIND attacks (melee / bow / throw / staff)
    abilities.py  - one function per ability key
    character.py  - Player reads the passive flags

Weapon tier tuple:  (sprite, damage, cooldown_ms, extras)
    melee extras : reach (px), arc (deg)
    bow extras   : speed
    throw extras : projectile, speed, range, returning, pierce
    staff extras : projectile, speed, explode (radius px), slow (ms)
"""
from dataclasses import dataclass, field


@dataclass
class Ability:
    key: str
    name: str
    desc: str
    cooldown_ms: int


@dataclass
class Hero:
    key: str             # also the sprite name in the atlas
    name: str
    title: str
    role: str            # short class label for the select screen
    hp: int
    speed: float
    weapon_kind: str     # "melee" | "bow" | "throw" | "staff"
    tiers: list
    ability: Ability
    passive_name: str
    passive_desc: str
    bio: str
    flags: dict = field(default_factory=dict)   # passive switches read by code

    @property
    def is_ranged(self):
        return self.weapon_kind != "melee"


HEROES = [
    # ------------------------------------------------------------- KNIGHTS
    Hero("knight_m", "Sir Aldric", "the Unbending", "Guardian Knight", hp=130, speed=4.6,
         weapon_kind="melee",
         tiers=[("rusty_sword", 20, 420, dict(reach=88, arc=110)),
                ("regular_sword", 26, 400, dict(reach=92, arc=115)),
                ("knight_sword", 34, 380, dict(reach=100, arc=120)),
                ("lavish_sword", 44, 360, dict(reach=108, arc=130))],
         ability=Ability("bulwark", "Bulwark",
                         "4s: take 70% less damage and REFLECT enemy projectiles.", 12000),
         passive_name="Parry", passive_desc="Sword swings destroy enemy projectiles.",
         bio="Swore to guard the King's gate. The gate is fine. He got bored.",
         flags=dict(armor=0.2, parry=True)),
    Hero("knight_f", "Dame Rowena", "of the Dawn", "Paladin", hp=115, speed=4.8,
         weapon_kind="melee",
         tiers=[("spear", 18, 380, dict(reach=118, arc=60)),
                ("duel_sword", 26, 360, dict(reach=96, arc=115)),
                ("golden_sword", 34, 340, dict(reach=102, arc=120)),
                ("red_gem_sword", 44, 320, dict(reach=110, arc=125))],
         ability=Ability("consecration", "Consecration",
                         "Holy nova: damages and knocks back nearby foes, heals 20 HP.", 10000),
         passive_name="Faith", passive_desc="Every kill heals 2 HP.",
         bio="Paladin of the Dawn Order. Believes in mercy, second chances, and very large swords.",
         flags=dict(armor=0.15, heal_on_kill=2)),
    # ------------------------------------------------------------- DWARVES
    Hero("dwarf_m", "Borin Ironbeard", "the Red", "Berserker", hp=140, speed=4.3,
         weapon_kind="melee",
         tiers=[("axe", 26, 520, dict(reach=84, arc=140)),
                ("waraxe", 36, 500, dict(reach=90, arc=150)),
                ("double_axe", 48, 480, dict(reach=98, arc=170))],
         ability=Ability("whirlwind", "Whirlwind",
                         "3s: spin your axe, hitting everything around you.", 11000),
         passive_name="Rage", passive_desc="Below 50% HP you deal 35% more damage.",
         bio="Lost a bet, his beard, and his temper. Found two of them again.",
         flags=dict(armor=0.15, rage=True)),
    Hero("dwarf_f", "Hilda Stonefuse", "Bombsmith", "Demolitionist", hp=125, speed=4.4,
         weapon_kind="melee",
         tiers=[("hammer", 24, 480, dict(reach=82, arc=120)),
                ("mace", 32, 460, dict(reach=86, arc=125)),
                ("baton_with_spikes", 40, 440, dict(reach=90, arc=130)),
                ("big_hammer", 54, 470, dict(reach=104, arc=140))],
         ability=Ability("powder_keg", "Powder Keg",
                         "Lob a bomb that blasts a large area after a short fuse.", 7000),
         passive_name="Haggler", passive_desc="Shop prices -15%. Crates & chests drop extra gold.",
         bio="Mining engineer. Her safety record is 'technically still alive'.",
         flags=dict(armor=0.1, discount=0.15, looter=True)),
    # ------------------------------------------------------------- ELVES
    Hero("elf_m", "Faelar", "Windstrider", "Ranger", hp=100, speed=5.0,
         weapon_kind="bow",
         tiers=[("bow", 14, 330, dict(speed=11)),
                ("bow_2", 19, 300, dict(speed=12.5))],
         ability=Ability("arrow_rain", "Arrow Storm",
                         "Release 24 arrows in every direction at once.", 9000),
         passive_name="Keen Eye", passive_desc="+12% critical hit chance.",
         bio="The original hero of this dungeon. Came back because he left his good bow down here.",
         flags=dict(crit_bonus=0.12)),
    Hero("elf_f", "Sylwen", "Moonshade", "Huntress", hp=95, speed=5.4,
         weapon_kind="bow",
         tiers=[("bow", 12, 290, dict(speed=12)),
                ("bow_2", 17, 260, dict(speed=13.5))],
         ability=Ability("focus", "Hunter's Focus",
                         "5s: double fire rate, arrows pierce 2 extra foes, +20% crit.", 14000),
         passive_name="Fleet", passive_desc="+12% move speed.",
         bio="Tracks anything that leaves footprints. Monsters, deer, overdue library books.",
         flags=dict(speed_bonus=0.12)),
    # ------------------------------------------------------------- LIZARDFOLK
    Hero("lizard_m", "Ssarik", "the Unseen", "Assassin", hp=95, speed=5.2,
         weapon_kind="throw",
         tiers=[("knife", 9, 190, dict(projectile="knife", speed=14, range=430, returning=False, pierce=0)),
                ("throwing_axe", 18, 300, dict(projectile="throwing_axe", speed=11, range=380,
                                               returning=True, pierce=3))],
         ability=Ability("smoke_step", "Smoke Step",
                         "Blink forward and turn invisible for 3s. Next hit is a guaranteed crit.", 10000),
         passive_name="Cold Blood", passive_desc="Critical hits deal x2.5 instead of x2.",
         bio="Professional assassin. Took this job because the target 'is already a monster, so no paperwork'.",
         flags=dict(crit_mult=2.5)),
    Hero("lizard_f", "Vexa", "Venomtongue", "Duelist", hp=110, speed=5.0,
         weapon_kind="melee",
         tiers=[("machete", 16, 300, dict(reach=82, arc=100)),
                ("cleaver", 21, 290, dict(reach=84, arc=105)),
                ("katana", 27, 270, dict(reach=96, arc=110)),
                ("saw_sword", 33, 260, dict(reach=98, arc=115)),
                ("anime_sword", 41, 240, dict(reach=110, arc=120))],
         ability=Ability("venom", "Venom Edge",
                         "6s: hits poison enemies and heal you for 15% of damage.", 12000),
         passive_name="Scales", passive_desc="Regenerate 1 HP every 2 seconds.",
         bio="Fastest blade in the swamp. Collects swords the way others collect spoons.",
         flags=dict(armor=0.1, regen=True)),
    # ------------------------------------------------------------- WIZARDS
    Hero("wizzard_m", "Ignatius", "the Kindled", "Pyromancer", hp=90, speed=4.7,
         weapon_kind="staff",
         tiers=[("red_magic_staff", 16, 420, dict(projectile="pyro", speed=8, explode=55, slow=0))],
         ability=Ability("meteor", "Meteor",
                         "Call a meteor on the nearest enemy: huge damage in a big area.", 10000),
         passive_name="Pyromania", passive_desc="Explosions are 25% larger.",
         bio="Graduated top of his class. The class was in a building that is no longer there.",
         flags=dict(aoe_bonus=0.25)),
    Hero("wizzard_f", "Isolde", "Frostweaver", "Cryomancer", hp=90, speed=4.8,
         weapon_kind="staff",
         tiers=[("green_magic_staff", 13, 340, dict(projectile="frost", speed=9.5, explode=0, slow=1400))],
         ability=Ability("frost_nova", "Frost Nova",
                         "Freeze every enemy near you for 2.5s. Frozen foes take +50% damage.", 11000),
         passive_name="Mana Flow", passive_desc="Ability cooldown -20%.",
         bio="Can chill a room in seconds - with spells, or by talking about her thesis.",
         flags=dict(cd_mult=0.8)),
]
HERO_BY_KEY = {h.key: h for h in HEROES}

# Weapon sound per hero (keys of sounds.SFX) - every hero sounds different.
ATTACK_SOUND = {
    "knight_m": "sword_swing", "knight_f": "spear_thrust", "dwarf_m": "axe_swing",
    "dwarf_f": "hammer_smash", "elf_m": "bow_twang", "elf_f": "bow_quick",
    "lizard_m": "knife_throw", "lizard_f": "blade_slash", "wizzard_m": "fire_cast",
    "wizzard_f": "frost_cast",
}

# Staff heroes have only one sprite tier; the Forge empowers them instead.
STAFF_EMPOWER = [1.0, 1.3, 1.65, 2.0]


def max_tier(hero):
    return (len(STAFF_EMPOWER) if hero.weapon_kind == "staff" else len(hero.tiers)) - 1
