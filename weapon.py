"""
weapon.py - player weapons and every kind of projectile.

Player weapons share one interface (Strategy pattern):

    weapon.update(game, aim_angle, fire, now)   # may attack
    weapon.draw(surface, camera, now)

and are created by make_weapon(hero, tier, assets). The four KINDS:

    MeleeWeapon   swing arc: instantly hits every enemy inside a cone
                  (reach x arc) - simple, reliable, no "missed because the
                  sprite moved 2 px" frustration.
    BowWeapon     fires PlayerShot arrows (multishot / pierce upgrades)
    ThrowWeapon   knives or a returning throwing axe (boomerang)
    StaffWeapon   magic bolts: pyro (explodes) or frost (slows, pierces)

Aiming is decoupled from input (see main.InputState / Game.resolve_aim):
weapons receive an angle in degrees (0 = right, counter-clockwise +).

Sprite orientation: every 0x72 weapon sprite points UP (blade at the top).
Rotating by (angle - 90) therefore points it along `angle`.
"""
import math
import pygame
import constants
from heroes import STAFF_EMPOWER, ATTACK_SOUND


def _vec(angle_deg):
    a = math.radians(angle_deg)
    return math.cos(a), -math.sin(a)          # screen y grows downwards


def angle_diff(a, b):
    """Smallest absolute difference between two angles in degrees."""
    return abs((a - b + 180) % 360 - 180)


# ==========================================================================
# Player weapons
# ==========================================================================
class BaseWeapon:
    def __init__(self, hero, tier, assets):
        self.hero, self.tier, self.assets = hero, tier, assets
        idx = min(tier, len(hero.tiers) - 1)
        self.sprite_name, self.base_damage, self.cooldown, self.extra = hero.tiers[idx]
        self.empower = STAFF_EMPOWER[tier] if hero.weapon_kind == "staff" else 1.0
        self.image = assets.weapon(self.sprite_name, constants.SCALE * 0.9)
        self.angle = 0.0
        self.last_attack = -10_000

    def ready(self, game, now):
        mult = game.player.fire_rate_mult
        if game.player.has_status("focus", now):
            mult *= 0.5
        return now - self.last_attack >= self.cooldown * mult

    def damage_for_sheet(self, player):
        """Same as damage() but without needing the Game (shop character sheet)."""
        return self.base_damage * self.empower * player.damage_mult

    def damage(self, game):
        # Shop "Sharp" upgrades scale every weapon through player.damage_mult.
        return self.base_damage * self.empower * game.player.damage_mult

    def update(self, game, aim, fire, now):
        if aim is not None:
            self.angle = aim
        if fire and game.player.alive and self.ready(game, now):
            self.last_attack = now
            self.attack(game, now)
            return True
        return False

    def attack(self, game, now):
        raise NotImplementedError

    def draw(self, surface, camera, now, player):
        img = pygame.transform.rotate(self.image, self.angle - 90)
        vx, vy = _vec(self.angle)
        r = camera.apply(player.rect)
        cx = r.centerx + vx * 22
        cy = r.centery + 6 + vy * 22
        surface.blit(img, (cx - img.get_width() // 2, cy - img.get_height() // 2))


class MeleeWeapon(BaseWeapon):
    SWING_MS = 170

    def __init__(self, hero, tier, assets):
        super().__init__(hero, tier, assets)
        self.reach = self.extra["reach"]
        self.arc = self.extra["arc"]
        self.swing_start = -10_000
        self.swing_from = 0

    def attack(self, game, now):
        p = game.player
        reach = self.reach * p.reach_mult
        arc = self.arc * p.reach_mult
        self.swing_start = now
        self.swing_from = self.angle + arc / 2
        hit_any = False
        for e in list(game.enemies):
            if not e.alive:
                continue
            dx, dy = e.rect.centerx - p.rect.centerx, e.rect.centery - p.rect.centery
            dist = math.hypot(dx, dy)
            if dist > reach + e.rect.width / 2:
                continue
            ang = math.degrees(math.atan2(-dy, dx))
            # very close enemies are always hit (they are "inside" the arc)
            if dist < 30 or angle_diff(ang, self.angle) <= arc / 2:
                d = dist or 1
                k = constants.MELEE_KNOCKBACK
                game.hit_enemy(e, self.damage(game), now, push=(dx / d * k, dy / d * k),
                               stagger_ms=constants.MELEE_STAGGER_MS)
                hit_any = True
        for c in list(game.breakables()):
            dx, dy = c.rect.centerx - p.rect.centerx, c.rect.centery - p.rect.centery
            if math.hypot(dx, dy) < reach + 20 and angle_diff(math.degrees(math.atan2(-dy, dx)), self.angle) <= arc / 2:
                c.smash(game, now)
        # Parry passive / Whirlwind: destroy enemy projectiles in the arc
        if p.hero.flags.get("parry"):
            for proj in list(game.projectiles):
                dx, dy = proj.fx - p.rect.centerx, proj.fy - p.rect.centery
                if math.hypot(dx, dy) < reach and angle_diff(math.degrees(math.atan2(-dy, dx)), self.angle) <= arc / 2:
                    proj.kill()
        game.assets.play(ATTACK_SOUND.get(p.hero.key, "melee_whoosh"))
        if hit_any:
            game.assets.play("melee_hit")

    def draw(self, surface, camera, now, player):
        t = (now - self.swing_start) / self.SWING_MS
        if 0 <= t <= 1:
            # sweep from one edge of the arc to the other, with a trail
            arc = self.arc * player.reach_mult
            reach = self.reach * player.reach_mult
            a = self.swing_from - arc * t
            r = camera.apply(player.rect)
            trail = pygame.Surface((reach * 2 + 4, reach * 2 + 4), pygame.SRCALPHA)
            pts = [(reach + 2, reach + 2)]
            steps = 8
            for i in range(steps + 1):
                aa = math.radians(self.swing_from - arc * t * i / steps)
                pts.append((reach + 2 + math.cos(aa) * reach, reach + 2 - math.sin(aa) * reach))
            if len(pts) > 2:
                pygame.draw.polygon(trail, (255, 255, 255, 55), pts)
            surface.blit(trail, (r.centerx - reach - 2, r.centery + 6 - reach - 2))
            img = pygame.transform.rotate(self.image, a - 90)
            vx, vy = _vec(a)
            cx, cy = r.centerx + vx * reach * 0.55, r.centery + 6 + vy * reach * 0.55
            surface.blit(img, (cx - img.get_width() // 2, cy - img.get_height() // 2))
        else:
            super().draw(surface, camera, now, player)


class BowWeapon(BaseWeapon):
    def attack(self, game, now):
        p = game.player
        n = p.multishot
        focus = p.has_status("focus", now)
        for i in range(n):
            a = self.angle + (i - (n - 1) / 2) * 9
            game.player_shots.add(PlayerShot(self.assets.projectiles["arrow"], p.rect.centerx, p.rect.centery,
                                             a, self.extra["speed"], self.damage(game),
                                             pierce=p.pierce + (2 if focus else 0)))
        game.assets.play(ATTACK_SOUND.get(p.hero.key, "shot"))

    def draw(self, surface, camera, now, player):
        # The 0x72 bow sprite faces right with the string on the left, so
        # rotate by the plain angle (not angle-90 like blades).
        img = pygame.transform.rotate(self.image, self.angle)
        vx, vy = _vec(self.angle)
        r = camera.apply(player.rect)
        surface.blit(img, (r.centerx + vx * 18 - img.get_width() // 2,
                           r.centery + 6 + vy * 18 - img.get_height() // 2))


class ThrowWeapon(BaseWeapon):
    def attack(self, game, now):
        p = game.player
        ex = self.extra
        n = p.multishot
        for i in range(n):
            a = self.angle + (i - (n - 1) / 2) * 8
            game.player_shots.add(PlayerShot(self.assets.projectiles[ex["projectile"]], p.rect.centerx,
                                             p.rect.centery, a, ex["speed"], self.damage(game),
                                             pierce=ex["pierce"] + p.pierce, max_range=ex["range"],
                                             returning=ex["returning"], spin=ex["returning"], owner=p))
        game.assets.play(ATTACK_SOUND.get(p.hero.key, "shot"))


class StaffWeapon(BaseWeapon):
    def attack(self, game, now):
        p = game.player
        ex = self.extra
        n = p.multishot
        explode = ex["explode"] * (1 + p.hero.flags.get("aoe_bonus", 0)) if ex["explode"] else 0
        for i in range(n):
            a = self.angle + (i - (n - 1) / 2) * 10
            game.player_shots.add(PlayerShot(self.assets.projectiles[ex["projectile"]], p.rect.centerx,
                                             p.rect.centery, a, ex["speed"], self.damage(game),
                                             pierce=p.pierce + (1 if ex["slow"] else 0),
                                             explode=explode, slow_ms=ex["slow"]))
        game.assets.play(ATTACK_SOUND.get(p.hero.key, "shot"))


def make_weapon(hero, tier, assets):
    cls = {"melee": MeleeWeapon, "bow": BowWeapon, "throw": ThrowWeapon, "staff": StaffWeapon}[hero.weapon_kind]
    return cls(hero, tier, assets)


# ==========================================================================
# Projectiles
# ==========================================================================
class PlayerShot(pygame.sprite.Sprite):
    """
    Generic player projectile. Options cover every hero:
        pierce      extra enemies passed through
        explode     radius of an AoE blast on impact (pyromancer)
        slow_ms     slow applied on hit (cryomancer)
        returning   flies out to max_range then homes back to `owner`
        spin        rotate sprite while flying (axes)
    """
    def __init__(self, image, x, y, angle, speed, damage, pierce=0, max_range=constants.ARROW_MAX_RANGE,
                 explode=0, slow_ms=0, returning=False, spin=False, owner=None, reflected=False):
        super().__init__()
        self.base_image = image
        self.angle = angle
        self.image = pygame.transform.rotate(image, angle - 90)
        self.rect = self.image.get_rect(center=(x, y))
        self.fx, self.fy = float(x), float(y)
        vx, vy = _vec(angle)
        self.dx, self.dy = vx * speed, vy * speed
        self.speed = speed
        self.damage = damage
        self.pierce_left = pierce
        self.max_range = max_range
        self.explode, self.slow_ms = explode, slow_ms
        self.returning, self.spin, self.owner = returning, spin, owner
        self.coming_back = False
        self.travelled = 0.0
        self.already_hit = set()
        self.reflected = reflected

    def update(self, game, now):
        if self.coming_back and self.owner:
            tx, ty = self.owner.rect.centerx - self.fx, self.owner.rect.centery - self.fy
            d = math.hypot(tx, ty)
            if d < 30:
                self.kill()
                return
            self.dx, self.dy = tx / d * self.speed * 1.2, ty / d * self.speed * 1.2
        self.fx += self.dx
        self.fy += self.dy
        self.travelled += self.speed
        self.rect.center = (round(self.fx), round(self.fy))

        if game.world.is_solid_px(self.fx, self.fy) and not self.coming_back:
            if self.returning:
                self.coming_back = True
                self.already_hit.clear()
            else:
                self._impact(game, now)
                return
        if self.travelled > self.max_range:
            if self.returning and not self.coming_back:
                self.coming_back = True
                self.already_hit.clear()
            elif not self.returning:
                self.kill()
                return
        if self.travelled > self.max_range * 3:          # safety net
            self.kill()
            return

        for enemy in game.enemies:
            if not enemy.alive or id(enemy) in self.already_hit:
                continue
            if enemy.rect.colliderect(self.rect):
                sp = math.hypot(self.dx, self.dy) or 1
                if self.explode:
                    self._impact(game, now)
                    return
                game.hit_enemy(enemy, self.damage, now, push=(self.dx / sp, self.dy / sp),
                               slow_ms=self.slow_ms)
                self.already_hit.add(id(enemy))
                if self.pierce_left > 0:
                    self.pierce_left -= 1
                elif not self.returning:
                    self.kill()
                    return
        for c in list(game.breakables()):
            if c.rect.colliderect(self.rect):
                c.smash(game, now)

    def _impact(self, game, now):
        if self.explode:
            from hazards import Blast
            game.hazards.add(Blast(self.fx, self.fy, self.explode, 0, self.damage, owner="player",
                                   colour=(255, 140, 40), now=now))
        self.kill()

    def draw(self, surface, camera):
        img = self.image
        if self.spin:
            img = pygame.transform.rotate(self.base_image, (pygame.time.get_ticks() * 0.9) % 360)
        r = camera.apply(self.rect)
        surface.blit(img, (r.centerx - img.get_width() // 2, r.centery - img.get_height() // 2))


class Projectile(pygame.sprite.Sprite):
    """
    Enemy projectile. `effect` in {None, "slow", "poison"}; `homing` > 0
    makes it steer towards the player (radians per frame).
    """
    def __init__(self, image, x, y, vx, vy, damage, effect=None, homing=0.0, life=240):
        super().__init__()
        self.base_image = image
        self.image = pygame.transform.rotate(image, math.degrees(math.atan2(-vy, vx)) - 90)
        self.rect = self.image.get_rect(center=(x, y))
        self.hitbox = pygame.Rect(0, 0, 16, 16)
        self.fx, self.fy = float(x), float(y)
        self.vx, self.vy = vx, vy
        self.damage = damage
        self.effect, self.homing = effect, homing
        self.life, self.max_life = 0, life

    def update(self, game, now):
        p = game.player
        if self.homing and p.alive:
            want = math.atan2(p.rect.centery - self.fy, p.rect.centerx - self.fx)
            cur = math.atan2(self.vy, self.vx)
            diff = (want - cur + math.pi) % math.tau - math.pi
            cur += max(-self.homing, min(self.homing, diff))
            sp = math.hypot(self.vx, self.vy)
            self.vx, self.vy = math.cos(cur) * sp, math.sin(cur) * sp
            self.image = pygame.transform.rotate(self.base_image, math.degrees(-cur) - 90)
        self.fx += self.vx
        self.fy += self.vy
        self.life += 1
        self.rect.center = self.hitbox.center = (round(self.fx), round(self.fy))
        if self.life > self.max_life or game.world.is_solid_px(self.fx, self.fy):
            self.kill()
            return
        if p.alive and self.hitbox.colliderect(p.rect):
            if p.has_status("bulwark", now):
                # Reflect: turn into a player shot flying back
                ang = math.degrees(math.atan2(self.vy, -self.vx))
                game.player_shots.add(PlayerShot(self.base_image, self.fx, self.fy, ang,
                                                 math.hypot(self.vx, self.vy) * 1.3, self.damage * 2,
                                                 reflected=True))
                self.kill()
                return
            game.damage_player(self.damage, now, effect=self.effect)
            self.kill()

    def draw(self, surface, camera):
        r = camera.apply(self.rect)
        surface.blit(self.image, (r.centerx - self.image.get_width() // 2,
                                  r.centery - self.image.get_height() // 2))
