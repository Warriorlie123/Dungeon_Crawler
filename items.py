"""
items.py - collectible pickups: coins and flasks.

Flask colours (0x72 art) and effects:
    red     heal 25   (big: 50)   - at full HP it is stored instead (H to drink)
    blue    ability cooldown reset (big: also 4s haste)
    green   regeneration: 4 HP/s for 5s (big: 10s)
    yellow  haste: +35% speed for 6s (big: 10s)

Coins are pulled toward the player inside the magnet radius, and loot dropped
by enemies "pops" outward so a pile of coins spreads out visibly.
"""
import math
import random
import pygame


class Item(pygame.sprite.Sprite):
    COIN, FLASK = "coin", "flask"

    def __init__(self, x, y, kind, frames, value=1, pop=False, flask=None):
        super().__init__()
        self.kind = kind
        self.flask = flask              # e.g. "red", "big_green"
        self.frames = frames
        self.frame_index = 0
        self.anim_time = 0
        self.image = frames[0]
        self.rect = self.image.get_rect(center=(x, y))
        self.fx, self.fy = float(x), float(y)
        self.value = value
        if pop:
            a = random.uniform(0, math.tau)
            s = random.uniform(2.0, 4.0)
            self.vx, self.vy = math.cos(a) * s, math.sin(a) * s
        else:
            self.vx = self.vy = 0.0
        self.spawn_time = pygame.time.get_ticks()

    def update(self, game, now):
        world, player = game.world, game.player
        if self.vx or self.vy:
            nx, ny = self.fx + self.vx, self.fy + self.vy
            if not world.is_solid_px(nx, ny):
                self.fx, self.fy = nx, ny
            self.vx *= 0.85
            self.vy *= 0.85
            if abs(self.vx) + abs(self.vy) < 0.1:
                self.vx = self.vy = 0.0
        if self.kind == self.COIN and player.alive and now - self.spawn_time > 250:
            dx, dy = player.rect.centerx - self.fx, player.rect.centery - self.fy
            d = math.hypot(dx, dy)
            if d < player.magnet:
                self.fx += dx / (d or 1) * 7.0
                self.fy += dy / (d or 1) * 7.0
        self.rect.center = (round(self.fx), round(self.fy))

        if player.alive and self.rect.colliderect(player.rect):
            if self.kind == self.COIN:
                player.coins += self.value
                player.coins_earned += self.value
                game.assets.play("coin")
                self.kill()
            elif self.kind == self.FLASK:
                if self._drink(game, now):
                    self.kill()

        if len(self.frames) > 1 and now - self.anim_time > 150:
            self.frame_index = (self.frame_index + 1) % len(self.frames)
            self.anim_time = now
            self.image = self.frames[self.frame_index]

    def _drink(self, game, now):
        p = game.player
        big = self.flask.startswith("big_")
        colour = self.flask.replace("big_", "")
        x, y = p.rect.centerx, p.rect.top
        if colour == "red":
            if p.health >= p.max_hp:
                if p.potions < 3:
                    p.potions += 1
                    game.float_text(x, y, "+1 POTION", (255, 120, 120))
                    return True
                return False             # leave it on the floor for later
            amt = 50 if big else 25
            game.heal_player(amt)
        elif colour == "blue":
            p.ability_ready_at = 0
            game.float_text(x, y, "ABILITY READY", (120, 170, 255))
            if big:
                p.add_status("haste", now, 4000)
        elif colour == "green":
            p.add_status("regen", now, 10000 if big else 5000)
            game.float_text(x, y, "REGEN", (120, 230, 120))
        elif colour == "yellow":
            p.add_status("haste", now, 10000 if big else 6000)
            game.float_text(x, y, "HASTE", (255, 230, 90))
        game.assets.play("potion_drink")
        return True

    def draw(self, surface, camera):
        surface.blit(self.image, camera.apply(self.rect))
