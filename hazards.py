"""
hazards.py - things on the floor that are neither actors nor pickups.

    Blast        telegraphed circular explosion (bombs, meteors, slams)
    Lob          a projectile thrown in an arc; calls on_land() when it lands
    Puddle       lingering area: poison (damage over time) or goo (slows)
    SpikeTrap    periodic floor spikes - hurt the player AND enemies
    Chest        opens on touch: loot... or a Mimic!
    Crate        breakable by attacks, may contain gold
    Ring         purely visual expanding circle (shockwaves, novas)

Every hazard implements update(game, now) and draw(surface, camera, now).
They receive the Game object because their effects cross systems (damage the
player, spawn items, spawn enemies). Keeping that coupling in ONE well-known
place is simpler than threading a dozen callbacks through every class.
"""
import math
import random
import pygame
import constants


def _circle_alpha(surface, colour, center, radius, alpha, width=0):
    r = max(1, int(radius))
    s = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
    pygame.draw.circle(s, colour + (alpha,), (r + 1, r + 1), r, width)
    surface.blit(s, (center[0] - r - 1, center[1] - r - 1))


class Hazard(pygame.sprite.Sprite):
    layer = 0           # 0 = drawn under actors, 1 = above

    def update(self, game, now):
        pass

    def draw(self, surface, camera, now):
        pass


class Ring(Hazard):
    layer = 1

    def __init__(self, x, y, radius, colour=(255, 255, 255), ms=300, now=0):
        super().__init__()
        self.x, self.y, self.radius, self.colour = x, y, radius, colour
        self.start, self.ms = now, ms

    def update(self, game, now):
        if now - self.start > self.ms:
            self.kill()

    def draw(self, surface, camera, now):
        t = min(1.0, (now - self.start) / self.ms)
        ox, oy = camera.offset
        _circle_alpha(surface, self.colour, (self.x - ox, self.y - oy), self.radius * (0.3 + 0.7 * t),
                      int(220 * (1 - t)), 4)


class Blast(Hazard):
    """
    Telegraph -> explosion. owner="enemy" hurts the player (and spikes the
    camera), owner="player" hurts enemies via game.hit_enemy so crits,
    armour etc. are applied consistently.
    """
    def __init__(self, x, y, radius, delay_ms, damage, owner="enemy", colour=(255, 120, 40), now=0,
                 effect=None):
        super().__init__()
        self.x, self.y, self.radius = x, y, radius
        self.detonate_at = now + delay_ms
        self.start = now
        self.damage, self.owner, self.colour, self.effect = damage, owner, colour, effect
        self.done = False

    def update(self, game, now):
        if now < self.detonate_at:
            return
        if not self.done and self.damage <= 0:
            self.done = True                 # pure telegraph (e.g. bomb fuse marker)
        if not self.done:
            self.done = True
            game.camera.shake(6 if self.owner == "enemy" else 4, 180)
            game.assets.play("explosion")
            game.hazards.add(Ring(self.x, self.y, self.radius, self.colour, 280, now))
            if self.owner == "enemy":
                p = game.player
                if math.hypot(p.rect.centerx - self.x, p.rect.centery - self.y) < self.radius + 16:
                    game.damage_player(self.damage, now, effect=self.effect)
            else:
                for e in list(game.enemies):
                    if e.alive and math.hypot(e.rect.centerx - self.x, e.rect.centery - self.y) \
                            < self.radius + e.rect.width / 2:
                        dx, dy = e.rect.centerx - self.x, e.rect.centery - self.y
                        d = math.hypot(dx, dy) or 1
                        game.hit_enemy(e, self.damage, now, push=(dx / d, dy / d), aoe=True)
                for c in list(game.breakables()):
                    if math.hypot(c.rect.centerx - self.x, c.rect.centery - self.y) < self.radius + 20:
                        c.smash(game, now)
        if now > self.detonate_at + 60:
            self.kill()

    def draw(self, surface, camera, now):
        ox, oy = camera.offset
        c = (self.x - ox, self.y - oy)
        if now < self.detonate_at:
            t = (now - self.start) / max(1, self.detonate_at - self.start)
            _circle_alpha(surface, self.colour, c, self.radius, 50 + int(40 * t))
            _circle_alpha(surface, self.colour, c, self.radius * t, 90)
            _circle_alpha(surface, self.colour, c, self.radius, 200, 2)
        else:
            _circle_alpha(surface, (255, 240, 200), c, self.radius, 180)


class Lob(Hazard):
    """A thrown object following a parabola from src to dst."""
    layer = 1

    def __init__(self, frames, src, dst, flight_ms, on_land, now=0, fuse_ms=0):
        super().__init__()
        self.frames = frames
        self.src, self.dst = src, dst
        self.start, self.flight = now, flight_ms
        self.on_land = on_land
        self.fuse_ms = fuse_ms
        self.landed_at = None
        self.pos = src

    def update(self, game, now):
        t = (now - self.start) / self.flight
        if t < 1:
            x = self.src[0] + (self.dst[0] - self.src[0]) * t
            y = self.src[1] + (self.dst[1] - self.src[1]) * t - math.sin(math.pi * t) * 70
            self.pos = (x, y)
            return
        self.pos = self.dst
        if self.landed_at is None:
            self.landed_at = now
        if now - self.landed_at >= self.fuse_ms:
            self.on_land(game, self.dst, now)
            self.kill()

    def draw(self, surface, camera, now):
        ox, oy = camera.offset
        img = self.frames[(now // 120) % len(self.frames)]
        if self.landed_at is None:   # shadow on the ground while airborne
            _circle_alpha(surface, (0, 0, 0), (self.dst[0] - ox, self.dst[1] - oy), 12, 70)
        surface.blit(img, (self.pos[0] - ox - img.get_width() // 2, self.pos[1] - oy - img.get_height() // 2))


class Puddle(Hazard):
    KINDS = {"poison": (90, 220, 80), "goo": (120, 150, 60), "fire": (255, 120, 40)}

    def __init__(self, x, y, radius, kind, ms, damage=0, now=0):
        super().__init__()
        self.x, self.y, self.radius, self.kind = x, y, radius, kind
        self.until, self.damage = now + ms, damage
        self.next_tick = now
        self.colour = self.KINDS[kind]

    def update(self, game, now):
        if now > self.until:
            self.kill()
            return
        p = game.player
        if math.hypot(p.rect.centerx - self.x, p.rect.centery - self.y) < self.radius:
            if self.kind == "goo":
                p.add_status("slow", now, 400)
            elif now >= self.next_tick:
                self.next_tick = now + 500
                game.damage_player(self.damage, now, bypass_iframes=True)

    def draw(self, surface, camera, now):
        ox, oy = camera.offset
        fade = max(0.0, min(1.0, (self.until - now) / 600))
        _circle_alpha(surface, self.colour, (self.x - ox, self.y - oy), self.radius, int(110 * fade))


class SpikeTrap(Hazard):
    """
    State machine on a fixed cycle (offset per trap so they don't all sync):
        0..1400 ms  down     (frame 0)
        1400..1550  rising   (frames 1-2, telegraph)
        1550..2150  UP       (frame 3, damages)
        2150..2400  retract
    """
    CYCLE = 2400

    def __init__(self, x, y, frames, offset):
        super().__init__()
        self.rect = pygame.Rect(0, 0, constants.TILE_SIZE - 8, constants.TILE_SIZE - 8)
        self.rect.center = (x, y)
        self.frames, self.offset = frames, offset

    def phase(self, now):
        return (now + self.offset) % self.CYCLE

    def is_up(self, now):
        return 1550 <= self.phase(now) < 2150

    def update(self, game, now):
        up = self.is_up(now)
        if up and not getattr(self, "was_up", False):
            p = game.player.rect
            if abs(p.centerx - self.rect.centerx) + abs(p.centery - self.rect.centery) < 300:
                game.assets.play("spikes")
        self.was_up = up
        if not up:
            return
        if game.player.rect.colliderect(self.rect):
            game.damage_player(int(8 * game.level_cfg.get("dmg_mult", 1)), now)
        for e in game.enemies:
            if e.alive and not e.is_boss and e.rect.colliderect(self.rect) and now >= getattr(e, "spike_cd", 0):
                e.spike_cd = now + 600
                game.hit_enemy(e, 15, now, aoe=True)

    def draw(self, surface, camera, now):
        ph = self.phase(now)
        idx = 0 if ph < 1400 else 1 if ph < 1475 else 2 if ph < 1550 else 3 if ph < 2150 else 1
        img = self.frames[idx]
        r = camera.apply(self.rect)
        surface.blit(img, img.get_rect(center=r.center))


class Chest(Hazard):
    def __init__(self, x, y, assets, mimic=False):
        super().__init__()
        self.assets = assets
        self.mimic = mimic
        self.frames = assets.chest["mimic" if mimic else "full"]
        self.rect = self.frames[0].get_rect(center=(x, y))
        self.opened_at = None

    def update(self, game, now):
        if self.opened_at is None:
            if game.player.alive and self.rect.inflate(30, 30).colliderect(game.player.rect):
                self.opened_at = now
                if self.mimic:
                    game.assets.play("mimic")
                    game.spawn_enemy("mimic", self.rect.centerx, self.rect.centery, awake=True)
                    game.say_banner("MIMIC!", "That chest has teeth.", now, 1200)
                    self.kill()
                    return
                game.assets.play("chest_open")
                n = random.randint(4, 8) + (4 if game.player.hero.flags.get("looter") else 0)
                game.drop_coins(self.rect.centerx, self.rect.centery, n)
                game.drop_flask(self.rect.centerx, self.rect.centery, force=True)
        elif now - self.opened_at > 6000:
            self.kill()

    def draw(self, surface, camera, now):
        if self.opened_at is None:
            img = self.frames[0]
        else:
            img = self.assets.chest["empty"][min(2, (now - self.opened_at) // 120)]
        surface.blit(img, camera.apply(self.rect))


class Crate(Hazard):
    def __init__(self, x, y, assets):
        super().__init__()
        self.img = assets.crate
        self.rect = self.img.get_rect(center=(x, y))
        self.rect.height = 40
        self.rect.centery = y

    def smash(self, game, now):
        if not self.alive():
            return
        game.hazards.add(Ring(self.rect.centerx, self.rect.centery, 30, (180, 130, 80), 200, now))
        game.assets.play("crate_break")
        bonus = 2 if game.player.hero.flags.get("looter") else 0
        if random.random() < 0.5:
            game.drop_coins(self.rect.centerx, self.rect.centery, random.randint(1, 3) + bonus)
        if random.random() < 0.12:
            game.drop_flask(self.rect.centerx, self.rect.centery)
        self.kill()

    def update(self, game, now):
        p = game.player
        if p.dashing and p.rect.colliderect(self.rect):
            self.smash(game, now)

    def draw(self, surface, camera, now):
        r = camera.apply(self.rect)
        surface.blit(self.img, (r.centerx - self.img.get_width() // 2, r.bottom - self.img.get_height()))
