"""
shop.py - Grizzle the goblin merchant: spend coins between levels.

Design
------
* The catalogue is DATA (ShopItem list). `apply` mutates the Player; price
  grows per purchase (price_step); `max_stack` caps it; `only` restricts an
  item to ranged or melee heroes (multishot is pointless on a sword).
* THE FORGE (always offered while upgrades remain) moves the hero's weapon
  up a tier - new sprite, more damage. Staff users "empower" instead.
* Each visit: Healing + Forge + 4 random items. Reroll for a fee.
* Haggler passive (dwarf_f) gives a discount; Grizzle comments on it.
* Fully keyboard operable: 1-6 buy, R reroll, ENTER continue.
"""
import random
from dataclasses import dataclass
from typing import Callable
import pygame
import constants
from heroes import max_tier
from ui import draw_text, Mouse


@dataclass
class ShopItem:
    key: str
    name: str
    desc: str
    base_price: int
    price_step: int
    max_stack: int
    apply: Callable
    always: bool = False
    only: str = None            # None | "ranged" | "melee"

    def price(self, bought, discount=0.0):
        return max(1, int((self.base_price + self.price_step * bought) * (1 - discount)))


def _heal(p):    p.heal(40)
def _max_hp(p):  p.max_hp += 20; p.heal(20)
def _damage(p):  p.damage_mult += 0.2
def _rate(p):    p.fire_rate_mult *= 0.87
def _multi(p):   p.multishot += 1
def _pierce(p):  p.pierce += 1
def _reach(p):   p.reach_mult += 0.15
def _speed(p):   p.speed_mult += 0.08
def _magnet(p):  p.magnet += 60
def _shield(p):  p.shields += 1
def _dash(p):    p.dash_cd_mult *= 0.75
def _crit(p):    p.crit_chance += 0.07
def _potion(p):  p.potions += 1
def _focus(p):   p.ability_cd_mult *= 0.85
def _forge(p):   p.weapon_tier += 1      # Game rebuilds the weapon object


CATALOGUE = [
    ShopItem("heal",   "Healing Draught", "Restore 40 HP now",              6, 2, 99, _heal, always=True),
    ShopItem("forge",  "THE FORGE",       "Upgrade your weapon a tier",    25, 25, 99, _forge, always=True),
    ShopItem("potion", "Spare Potion",    "Carry one, H to drink",          8, 2, 99, _potion),
    ShopItem("maxhp",  "Heart Container", "+20 max HP",                    18, 10, 6, _max_hp),
    ShopItem("dmg",    "Whetstone",       "+20% damage",                   15, 10, 8, _damage),
    ShopItem("rate",   "Quick Hands",     "Attack 13% faster",             15, 10, 5, _rate),
    ShopItem("multi",  "Split Shot",      "+1 projectile per attack",      30, 25, 2, _multi, only="ranged"),
    ShopItem("pierce", "Piercing Tips",   "Shots pass +1 enemy",           22, 15, 3, _pierce, only="ranged"),
    ShopItem("reach",  "Long Grip",       "+15% melee reach & arc",        18, 12, 3, _reach, only="melee"),
    ShopItem("speed",  "Swift Boots",     "+8% move speed",                12, 8, 3, _speed),
    ShopItem("magnet", "Coin Magnet",     "Bigger coin pickup radius",     10, 8, 3, _magnet),
    ShopItem("shield", "Guardian Rune",   "Block the next hit",            14, 6, 5, _shield),
    ShopItem("dash",   "Shadow Step",     "Dash cooldown -25%",            14, 10, 2, _dash),
    ShopItem("crit",   "Eagle Eye",       "+7% critical chance",           16, 10, 4, _crit),
    ShopItem("focus",  "Arcane Focus",    "Ability cooldown -15%",         20, 14, 3, _focus),
]
REROLL_PRICE = 4

QUIPS = [
    "Everything must go! Mostly because monsters keep eating my stock.",
    "No refunds. No returns. No questions about where the swords came from.",
    "Ah, a returning customer! Still alive, I see. Good for business.",
    "Prices are higher down here. Danger pricing. Very modern.",
    "Buy something or I start charging for the oxygen.",
    "I sold the last hero a shield. Ask me how that went. Actually, don't.",
]


class Shop:
    def __init__(self, assets):
        self.assets = assets
        self.bought = {it.key: 0 for it in CATALOGUE}
        self.offer = []
        self.message, self.message_time = "", 0
        self.quip = random.choice(QUIPS)

    def reset(self):
        self.bought = {it.key: 0 for it in CATALOGUE}

    def _fits(self, it, player):
        if it.only == "ranged" and not player.hero.is_ranged:
            return False
        if it.only == "melee" and player.hero.is_ranged:
            return False
        if it.key == "forge":
            return player.weapon_tier < max_tier(player.hero)
        return self.bought[it.key] < it.max_stack

    def roll_offer(self, player):
        always = [it for it in CATALOGUE if it.always and self._fits(it, player)]
        rest = [it for it in CATALOGUE if not it.always and self._fits(it, player)]
        self.offer = always + random.sample(rest, min(6 - len(always), len(rest)))
        self.quip = random.choice(QUIPS)

    def discount(self, player):
        return player.hero.flags.get("discount", 0.0)

    def try_buy(self, idx, player, now):
        if idx >= len(self.offer):
            return False
        it = self.offer[idx]
        price = it.price(self.bought[it.key], self.discount(player))
        if not self._fits(it, player):
            self._say("Sold out!", now)
            self.assets.play("shop_deny")
        elif player.coins < price:
            self._say("Not enough coins!", now)
            self.assets.play("shop_deny")
        elif it.key == "heal" and player.health >= player.max_hp:
            self._say("Already at full health", now)
            self.assets.play("shop_deny")
        else:
            player.coins -= price
            it.apply(player)
            self.bought[it.key] += 1
            self.assets.play("forge" if it.key == "forge" else "shop_buy")
            self._say(f"Bought {it.name}", now)
            return True
        return False

    def try_reroll(self, player, now):
        if player.coins >= REROLL_PRICE:
            player.coins -= REROLL_PRICE
            self.roll_offer(player)
            self._say("New stock!", now)
            self.assets.play("ui_confirm")
        else:
            self._say("Not enough coins!", now)
            self.assets.play("shop_deny")

    def _say(self, msg, now):
        self.message, self.message_time = msg, now

    # ------------------------------------------------------------------
    def handle_and_draw(self, surface, player, next_level, keys_pressed, now):
        """
        Draw the shop; returns True when the player chooses to continue.

        Layout (800x600):
            top     merchant portrait, name, quip
            left    CHARACTER SHEET - every stat the shop can change, so the
                    effect of a purchase is visible immediately
            right   6 item cards (2 x 3), footer with controls + CONTINUE
        """
        a = self.assets
        W = constants.SCREEN_WIDTH
        surface.fill(constants.SHOP_BG)

        # ---- header -----------------------------------------------------------
        frames = a.animation("goblin", 1.2)[0]
        img = frames[(now // 140) % len(frames)]
        surface.blit(img, img.get_rect(midbottom=(44, 66)))
        draw_text(surface, "GRIZZLE'S WARES", a.font, constants.YELLOW, 84, 12)
        draw_text(surface, self.quip, a.font_tiny, (210, 200, 170), 84, 40, shadow=False)
        if self.discount(player):
            draw_text(surface, "Haggler: -15% on everything (grumble)", a.font_tiny, constants.GREEN, 84, 54,
                      shadow=False)
        draw_text(surface, f"Next: level {next_level}", a.font_small, constants.GREY, W - 150, 16)

        self._draw_sheet(surface, player, pygame.Rect(12, 76, 236, 440), now)

        # ---- item cards -----------------------------------------------------------
        mouse = pygame.mouse.get_pos()
        cw, ch, x0, y0 = 258, 92, 262, 76
        disc = self.discount(player)
        for i, it in enumerate(self.offer):
            col, row = i % 2, i // 2
            x, y = x0 + col * (cw + 10), y0 + row * (ch + 10)
            rect = pygame.Rect(x, y, cw, ch)
            bought = self.bought[it.key]
            price = it.price(bought, disc)
            sold_out = not self._fits(it, player)
            affordable = player.coins >= price and not sold_out
            hover = rect.collidepoint(mouse)
            pygame.draw.rect(surface, (60, 50, 70) if hover else (45, 38, 55), rect, border_radius=6)
            pygame.draw.rect(surface, constants.YELLOW if affordable else constants.DARK_GREY, rect, 2,
                             border_radius=6)
            draw_text(surface, f"{i + 1}", a.font, constants.YELLOW, x + 10, y + 10)
            draw_text(surface, it.name, a.font_small, constants.WHITE, x + 40, y + 12)
            desc = it.desc
            if it.key == "forge" and not sold_out:
                nxt = min(player.weapon_tier + 1, len(player.hero.tiers) - 1)
                if player.hero.weapon_kind == "staff":
                    desc = "Empower your staff"
                else:
                    desc = "-> " + player.hero.tiers[nxt][0].replace("_", " ")
                    w_img = a.weapon(player.hero.tiers[nxt][0], 2.0)
                    surface.blit(w_img, w_img.get_rect(midright=(rect.right - 12, rect.centery)))
            draw_text(surface, desc, a.font_tiny, constants.GREY, x + 40, y + 34, shadow=False)
            label = "SOLD OUT" if sold_out else f"{price} G"
            draw_text(surface, label, a.font_med, constants.YELLOW if affordable else constants.RED, x + 40, y + 60)
            if it.max_stack < 99:
                draw_text(surface, f"{bought}/{it.max_stack}", a.font_tiny, constants.GREY, x + cw - 44, y + 66,
                          shadow=False)
            if Mouse.released and hover:
                self.try_buy(i, player, now)

        for k in keys_pressed:
            if pygame.K_1 <= k <= pygame.K_6:
                self.try_buy(k - pygame.K_1, player, now)
            elif k == pygame.K_r:
                self.try_reroll(player, now)

        draw_text(surface, f"[1-6] buy   [R] reroll ({REROLL_PRICE} G)   [ENTER] continue",
                  a.font_tiny, constants.WHITE, 262 + 263, 400, center=True, shadow=False)
        cont = pygame.Rect(262 + 263 - 110, 470, 220, 40)
        hover = cont.collidepoint(mouse)
        pygame.draw.rect(surface, (90, 30, 30) if hover else (70, 20, 20), cont, border_radius=6)
        draw_text(surface, "CONTINUE", a.font_med, constants.WHITE, cont.centerx, cont.centery, center=True)
        if now - self.message_time < 1500 and self.message:
            draw_text(surface, self.message, a.font_med, constants.CYAN, 262 + 263, 435, center=True)
        return (Mouse.released and hover) or pygame.K_RETURN in keys_pressed or \
            pygame.K_SPACE in keys_pressed or pygame.K_KP_ENTER in keys_pressed

    def _draw_sheet(self, surface, p, rect, now):
        """Character sheet: portrait, gold, and every upgradeable stat."""
        a = self.assets
        h = p.hero
        pygame.draw.rect(surface, (30, 24, 40), rect, border_radius=8)
        pygame.draw.rect(surface, (90, 75, 110), rect, 2, border_radius=8)
        x, y = rect.x + 12, rect.y + 10
        frames = a.animation(h.key)[0]
        img = frames[(now // 140) % len(frames)]
        surface.blit(img, img.get_rect(bottomleft=(x, y + 84)))
        w_img = p.weapon.image
        surface.blit(w_img, w_img.get_rect(midbottom=(x + 72, y + 80)))
        draw_text(surface, h.name, a.font_small, constants.YELLOW, x + 92, y + 6)
        draw_text(surface, h.role, a.font_tiny, constants.CYAN, x + 92, y + 22, shadow=False)
        coin = a.coin_frames[(now // 150) % 4]
        surface.blit(coin, coin.get_rect(midleft=(x + 90, y + 52)))
        draw_text(surface, str(p.coins), a.font_med, constants.YELLOW, x + 116, y + 45)

        dmg = p.weapon.damage_for_sheet(p)
        rate = 1000 / (p.weapon.cooldown * p.fire_rate_mult)
        rows = [
            ("Health", f"{p.health}/{p.max_hp}"),
            ("Armor", f"{h.flags.get('armor', 0) * 100:.0f}% less dmg"),
            ("Weapon", p.weapon.sprite_name.replace("_magic", "").replace("_", " ")[:13]),
            ("Tier", f"{p.weapon_tier + 1}/{max_tier(h) + 1}"),
            ("Damage", f"{dmg:.0f}  (x{p.damage_mult:.2f})"),
            ("Attacks/sec", f"{rate:.1f}"),
            ("Crit chance", f"{p.crit_chance * 100:.0f}%"),
            ("Move speed", f"{p.speed_mult * h.speed / 5 * 100:.0f}%"),
        ]
        if h.is_ranged:
            rows.append(("Projectiles", f"{p.multishot}  pierce {p.pierce}"))
        else:
            rows.append(("Reach", f"{p.reach_mult * 100:.0f}%"))
        rows += [
            ("Dash cooldown", f"{1.2 * p.dash_cd_mult:.1f}s"),
            (f"{h.ability.name}", f"{p.ability_cd / 1000:.1f}s"),
            ("Shields", str(p.shields)),
            ("Potions", str(p.potions)),
            ("Coin magnet", f"{p.magnet}px"),
        ]
        yy = y + 96
        for label, val in rows:
            draw_text(surface, label, a.font_tiny, constants.GREY, x, yy, shadow=False)
            draw_text(surface, val, a.font_tiny, constants.WHITE, x + 112, yy, shadow=False)
            yy += 17
        yy += 8
        for title, body in ((f"[E] {h.ability.name}", h.ability.desc), (f"Passive: {h.passive_name}", h.passive_desc)):
            draw_text(surface, title, a.font_tiny, (230, 200, 120), x, yy, shadow=False)
            yy += 13
            line = ""
            for word in body.split() + [None]:
                test = (line + " " + word).strip() if word else line
                if word is None or a.font_tiny.size(test)[0] > rect.width - 26:
                    draw_text(surface, line, a.font_tiny, (180, 170, 160), x + 6, yy, shadow=False)
                    yy += 12
                    line = word or ""
                else:
                    line = test
            yy += 6
