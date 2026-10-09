"""
lore.py - the story of "The Seal of Vel Duran" and the cutscene player.

Scenes are DATA: a list of (speaker, portrait, text) lines. `portrait` is an
atlas animation name ("angel", "ogre", ...), "{hero}" for the player's hero,
a LIST of names (drawn as a little line-up, used by the narrator), or None. Text may contain {hero_name}, {hero_title} and
{role}, filled in at runtime, so every hero gets the same story told
about THEM.

When scenes play (see SCENE_AFTER_LEVEL / SCENE_BEFORE_LEVEL):
  before 1   intro + Act I card          after 3, 5, 8   boss epilogues
  after 10   Act I finale, Act II card   after 13, 15, 18 boss epilogues
  before 20  the final confrontation     after 20  ending + hero epilogue
"""
import math
import pygame
import constants
from ui import draw_text, Mouse

NARRATOR = None
VOICE = "voice"       # the mysterious guiding voice (rendered as a glowing orb)

SCENES = {
    "intro": [
        ("", ["imp", "big_demon", "angel", "big_demon", "chort"],
         "Three hundred years ago, the archangel SERAPHIEL sealed a demon horde beneath "
         "the mountain city of Vel Duran."),
        ("", ["knight_f", "dwarf_m", "goblin", "wizzard_f", "elf_m"],
         "The city built a cathedral on top of the seal, a tavern on top of the "
         "cathedral, and a very confusing tax office on top of the tavern."),
        ("", ["tiny_zombie", "skelet", "slug", "goblin", "tiny_slug"],
         "Last spring, the cellars started breathing. Then they started biting."),
        ("ROYAL DECREE", NARRATOR, "WANTED: one (1) hero to clear the Undercroft. Reward: 10,000 gold. "
                                   "Funeral costs not included."),
        ("{hero_name}", "{hero}", "Ten thousand gold. Fine. How deep can a cellar possibly be?"),
        ("THE VOICE", VOICE, "...deeper than you think, little light. Come down. I will guide you."),
        ("{hero_name}", "{hero}", "...Did the dungeon just talk to me? Great. Wonderful. Very normal."),
    ],
    "act1": [("ACT I", NARRATOR, "THE UNDERCROFT")],
    "after_3": [
        ("OGRE CHIEFTAIN", "ogre", "Ugh... tell my mother... I was a good boy..."),
        ("{hero_name}", "{hero}", "You ate the last three adventurers."),
        ("OGRE CHIEFTAIN", "ogre", "...a good boy... with a healthy appetite."),
        ("THE VOICE", VOICE, "Well done, little light. The seal grows weaker. Go deeper."),
    ],
    "after_5": [
        ("BONE LORD", "skelet", "Fool... you think we climbed up here to INVADE?"),
        ("BONE LORD", "skelet", "We were not escaping the seal. We were FLEEING what is beneath it."),
        ("{hero_name}", "{hero}", "That's... ominous. Could you be more specific?"),
        ("BONE LORD", "skelet", "No. I am dying. Dramatically. Goodbye."),
    ],
    "after_8": [
        ("GRIZZLE", "goblin", "Psst. Merchant again. Did you notice my prices going up?"),
        ("{hero_name}", "{hero}", "Every. Single. Floor."),
        ("GRIZZLE", "goblin", "It's called 'danger pricing'. Very modern. Also a giant zombie ate my cart."),
        ("THE VOICE", VOICE, "Ignore the goblin. Only two more halls stand between us."),
        ("{hero_name}", "{hero}", "'Between us'? Are you... waiting for me?"),
        ("THE VOICE", VOICE, "...Hurry."),
    ],
    "after_10": [
        ("DEMON BRUTE", "big_demon", "Hah... you think *I* was cracking the seal?"),
        ("DEMON BRUTE", "big_demon", "I was its JAILER, fool. I kept the door shut. Three centuries of "
                                     "door duty. No breaks."),
        ("DEMON BRUTE", "big_demon", "Now the way is open. She will be... so grateful..."),
        ("{hero_name}", "{hero}", "Who is 'she'? Hello? Don't die mid-sentence, that's so rude."),
        ("THE VOICE", VOICE, "Thank you, little light. The Hollow Deep is open. Come to me. Quickly."),
    ],
    "act2": [("ACT II", NARRATOR, "THE HOLLOW DEEP")],
    "after_13": [
        ("DR. MORBIUS", "doc", "The rot in these halls... it is not a disease, hero."),
        ("DR. MORBIUS", "doc", "It is GRIEF. Three hundred years of it, seeping through the stone."),
        ("{hero_name}", "{hero}", "Whose grief?"),
        ("DR. MORBIUS", "doc", "Ask the voice that whispers to you. Ask her why she cries at night."),
    ],
    "after_15": [
        ("ARCHMAGE NECROS", "necromancer", "So. You are the latest one she lured down."),
        ("ARCHMAGE NECROS", "necromancer", "The voice that guides you is SERAPHIEL. The seal never held the "
                                           "demons. It held HER - she bound herself as its lock."),
        ("ARCHMAGE NECROS", "necromancer", "Three centuries alone in the dark. It broke her. She has been "
                                           "opening the way one hero at a time."),
        ("{hero_name}", "{hero}", "So the kind, helpful voice is... the final boss."),
        ("ARCHMAGE NECROS", "necromancer", "Yes. Obviously. Did the creepy whispering not tip you off?"),
    ],
    "after_18": [
        ("PUMPKIN KING", "pumpkin_dude", "Wait wait wait! I was just the gardener! She MADE me king!"),
        ("{hero_name}", "{hero}", "You threw two hundred bombs at me."),
        ("PUMPKIN KING", "pumpkin_dude", "...Gardening is a very stressful job."),
        ("THE VOICE", VOICE, "You were supposed to KNEEL, little light. Not fight my children."),
    ],
    "before_20": [
        ("SERAPHIEL", "angel", "Every one of them came down for gold. Do you know what gold is worth "
                               "in the dark, {role}?"),
        ("SERAPHIEL", "angel", "Nothing. Light is worth something. And yours is so very bright."),
        ("{hero_name}", "{hero}", "I'm flattered. I'm also going to hit you a lot."),
        ("SERAPHIEL", "angel", "Then come. Let us see whose light lasts longer."),
    ],
    "ending": [
        ("SERAPHIEL", "angel", "...Ah. The dark is... quiet now."),
        ("SERAPHIEL", "angel", "I was so tired, little light. Thank you for letting me rest."),
        ("", ["angel"], "The seal knitted itself closed around the sleeping angel - gently this time, "
                        "like a blanket instead of a cage."),
        ("", ["{hero}"], "{hero_name} climbed back into the sunlight to collect the reward."),
        ("ROYAL TREASURER", NARRATOR, "Ten thousand gold, minus the 40% dungeon cleaning tax, the "
                                      "torch usage fee, and the overtime for this conversation."),
        ("{hero_name}", "{hero}", "{epilogue}"),
    ],
}

# Per-hero last line of the ending.
EPILOGUES = {
    "knight_m": "I'm going back to guarding the gate. It's quiet. Nothing talks to me from the floor.",
    "knight_f": "I shall pray for her. And then file a complaint about that tax.",
    "dwarf_m": "Six thousand gold. Enough to buy back my beard. Long story.",
    "dwarf_f": "Next time I'm just blowing up the whole mountain. Saves a lot of walking.",
    "elf_m": "Found my good bow on floor 17, by the way. Worth it.",
    "elf_f": "I'm keeping one of the pumpkins. Don't ask.",
    "lizard_m": "Technically, I was paid to kill a monster. I'll call it 'complicated'.",
    "lizard_f": "Twenty floors, forty swords. My collection is complete. ...For now.",
    "wizzard_m": "And I only set myself on fire NINE times. A personal record.",
    "wizzard_f": "This will make an excellent thesis chapter. 'On Angels, Grief, and Cold Damage'.",
}

SCENE_BEFORE_LEVEL = {1: ["intro", "act1"], 11: ["act2"], 20: ["before_20"]}
SCENE_AFTER_LEVEL = {3: "after_3", 5: "after_5", 8: "after_8", 10: "after_10",
                     13: "after_13", 15: "after_15", 18: "after_18", 20: "ending"}


class Cutscene:
    """
    Plays one or more scenes with a typewriter effect.
    ENTER / SPACE / click: finish the line, then next line.  ESC: skip all.
    """
    CHARS_PER_MS = 0.045

    def __init__(self, assets, scene_keys, hero):
        self.assets = assets
        self.hero = hero
        self.lines = []
        for k in scene_keys:
            self.lines.extend(SCENES[k])
        self.index = 0
        self.line_start = None
        self.done = False

    def _fmt(self, text):
        return text.format(hero_name=self.hero.name, hero_title=self.hero.title, role=self.hero.role.lower(),
                           epilogue=EPILOGUES.get(self.hero.key, ""))

    def _fit(self, key, target_h):
        """Scale factor so a sprite is ~target_h px tall whatever its source size
        (16px imps and 36px demons should look similar in a portrait)."""
        frame = self.assets.animation(key)[0][0]
        return round(max(0.8, min(3.0, target_h / frame.get_height())), 2)

    def _wrap(self, text, font, width):
        words, lines, cur = text.split(" "), [], ""
        for w in words:
            test = (cur + " " + w).strip()
            if font.size(test)[0] > width:
                lines.append(cur)
                cur = w
            else:
                cur = test
        if cur:
            lines.append(cur)
        return lines

    def update_and_draw(self, surface, keys_pressed, now):
        if self.done:
            return True
        if self.line_start is None:
            self.line_start = now
        speaker, portrait, text = self.lines[self.index]
        text = self._fmt(text)
        speaker = self._fmt(speaker)
        shown = min(len(text), int((now - self.line_start) * self.CHARS_PER_MS) + 1)
        if shown != getattr(self, "_last_shown", None) and shown < len(text) and shown % 3 == 0:
            self.assets.play("text_blip")
        self._last_shown = shown

        advance = Mouse.released or pygame.K_RETURN in keys_pressed or pygame.K_SPACE in keys_pressed \
            or pygame.K_KP_ENTER in keys_pressed
        if pygame.K_ESCAPE in keys_pressed:
            self.done = True
            return True
        if advance:
            if shown < len(text):
                self.line_start = -10 ** 9           # reveal whole line
            else:
                self.index += 1
                self.line_start = now
                if self.index >= len(self.lines):
                    self.done = True
                    return True
                speaker, portrait, text = self.lines[self.index]
                text, speaker = self._fmt(text), self._fmt(speaker)
                shown = 1

        W, H = constants.SCREEN_WIDTH, constants.SCREEN_HEIGHT
        a = self.assets
        surface.fill((12, 8, 16))
        # Title cards ("ACT I") get their own big layout
        if speaker.startswith("ACT"):
            draw_text(surface, speaker, a.font_big, constants.YELLOW, W // 2, H // 2 - 40, center=True)
            draw_text(surface, text, a.font, constants.WHITE, W // 2, H // 2 + 10, center=True)
            draw_text(surface, "ENTER", a.font_small, constants.GREY, W // 2, H - 40, center=True)
            return False

        # Portrait
        px, py = 150, 250
        if portrait == VOICE:
            pulse = 30 + 8 * math.sin(now / 200)
            for r, al in ((pulse + 30, 40), (pulse + 15, 80), (pulse, 200)):
                s = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
                pygame.draw.circle(s, (255, 240, 190, al), (r, r), int(r))
                surface.blit(s, (px - r, py - r))
        elif isinstance(portrait, list):
            # narrator montage: characters standing in a row on a strip of floor
            n = len(portrait)
            floor = a.act2["floors"][0]
            for i in range(-1, W // floor.get_width() + 1):
                surface.blit(floor, (i * floor.get_width(), 300))
            for i, name in enumerate(portrait):
                key = self.hero.key if name == "{hero}" else name
                frames = a.animation(key, self._fit(key, 90 if n > 1 else 150))[0]
                img = frames[(now // 140 + i) % len(frames)]
                cx = W // 2 + (i - (n - 1) / 2) * 130
                surface.blit(img, img.get_rect(midbottom=(cx, 330)))
        elif portrait:
            key = self.hero.key if portrait == "{hero}" else portrait
            frames = a.animation(key, self._fit(key, 150))[0]
            img = frames[(now // 140) % len(frames)]
            surface.blit(img, img.get_rect(midbottom=(px, py + 90)))

        # Text box
        box = pygame.Rect(40, 380, W - 80, 180)
        pygame.draw.rect(surface, (30, 24, 40), box, border_radius=8)
        pygame.draw.rect(surface, (120, 100, 150), box, 2, border_radius=8)
        if speaker:
            draw_text(surface, speaker, a.font_med, constants.YELLOW, box.x + 20, box.y + 16)
        # Wrap the FULL line first, then reveal characters across the wrapped
        # rows - otherwise words would jump between rows while typing.
        budget = shown
        for i, ln in enumerate(self._wrap(text, a.font_small, box.width - 40)[:7]):
            part = ln[:max(0, budget)]
            budget -= len(ln) + 1
            if part:
                draw_text(surface, part, a.font_small, constants.WHITE, box.x + 20, box.y + 48 + i * 18,
                          shadow=False)
        draw_text(surface, "ENTER next   ESC skip", a.font_tiny, constants.GREY, box.right - 190, box.bottom - 18,
                  shadow=False)
        draw_text(surface, f"{self.index + 1}/{len(self.lines)}", a.font_tiny, constants.GREY, box.x + 20,
                  box.bottom - 18, shadow=False)
        return False
