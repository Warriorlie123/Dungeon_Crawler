"""
tools/smoke_test.py - headless automated play-test.

Runs the real Game class without a window (SDL "dummy" drivers) and with a
fake clock that advances 16 ms per frame, so minutes of gameplay simulate in
seconds. It checks that:
  * the menu -> hero select -> cutscene -> level flow works,
  * every level 1-20 loads and can be cleared (boss levels unlock the exit),
  * every hero's weapon and ability work without exceptions,
  * shop purchases (incl. the Forge) work, death/restart and pause work,
  * every cutscene can be clicked through.

    python tools/smoke_test.py                 full run
    python tools/smoke_test.py --shots         also save screenshots
"""
import os
import random
import sys
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame

_fake_now = [0]
pygame.time.get_ticks = lambda: _fake_now[0]

import constants  # noqa: E402
import main  # noqa: E402
import lore  # noqa: E402
from heroes import HEROES  # noqa: E402

SHOTS = "--shots" in sys.argv
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screens")
GOD = 10 ** 9


def key_ev(k, t=pygame.KEYDOWN):
    return pygame.event.Event(t, key=k, mod=0, unicode="", scancode=0)


def step(game, events=(), n=1):
    """Advance n frames. Key presses are released on the following frame,
    like a real tap - otherwise keys would stay 'held' forever."""
    releases = []
    for _ in range(n):
        _fake_now[0] += 16
        game.frame(list(events) + releases)
        releases = [key_ev(e.key, pygame.KEYUP) for e in events if e.type == pygame.KEYDOWN]
        events = ()
    if releases:
        _fake_now[0] += 16
        game.frame(releases)


def shot(game, name):
    if SHOTS:
        os.makedirs(OUT, exist_ok=True)
        pygame.image.save(game.screen, os.path.join(OUT, name + ".png"))


def teleport(game, x, y):
    p = game.player
    p.rect.center = (x, y)
    p.fx, p.fy = float(x), float(y)


def skip_cutscene(game, name=None):
    n = 0
    while game.state == "cutscene" and n < 400:
        if name and n == 1:
            step(game, n=40)
            shot(game, name)
        step(game, [key_ev(pygame.K_RETURN)])
        n += 1


def clear_level(game, use_ability=True, max_frames=40000):
    """God-mode bot: teleport near the closest enemy, auto-fire, spam ability."""
    p = game.player
    game.auto_fire = True
    frames = 0
    while [e for e in game.enemies if e.alive] and frames < max_frames:
        target = min((e for e in game.enemies if e.alive), key=lambda e: e.dist_to(p))
        limit = 70 if p.hero.weapon_kind == "melee" else 200
        if target.dist_to(p) > limit or not game.world.line_of_sight(p.rect.center, target.rect.center):
            for _ in range(10):      # never land on the exit ladder by accident
                fx, fy = game.world.random_floor_near(target.rect.centerx, target.rect.centery, 2)
                if not game.world.exit_rect.inflate(60, 60).collidepoint(fx, fy):
                    break
            teleport(game, fx, fy)
        assert game.state == "play", game.state
        p.invuln_until = _fake_now[0] + GOD
        p.health = p.max_hp
        ev = [key_ev(pygame.K_e)] if use_ability and frames % 120 == 0 else []
        # melee heroes need to face the target: also hold the matching arrow key
        step(game, ev, n=10)
        frames += 10
    return frames


def run():
    random.seed(1)
    pygame.init()
    pygame.display.set_mode((constants.SCREEN_WIDTH, constants.SCREEN_HEIGHT))
    game = main.Game(audio=False)

    # ---- menu -> select -> intro ---------------------------------------------------
    step(game, n=3)
    shot(game, "00_menu")
    step(game, [key_ev(pygame.K_RETURN)])
    assert game.state == "select", game.state
    step(game, [key_ev(pygame.K_RIGHT)], n=1)
    step(game, n=30)
    shot(game, "01_select")
    step(game, [key_ev(pygame.K_LEFT)])           # back to knight_f
    step(game, [key_ev(pygame.K_DOWN)])           # knight_m
    step(game, [key_ev(pygame.K_RETURN)])
    assert game.state == "cutscene", game.state
    assert game.hero.key == "knight_m", game.hero.key
    skip_cutscene(game, "02_intro")
    assert game.state == "play", game.state

    # ---- full campaign with knight_m -----------------------------------------------
    for level in range(1, constants.MAX_LEVELS + 1):
        assert game.level == level, (game.level, level)
        n_enemies = len(game.enemies)
        step(game, n=140)
        if level in (1, 11, 14):
            shot(game, f"L{level:02d}_start")
        frames = clear_level(game)
        alive = [e for e in game.enemies if e.alive]
        for e in alive:
            print("SURVIVOR", e.key, e.rect, e.health, e.awake, e.status,
                  game.world.rect_hits_wall(e.rect), game.world.is_solid_px(*e.rect.center),
                  game.world.line_of_sight(game.player.rect.center, e.rect.center),
                  round(e.dist_to(game.player)), game.player.rect.center)
        assert not alive, f"level {level}: {len(alive)} enemies survived ({[e.key for e in alive]})"
        assert not game.exit_locked
        print(f"level {level:2d}: {n_enemies:2d} spawned, kills={game.player.kills:4d}, "
              f"coins={game.player.coins:4d}, frames={frames:5d}, boss={game.boss.name if game.boss else '-'}")
        game.player.invuln_until = 0
        step(game, n=40)
        # stragglers can appear after the sweep (mimic chests, revived bones)
        frames += clear_level(game)
        assert not game.exit_locked, [e.key for e in game.enemies if e.alive]
        from hazards import Chest
        for h in list(game.hazards):     # an unopened mimic next to the ladder would re-lock it
            if isinstance(h, Chest):
                h.kill()
        teleport(game, *game.world.exit_rect.center)
        step(game, n=2)
        if game.state == "cutscene":
            skip_cutscene(game, f"C{level:02d}_scene")
        if level < constants.MAX_LEVELS:
            assert game.state == "shop", (level, game.state)
            game.player.coins += 150
            before = game.player.coins
            if level == 1:
                step(game, n=2)
                shot(game, "S01_shop")
            for k in (pygame.K_2, pygame.K_1, pygame.K_3, pygame.K_r, pygame.K_4, pygame.K_5):
                step(game, [key_ev(k)])
            assert game.player.coins < before, "shop purchase failed"
            step(game, [key_ev(pygame.K_RETURN)])
            skip_cutscene(game)
            assert game.state == "play", (level, game.state)
        else:
            assert game.state == "victory", game.state
            step(game, n=2)
            shot(game, "V_victory")
    print("weapon tier reached:", game.player.weapon_tier, game.player.weapon.sprite_name)

    # ---- every hero: weapon + ability on a busy level ------------------------------
    for hero in HEROES:
        g = main.Game(audio=False, start_level=14)
        g.skip_cutscenes = True
        g.new_game(hero)
        assert g.state == "play"
        g.player.weapon_tier = 1 if hero.weapon_kind != "staff" else 2
        from weapon import make_weapon
        g.player.weapon = make_weapon(hero, g.player.weapon_tier, g.assets)
        step(g, n=120)
        frames = clear_level(g, max_frames=4000)
        left = len([e for e in g.enemies if e.alive])
        # extra ability uses with an enemy close by, to exercise every branch
        print(f"hero {hero.key:10s} cleared L14 in {frames:5d} frames, left={left}, "
              f"kills={g.player.kills}")
        if SHOTS and hero.key in ("dwarf_f", "wizzard_f", "lizard_f", "elf_m"):
            g2 = main.Game(audio=False, start_level=9)
            g2.skip_cutscenes = True
            g2.new_game(hero)
            step(g2, n=140)
            p = g2.player
            tgt = min(g2.enemies, key=lambda e: e.dist_to(p))
            fx, fy = g2.world.random_floor_near(tgt.rect.centerx, tgt.rect.centery, 2)
            teleport(g2, fx, fy)
            p.invuln_until = _fake_now[0] + GOD
            g2.auto_fire = True
            step(g2, n=30)
            step(g2, [key_ev(pygame.K_e)], n=1)
            step(g2, n=12)
            shot(g2, f"H_{hero.key}")

    # ---- boss screenshots ------------------------------------------------------------
    for lv in (3, 8, 13, 15, 18, 20):
        g = main.Game(audio=False, start_level=lv)
        g.skip_cutscenes = True
        g.new_game(HEROES[lv % 10])
        b = g.boss
        for e in g.enemies:
            if not e.is_boss:
                e.alive = False
        step(g, n=2)
        x, y = g.world.random_floor_near(b.rect.centerx - 250, b.rect.centery, 1)
        teleport(g, x, y)
        g.player.invuln_until = _fake_now[0] + GOD
        g.auto_fire = True
        b.health = int(b.max_hp * 0.25)
        step(g, n=200)
        shot(g, f"B{lv:02d}_boss")
        print(f"boss L{lv} {b.name}: hp {b.health}/{b.max_hp}, projectiles {len(g.projectiles)}, "
              f"hazards {len(g.hazards)}, enemies {len(g.enemies)}")

    # ---- every cutscene renders ----------------------------------------------------------
    g = main.Game(audio=False)
    g.hero = HEROES[3]
    for key in lore.SCENES:
        g.play_cutscene([key], lambda: setattr(g, "state", "menu"))
        skip_cutscene(g)

    # ---- death / restart / pause ----------------------------------------------------------
    g = main.Game(audio=False, start_level=2)
    g.skip_cutscenes = True
    g.new_game(HEROES[0])
    g.player.take_damage(10 ** 6, _fake_now[0] + 10 ** 6)
    _fake_now[0] += 10 ** 6
    step(g, n=200)
    assert g.state == "dead"
    shot(g, "X_dead")
    step(g, [key_ev(pygame.K_r)])
    assert g.state == "play" and g.player.alive
    step(g, [key_ev(pygame.K_ESCAPE)])
    assert g.state == "pause"
    # ---- settings screen (from menu and from pause) -------------------------------------
    g = main.Game(audio=True)       # real SoundBank (dummy audio driver)
    step(g, n=2)
    step(g, [key_ev(pygame.K_o)])
    assert g.state == "settings", g.state
    vol = g.settings.music
    step(g, [key_ev(pygame.K_DOWN)])
    step(g, [key_ev(pygame.K_LEFT)])
    assert g.settings.music < vol, "music slider did not move"
    step(g, n=2)
    shot(g, "Z_settings")
    step(g, [key_ev(pygame.K_ESCAPE)])
    assert g.state == "menu"
    g.settings.music = vol
    g.settings.save()
    g.skip_cutscenes = True
    g.new_game(HEROES[7])
    step(g, n=30)
    step(g, [key_ev(pygame.K_e)])          # ability sound path
    step(g, [key_ev(pygame.K_ESCAPE)])
    step(g, [key_ev(pygame.K_o)])
    assert g.state == "settings"
    step(g, [key_ev(pygame.K_ESCAPE)])
    assert g.state == "pause"
    print("sounds loaded:", len(g.sounds.sounds), "missing slots:", len(g.sounds.missing()))
    print("ALL SMOKE TESTS PASSED")


if __name__ == "__main__":
    run()
