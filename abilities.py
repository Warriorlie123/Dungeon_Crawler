"""
abilities.py - one function per hero ability (E key / right click).

Dispatch table pattern: ABILITIES[key](game, now) -> bool (True = used).
Returning False (e.g. no valid target) means the cooldown is NOT consumed.

Most abilities are expressed with the shared building blocks:
    player status effects  (bulwark, focus, venom, invisible, whirlwind)
    hazards.Blast          (telegraphed AoE)
    hazards.Ring           (visual shockwave)
    weapon.PlayerShot      (projectiles)
so each ability is only a handful of lines.
"""
import math
from hazards import Blast, Ring, Lob
from weapon import PlayerShot


def bulwark(game, now):
    game.player.add_status("bulwark", now, 4000)
    game.hazards.add(Ring(*game.player.rect.center, 70, (120, 200, 255), 400, now))
    return True


def consecration(game, now):
    p = game.player
    r = 170
    game.hazards.add(Ring(*p.rect.center, r, (255, 240, 150), 450, now))
    for e in list(game.enemies):
        if not e.alive:
            continue
        dx, dy = e.rect.centerx - p.rect.centerx, e.rect.centery - p.rect.centery
        d = math.hypot(dx, dy)
        if d < r + e.rect.width / 2:
            game.hit_enemy(e, 40 * p.weapon.empower * p.damage_mult, now,
                           push=(dx / (d or 1) * 3, dy / (d or 1) * 3), aoe=True)
    game.heal_player(20)
    return True


def whirlwind(game, now):
    game.player.add_status("whirlwind", now, 3000)
    return True


def whirlwind_tick(game, now):
    """Called every frame by Game while the whirlwind status is active."""
    p = game.player
    if now < getattr(p, "whirl_next", 0):
        return
    p.whirl_next = now + 200
    r = 95 * p.reach_mult
    game.hazards.add(Ring(*p.rect.center, r, (255, 200, 160), 200, now))
    for e in list(game.enemies):
        if e.alive:
            dx, dy = e.rect.centerx - p.rect.centerx, e.rect.centery - p.rect.centery
            d = math.hypot(dx, dy)
            if d < r + e.rect.width / 2:
                game.hit_enemy(e, p.weapon.damage(game) * 0.6, now, push=(dx / (d or 1) * 2, dy / (d or 1) * 2),
                               stagger_ms=250)
    for proj in list(game.projectiles):
        if math.hypot(proj.fx - p.rect.centerx, proj.fy - p.rect.centery) < r:
            proj.kill()


def powder_keg(game, now):
    p = game.player
    vx, vy = math.cos(math.radians(p.aim_angle)), -math.sin(math.radians(p.aim_angle))
    dist = 230
    tx, ty = p.rect.centerx + vx * dist, p.rect.centery + vy * dist
    # stop at walls: walk back until the target is on the floor
    for _ in range(20):
        if not game.world.is_solid_px(tx, ty):
            break
        tx -= vx * 12
        ty -= vy * 12
    radius = 130 * (1 + p.hero.flags.get("aoe_bonus", 0))
    dmg = 75 * p.weapon.empower * p.damage_mult

    def land(g, pos, t):
        g.hazards.add(Blast(pos[0], pos[1], radius, 0, dmg, owner="player", now=t))
    game.hazards.add(Lob(game.assets.bomb, p.rect.center, (tx, ty), 450, land, now, fuse_ms=500))
    return True


def arrow_rain(game, now):
    p = game.player
    img = game.assets.projectiles["arrow"]
    dmg = p.weapon.damage(game)
    for i in range(24):
        game.player_shots.add(PlayerShot(img, p.rect.centerx, p.rect.centery, i * 15, 11, dmg,
                                         pierce=1 + p.pierce))
    return True


def focus(game, now):
    game.player.add_status("focus", now, 5000)
    return True


def smoke_step(game, now):
    p = game.player
    vx, vy = p.last_move_dir
    for _ in range(20):        # blink up to 200 px, stopping at walls
        nx, ny = p.fx + vx * 10, p.fy + vy * 10
        test = p.rect.copy()
        test.center = (round(nx), round(ny))
        if game.world.rect_hits_wall(test):
            break
        p.fx, p.fy = nx, ny
        p.rect.center = test.center
    game.hazards.add(Ring(*p.rect.center, 60, (160, 160, 160), 300, now))
    p.add_status("invisible", now, 3000)
    p.guaranteed_crit = True
    for e in game.enemies:       # enemies lose track of you
        e.last_seen = None
        if not e.is_boss:
            e.awake = False
    return True


def venom(game, now):
    game.player.add_status("venom", now, 6000)
    return True


def meteor(game, now):
    p = game.player
    target = game.nearest_visible_enemy(700)
    if target:
        tx, ty = target.rect.center
    else:
        vx, vy = math.cos(math.radians(p.aim_angle)), -math.sin(math.radians(p.aim_angle))
        tx, ty = p.rect.centerx + vx * 250, p.rect.centery + vy * 250
    radius = 150 * (1 + p.hero.flags.get("aoe_bonus", 0))
    game.hazards.add(Blast(tx, ty, radius, 850, 130 * p.weapon.empower * p.damage_mult,
                           owner="player", colour=(255, 90, 30), now=now))
    return True


def frost_nova(game, now):
    p = game.player
    r = 230
    game.hazards.add(Ring(*p.rect.center, r, (150, 230, 255), 500, now))
    for e in list(game.enemies):
        if e.alive and math.hypot(e.rect.centerx - p.rect.centerx, e.rect.centery - p.rect.centery) < r:
            e.add_status("frozen", now, 1500 if e.is_boss else 2500)
            game.assets.play("freeze")
            game.hit_enemy(e, 25 * p.weapon.empower * p.damage_mult, now, aoe=True)
    return True


ABILITIES = {
    "bulwark": bulwark, "consecration": consecration, "whirlwind": whirlwind,
    "powder_keg": powder_keg, "arrow_rain": arrow_rain, "focus": focus,
    "smoke_step": smoke_step, "venom": venom, "meteor": meteor, "frost_nova": frost_nova,
}
