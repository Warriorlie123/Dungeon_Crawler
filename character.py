"""
character.py - the player, regular enemies and bosses.

Class hierarchy
---------------
    Actor           float position, hitbox, animation, drawing, status effects
      Player        hero-driven stats, dash, ability cooldown, i-frames
      Enemy         data-driven AI; behaviour chosen by MonsterType.behaviour
        Boss        phase-based attack-pattern scheduler

Design notes
------------
* WORLD coordinates everywhere; only draw() knows about the camera.
* Hitbox (self.rect) is decoupled from the sprite. Sprites are drawn anchored
  at the hitbox's bottom-centre ("feet") so any sprite size looks right.
* Status effects are a dict  name -> expiry_ms. A uniform mechanism for
  slow / poison / frozen / invisible / bulwark / ... instead of a boolean
  flag per effect. add_status() refreshes duration, has_status() tests.
* Enemies never touch sprite groups directly; they talk to the `game`
  object (spawn_enemy, enemy_projectile, add_hazard...). That one facade is
  easy to fake in tests.
"""
import math
import random
import pygame
import constants
from weapon import Projectile


class Actor:
    def __init__(self, x, y, animations, hitbox, hp):
        self.animations = animations          # [idle, run, hit]
        self.rect = pygame.Rect(0, 0, hitbox, hitbox)
        self.rect.center = (x, y)
        self.fx, self.fy = float(x), float(y)
        self.max_hp = hp
        self.health = hp
        self.alive = True
        self.flip = False
        self.action = 0                       # 0 idle, 1 run
        self.frame_index = 0
        self.anim_time = 0
        self.running = False
        self.flash_until = 0
        self.anim_speed_ms = 90
        self.status = {}                      # name -> expiry (ms)
        self.status_data = {}

    # ----------------------------------------------------------- status
    def add_status(self, name, now, ms, **data):
        self.status[name] = max(self.status.get(name, 0), now + ms)
        if data:
            self.status_data[name] = data

    def has_status(self, name, now):
        return self.status.get(name, 0) > now

    # ------------------------------------------------------------- anim
    def animate(self, now):
        action = 1 if self.running else 0
        if action != self.action:
            self.action = action
            self.frame_index = 0
            self.anim_time = now
        frames = self.animations[self.action]
        if now - self.anim_time > self.anim_speed_ms:
            self.frame_index = (self.frame_index + 1) % len(frames)
            self.anim_time = now
        self.frame_index %= len(frames)

    @property
    def image(self):
        return self.animations[self.action][self.frame_index]

    def sprite_for_draw(self, now):
        img = pygame.transform.flip(self.image, self.flip, False)
        if now < self.flash_until:
            img = img.copy()
            img.fill((180, 180, 180, 0), special_flags=pygame.BLEND_RGBA_ADD)
        return img

    def draw(self, surface, camera, now):
        img = self.sprite_for_draw(now)
        r = camera.apply(self.rect)
        surface.blit(img, (r.centerx - img.get_width() // 2, r.bottom - img.get_height() + 4))

    def dist_to(self, other):
        return math.hypot(self.rect.centerx - other.rect.centerx,
                          self.rect.centery - other.rect.centery)


# ==========================================================================
# Player
# ==========================================================================
class Player(Actor):
    def __init__(self, x, y, hero, assets):
        super().__init__(x, y, assets.animation(hero.key), constants.PLAYER_HITBOX, hero.hp)
        self.hero = hero
        # ---- persistent stats (shop) -------------------------------------
        self.coins = 0
        self.speed_mult = 1.0 + hero.flags.get("speed_bonus", 0)
        self.damage_mult = 1.0
        self.fire_rate_mult = 1.0
        self.multishot = 1
        self.pierce = 0
        self.reach_mult = 1.0
        self.magnet = 40
        self.shields = 0
        self.dash_cd_mult = 1.0
        self.ability_cd_mult = hero.flags.get("cd_mult", 1.0)
        self.potions = 0
        self.crit_chance = constants.CRIT_CHANCE + hero.flags.get("crit_bonus", 0)
        self.weapon_tier = 0
        # ---- transient --------------------------------------------------------
        self.invuln_until = 0
        self.dash_until = 0
        self.dash_ready_at = 0
        self.dash_dir = (0, 0)
        self.last_move_dir = (1, 0)
        self.ability_ready_at = 0
        self.aim_angle = 0.0
        self.guaranteed_crit = False
        self.next_regen = 0
        self.next_poison_tick = 0
        self.weapon = None            # set by Game (needs assets)
        self.kills = 0
        self.coins_earned = 0

    _PERSIST = ("coins", "speed_mult", "damage_mult", "fire_rate_mult", "multishot", "pierce",
                "reach_mult", "magnet", "shields", "dash_cd_mult", "ability_cd_mult", "potions",
                "max_hp", "health", "crit_chance", "weapon_tier", "kills", "coins_earned")

    def snapshot(self):
        return {k: getattr(self, k) for k in self._PERSIST}

    def restore(self, snap):
        for k, v in snap.items():
            setattr(self, k, v)

    # ------------------------------------------------------------ abilities
    @property
    def ability_cd(self):
        return int(self.hero.ability.cooldown_ms * self.ability_cd_mult)

    def try_dash(self, now):
        if now >= self.dash_ready_at:
            self.dash_until = now + constants.DASH_DURATION_MS
            self.dash_ready_at = now + int(constants.DASH_COOLDOWN_MS * self.dash_cd_mult)
            self.dash_dir = self.last_move_dir
            return True
        return False

    @property
    def dashing(self):
        return pygame.time.get_ticks() < self.dash_until

    def move(self, ix, iy, world, now):
        if ix or iy:
            length = math.hypot(ix, iy)
            self.last_move_dir = (ix / length, iy / length)
        speed = constants.PLAYER_SPEED * self.speed_mult * (self.hero.speed / 5.0)
        if self.has_status("slow", now):
            speed *= 0.55
        if self.has_status("whirlwind", now):
            speed *= 1.15
        if self.has_status("haste", now):
            speed *= 1.35
        if now < self.dash_until:
            dx = self.dash_dir[0] * speed * constants.DASH_SPEED_MULT
            dy = self.dash_dir[1] * speed * constants.DASH_SPEED_MULT
        elif ix or iy:
            dx, dy = self.last_move_dir[0] * speed, self.last_move_dir[1] * speed
        else:
            dx = dy = 0
        self.running = bool(dx or dy)
        if dx < 0:
            self.flip = True
        elif dx > 0:
            self.flip = False
        self.fx, self.fy, _, _ = world.move_rect(self.rect, self.fx, self.fy, dx, dy)
        if world.exit_rect and world.exit_rect.colliderect(self.rect):
            d = math.hypot(self.rect.centerx - world.exit_rect.centerx,
                           self.rect.centery - world.exit_rect.centery)
            return d < 24
        return False

    # -------------------------------------------------------------- damage
    def take_damage(self, amount, now, bypass_iframes=False):
        """Returns damage actually applied (0 = blocked)."""
        if not self.alive or now < self.dash_until:
            return 0
        if now < self.invuln_until and not bypass_iframes:
            return 0
        if not bypass_iframes:
            self.invuln_until = now + constants.PLAYER_INVULN_MS
        self.flash_until = now + 120
        if self.shields > 0 and not bypass_iframes:
            self.shields -= 1
            return 0
        if self.has_status("bulwark", now):
            amount *= 0.3
        amount *= 1.0 - self.hero.flags.get("armor", 0.0)     # melee heroes wear armour
        amount = max(1, int(round(amount)))
        self.health -= amount
        if self.health <= 0:
            self.health = 0
            self.alive = False
        return amount

    def heal(self, amount):
        self.health = min(self.max_hp, self.health + int(amount))

    def update(self, now):
        self.animate(now)
        if self.hero.flags.get("regen") and now >= self.next_regen and self.alive:
            self.next_regen = now + 2000
            self.heal(1)

    def draw(self, surface, camera, now):
        if now < self.invuln_until and (now // 80) % 2 == 0:
            return
        img = self.sprite_for_draw(now)
        if now < self.flash_until:
            img = pygame.transform.flip(self.animations[2][0], self.flip, False)   # hit frame
        if self.has_status("invisible", now):
            img = img.copy()
            img.set_alpha(80)
        r = camera.apply(self.rect)
        if now < self.dash_until:
            ghost = img.copy()
            ghost.set_alpha(90)
            surface.blit(ghost, (r.centerx - ghost.get_width() // 2 - int(self.dash_dir[0] * 18),
                                 r.bottom - ghost.get_height() + 4 - int(self.dash_dir[1] * 18)))
        surface.blit(img, (r.centerx - img.get_width() // 2, r.bottom - img.get_height() + 4))
        if self.has_status("bulwark", now):
            pygame.draw.circle(surface, (120, 200, 255), r.center, 40, 2)
        if self.has_status("slow", now):
            pygame.draw.circle(surface, (130, 220, 255), (r.centerx, r.bottom + 2), 14, 2)


# ==========================================================================
# Enemy
# ==========================================================================
class Enemy(Actor):
    is_boss = False

    def __init__(self, key, mtype, x, y, assets, level_cfg, elite=False):
        hp = int(mtype.hp * level_cfg.get("hp_mult", 1.0))
        dmg = int(mtype.damage * level_cfg.get("dmg_mult", 1.0))
        scale, tint, hitbox = mtype.draw_scale, mtype.tint, mtype.hitbox
        if elite:
            hp, dmg = int(hp * 2.2), int(dmg * 1.3)
            scale *= 1.3
            hitbox = int(hitbox * 1.2)
            tint = (255, 215, 90)
        super().__init__(x, y, assets.animation(mtype.sprite, scale, tint), hitbox, hp)
        self.key, self.mtype, self.elite = key, mtype, elite
        self.damage = dmg
        self.speed = mtype.speed * (1.1 if elite else 1.0)
        self.assets = assets
        self.awake = False
        self.last_seen = None
        self.stunned_until = 0
        self.knock = [0.0, 0.0]
        self.next_shot = 0
        self.zig_phase = random.random() * math.tau
        self.charge_state = None
        self.charge_dir = (0, 0)
        self.next_charge = 0
        self.show_bar_until = 0
        self.revived = False
        self.next_special = 0
        self.next_poison_tick = 0
        self.minions = []
        self.leap = None             # (start_ms, end_ms, from, to)
        self.contact_since = None    # when the current body contact started
        self.summons_left = 6        # summoners: total minions they may raise
        self.next_contact = 0        # contact-attack cooldown

    # --------------------------------------------------------------- hit
    def hurt(self, amount, now, push_dir=None, stagger_ms=0):
        """
        push_dir   : knock-back direction; its LENGTH scales the strength
                     (melee weapons pass ~2.4 so enemies are shoved out of
                     contact range - see MeleeWeapon.attack).
        stagger_ms : extra stun. A staggered enemy cannot move or deal
                     contact damage, which is what keeps melee heroes alive.
        """
        self.health -= amount
        self.flash_until = now + 90
        if not self.has_status("frozen", now):
            self.stunned_until = now + max(constants.ENEMY_STUN_MS, stagger_ms)
        self.show_bar_until = now + 2500
        self.awake = True
        self.contact_since = None            # getting hit interrupts a melee wind-up
        if push_dir and not self.is_boss:
            k = constants.ENEMY_KNOCKBACK * (0.5 if self.mtype.behaviour == "armored" else 1.0)
            self.knock = [push_dir[0] * k, push_dir[1] * k]
        if self.health <= 0:
            if self.mtype.behaviour == "reviver" and not self.revived:
                # Skeletons collapse into a bone pile and get back up.
                self.revived = True
                self.health = 1
                self.add_status("bones", now, 2600)
                return
            self.health = 0
            self.alive = False

    # ------------------------------------------------------------ helpers
    def _shoot(self, game, kind, target, damage=None, effect=None, homing=0.0, speed=None, spread=0.0):
        ang = math.atan2(target[1] - self.rect.centery, target[0] - self.rect.centerx) + spread
        sp = speed or constants.PROJECTILE_SPEED
        game.assets.play("enemy_shoot")
        game.projectiles.add(Projectile(self.assets.projectiles[kind], self.rect.centerx, self.rect.centery,
                                        math.cos(ang) * sp, math.sin(ang) * sp,
                                        damage or self.damage, effect=effect, homing=homing))

    # ------------------------------------------------------------ update
    def update(self, game, now):
        if not self.alive:
            return
        world, player = game.world, game.player
        self.animate(now)

        # Status: bones (revive timer), frozen, poison DoT
        if self.has_status("bones", now):
            self.running = False
            return
        if self.revived and self.status.get("bones", 0) and not self.has_status("bones", now):
            self.status.pop("bones")
            self.health = self.max_hp // 2
            game.float_text(self.rect.centerx, self.rect.top, "RISE!", (230, 230, 230))
            game.assets.play("bones_rise")
        if self.has_status("poison", now) and now >= self.next_poison_tick:
            self.next_poison_tick = now + 500
            game.hit_enemy(self, self.status_data.get("poison", {}).get("dps", 6), now, dot=True)
            if not self.alive:
                return
        if self.has_status("frozen", now):
            self.running = False
            return

        # Knock-back
        if abs(self.knock[0]) + abs(self.knock[1]) > 0.3:
            self.fx, self.fy, _, _ = world.move_rect(self.rect, self.fx, self.fy, *self.knock)
            self.knock[0] *= 0.7
            self.knock[1] *= 0.7

        # Perception
        dist = self.dist_to(player)
        invisible = player.has_status("invisible", now)
        sees = (not invisible) and dist < constants.ENEMY_AGGRO_RANGE * (1.4 if self.awake else 1.0) and \
            world.line_of_sight(self.rect.center, player.rect.center)
        if sees:
            if not self.awake:
                self.next_shot = now + random.randint(500, 1000)
                self.next_special = now + random.randint(800, 1600)
            self.awake = True
            self.last_seen = player.rect.center

        if self.mtype.behaviour == "mimic_wait":
            return
        if not self.awake or now < self.stunned_until or not player.alive:
            self.running = False
            return
        target = player.rect.center if sees else self.last_seen
        if target is None:
            self.running = False
            return
        tx, ty = target[0] - self.rect.centerx, target[1] - self.rect.centery
        tdist = math.hypot(tx, ty) or 1
        ux, uy = tx / tdist, ty / tdist
        speed = self.speed * (0.5 if self.has_status("slow", now) else 1.0)

        b = self.mtype.behaviour
        dx = dy = 0.0
        if b in ("ranged", "summoner", "bomber", "healer", "poisoner"):
            dx, dy = self._kite(dist, sees, ux, uy, speed)
            if sees and now >= self.next_shot:
                self.next_shot = now + self.mtype.shoot_cooldown_ms + random.randint(-200, 300)
                self._ranged_attack(game, now, player)
        elif b == "erratic":
            wobble = math.sin(now / 160 + self.zig_phase) * 0.9
            dx, dy = (ux - uy * wobble) * speed, (uy + ux * wobble) * speed
        elif b == "charger":
            dx, dy = self._charger(now, ux, uy, dist, sees, speed)
        elif b == "leaper":
            dx, dy = self._leaper(game, now, ux, uy, dist, sees, speed)
        elif b == "teleporter":
            if sees and now >= self.next_special and dist > 90:
                self.next_special = now + 3200
                x, y = world.random_floor_near(player.rect.centerx, player.rect.centery, 2)
                game.puff(self.rect.center, now)
                game.assets.play("teleport")
                self.fx, self.fy = float(x), float(y)
                self.rect.center = (x, y)
                self.stunned_until = now + 350          # brief grace after blinking
                game.puff(self.rect.center, now)
            elif dist > constants.ENEMY_STOP_RANGE:
                dx, dy = ux * speed, uy * speed
        elif b == "berserk":
            mult = 1.8 if self.health < self.max_hp / 2 else 1.0
            if mult > 1:
                self.tint_rage = True
            if dist > constants.ENEMY_STOP_RANGE:
                dx, dy = ux * speed * mult, uy * speed * mult
        elif b == "gooey":
            if now >= self.next_special:
                self.next_special = now + 650
                game.add_puddle(self.rect.centerx, self.rect.bottom - 8, 34, "goo", 2600)
            if dist > constants.ENEMY_STOP_RANGE:
                dx, dy = ux * speed, uy * speed
        elif b == "freezer":
            if sees and now >= self.next_shot and dist > 100:
                self.next_shot = now + self.mtype.shoot_cooldown_ms
                self._shoot(game, "ice", player.rect.center, int(self.damage * 0.7), effect="slow")
            if dist > constants.ENEMY_STOP_RANGE:
                dx, dy = ux * speed, uy * speed
        else:  # chaser, splitter, reviver, armored
            if dist > constants.ENEMY_STOP_RANGE:
                dx, dy = ux * speed, uy * speed

        self.running = bool(dx or dy)
        if dx < 0:
            self.flip = True
        elif dx > 0:
            self.flip = False
        self.fx, self.fy, hx, hy = world.move_rect(self.rect, self.fx, self.fy, dx, dy)
        if self.charge_state and self.charge_state[0] == "rush" and (hx or hy):
            self.charge_state = None
            self.next_charge = now + 2600

        # Contact attack with a short WIND-UP: an enemy must stay touching the
        # player for CONTACT_WINDUP_MS before it bites, then waits
        # CONTACT_COOLDOWN_MS. Previously contact hurt instantly, so melee
        # heroes (who must stand next to enemies) took far more damage than
        # ranged ones. Now a well-timed swing (knock-back + stagger) cancels
        # the wind-up entirely.
        if self.rect.colliderect(player.rect.inflate(6, 6)) and not self.leap:
            if self.contact_since is None:
                self.contact_since = now
                self.flash_until = now + 60          # tiny "about to bite" flash
            elif now - self.contact_since >= constants.CONTACT_WINDUP_MS and now >= self.next_contact:
                effect = "slow" if b == "freezer" else None
                game.damage_player(self.damage, now, effect=effect)
                self.next_contact = now + constants.CONTACT_COOLDOWN_MS
                self.contact_since = None
        else:
            self.contact_since = None

    def _kite(self, dist, sees, ux, uy, speed):
        pref = self.mtype.preferred_range
        if dist < pref * 0.7:
            return -ux * speed, -uy * speed
        if dist > pref * 1.2 or not sees:
            return ux * speed, uy * speed
        return -uy * speed * 0.5, ux * speed * 0.5

    def _ranged_attack(self, game, now, player):
        b = self.mtype.behaviour
        if b == "ranged":
            self._shoot(game, self.mtype.projectile, player.rect.center)
        elif b == "summoner":
            # Summons are a FINITE budget (SUMMON_BUDGET per summoner) and
            # minions crumble when their master dies (see on_death). Without
            # this, a few necromancers could raise skeletons forever and the
            # "clear the floor" exit lock could never be satisfied.
            self.minions = [m for m in self.minions if m.alive]
            if len(self.minions) < 3 and self.summons_left > 0:
                self.summons_left -= 2
                for _ in range(2):
                    x, y = game.world.random_floor_near(self.rect.centerx, self.rect.centery, 2)
                    m = game.spawn_enemy(self.mtype.summon or "skelet", x, y, awake=True)
                    if m:
                        self.minions.append(m)
                        game.puff((x, y), now, (150, 90, 220))
            else:
                self._shoot(game, self.mtype.projectile, player.rect.center)
        elif b == "bomber":
            tx = player.rect.centerx + random.randint(-30, 30)
            ty = player.rect.centery + random.randint(-30, 30)
            game.lob_bomb(self.rect.center, (tx, ty), int(self.damage * 1.6), 70, now)
        elif b == "poisoner":
            game.lob_flask(self.rect.center, player.rect.center, now, dps=max(3, self.damage // 2))
        elif b == "healer":
            # Heal up to 3 wounded allies (not other healers - two shamans
            # healing each other forever would make them unkillable).
            healed = False
            wounded = [e for e in game.enemies if e is not self and e.alive and e.health < e.max_hp
                       and e.mtype.behaviour != "healer" and not e.is_boss and self.dist_to(e) < 260]
            wounded.sort(key=lambda e: e.health / e.max_hp)
            for e in wounded[:3]:
                amt = int(e.max_hp * 0.12)
                e.health = min(e.max_hp, e.health + amt)
                game.float_text(e.rect.centerx, e.rect.top, f"+{amt}", (90, 230, 90))
                healed = True
            if healed:
                game.puff(self.rect.center, now, (90, 230, 90))
            else:
                self._shoot(game, self.mtype.projectile, player.rect.center)

    def _charger(self, now, ux, uy, dist, sees, speed):
        st = self.charge_state
        if st is None:
            if sees and dist < 380 and now >= self.next_charge:
                self.charge_state = ("wind", now + 550)
                self.charge_dir = (ux, uy)
                return 0, 0
            return ux * speed * 0.6, uy * speed * 0.6
        phase, t_end = st
        if phase == "wind":
            self.flash_until = now + 40
            if now >= t_end:
                self.charge_state = ("rush", now + 650)
            return 0, 0
        if now >= t_end:
            self.charge_state = None
            self.next_charge = now + 2600
        return self.charge_dir[0] * self.speed * 3.4, self.charge_dir[1] * self.speed * 3.4

    def _leaper(self, game, now, ux, uy, dist, sees, speed):
        """Crouch (telegraph) then jump along an arc to where the player WAS."""
        if self.leap:
            start, end, src, dst = self.leap
            t = (now - start) / (end - start)
            if t >= 1:
                self.leap = None
                self.fx, self.fy = float(dst[0]), float(dst[1])
                self.rect.center = dst
                if game.world.rect_hits_wall(self.rect):
                    self.fx, self.fy = float(src[0]), float(src[1])
                    self.rect.center = src
                game.add_ring(self.rect.centerx, self.rect.bottom, 50, (200, 200, 200), now)
                if self.rect.inflate(30, 30).colliderect(game.player.rect):
                    game.damage_player(self.damage, now)
                self.next_special = now + 1800
                return 0, 0
            x = src[0] + (dst[0] - src[0]) * t
            y = src[1] + (dst[1] - src[1]) * t
            self.fx, self.fy = x, y
            self.rect.center = (round(x), round(y))
            self.jump_h = math.sin(math.pi * t) * 50
            return 0, 0
        self.jump_h = 0
        if sees and dist < 330 and now >= self.next_special:
            if not hasattr(self, "crouch_until") or self.crouch_until < self.next_special:
                self.crouch_until = now + 420
            if now < self.crouch_until:
                self.flash_until = now + 40
                return 0, 0
            dst = (game.player.rect.centerx, game.player.rect.centery)
            self.leap = (now, now + 420, self.rect.center, dst)
            return 0, 0
        if dist > constants.ENEMY_STOP_RANGE:
            return ux * speed, uy * speed
        return 0, 0

    def on_death(self, game):
        for m in self.minions:                     # a summoner's minions die with it
            if m.alive:
                m.health, m.alive = 0, False
                m.revived = True                   # no skeleton comeback either
                game.puff(m.rect.center, pygame.time.get_ticks(), (150, 90, 220))
        if self.mtype.behaviour == "splitter" and self.mtype.split_into:
            for i in range(self.mtype.split_count):
                ang = i * math.tau / self.mtype.split_count
                game.spawn_enemy(self.mtype.split_into, self.rect.centerx + math.cos(ang) * 16,
                                 self.rect.centery + math.sin(ang) * 16, awake=True)

    def coin_drop(self):
        lo, hi = self.mtype.coins
        n = random.randint(lo, hi)
        return n * 2 if self.elite else n

    def draw(self, surface, camera, now):
        if self.has_status("bones", now):
            img = self.assets.skull
            r = camera.apply(self.rect)
            surface.blit(img, img.get_rect(midbottom=r.midbottom))
            return
        img = self.sprite_for_draw(now)
        if self.has_status("frozen", now):
            img = img.copy()
            img.fill((60, 120, 200, 0), special_flags=pygame.BLEND_RGBA_ADD)
        elif self.has_status("poison", now):
            img = img.copy()
            img.fill((0, 70, 0, 0), special_flags=pygame.BLEND_RGBA_ADD)
        r = camera.apply(self.rect)
        lift = int(getattr(self, "jump_h", 0))
        if lift:
            pygame.draw.ellipse(surface, (0, 0, 0), (r.centerx - 14, r.bottom - 6, 28, 10))
        surface.blit(img, (r.centerx - img.get_width() // 2, r.bottom - img.get_height() + 4 - lift))
        if self.mtype.behaviour == "armored":
            pygame.draw.rect(surface, (170, 170, 190), (r.centerx - 6, r.top - 22, 12, 6), 0, 2)
        if self.alive and now < self.show_bar_until and not self.is_boss:
            w = max(30, self.rect.width)
            pygame.draw.rect(surface, constants.BLACK, (r.centerx - w // 2, r.top - 14, w, 5))
            pygame.draw.rect(surface, constants.RED,
                             (r.centerx - w // 2, r.top - 14, int(w * self.health / self.max_hp), 5))


# ==========================================================================
# Boss
# ==========================================================================
class Boss(Enemy):
    """
    Pattern scheduler. phases = [(0.3, [...]), (0.6, [...]), (1.0, [...])]:
    the first phase whose threshold >= HP ratio is active. Each pattern has
    its own cooldown; a global gap prevents everything firing on one frame.
    The lowest phase (if there are several) is "enraged": faster + shorter
    cooldowns.
    """
    is_boss = True

    COOLDOWNS = {"aimed": 900, "spread3": 2200, "spread5": 2600, "ring": 3200, "spiral": 6000,
                 "charge": 5200, "summon": 9000, "slam": 4200, "bombs": 4500, "poison": 3800,
                 "teleport": 6500, "homing": 5000, "cross": 4000, "judgement": 7000}

    def __init__(self, key, btype, x, y, assets, level_cfg):
        from monsters import MonsterType
        shim = MonsterType(btype.name, btype.sprite, hp=btype.hp, speed=btype.speed, damage=btype.damage,
                           behaviour="boss", hitbox=btype.hitbox, draw_scale=btype.draw_scale,
                           tint=btype.tint, projectile=btype.projectile)
        super().__init__(key, shim, x, y, assets, {"hp_mult": 1.0, "dmg_mult": 1.0})
        self.btype = btype
        self.name = btype.name
        self.next_ready = {p: 0 for p in self.COOLDOWNS}
        self.global_gap_until = 0
        self.spiral_until = self.spiral_next = 0
        self.spiral_angle = 0.0
        self.phase_index = len(btype.phases) - 1
        self.anim_speed_ms = 120
        self.minions = []

    @property
    def phase_patterns(self):
        ratio = self.health / self.max_hp
        for i, (threshold, pats) in enumerate(self.btype.phases):
            if ratio <= threshold:
                self.phase_index = i
                return pats
        return self.btype.phases[-1][1]

    def hurt(self, amount, now, push_dir=None, stagger_ms=0):
        super().hurt(amount, now, None)
        self.stunned_until = 0           # bosses don't flinch

    def update(self, game, now):
        if not self.alive:
            return
        world, player = game.world, game.player
        self.animate(now)
        if self.has_status("poison", now) and now >= self.next_poison_tick:
            self.next_poison_tick = now + 500
            game.hit_enemy(self, self.status_data.get("poison", {}).get("dps", 6), now, dot=True)
        if self.has_status("frozen", now):
            self.running = False
            return
        dist = self.dist_to(player)
        if not self.awake:
            if dist < 560 and world.line_of_sight(self.rect.center, player.rect.center):
                self.awake = True
                for p in self.next_ready:
                    self.next_ready[p] = now + 1200
                game.on_boss_awake(self)
            else:
                return
        if not player.alive:
            self.running = False
            return

        pats = self.phase_patterns
        enraged = self.phase_index == 0 and len(self.btype.phases) > 1
        speed = self.speed * (1.3 if enraged else 1.0) * (0.6 if self.has_status("slow", now) else 1)
        tx, ty = player.rect.centerx - self.rect.centerx, player.rect.centery - self.rect.centery
        d = math.hypot(tx, ty) or 1
        ux, uy = tx / d, ty / d

        dx = dy = 0.0
        if self.charge_state:
            dx, dy = self._charger(now, ux, uy, dist, True, speed)
            if self.charge_state is None:
                self.next_ready["charge"] = now + self.COOLDOWNS["charge"]
        elif dist > 140:
            dx, dy = ux * speed, uy * speed
        self.running = bool(dx or dy)
        self.flip = dx < 0 if dx else self.flip
        self.fx, self.fy, hx, hy = world.move_rect(self.rect, self.fx, self.fy, dx, dy)
        if self.charge_state and self.charge_state[0] == "rush" and (hx or hy):
            self.charge_state = None
            self.next_ready["charge"] = now + self.COOLDOWNS["charge"]
            game.camera.shake(8, 250)

        if self.rect.colliderect(player.rect.inflate(6, 6)):
            game.damage_player(self.damage, now)

        if now < self.spiral_until and now >= self.spiral_next:
            self.spiral_next = now + 170
            self.spiral_angle += 0.38
            for k in range(4):
                self._radial(game, self.spiral_angle + k * math.pi / 2, 0.9)

        if now < self.global_gap_until or self.charge_state:
            return
        for p in pats:
            if now >= self.next_ready[p]:
                fired = self._fire(p, now, game)
                self.next_ready[p] = now + int(self.COOLDOWNS[p] * (0.75 if enraged else 1.0))
                if fired:
                    self.global_gap_until = now + 450
                    break

    def _radial(self, game, angle, speed_mult=1.0, homing=0.0, kind=None):
        sp = constants.PROJECTILE_SPEED * speed_mult
        effect = "poison" if self.btype.projectile == "poison" else None
        game.projectiles.add(Projectile(self.assets.projectiles[kind or self.btype.projectile],
                                        self.rect.centerx, self.rect.centery,
                                        math.cos(angle) * sp, math.sin(angle) * sp,
                                        int(self.damage * 0.7), effect=effect, homing=homing,
                                        life=300 if homing else 240))

    def _fire(self, p, now, game):
        pl = game.player
        if p in ("aimed", "spread3", "spread5", "ring", "cross", "homing"):
            game.assets.play("enemy_shoot")
        base = math.atan2(pl.rect.centery - self.rect.centery, pl.rect.centerx - self.rect.centerx)
        if p == "aimed":
            self._radial(game, base, 1.25)
        elif p in ("spread3", "spread5"):
            n = 3 if p == "spread3" else 5
            for i in range(n):
                self._radial(game, base + (i - (n - 1) / 2) * 0.22, 1.1)
        elif p == "ring":
            off = random.random()
            for i in range(12):
                self._radial(game, off + i * math.tau / 12, 0.85)
        elif p == "cross":
            off = random.choice((0, math.pi / 4))
            for i in range(4):
                for k in range(3):
                    self._radial(game, off + i * math.pi / 2, 0.8 + k * 0.25)
        elif p == "spiral":
            self.spiral_until = now + 1800
        elif p == "charge":
            self.charge_state = ("wind", now + 700)
            self.charge_dir = (math.cos(base), math.sin(base))
        elif p == "homing":
            for i in range(3):
                self._radial(game, base + (i - 1) * 0.9, 0.7, homing=0.035)
        elif p == "slam":
            game.assets.play("boss_slam")
            game.add_blast(self.rect.centerx, self.rect.centery, 170, 800, int(self.damage * 1.3), now)
            for i in range(10):
                self._radial(game, i * math.tau / 10, 0.6)
        elif p == "bombs":
            for _ in range(5):
                tx = pl.rect.centerx + random.randint(-140, 140)
                ty = pl.rect.centery + random.randint(-140, 140)
                game.lob_bomb(self.rect.center, (tx, ty), int(self.damage * 1.3), 80, now)
        elif p == "poison":
            for _ in range(3):
                tx = pl.rect.centerx + random.randint(-90, 90)
                ty = pl.rect.centery + random.randint(-90, 90)
                game.lob_flask(self.rect.center, (tx, ty), now, dps=max(4, self.damage // 3), radius=75)
        elif p == "teleport":
            x, y = game.world.random_floor_near(pl.rect.centerx, pl.rect.centery, 6)
            if math.hypot(x - pl.rect.centerx, y - pl.rect.centery) < 160:
                return False
            game.puff(self.rect.center, now, (200, 160, 255))
            game.assets.play("teleport")
            test = self.rect.copy()
            test.center = (x, y)
            if game.world.rect_hits_wall(test):
                return False
            self.fx, self.fy = float(x), float(y)
            self.rect.center = (x, y)
            game.puff(self.rect.center, now, (200, 160, 255))
        elif p == "judgement":
            for k in range(3):
                game.add_blast(pl.rect.centerx + random.randint(-60, 60),
                               pl.rect.centery + random.randint(-60, 60),
                               90, 900 + k * 350, int(self.damage * 1.2), now, colour=(255, 240, 150))
        elif p == "summon":
            self.minions = [m for m in self.minions if m.alive]
            if not self.btype.summon or len(self.minions) >= 6:
                return False
            for _ in range(3):
                x, y = game.world.random_floor_near(self.rect.centerx, self.rect.centery, 4)
                m = game.spawn_enemy(random.choice(self.btype.summon), x, y, awake=True)
                if m:
                    self.minions.append(m)
                    game.puff((x, y), now)
        return True

    def coin_drop(self):
        return self.btype.coins

    def on_death(self, game):
        pass
