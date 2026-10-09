"""
hero_select.py - the "choose your hero" screen.

Layout: a 5 x 2 grid of animated hero cards (classes in columns, female on
top, male below) and an info panel describing the highlighted hero: role,
weapon, ability, passive, stat bars and a short bio.

Controls: arrow keys / WASD move the highlight, ENTER confirms, ESC goes
back. Mouse: hover highlights, click confirms. All keyboard-reachable for
touchpad users.
"""
import pygame
import constants
from heroes import HEROES, max_tier
from ui import draw_text, Mouse

# column order: knight, dwarf, elf, lizard, wizard ; row 0 = female, row 1 = male
GRID = [[h for h in HEROES if h.key == f"{c}_{g}"][0]
        for g in ("f", "m") for c in ("knight", "dwarf", "elf", "lizard", "wizzard")]


class HeroSelect:
    COLS, CARD_W, CARD_H = 5, 140, 120

    def __init__(self, assets):
        self.assets = assets
        self.index = 0
        self.card_rects = []
        x0 = (constants.SCREEN_WIDTH - (self.COLS * self.CARD_W + (self.COLS - 1) * 12)) // 2
        for i in range(len(GRID)):
            col, row = i % self.COLS, i // self.COLS
            self.card_rects.append(pygame.Rect(x0 + col * (self.CARD_W + 12), 56 + row * (self.CARD_H + 10),
                                               self.CARD_W, self.CARD_H))

    def update_and_draw(self, surface, keys_pressed, now):
        """Returns a Hero when chosen, "back" on ESC, else None."""
        a = self.assets
        W = constants.SCREEN_WIDTH
        # ---- input --------------------------------------------------------
        col, row = self.index % self.COLS, self.index // self.COLS
        for k in keys_pressed:
            if k in (pygame.K_LEFT, pygame.K_a):
                col = (col - 1) % self.COLS
            elif k in (pygame.K_RIGHT, pygame.K_d):
                col = (col + 1) % self.COLS
            elif k in (pygame.K_UP, pygame.K_w, pygame.K_DOWN, pygame.K_s):
                row = 1 - row
        if row * self.COLS + col != self.index:
            self.assets.play("ui_move")
        self.index = row * self.COLS + col
        mouse = pygame.mouse.get_pos()
        moved = pygame.mouse.get_rel() != (0, 0)     # read once per frame (it resets)
        for i, r in enumerate(self.card_rects):
            if r.collidepoint(mouse) and (Mouse.pressed or moved):
                self.index = i
        chosen = None
        if pygame.K_RETURN in keys_pressed or pygame.K_KP_ENTER in keys_pressed or pygame.K_SPACE in keys_pressed:
            chosen = GRID[self.index]
        if Mouse.released and self.card_rects[self.index].collidepoint(mouse):
            chosen = GRID[self.index]
        if pygame.K_ESCAPE in keys_pressed:
            self.assets.play("ui_back")
            return "back"
        if chosen:
            self.assets.play("ui_confirm")

        # ---- draw -----------------------------------------------------------
        surface.fill((18, 14, 24))
        draw_text(surface, "CHOOSE YOUR HERO", a.font, constants.YELLOW, W // 2, 26, center=True)
        for i, (hero, rect) in enumerate(zip(GRID, self.card_rects)):
            sel = i == self.index
            pygame.draw.rect(surface, (55, 45, 70) if sel else (34, 28, 44), rect, border_radius=6)
            pygame.draw.rect(surface, constants.YELLOW if sel else (70, 60, 90), rect, 2, border_radius=6)
            frames = a.animation(hero.key)[1 if sel else 0]
            img = frames[(now // 110) % len(frames)]
            surface.blit(img, img.get_rect(midbottom=(rect.centerx - 18, rect.bottom - 22)))
            w_img = a.weapon(hero.tiers[0][0], 2.0)
            surface.blit(w_img, w_img.get_rect(midbottom=(rect.centerx + 34, rect.bottom - 26)))
            draw_text(surface, hero.role.upper(), a.font_tiny, constants.WHITE if sel else constants.GREY,
                      rect.centerx, rect.bottom - 11, center=True, shadow=False)

        # ---- info panel -------------------------------------------------------
        h = GRID[self.index]
        panel = pygame.Rect(30, 320, W - 60, 268)
        pygame.draw.rect(surface, (30, 24, 40), panel, border_radius=8)
        pygame.draw.rect(surface, (90, 75, 110), panel, 2, border_radius=8)
        x, y = panel.x + 18, panel.y + 14
        draw_text(surface, f"{h.name.upper()} {h.title}", a.font_med, constants.YELLOW, x, y)
        draw_text(surface, h.role, a.font_small, constants.CYAN, x, y + 22)
        weapons = " > ".join(t[0].replace("_", " ") for t in h.tiers)
        draw_text(surface, f"Weapon: {weapons}", a.font_tiny, constants.GREY, x, y + 40, shadow=False)

        draw_text(surface, f"[E] {h.ability.name}  ({h.ability.cooldown_ms // 1000}s)", a.font_small,
                  constants.WHITE, x, y + 62)
        self._wrapped(surface, h.ability.desc, x + 12, y + 80, 470)
        draw_text(surface, f"Passive: {h.passive_name}", a.font_small, constants.WHITE, x, y + 118)
        self._wrapped(surface, h.passive_desc, x + 12, y + 136, 470)
        self._wrapped(surface, '"' + h.bio + '"', x, y + 172, 480, colour=(200, 180, 140))

        # stat bars
        bx = panel.right - 230
        stats = (("HEALTH", h.hp / 140), ("SPEED", (h.speed - 4.0) / 1.5),
                 ("POWER", h.tiers[0][1] * 1000 / h.tiers[0][2] / 60),
                 ("RANGE", {"melee": 0.3, "throw": 0.6, "staff": 0.8, "bow": 1.0}[h.weapon_kind]),
                 ("UPGRADES", max_tier(h) / 4),
                 ("ARMOR", h.flags.get("armor", 0) / 0.2))
        for i, (label, v) in enumerate(stats):
            yy = panel.y + 20 + i * 26
            draw_text(surface, label, a.font_tiny, constants.GREY, bx, yy + 2, shadow=False)
            pygame.draw.rect(surface, (50, 44, 60), (bx + 90, yy, 110, 10))
            pygame.draw.rect(surface, constants.GREEN, (bx + 90, yy, int(110 * max(0.08, min(1, v))), 10))
        draw_text(surface, "ARROWS choose   ENTER start   ESC back", a.font_tiny, constants.GREY,
                  W // 2, panel.bottom - 14, center=True, shadow=False)
        return chosen

    def _wrapped(self, surface, text, x, y, width, colour=(190, 190, 190)):
        font = self.assets.font_tiny
        words, line, row = text.split(), "", 0
        for w in words + [None]:
            test = (line + " " + w).strip() if w else line
            if w is None or font.size(test)[0] > width:
                draw_text(surface, line, font, colour, x, y + row * 13, shadow=False)
                row += 1
                line = w or ""
            else:
                line = test
