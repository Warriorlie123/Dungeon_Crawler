# Dungeon Crawler — The Seal of Vel Duran

A top-down pygame dungeon crawler with 10 heroes, 20 levels, 8 bosses, 22
monster types, a shop and weapon forge between levels, and story cutscenes.
Every character in **0x72's DungeonTileset II** has a role in the game.

```
pip install pygame
python main.py                              # play
python main.py --level 12 --hero lizard_f   # jump straight in (testing)
python tools/smoke_test.py                  # headless bot plays all 20 levels + every hero
python tools/level_generator.py             # regenerate levels 4-20
python tools/build_atlas.py <0x72 frames folder>   # rebuild the sprite atlas
```

## Controls

| Action | Keyboard | Mouse / touchpad |
|---|---|---|
| Move | `W A S D` | – |
| Attack in a direction (hold to repeat) | `Arrow keys` | Hold left button |
| Auto-aim at the nearest enemy (hold) | `SPACE` | – |
| Toggle auto-fire | `F` | – |
| Hero ability | `E` (or `Q`) | Right click |
| Dash (brief invulnerability) | `SHIFT` | – |
| Drink a carried potion | `H` | – |
| Minimap on/off / pause | `M` / `ESC` | – |
| Shop: buy / reroll / continue | `1`-`6` / `R` / `ENTER` | Click |
| Cutscenes: next / skip | `ENTER` / `ESC` | Click |

**On a touchpad:** turn on auto-fire with `F`, move with WASD and use `E`.
You never need to aim with the cursor.

## Sound & settings

* **Settings** (`O` in the main menu or the pause menu): master, music and
  sound-effect volume, plus screen shake on/off. They are saved to
  `settings.json`; delete that file to reset them.
* **Bundled audio:** all 54 effects and 6 music tracks were synthesised from
  scratch by `tools/make_sounds.py` in a retro chiptune style, so there are no
  licence issues. Act I still uses the original `music.wav`. Re-run the script
  to regenerate them, or replace any single file with your own.
* **Sound slots:** the game knows 58 sound effects and 7 music tracks.
  `assets/audio/sfx/SOUND_LIST.txt` lists every file name and what it should
  sound like. Drop `<name>.wav` (or `.ogg`/`.mp3`) into `assets/audio/sfx/`
  and music into `assets/audio/music/`. You can add them one at a time.
  Anything missing falls back to a similar sound or the original ones, so
  the game is never broken by a missing file.
* **Every hero's weapon has its own sound slot** (sword_swing, axe_swing,
  bow_quick, frost_cast, ...), and so does every ability.
* **Music** switches automatically between menu, Act I, Act II, boss fights,
  shop, cutscenes and the ending.
* Run `python sounds.py` to regenerate SOUND_LIST.txt after adding new slots.

## Heroes

You pick a hero on the selection screen. Each one has a weapon family that
the **Forge** in the shop upgrades tier by tier, plus an ability and a passive.

| Hero | Role | Weapon tiers | Ability (E) | Passive |
|---|---|---|---|---|
| Sir Aldric (knight_m) | Guardian | rusty → regular → knight → lavish sword | **Bulwark**: 70% damage reduction for 4s and reflects projectiles | **Parry**: swings destroy projectiles |
| Dame Rowena (knight_f) | Paladin | spear → duel → golden → red-gem sword | **Consecration**: holy nova, knockback, +20 HP | **Faith**: +2 HP per kill |
| Borin (dwarf_m) | Berserker | axe → waraxe → double axe | **Whirlwind**: 3s spin that hits everything nearby | **Rage**: +35% damage below half HP |
| Hilda (dwarf_f) | Demolitionist | hammer → mace → spiked baton → big hammer | **Powder Keg**: big bomb | **Haggler**: −15% shop prices, extra loot |
| Faelar (elf_m) | Ranger | bow → bow II | **Arrow Storm**: 24 arrows in every direction | +12% crit |
| Sylwen (elf_f) | Huntress | bow → bow II | **Hunter's Focus**: double fire rate, piercing, crits | +12% speed |
| Ssarik (lizard_m) | Assassin | thrown knives → returning throwing axe | **Smoke Step**: blink, 3s invisibility, next hit always crits | Crits deal ×2.5 |
| Vexa (lizard_f) | Duelist | machete → cleaver → katana → saw sword → anime sword | **Venom Edge**: hits poison enemies and heal you | HP regeneration |
| Ignatius (wizzard_m) | Pyromancer | red staff (fire bolts that explode) | **Meteor**: huge blast on the nearest enemy | Explosions 25% larger |
| Isolde (wizzard_f) | Cryomancer | green staff (frost bolts that slow and pierce) | **Frost Nova**: freezes enemies; frozen enemies take +50% damage | −20% ability cooldown |

### Melee survivability

Melee heroes have to stand next to monsters, so three rules keep them alive:

* **Knock-back + stagger:** melee hits shove enemies about 70 px away and stun
  them for 0.38 s. A staggered enemy can't move or bite.
* **Contact wind-up:** a monster has to stay touching you for 0.26 s before it
  bites, then waits 0.9 s. Each of your swings cancels that wind-up.
* **Armor:** Guardian Knight 20%, Paladin and Berserker 15%, Demolitionist
  and Duelist 10% less damage taken. It is shown on the select screen and in
  the shop.

These numbers are `CONTACT_WINDUP_MS`, `CONTACT_COOLDOWN_MS`,
`MELEE_KNOCKBACK` and `MELEE_STAGGER_MS` in `constants.py`.

## Monsters and their mechanics

| Monster | Behaviour |
|---|---|
| tiny_zombie, goblin | erratic zig-zag swarmers |
| imp | ranged, keeps its distance |
| skelet | **reviver**: collapses into a bone pile and gets back up once (smash the bones!) |
| zombie, big_zombie | **berserk**: get much faster below 50% HP |
| slug → tiny_slug, muddy → mudling | **splitters** |
| chort | **teleporter**: blinks next to you |
| wogol, mimic | **leapers**: crouch (telegraph), then jump at you |
| orc_warrior, ogre | **chargers**: wind up, then rush |
| orc_shaman | **healer**: heals wounded allies (kill it first) |
| masked_orc | **armored**: takes 50% damage unless frozen |
| swampy | leaves slowing goo behind it |
| ice_zombie | frost shots and touch that slow you |
| necromancer | **summoner**: raises skeletons |
| doc | throws flasks that leave poison puddles |
| pumpkin_dude | lobs bombs with a visible fuse circle |
| chest_mimic | some chests (from level 6 on) are mimics |

**Elites:** about 10% of enemies are gold-coloured, bigger and tougher, and
drop double loot.

## Bosses

| Level | Boss | Signature attacks |
|---|---|---|
| 3 | Ogre Chieftain (ogre) | charge, ground slam, goblin calls |
| 5 | Bone Lord (skelet) | bone rings, raises skeletons, spiral |
| 8 | Rotting Colossus (big_zombie) | slam, poison flasks, zombie hordes |
| 10 | Demon Brute (big_demon) | 3 phases: spreads, charges, spirals |
| 13 | Doctor Morbius (doc) | poison barrages, teleport, homing orbs |
| 15 | Archmage Necros (necromancer) | teleport, homing orbs, summons |
| 18 | The Pumpkin King (pumpkin_dude) | bomb barrages, charges |
| 20 | **Seraphiel** (angel) | 3 phases: holy crosses, spirals, homing, *Judgement* strikes |

White marks on the boss health bar show where its phases change.

### Locked ladder (every level)

The exit ladder is locked until the floor is clear: every monster, the boss
and any summons have to die. The HUD shows how many foes are left. Once only
3 remain, they pulse on the minimap and red arrows at the screen edge point
to them. When the floor is clear the ladder unlocks with a sound and appears
on the minimap. Summoners can only raise a limited number of minions, and
those minions die together with their master.

## World

* **Minimap (Dead Cells style):** only the paths you have actually seen are
  drawn. Enemies, the exit and unexplored rooms stay hidden until you find them.
* **Act I – The Undercroft (1–10)** uses the original tiles. **Act II – The
  Hollow Deep (11–20)** uses the 0x72 tiles, with banners, fountains and
  wall decorations.
* **Props:** crates you can break, chests (watch out for mimics) and spike
  traps. Spikes hurt monsters too, so lure them in.
* **Flasks:** red heals, blue resets your ability cooldown, green regenerates,
  and yellow gives a speed boost. Big flasks are stronger.
* **Shop (Grizzle the goblin):** healing, the **Forge**, max HP, damage,
  attack speed, multishot and pierce (ranged heroes), reach (melee heroes),
  boots, magnet, shields, dash and ability cooldowns.
* **Story:** cutscenes play at the start, after every boss, and at the act
  change and the ending. Every hero gets their own last line in the ending.
  `ESC` skips a cutscene.

## Code map

| File | Responsibility |
|---|---|
| `main.py` | `Game` state machine. Also the single facade for damage rules (`hit_enemy`, `damage_player`) |
| `heroes.py` | Hero data: stats, weapon tiers, ability, passive |
| `weapon.py` | Melee, bow, throw and staff weapons; player and enemy projectiles |
| `abilities.py` | One function per hero ability |
| `character.py` | `Player`, `Enemy` (17 behaviours), `Boss` (pattern scheduler) |
| `monsters.py` | **Data:** monsters, bosses, 20 level configs |
| `hazards.py` | Blasts, lobbed bombs and flasks, puddles, spikes, chests, crates |
| `items.py` | Coins and flasks |
| `world.py` | Level loading, collision, line of sight, camera, Act I/II rendering, minimap |
| `lore.py` | Story text and the cutscene player |
| `hero_select.py`, `shop.py`, `ui.py` | Screens, HUD, buttons |
| `assets.py` | Atlas and image loading with caching |
| `sounds.py` | Sound slots, fallbacks, volume, music switching |
| `settings.py` | Saved settings and the settings screen |
| `tools/` | Atlas builder, level generator, headless smoke test |

## Adding things

* **A monster:** add a `MonsterType` to `monsters.MONSTERS` (sprite = atlas
  name, behaviour = one from the table above), then list its key in a level pool.
* **A boss:** add a `BossType` with phases built from the pattern names in
  `character.Boss`, then set it in `_BOSS_AT`.
* **A hero:** add a `Hero` to `heroes.py`. If it needs a new ability, add one
  function to `abilities.py`.

## Credits

Character and tile art: [16x16 DungeonTileset II](https://0x72.itch.io/dungeontileset-ii) by 0x72.
Sound effects and music for Act II onwards: generated with `tools/make_sounds.py`.
