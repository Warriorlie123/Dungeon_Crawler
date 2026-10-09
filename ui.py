"""
ui.py - buttons, HUD, floating text, screen transitions.

Button fix
----------
The original Button returned True on EVERY frame the mouse button was held
down over it. Holding the click for ~100 ms therefore triggered the action
6 times, and the click "leaked" into the game (e.g. pressing RESUME also
fired an arrow because the button was still down on the next frame).
The new Button fires once, on RELEASE, and only if the press also started
on the button - the standard behaviour of desktop UI toolkits.
Buttons can additionally be activated with the keyboard (`hotkey`), which
matters for touchpad users.
"""
import math
import pygame
import constants


def draw_text(surface, text, font, colour, x, y, center=False, shadow=True):
    img = font.render(text, True, colour)
    rect = img.get_rect()
    if center:
        rect.center = (x, y)
    else:
        rect.topleft = (x, y)
    if shadow:
        sh = font.render(text, True, (0, 0, 0))
        surface.blit(sh, rect.move(2, 2))
    surface.blit(img, rect)
    return rect


class Mouse:
    """
    Tracks mouse button EDGES (pressed this frame / released this frame).
    Updated once per frame from the event queue by main.py.
    """
    pressed = False      # went down this frame
    released = False     # went up this frame
    held = False

    @classmethod
    def begin_frame(cls):
        cls.pressed = cls.released = False

    @classmethod
    def handle(cls, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            cls.pressed = True
            cls.held = True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            cls.released = True
            cls.held = False


class Button:
    click_sound = None          # set by Game: callable played on every click

    def __init__(self, x, y, image, hotkey=None):
        self.image = image
        self.rect = self.image.get_rect(topleft=(x, y))
        self.armed = False
        self.hotkey = hotkey

    def draw(self, surface, keys_pressed=()):
        """Draw and return True exactly once per completed click/keypress."""
        action = False
        pos = pygame.mouse.get_pos()
        over = self.rect.collidepoint(pos)
        if Mouse.pressed and over:
            self.armed = True
        if Mouse.released:
            if self.armed and over:
                action = True
            self.armed = False
        if self.hotkey is not None and self.hotkey in keys_pressed:
            action = True
        if action and Button.click_sound:
            Button.click_sound()
        img = self.image
        if over:
            img = self.image.copy()
            img.fill((40, 40, 40, 0), special_flags=pygame.BLEND_RGBA_ADD)
        surface.blit(img, self.rect)
        return action


class FloatingText(pygame.sprite.Sprite):
    """Damage numbers / pickups. Lives in WORLD coordinates."""

    def __init__(self, x, y, text, colour, font, life=40):
        super().__init__()
        self.image = font.render(text, True, colour)
        self.rect = self.image.get_rect(center=(x, y))
        self.counter = 0
        self.life = life

    def update(self):
        self.rect.y -= 1
        self.counter += 1
        if self.counter > self.life:
            self.kill()

    def draw(self, surface, camera):
        surface.blit(self.image, camera.apply(self.rect))


class ScreenFade:
    """Same visual effect as the original, kept for familiarity."""

    def __init__(self, direction, colour, speed):
        self.direction = direction
        self.colour = colour
        self.speed = speed
        self.fade_counter = 0

    def fade(self, screen):
        W, H = constants.SCREEN_WIDTH, constants.SCREEN_HEIGHT
        self.fade_counter += self.speed
        if self.direction == 1:   # whole-screen "doors opening" reveal
            pygame.draw.rect(screen, self.colour, (0 - self.fade_counter, 0, W // 2, H))
            pygame.draw.rect(screen, self.colour, (W // 2 + self.fade_counter, 0, W, H))
            pygame.draw.rect(screen, self.colour, (0, 0 - self.fade_counter, W, H // 2))
            pygame.draw.rect(screen, self.colour, (0, H // 2 + self.fade_counter, W, H))
        elif self.direction == 2:  # curtain falling down
            pygame.draw.rect(screen, self.colour, (0, 0, W, 0 + self.fade_counter))
        # FIX: the vertical fade compared against SCREEN_WIDTH (800) although
        # it only needs SCREEN_HEIGHT (600) - the death menu appeared late.
        limit = W if self.direction == 1 else H
        return self.fade_counter >= limit


def draw_hud(surface, assets, player, level, auto_fire, now):
    W = constants.SCREEN_WIDTH
    pygame.draw.rect(surface, constants.PANEL, (0, 0, W, constants.HUD_HEIGHT))
    pygame.draw.line(surface, constants.WHITE, (0, constants.HUD_HEIGHT), (W, constants.HUD_HEIGHT))

    # Hearts: each heart = 20 HP. Max HP can grow, so draw max_hp/20 hearts
    # (shrinking them if there are many).
    n_hearts = min(12, math.ceil(player.max_hp / 20))   # cap: HUD space is finite
    step = 50 if n_hearts <= 6 else max(26, 300 // n_hearts)
    for i in range(n_hearts):
        hp_here = player.health - i * 20
        img = assets.heart_full if hp_here >= 20 else assets.heart_half if hp_here > 0 else assets.heart_empty
        if step < 50:
            img = pygame.transform.scale(img, (step - 2, step - 2))
        surface.blit(img, (6 + i * step, 0 if step == 50 else 8))

    # Shield charges as cyan pips under the hearts
    for i in range(player.shields):
        pygame.draw.circle(surface, constants.CYAN, (14 + i * 14, 44), 5)

    x0 = 330
    draw_text(surface, f"LVL {level}", assets.font_small, constants.WHITE, x0, 5, shadow=False)
    if auto_fire:
        draw_text(surface, "AUTO-FIRE", assets.font_tiny, constants.GREEN, x0 + 70, 6, shadow=False)

    def bar(y, frac, colour, label):
        frac = max(0.0, min(1.0, frac))
        pygame.draw.rect(surface, constants.DARK_GREY, (x0, y, 80, 7))
        pygame.draw.rect(surface, colour if frac >= 1 else constants.GREY, (x0, y, int(80 * frac), 7))
        draw_text(surface, label, assets.font_tiny, constants.WHITE if frac >= 1 else constants.GREY,
                  x0 + 86, y, shadow=False)
    cd_total = constants.DASH_COOLDOWN_MS * player.dash_cd_mult
    bar(21, 1 - (player.dash_ready_at - now) / cd_total, constants.CYAN, "SHIFT dash")
    bar(35, 1 - (player.ability_ready_at - now) / max(1, player.ability_cd), constants.YELLOW,
        "E " + player.hero.ability.name)

    # Potions
    surface.blit(assets.potion, (W - 215, 10))
    draw_text(surface, f"{player.potions}", assets.font, constants.WHITE, W - 185, 15)
    # Coins (animated icon)
    coin = assets.coin_frames[(now // 150) % 4]
    surface.blit(coin, coin.get_rect(center=(W - 120, 25)))
    draw_text(surface, f"{player.coins}", assets.font, constants.YELLOW, W - 100, 15)



def draw_boss_bar(surface, assets, boss):
    W = constants.SCREEN_WIDTH
    w = 500
    x = (W - w) // 2
    y = constants.SCREEN_HEIGHT - 40
    pygame.draw.rect(surface, constants.BLACK, (x - 3, y - 3, w + 6, 22))
    pygame.draw.rect(surface, (90, 0, 0), (x, y, w, 16))
    pygame.draw.rect(surface, constants.RED, (x, y, int(w * boss.health / boss.max_hp), 16))
    draw_text(surface, boss.name, assets.font_med, constants.WHITE, W // 2, y - 14, center=True)
    # phase pips: one per phase, lit while that phase is still ahead
    n = len(boss.btype.phases)
    for i in range(n - 1):
        thr = boss.btype.phases[i][0]
        px = x + int(w * thr)
        pygame.draw.line(surface, constants.WHITE, (px, y), (px, y + 15), 2)


def draw_banner(surface, assets, text, sub=None, alpha=255):
    W, H = constants.SCREEN_WIDTH, constants.SCREEN_HEIGHT
    band = pygame.Surface((W, 90), pygame.SRCALPHA)
    band.fill((0, 0, 0, min(170, alpha)))
    surface.blit(band, (0, H // 2 - 70))
    draw_text(surface, text, assets.font_big, constants.YELLOW, W // 2, H // 2 - 40, center=True)
    if sub:
        draw_text(surface, sub, assets.font_small, constants.WHITE, W // 2, H // 2, center=True)
