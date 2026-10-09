"""
settings.py - persistent user options (volume etc.) and the settings screen.

Settings are saved to settings.json next to main.py whenever they change,
so they survive restarts. The file is plain JSON on purpose: easy to inspect
or delete to reset everything. Unknown/corrupt files fall back to defaults
instead of crashing the game.

The screen is opened from the main menu (O / SETTINGS button) and from the
pause menu (O). Controls: UP/DOWN pick a row, LEFT/RIGHT change it,
ESC/ENTER goes back. Mouse: click or drag on a slider.
"""
import json
import os
from dataclasses import dataclass, asdict
import pygame
import constants
from ui import draw_text, Mouse

SETTINGS_FILE = os.path.join(constants.BASE_DIR, "settings.json")


@dataclass
class Settings:
    master: float = 0.8
    music: float = 0.6
    sfx: float = 0.8
    screen_shake: bool = True

    @classmethod
    def load(cls):
        try:
            with open(SETTINGS_FILE) as f:
                data = json.load(f)
            s = cls()
            for k, v in data.items():
                if hasattr(s, k):
                    setattr(s, k, type(getattr(s, k))(v))
            s.clamp()
            return s
        except (OSError, ValueError, TypeError):
            return cls()

    def clamp(self):
        for k in ("master", "music", "sfx"):
            setattr(self, k, round(max(0.0, min(1.0, getattr(self, k))), 2))

    def save(self):
        try:
            with open(SETTINGS_FILE, "w") as f:
                json.dump(asdict(self), f, indent=2)
        except OSError:
            pass          # read-only folder: settings just won't persist


class SettingsScreen:
    ROWS = [("master", "MASTER VOLUME"), ("music", "MUSIC"), ("sfx", "SOUND EFFECTS"),
            ("screen_shake", "SCREEN SHAKE"), ("back", "BACK")]

    def __init__(self, assets, settings, soundbank):
        self.assets, self.settings, self.sounds = assets, settings, soundbank
        self.index = 0
        self.dragging = None
        self.bar_rects = {}

    def _change(self, key, delta):
        s = self.settings
        if key == "screen_shake":
            s.screen_shake = not s.screen_shake
        else:
            setattr(s, key, getattr(s, key) + delta)
            s.clamp()
        self.sounds.apply_volumes()
        if key in ("sfx", "master"):
            self.sounds.play("ui_move")      # instant feedback at the new volume
        s.save()

    def update_and_draw(self, surface, keys_pressed, now, background=None):
        """Returns True when the player leaves the screen."""
        a = self.assets
        W, H = constants.SCREEN_WIDTH, constants.SCREEN_HEIGHT
        # ---- keyboard ---------------------------------------------------------
        for k in keys_pressed:
            if k in (pygame.K_UP, pygame.K_w):
                self.index = (self.index - 1) % len(self.ROWS)
                self.sounds.play("ui_move")
            elif k in (pygame.K_DOWN, pygame.K_s):
                self.index = (self.index + 1) % len(self.ROWS)
                self.sounds.play("ui_move")
            elif k in (pygame.K_LEFT, pygame.K_a, pygame.K_RIGHT, pygame.K_d):
                key = self.ROWS[self.index][0]
                if key != "back":
                    self._change(key, 0.1 if k in (pygame.K_RIGHT, pygame.K_d) else -0.1)
            elif k in (pygame.K_ESCAPE, pygame.K_o) or \
                    (k in (pygame.K_RETURN, pygame.K_SPACE) and self.ROWS[self.index][0] == "back"):
                self.sounds.play("ui_back")
                self.settings.save()
                return True
            elif k in (pygame.K_RETURN, pygame.K_SPACE) and self.ROWS[self.index][0] == "screen_shake":
                self._change("screen_shake", 0)

        # ---- mouse --------------------------------------------------------------
        mx, my = pygame.mouse.get_pos()
        if Mouse.pressed:
            for key, r in self.bar_rects.items():
                if r.inflate(0, 16).collidepoint(mx, my):
                    if key == "screen_shake":
                        self._change(key, 0)
                    elif key == "back":
                        self.sounds.play("ui_back")
                        self.settings.save()
                        return True
                    else:
                        self.dragging = key
        if not Mouse.held and self.dragging:
            self.settings.save()
            self.dragging = None
        if self.dragging:
            r = self.bar_rects[self.dragging]
            setattr(self.settings, self.dragging, (mx - r.x) / r.width)
            self.settings.clamp()
            self.sounds.apply_volumes()

        # ---- draw ------------------------------------------------------------------
        if background is not None:
            surface.blit(background, (0, 0))
            veil = pygame.Surface((W, H), pygame.SRCALPHA)
            veil.fill((10, 6, 16, 240))
            surface.blit(veil, (0, 0))
        else:
            surface.fill((18, 14, 24))
        draw_text(surface, "SETTINGS", a.font_big, constants.YELLOW, W // 2, 80, center=True)
        for i, (key, label) in enumerate(self.ROWS):
            y = 170 + i * 70
            sel = i == self.index
            col = constants.YELLOW if sel else constants.WHITE
            if key == "back":
                r = pygame.Rect(W // 2 - 90, y, 180, 36)
                pygame.draw.rect(surface, (70, 20, 20) if not sel else (110, 35, 35), r, border_radius=6)
                draw_text(surface, label, a.font_med, constants.WHITE, r.centerx, r.centery, center=True)
                self.bar_rects[key] = r
                continue
            draw_text(surface, label, a.font_med, col, 150, y + 4)
            r = pygame.Rect(430, y + 6, 220, 14)
            self.bar_rects[key] = r
            if key == "screen_shake":
                txt = "ON" if self.settings.screen_shake else "OFF"
                draw_text(surface, f"< {txt} >", a.font_med, col, r.x, y + 4)
                continue
            v = getattr(self.settings, key)
            pygame.draw.rect(surface, (50, 44, 60), r, border_radius=4)
            pygame.draw.rect(surface, constants.GREEN if sel else (90, 170, 100),
                             (r.x, r.y, int(r.width * v), r.height), border_radius=4)
            pygame.draw.circle(surface, constants.WHITE, (r.x + int(r.width * v), r.centery), 9)
            draw_text(surface, f"{int(v * 100)}%", a.font_small, col, r.right + 20, y + 6)
        draw_text(surface, "UP/DOWN select   LEFT/RIGHT adjust   ESC back   (mouse: drag)",
                  a.font_tiny, constants.GREY, W // 2, H - 30, center=True, shadow=False)
        if not self.sounds.enabled:
            draw_text(surface, "No audio device found - sound is disabled", a.font_small, constants.RED,
                      W // 2, H - 60, center=True)
        return False
