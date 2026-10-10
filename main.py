"""
main.py - entry point and game-state machine.

Run:   python main.py                          (normal)
       python main.py --level 12 --hero elf_f  (jump straight in - testing)

Architecture overview
---------------------
    Game                    owns all state, one method per screen
      .state                "menu" | "select" | "cutscene" | "play" | "pause"
                            | "shop" | "dead" | "victory"
      .load_level(n)        the ONLY place a level is built
      .frame(events)        one tick: input -> update -> draw for current state

    InputState              converts keyboard/mouse into intent

The Game also acts as a FACADE for gameplay systems: enemies, weapons,
hazards and abilities call game.hit_enemy(), game.damage_player(),
game.spawn_enemy(), game.lob_bomb() ... instead of manipulating each other
directly. All damage rules (crits, armour, frozen bonus, rage, venom,
poison, slows) therefore live in exactly one place: hit_enemy /
damage_player below.

Flow:  menu -> select hero -> intro cutscene -> level 1 -> shop -> level 2
       ... boss levels are followed by a story cutscene ... level 20 ->
       ending cutscene -> victory screen.
"""
import math
import random
import sys
import pygame
import constants
import monsters
import lore
from abilities import ABILITIES, whirlwind_tick
from assets import Assets
from world import World, Camera
from character import Player, Enemy, Boss
from weapon import make_weapon
from items import Item
from shop import Shop
from hazards import Blast, Lob, Puddle, Ring, SpikeTrap, Chest, Crate
from heroes import HERO_BY_KEY
from hero_select import HeroSelect
from settings import Settings, SettingsScreen
from sounds import SoundBank
from ui import (Button, Mouse, FloatingText, ScreenFade, draw_text, draw_hud,
                draw_boss_bar, draw_banner)


# ==========================================================================
# Input
# ==========================================================================
class InputState:
    """
    Tracks held keys ourselves (KEYDOWN/KEYUP). On focus loss the set is
    cleared - the fix for "stuck" movement after alt-tab.
    """
    MOVE_KEYS = {pygame.K_a: (-1, 0), pygame.K_d: (1, 0), pygame.K_w: (0, -1), pygame.K_s: (0, 1)}
    AIM_KEYS = {pygame.K_LEFT: (-1, 0), pygame.K_RIGHT: (1, 0), pygame.K_UP: (0, -1), pygame.K_DOWN: (0, 1)}

    def __init__(self):
        self.held = set()
        self.pressed = set()
        self.mouse_moved_at = -10_000
        self.right_click = False

    def begin_frame(self):
        self.pressed = set()
        self.right_click = False

    def handle(self, event, now):
        if event.type == pygame.KEYDOWN:
            self.held.add(event.key)
            self.pressed.add(event.key)
        elif event.type == pygame.KEYUP:
            self.held.discard(event.key)
        elif event.type == pygame.MOUSEMOTION:
            self.mouse_moved_at = now
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            self.right_click = True
        elif event.type == pygame.WINDOWFOCUSLOST:
            self.held.clear()
            Mouse.held = False

    def move_vector(self):
        return (sum(v[0] for k, v in self.MOVE_KEYS.items() if k in self.held),
                sum(v[1] for k, v in self.MOVE_KEYS.items() if k in self.held))

    def aim_vector(self):
        return (sum(v[0] for k, v in self.AIM_KEYS.items() if k in self.held),
                sum(v[1] for k, v in self.AIM_KEYS.items() if k in self.held))


def angle_to(src, dst):
    """Degrees, 0 = right, counter-clockwise positive (pygame y is down)."""
    return math.degrees(math.atan2(-(dst[1] - src[1]), dst[0] - src[0]))


# ==========================================================================
# Game
# ==========================================================================
class Game:
    def __init__(self, start_level=1, audio=True, hero_key=None):
        self.screen = pygame.display.get_surface()
        self.clock = pygame.time.Clock()
        self.settings = Settings.load()
        self.sounds = SoundBank(self.settings, enabled=audio)
        self.assets = Assets(audio=audio, sound_bank=self.sounds)
        a = self.assets
        Button.click_sound = lambda: a.play("ui_confirm")
        self.settings_screen = SettingsScreen(a, self.settings, self.sounds)
        self.settings_return = "menu"
        self.settings_bg = None
        self.ability_was_ready = True
        self.level_cfg = {}
        self.boss = None
        W, H = constants.SCREEN_WIDTH, constants.SCREEN_HEIGHT
        self.start_button = Button(W // 2 - 145, H // 2 - 170, a.buttons["start"], pygame.K_RETURN)
        self.exit_button = Button(W // 2 - 110, H // 2 + 60, a.buttons["exit"], None)
        self.restart_button = Button(W // 2 - 175, H // 2 - 60, a.buttons["restart"], pygame.K_r)
        self.resume_button = Button(W // 2 - 175, H // 2 - 170, a.buttons["resume"], None)
        # Same art style as the original buttons (tools: composed from their letters)
        self.settings_button = Button(0, 0, a.buttons["settings"], pygame.K_o)
        self.intro_fade = ScreenFade(1, constants.BLACK, 6)
        self.death_fade = ScreenFade(2, constants.PINK, 6)

        self.input = InputState()
        self.camera = Camera()
        self.camera.settings = self.settings          # screen-shake on/off option
        self.shop = Shop(a)
        self.hero_select = HeroSelect(a)
        self.state = "menu"
        self.start_level = start_level
        self.forced_hero = HERO_BY_KEY.get(hero_key) if hero_key else None
        self.level = start_level
        self.auto_fire = False
        self.show_minimap = True
        self.running = True
        self.player = None
        self.hero = None
        self.player_snapshot = None
        self.banner = None
        self.start_time = 0
        self.cutscene = None
        self.after_cutscene = None
        self.skip_cutscenes = False          # tests set this

    # ------------------------------------------------------------------
    # Flow helpers
    # ------------------------------------------------------------------
    def play_cutscene(self, keys, then):
        """Show scenes `keys` (list), then call `then()`."""
        if self.skip_cutscenes or not keys:
            then()
            return
        self.cutscene = lore.Cutscene(self.assets, keys, self.hero)
        self.after_cutscene = then
        self.state = "cutscene"

    def new_game(self, hero):
        self.hero = hero
        self.level = self.start_level
        self.shop.reset()
        self.player = None
        self.player_snapshot = None
        self.start_time = pygame.time.get_ticks()
        self.play_cutscene(lore.SCENE_BEFORE_LEVEL.get(self.level, []), self._enter_level)

    def _enter_level(self):
        self.load_level(self.level)
        self.state = "play"
        Mouse.held = False

    def finish_level(self):
        """Called when the player steps on an unlocked exit."""
        self.assets.play("level_complete")
        scene = lore.SCENE_AFTER_LEVEL.get(self.level)
        if self.level >= constants.MAX_LEVELS:
            def to_victory():
                self.state = "victory"
                self.assets.play("victory")
            self.play_cutscene([scene] if scene else [], to_victory)
            return

        def to_shop():
            self.shop.roll_offer(self.player)
            self.state = "shop"
        self.play_cutscene([scene] if scene else [], to_shop)

    # ------------------------------------------------------------------
    # Level management - the ONE place where a level is (re)built
    # ------------------------------------------------------------------
    def load_level(self, n, restore_snapshot=False):
        a = self.assets
        self.world = World(n, a)
        self.level_cfg = monsters.LEVELS.get(n, {})
        px, py = self.world.player_spawn
        old = self.player
        self.player = Player(px, py, self.hero, a)
        if restore_snapshot and self.player_snapshot:
            self.player.restore(self.player_snapshot)
        elif old is not None:
            self.player.restore(old.snapshot())
        self.player_snapshot = self.player.snapshot()
        self.player.invuln_until = pygame.time.get_ticks() + 1000
        self.player.weapon = make_weapon(self.hero, self.player.weapon_tier, a)

        self.enemies = []
        self.projectiles = pygame.sprite.Group()     # enemy projectiles
        self.player_shots = pygame.sprite.Group()
        self.items = pygame.sprite.Group()
        self.texts = pygame.sprite.Group()
        self.hazards = pygame.sprite.Group()
        for key, x, y in self.world.enemy_spawns:
            self.spawn_enemy(key, x, y, allow_elite=True)
        self.boss = None
        if self.world.boss_spawn:
            bkey, bx, by = self.world.boss_spawn
            self.boss = Boss(bkey, monsters.BOSSES[bkey], bx, by, a, self.level_cfg)
            self.enemies.append(self.boss)
        for kind, x, y in self.world.item_spawns:
            if kind == "coin":
                self.items.add(Item(x, y, "coin", a.coin_frames))
            else:
                self.items.add(Item(x, y, "flask", [a.flasks["red"]], flask="red"))
        for i, (kind, x, y) in enumerate(self.world.prop_spawns):
            if kind == "spikes":
                self.hazards.add(SpikeTrap(x, y, a.spikes, offset=(i * 377) % SpikeTrap.CYCLE))
            elif kind == "chest":
                self.hazards.add(Chest(x, y, a, mimic=random.random() < self.level_cfg.get("mimic_chance", 0)))
            elif kind == "crate":
                self.hazards.add(Crate(x, y, a))

        self.camera.snap_to(self.player.rect)
        self.intro_fade.fade_counter = 0
        self.death_fade.fade_counter = 0
        self.intro_active = True
        if self.boss:
            sub = f"BOSS: {self.boss.name}"
        else:
            sub = "Clear the floor to unlock the ladder"
        self.banner = (f"LEVEL {n}", sub, pygame.time.get_ticks() + 2400)
        self.exit_was_unlocked = False

    # ------------------------------------------------------------------
    # Facade used by enemies / weapons / hazards / abilities
    # ------------------------------------------------------------------
    def spawn_enemy(self, key, x, y, allow_elite=False, awake=False):
        mtype = monsters.MONSTERS.get(key)
        if mtype is None:
            return None
        elite = allow_elite and self.level >= 2 and key != "mimic" and random.random() < constants.ELITE_CHANCE
        e = Enemy(key, mtype, x, y, self.assets, self.level_cfg, elite)
        if awake or not allow_elite:
            e.awake = True
        self.enemies.append(e)
        return e

    def hit_enemy(self, e, amount, now, push=None, aoe=False, dot=False, slow_ms=0, stagger_ms=0, ranged=False):
        """Single source of truth for damage dealt TO enemies."""
        if not e.alive:
            return 0
        p = self.player
        crit = False
        if not dot:
            if p.guaranteed_crit:
                crit, p.guaranteed_crit = True, False
            else:
                crit = random.random() < p.crit_chance
        dmg = amount
        if crit:
            dmg *= p.hero.flags.get("crit_mult", constants.CRIT_MULT)
        if p.hero.flags.get("rage") and p.health < p.max_hp / 2:
            dmg *= 1.35
        if e.has_status("frozen", now):
            dmg *= 1.5
        if e.mtype.behaviour == "armored" and not e.has_status("frozen", now):
            dmg *= 0.5
        flinch = True
        if ranged:
            dmg *= constants.RANGED_DAMAGE_MULT
            flinch = False
            if push:
                push = (push[0] * constants.RANGED_KNOCKBACK_MULT, push[1] * constants.RANGED_KNOCKBACK_MULT)
        dmg = max(1, int(round(dmg)))
        e.hurt(dmg, now, push, stagger_ms, flinch=flinch)
        if slow_ms:
            e.add_status("slow", now, slow_ms)
        if p.has_status("venom", now) and not dot and not aoe:
            e.add_status("poison", now, 3000, dps=max(4, int(dmg * 0.25)))
            self.heal_player(dmg * 0.15)
        if dot:
            col, font = (110, 220, 90), self.assets.font_small
        elif crit:
            col, font = constants.YELLOW, self.assets.font
        else:
            col, font = constants.RED, self.assets.font_med
        self.texts.add(FloatingText(e.rect.centerx + random.randint(-8, 8), e.rect.top,
                                    f"{dmg}!" if crit else str(dmg), col, font))
        if not dot:
            self.assets.play("hit")
        return dmg

    def damage_player(self, amount, now, effect=None, bypass_iframes=False):
        p = self.player
        shields_before = p.shields
        if effect == "slow":
            p.add_status("slow", now, 1800)
        elif effect == "poison":
            p.add_status("poison", now, 2500)
        dealt = p.take_damage(amount, now, bypass_iframes=bypass_iframes)
        if p.shields < shields_before:
            self.assets.play("shield_block")
        if dealt > 0:
            self.camera.shake(5 if not bypass_iframes else 2, 150)
            self.assets.play("player_hurt")
            self.texts.add(FloatingText(p.rect.centerx, p.rect.top, f"-{dealt}", constants.PINK,
                                        self.assets.font_med))
        return dealt

    def heal_player(self, amount):
        amount = int(amount)
        if amount <= 0:
            return
        before = self.player.health
        self.player.heal(amount)
        if self.player.health > before:
            self.texts.add(FloatingText(self.player.rect.centerx, self.player.rect.top,
                                        f"+{self.player.health - before}", constants.GREEN, self.assets.font_small))

    def float_text(self, x, y, text, colour):
        self.texts.add(FloatingText(x, y, text, colour, self.assets.font_small))

    def say_banner(self, text, sub, now, ms=1500):
        self.banner = (text, sub, now + ms)

    def puff(self, pos, now, colour=(200, 200, 200)):
        self.hazards.add(Ring(pos[0], pos[1], 40, colour, 260, now))

    def add_ring(self, x, y, r, colour, now):
        self.hazards.add(Ring(x, y, r, colour, 260, now))

    def add_blast(self, x, y, radius, delay, damage, now, colour=(255, 120, 40)):
        self.hazards.add(Blast(x, y, radius, delay, damage, owner="enemy", colour=colour, now=now))

    def add_puddle(self, x, y, radius, kind, ms, damage=0):
        self.hazards.add(Puddle(x, y, radius, kind, ms, damage, pygame.time.get_ticks()))

    def lob_bomb(self, src, dst, damage, radius, now):
        dst = self._floor_target(src, dst)
        self.assets.play("bomb_throw")

        def land(g, pos, t):
            g.hazards.add(Blast(pos[0], pos[1], radius, 0, damage, owner="enemy", now=t))
        # the fuse shows a telegraph circle so bombs are always dodgeable
        self.hazards.add(Blast(dst[0], dst[1], radius, 1300, 0, owner="enemy", colour=(255, 200, 80), now=now))
        self.hazards.add(Lob(self.assets.bomb, src, dst, 650, land, now, fuse_ms=650))

    def lob_flask(self, src, dst, now, dps=5, radius=60):
        dst = self._floor_target(src, dst)
        self.assets.play("bomb_throw")

        def land(g, pos, t):
            g.assets.play("splash")
            g.hazards.add(Puddle(pos[0], pos[1], radius, "poison", 3500, dps, t))
            g.hazards.add(Ring(pos[0], pos[1], radius, (90, 220, 80), 250, t))
        self.hazards.add(Lob([self.assets.flasks["green"]], src, dst, 600, land, now))

    def _floor_target(self, src, dst):
        """Pull a throw target back toward the thrower until it is on the floor."""
        x, y = dst
        for _ in range(30):
            if not self.world.is_solid_px(x, y):
                break
            x += (src[0] - x) * 0.1
            y += (src[1] - y) * 0.1
        return x, y

    def drop_coins(self, x, y, n):
        for _ in range(n):
            self.items.add(Item(x, y, "coin", self.assets.coin_frames, 1, pop=True))

    def drop_flask(self, x, y, force=False):
        colour = random.choices(["red", "blue", "green", "yellow"], weights=[5, 2, 2, 2])[0]
        if force or random.random() < 0.5:
            name = ("big_" if random.random() < 0.25 else "") + colour
            self.items.add(Item(x, y, "flask", [self.assets.flasks[name]], pop=True, flask=name))

    def breakables(self):
        return [h for h in self.hazards if isinstance(h, Crate)]

    def on_boss_awake(self, boss):
        self.say_banner(boss.name, boss.btype.title, pygame.time.get_ticks(), 1800)
        self.assets.play("boss_roar")
        self.camera.shake(6, 400)

    # ---- exit lock -----------------------------------------------------------
    # The ladder is locked on EVERY level until the floor is cleared: all
    # monsters (including boss, split children and summons) must be dead.
    # To avoid frustrating hunts for one lost goblin, the last few enemies
    # are revealed on the minimap and by an arrow at the screen edge
    # (see HUNT_REVEAL and draw_hunt_arrows).
    HUNT_REVEAL = 3

    @property
    def enemies_left(self):
        return sum(1 for e in self.enemies if e.alive)

    @property
    def exit_locked(self):
        return self.enemies_left > 0

    def _check_unlock(self, now):
        if not self.exit_was_unlocked and not self.exit_locked:
            self.exit_was_unlocked = True
            self.say_banner("LADDER UNLOCKED", "The way down is open!", now, 2200)
            self.assets.play("exit_unlock")
            self.world.reveal_exit()

    def draw_hunt_arrows(self, now):
        """Point at the last few enemies when they are off-screen."""
        left = [e for e in self.enemies if e.alive]
        if not left or len(left) > self.HUNT_REVEAL:
            return
        W, H = constants.SCREEN_WIDTH, constants.SCREEN_HEIGHT
        view = pygame.Rect(0, constants.HUD_HEIGHT, W, H - constants.HUD_HEIGHT)
        cx, cy = W // 2, (H + constants.HUD_HEIGHT) // 2
        pulse = 180 + int(70 * math.sin(now / 150))
        for e in left:
            r = self.camera.apply(e.rect)
            if view.colliderect(r):
                continue
            ang = math.atan2(r.centery - cy, r.centerx - cx)
            # place the arrow on an ellipse just inside the screen edge
            ax = cx + math.cos(ang) * (W / 2 - 30)
            ay = cy + math.sin(ang) * ((H - constants.HUD_HEIGHT) / 2 - 30)
            tip = (ax + math.cos(ang) * 14, ay + math.sin(ang) * 14)
            l = (ax + math.cos(ang + 2.5) * 12, ay + math.sin(ang + 2.5) * 12)
            rt = (ax + math.cos(ang - 2.5) * 12, ay + math.sin(ang - 2.5) * 12)
            pygame.draw.polygon(self.screen, (255, 60, 60), [tip, l, rt])
            pygame.draw.polygon(self.screen, (pulse, pulse, pulse), [tip, l, rt], 2)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------
    def run(self):
        while self.running:
            self.clock.tick(constants.FPS)
            self.frame(pygame.event.get())
            pygame.display.update()
        pygame.quit()

    def frame(self, events):
        now = pygame.time.get_ticks()
        Mouse.begin_frame()
        self.input.begin_frame()
        for ev in events:
            if ev.type == pygame.QUIT:
                self.running = False
            Mouse.handle(ev)
            self.input.handle(ev, now)
            if ev.type == pygame.WINDOWFOCUSLOST and self.state == "play":
                self.state = "pause"
        getattr(self, f"state_{self.state}")(now)
        self.sounds.play_music(self.music_for_state())

    def music_for_state(self):
        """Pick the music track for what is on screen (no-op if unchanged)."""
        st = self.state
        if st in ("menu", "select") or (st == "settings" and self.settings_return == "menu"):
            return "menu"
        if st == "cutscene":
            final = self.level >= constants.MAX_LEVELS and self.boss is not None and not self.boss.alive
            return "ending" if final else "story"
        if st == "shop":
            return "shop"
        if st == "victory":
            return "ending"
        if self.boss is not None and self.boss.alive and self.boss.awake:
            return "boss"
        return "act2" if self.level_cfg.get("act") == 2 else "act1"

    # ------------------------------------------------------------------
    # Screens
    # ------------------------------------------------------------------
    def state_menu(self, now):
        s, a = self.screen, self.assets
        W, H = constants.SCREEN_WIDTH, constants.SCREEN_HEIGHT
        s.fill(constants.MENU_BG)
        draw_text(s, "DUNGEON CRAWLER", a.font_big, constants.YELLOW, W // 2, 50, center=True)
        draw_text(s, "THE SEAL OF VEL DURAN", a.font_small, constants.WHITE, W // 2, 84, center=True)
        self._place(self.start_button, 108)
        self._place(self.settings_button, 213)
        self._place(self.exit_button, 318)
        if self.start_button.draw(s, self.input.pressed):
            if self.forced_hero:
                self.new_game(self.forced_hero)
            else:
                self.state = "select"
            return
        if self.exit_button.draw(s, self.input.pressed) or pygame.K_ESCAPE in self.input.pressed:
            self.running = False
            return
        if self.settings_button.draw(s, self.input.pressed):
            self.open_settings("menu")
            return
        self._draw_controls(H - 90)

    @staticmethod
    def _place(button, y):
        """Centre a button horizontally at height y (buttons are shared by
        several screens, each with its own layout)."""
        button.rect.midtop = (constants.SCREEN_WIDTH // 2, y)

    def open_settings(self, return_to):
        self.settings_return = return_to
        self.settings_bg = self.screen.copy()
        self.state = "settings"
        self.assets.play("ui_confirm")

    def state_settings(self, now):
        if self.settings_screen.update_and_draw(self.screen, self.input.pressed, now, self.settings_bg):
            self.state = self.settings_return
            Mouse.held = False

    def _draw_controls(self, y):
        s, a = self.screen, self.assets
        lines = ["WASD move   SHIFT dash   E / right-click ability   H potion",
                 "ARROWS attack   SPACE auto-aim   F auto-fire   M map",
                 "mouse: hold left button to attack   ESC pause"]
        for i, t in enumerate(lines):
            draw_text(s, t, a.font_small, constants.WHITE, constants.SCREEN_WIDTH // 2, y + i * 18, center=True)

    def state_select(self, now):
        res = self.hero_select.update_and_draw(self.screen, self.input.pressed, now)
        if res == "back":
            self.state = "menu"
        elif res is not None:
            self.new_game(res)

    def state_cutscene(self, now):
        if self.cutscene is None:              # defensive: never get stuck
            self.state = "menu"
            return
        if self.cutscene.update_and_draw(self.screen, self.input.pressed, now):
            self.cutscene = None
            nxt, self.after_cutscene = self.after_cutscene, None
            nxt()

    def state_pause(self, now):
        s = self.screen
        self.draw_world(now)
        veil = pygame.Surface((constants.SCREEN_WIDTH, constants.SCREEN_HEIGHT), pygame.SRCALPHA)
        veil.fill((60, 0, 0, 200))
        s.blit(veil, (0, 0))
        self._place(self.resume_button, 70)
        self._place(self.restart_button, 170)
        self._place(self.settings_button, 270)
        self._place(self.exit_button, 370)
        if self.resume_button.draw(s, self.input.pressed) or pygame.K_ESCAPE in self.input.pressed \
                or pygame.K_p in self.input.pressed:
            self.state = "play"
            Mouse.held = False
        elif self.restart_button.draw(s, self.input.pressed):
            self.load_level(self.level, restore_snapshot=True)
            self.state = "play"
        elif self.exit_button.draw(s, self.input.pressed):
            self.state = "menu"
        elif self.settings_button.draw(s, self.input.pressed):
            self.open_settings("pause")
            return
        self._draw_controls(constants.SCREEN_HEIGHT - 70)

    def state_shop(self, now):
        done = self.shop.handle_and_draw(self.screen, self.player, self.level + 1, self.input.pressed, now)
        if self.player.weapon.tier != self.player.weapon_tier:       # bought at the Forge
            self.player.weapon = make_weapon(self.hero, self.player.weapon_tier, self.assets)
        if done:
            self.level += 1
            self.play_cutscene(lore.SCENE_BEFORE_LEVEL.get(self.level, []), self._enter_level)

    def state_dead(self, now):
        self.draw_world(now)
        if self.death_fade.fade(self.screen):
            draw_text(self.screen, "YOU DIED", self.assets.font_big, constants.WHITE,
                      constants.SCREEN_WIDTH // 2, 120, center=True)
            self._place(self.restart_button, 220)
            self._place(self.exit_button, 340)
            if self.restart_button.draw(self.screen, self.input.pressed):
                self.load_level(self.level, restore_snapshot=True)
                self.player.health = self.player.max_hp
                self.state = "play"
            elif self.exit_button.draw(self.screen, self.input.pressed):
                self.state = "menu"

    def state_victory(self, now):
        s, a, p = self.screen, self.assets, self.player
        W = constants.SCREEN_WIDTH
        s.fill((20, 30, 20))
        draw_text(s, "VICTORY!", a.font_big, constants.YELLOW, W // 2, 90, center=True)
        draw_text(s, f"{self.hero.name} {self.hero.title}", a.font_med, constants.WHITE, W // 2, 140, center=True)
        frames = a.animation(self.hero.key, 1.5)[0]
        img = frames[(now // 140) % len(frames)]
        s.blit(img, img.get_rect(midbottom=(W // 2, 300)))
        mins = (now - self.start_time) // 60000
        secs = (now - self.start_time) // 1000 % 60
        for i, t in enumerate((f"Enemies slain: {p.kills}", f"Gold earned:   {p.coins_earned}",
                               f"Time:          {mins}m {secs:02d}s")):
            draw_text(s, t, a.font_med, constants.WHITE, W // 2 - 170, 330 + i * 34)
        draw_text(s, "ENTER - back to menu", a.font_small, constants.GREY, W // 2, 500, center=True)
        if pygame.K_RETURN in self.input.pressed or Mouse.released:
            self.state = "menu"

    # ------------------------------------------------------------------
    # Gameplay
    # ------------------------------------------------------------------
    def nearest_visible_enemy(self, max_range=constants.AUTO_AIM_RANGE):
        best, best_d = None, max_range
        for e in self.enemies:
            if not e.alive or e.has_status("bones", pygame.time.get_ticks()):
                continue
            d = e.dist_to(self.player)
            if d < best_d and self.world.line_of_sight(self.player.rect.center, e.rect.center):
                best, best_d = e, d
        return best

    def resolve_aim(self, now):
        """(aim_angle, fire) from all input sources - touchpad-friendly priority."""
        inp, p = self.input, self.player
        ax, ay = inp.aim_vector()
        if ax or ay:
            return math.degrees(math.atan2(-ay, ax)), True
        if pygame.K_SPACE in inp.held or self.auto_fire:
            target = self.nearest_visible_enemy()
            if target:
                return angle_to(p.rect.center, target.rect.center), True
            if pygame.K_SPACE in inp.held:
                dx, dy = p.last_move_dir
                return math.degrees(math.atan2(-dy, dx)), True
        ox, oy = self.camera.offset
        mx, my = pygame.mouse.get_pos()
        mouse_world = (mx + ox, my + oy)
        if Mouse.held:
            return angle_to(p.rect.center, mouse_world), True
        if now - inp.mouse_moved_at < 1500:
            return angle_to(p.rect.center, mouse_world), False
        return None, False

    def state_play(self, now):
        p, w, a, inp = self.player, self.world, self.assets, self.input

        if pygame.K_ESCAPE in inp.pressed or pygame.K_p in inp.pressed:
            a.play("pause")
            self.state = "pause"
            inp.pressed -= {pygame.K_ESCAPE, pygame.K_p}
            self.state_pause(now)
            return
        if pygame.K_f in inp.pressed:
            self.auto_fire = not self.auto_fire
        if pygame.K_m in inp.pressed or pygame.K_TAB in inp.pressed:
            self.show_minimap = not self.show_minimap
        if pygame.K_h in inp.pressed and p.potions > 0 and p.health < p.max_hp:
            p.potions -= 1
            self.heal_player(25)
            a.play("potion_drink")
        if (pygame.K_LSHIFT in inp.pressed or pygame.K_RSHIFT in inp.pressed) and p.alive:
            if p.try_dash(now):
                a.play("dash")
        if (pygame.K_e in inp.pressed or pygame.K_q in inp.pressed or inp.right_click) and p.alive \
                and now >= p.ability_ready_at:
            if ABILITIES[p.hero.ability.key](self, now):
                p.ability_ready_at = now + p.ability_cd
                a.play("ability_" + p.hero.ability.key)
        ready = now >= p.ability_ready_at
        if ready and not self.ability_was_ready:
            a.play("ability_ready")
        self.ability_was_ready = ready

        # ---- player ------------------------------------------------------
        on_exit = False
        if p.alive:
            mx, my = inp.move_vector()
            on_exit = p.move(mx, my, w, now)
            aim, fire = self.resolve_aim(now)
            if aim is not None:
                p.aim_angle = aim
            if not p.has_status("whirlwind", now):
                p.weapon.update(self, aim, fire, now)
            else:
                whirlwind_tick(self, now)
            if p.has_status("regen", now) and now >= getattr(p, "regen_tick", 0):
                p.regen_tick = now + 250
                p.heal(1)
            if p.has_status("poison", now) and now >= p.next_poison_tick:
                p.next_poison_tick = now + 500
                self.damage_player(3, now, bypass_iframes=True)
        p.update(now)

        # ---- world simulation ----------------------------------------------
        for e in list(self.enemies):
            e.update(self, now)
        self._separate_enemies()
        for shot in list(self.player_shots):
            shot.update(self, now)
        for proj in list(self.projectiles):
            proj.update(self, now)
        for hz in list(self.hazards):
            hz.update(self, now)

        # ---- deaths & loot ---------------------------------------------------
        for e in [e for e in self.enemies if not e.alive]:
            self.enemies.remove(e)
            p.kills += 1
            a.play("boss_defeated" if e.is_boss else "enemy_death")
            e.on_death(self)
            if p.hero.flags.get("heal_on_kill"):
                p.heal(p.hero.flags["heal_on_kill"])
            self.drop_coins(e.rect.centerx, e.rect.centery, e.coin_drop())
            if e.is_boss:
                self.camera.shake(12, 700)
                self.projectiles.empty()
                for m in self.enemies:          # minions crumble with their master
                    if m.alive:
                        m.health, m.alive = 0, False
                self.say_banner("BOSS DEFEATED", "Clear the remaining monsters!", now, 2500)
                self.drop_flask(e.rect.centerx, e.rect.centery, force=True)
            elif random.random() < (0.08 if not e.elite else 0.6):
                self.drop_flask(e.rect.centerx, e.rect.centery, force=True)

        for item in list(self.items):
            item.update(self, now)
        self.texts.update()

        self.world.reveal(p.rect)
        self.camera.follow(p.rect, 16)
        self.draw_world(now)

        self._check_unlock(now)
        if on_exit:
            if self.exit_locked:
                if not self.banner or now > self.banner[2]:
                    n = self.enemies_left
                    sub = ("Defeat the boss first!" if self.boss is not None and self.boss.alive
                           else f"{n} monster{'s' if n != 1 else ''} still lurk on this floor")
                    self.say_banner("LOCKED", sub, now, 1400)
            else:
                self.finish_level()
            return

        if self.intro_active and self.intro_fade.fade(self.screen):
            self.intro_active = False
        if not p.alive:
            self.state = "dead"
            a.play("player_death")
            a.play("game_over")
            pygame.mixer.music.fadeout(800) if self.sounds.enabled else None
            self.sounds.current_music = None

    def _separate_enemies(self):
        """Cheap soft-collision so enemies do not stack into one sprite."""
        live = [e for e in self.enemies if e.alive and e.awake and not e.leap]
        for i in range(len(live)):
            a = live[i]
            for b in live[i + 1:]:
                dx = b.rect.centerx - a.rect.centerx
                dy = b.rect.centery - a.rect.centery
                min_d = (a.rect.width + b.rect.width) * 0.45
                d2 = dx * dx + dy * dy
                if 0 < d2 < min_d * min_d:
                    d = math.sqrt(d2)
                    push = (min_d - d) * 0.25
                    ux, uy = dx / d, dy / d
                    if not a.is_boss:
                        a.fx, a.fy, _, _ = self.world.move_rect(a.rect, a.fx, a.fy, -ux * push, -uy * push)
                    if not b.is_boss:
                        b.fx, b.fy, _, _ = self.world.move_rect(b.rect, b.fx, b.fy, ux * push, uy * push)

    def draw_world(self, now):
        s, a, cam, p = self.screen, self.assets, self.camera, self.player
        s.fill((14, 10, 18) if self.level_cfg.get("act") == 2 else constants.BG)
        self.world.draw(s, cam, self.exit_locked)
        for hz in self.hazards:
            if hz.layer == 0:
                hz.draw(s, cam, now)
        for item in self.items:
            item.draw(s, cam)
        actors = sorted([e for e in self.enemies if e.alive] + [p], key=lambda o: o.rect.bottom)
        for actor in actors:
            actor.draw(s, cam, now)
            if actor is p and p.alive and not p.has_status("whirlwind", now):
                p.weapon.draw(s, cam, now, p)
        if p.has_status("whirlwind", now):
            img = pygame.transform.rotate(p.weapon.image, (now * 1.4) % 360)
            r = cam.apply(p.rect)
            for k in range(2):
                ang = math.radians((now * 1.4) % 360 + k * 180)
                s.blit(img, img.get_rect(center=(r.centerx + math.cos(ang) * 50, r.centery - math.sin(ang) * 50)))
        for shot in self.player_shots:
            shot.draw(s, cam)
        for proj in self.projectiles:
            proj.draw(s, cam)
        for hz in self.hazards:
            if hz.layer == 1:
                hz.draw(s, cam, now)
        for t in self.texts:
            t.draw(s, cam)
        if self.show_minimap:
            hunt = [e for e in self.enemies if e.alive]
            self.world.draw_minimap(s, p.rect, hunt if len(hunt) <= self.HUNT_REVEAL else None, now)
        self.draw_hunt_arrows(now)
        draw_hud(s, a, p, self.level, self.auto_fire, now)
        n = self.enemies_left
        if n:
            draw_text(s, f"FOES LEFT {n}", a.font_tiny, (255, 120, 110), 482, 6, shadow=False)
        else:
            draw_text(s, "LADDER OPEN", a.font_tiny, constants.GREEN, 482, 6, shadow=False)
        if self.boss and self.boss.alive and self.boss.awake:
            draw_boss_bar(s, a, self.boss)
        if self.banner and now < self.banner[2]:
            draw_banner(s, a, self.banner[0], self.banner[1])


def parse_args():
    level, hero = 1, None
    if "--level" in sys.argv:
        try:
            level = max(1, min(constants.MAX_LEVELS, int(sys.argv[sys.argv.index("--level") + 1])))
        except (IndexError, ValueError):
            pass
    if "--hero" in sys.argv:
        try:
            hero = sys.argv[sys.argv.index("--hero") + 1]
        except IndexError:
            pass
    return level, hero


def main():
    audio = True
    try:
        pygame.mixer.init()
    except pygame.error:
        audio = False
    pygame.init()
    pygame.display.set_mode((constants.SCREEN_WIDTH, constants.SCREEN_HEIGHT))
    pygame.display.set_caption("Dungeon Crawler - The Seal of Vel Duran")
    level, hero = parse_args()
    Game(start_level=level, audio=audio, hero_key=hero).run()


if __name__ == "__main__":
    main()
