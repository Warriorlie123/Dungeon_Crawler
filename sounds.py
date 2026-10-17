"""
sounds.py - sound effects, music and volume control.

How it works
------------
* SFX lists every sound the game can play: a KEY, a short description (also
  written to assets/audio/sfx/SOUND_LIST.txt so the sound designer knows
  what is needed), a base volume, and a FALLBACK key.
* The bundled sounds were synthesised from scratch by tools/make_sounds.py
  (retro / chiptune style, no licence issues). Replace any of them with a
  recording of your own by dropping a file with the same name in the folder.
* On start-up SoundBank looks for  assets/audio/sfx/<key>.wav|.ogg|.mp3
  (wav or ogg recommended). Anything missing falls back to its fallback
  sound (e.g. "sword_swing" -> "melee_whoosh" -> the original "shot"), or is
  silent. So you can add sounds ONE FILE AT A TIME - just drop a correctly
  named file in the folder and restart the game. No code changes needed.
* Volume = master x (music | sfx) x per-sound base volume. The three user
  levels are stored in settings.json next to main.py (see settings.py).
* A per-key throttle stops the same sound from being triggered dozens of
  times in a single frame (24 arrows from Arrow Storm = one sound).

Music works the same way: MUSIC maps a track key to a file name in
assets/audio/music/ with the original music.wav as the fallback for all.
"""
import os
import pygame
import constants

SFX_DIR = constants.asset_path("audio", "sfx")
MUSIC_DIR = constants.asset_path("audio", "music")
EXTS = (".wav", ".ogg", ".mp3")

# key: (description, base volume, fallback key or None)
SFX = {
    # ---- original sounds (already in assets/audio) ---------------------------
    "shot":            ("(original) arrow_shot.mp3", 0.5, None),
    "hit":             ("(original) arrow_hit.wav", 0.5, None),
    "coin":            ("(original) coin.wav", 0.4, None),
    "heal":            ("(original) heal.wav", 0.5, None),

    # ---- hero weapons: one per hero --------------------------------------------
    "melee_whoosh":    ("generic weapon swing whoosh (fallback for all melee)", 0.5, "shot"),
    "sword_swing":     ("Sir Aldric - sword swing, metallic whoosh", 0.5, "melee_whoosh"),
    "spear_thrust":    ("Dame Rowena - quick spear/sword thrust with a holy shimmer", 0.5, "melee_whoosh"),
    "axe_swing":       ("Borin - heavy axe swing, deep whoosh", 0.55, "melee_whoosh"),
    "hammer_smash":    ("Hilda - hammer swing with a heavy thud", 0.55, "melee_whoosh"),
    "bow_twang":       ("Faelar - bow string release", 0.5, "shot"),
    "bow_quick":       ("Sylwen - short, light bow shot", 0.45, "bow_twang"),
    "knife_throw":     ("Ssarik - thrown knife whizz", 0.45, "shot"),
    "blade_slash":     ("Vexa - fast thin blade slash", 0.5, "melee_whoosh"),
    "fire_cast":       ("Ignatius - fire bolt cast (fwoosh)", 0.5, "shot"),
    "frost_cast":      ("Isolde - ice bolt cast (crystal chime)", 0.5, "shot"),
    "melee_hit":       ("weapon hits flesh (melee impact)", 0.5, "hit"),

    # ---- abilities: one per hero -------------------------------------------------
    "ability_bulwark":      ("Bulwark - shield raise, metallic clang", 0.6, None),
    "ability_consecration": ("Consecration - holy choir burst", 0.6, None),
    "ability_whirlwind":    ("Whirlwind - spinning wind loop (~3s)", 0.6, None),
    "ability_powder_keg":   ("Powder Keg - bomb throw + fuse hiss", 0.6, None),
    "ability_arrow_rain":   ("Arrow Storm - many bows firing at once", 0.6, "bow_twang"),
    "ability_focus":        ("Hunter's Focus - deep breath / power-up", 0.6, None),
    "ability_smoke_step":   ("Smoke Step - poof + vanish", 0.6, "teleport"),
    "ability_venom":        ("Venom Edge - hiss / blade coating", 0.6, None),
    "ability_meteor":       ("Meteor - incoming fireball whistle", 0.6, None),
    "ability_frost_nova":   ("Frost Nova - ice burst / shatter", 0.6, None),

    # ---- player ---------------------------------------------------------------------
    "player_hurt":     ("player takes damage (grunt / hit)", 0.45, "hit"),
    "player_death":    ("player dies", 0.5, None),
    "dash":            ("dash whoosh", 0.4, None),
    "shield_block":    ("Guardian Rune absorbs a hit (glass ding)", 0.6, None),
    "ability_ready":   ("ability cooldown finished (soft ping)", 0.35, None),

    # ---- enemies -----------------------------------------------------------------------
    "enemy_death":     ("generic monster death (squish / poof)", 0.45, None),
    "enemy_shoot":     ("enemy fires a projectile (whoosh)", 0.22, None),
    "bones_rise":      ("skeleton reassembles (rattling bones)", 0.5, None),
    "teleport":        ("teleport puff (chort / bosses)", 0.45, None),
    "explosion":       ("bomb / meteor explosion", 0.6, None),
    "bomb_throw":      ("bomb or flask thrown (short whoosh)", 0.4, None),
    "splash":          ("poison flask shatters on the floor", 0.45, None),
    "spikes":          ("spike trap shoots up", 0.3, None),
    "freeze":          ("enemy frozen (ice crackle)", 0.45, None),

    # ---- bosses ----------------------------------------------------------------------
    "boss_roar":       ("boss notices you / fight starts (roar)", 0.7, None),
    "boss_slam":       ("boss ground slam (deep boom)", 0.7, "explosion"),
    "boss_defeated":   ("boss dies (big crash + reverb)", 0.8, "explosion"),

    # ---- world / items --------------------------------------------------------------
    "chest_open":      ("treasure chest opens", 0.55, None),
    "mimic":           ("mimic reveals itself (chomp + growl)", 0.6, None),
    "crate_break":     ("wooden crate breaks", 0.5, None),
    "potion_drink":    ("drink a flask (gulp)", 0.5, "heal"),
    "exit_unlock":     ("floor cleared - the ladder unlocks (chime + latch)", 0.6, "ability_ready"),
    "level_complete":  ("climbing down the ladder / level done", 0.45, None),

    # ---- UI ----------------------------------------------------------------------------
    "ui_move":         ("menu cursor moves (tick)", 0.25, None),
    "ui_confirm":      ("menu confirm", 0.35, None),
    "ui_back":         ("menu back / cancel", 0.3, None),
    "shop_buy":        ("purchase (cash register / coins)", 0.4, "coin"),
    "shop_deny":       ("cannot afford (buzz)", 0.3, None),
    "forge":           ("weapon upgraded at the Forge (anvil clang)", 0.6, "shop_buy"),
    "text_blip":       ("cutscene typewriter blip (very short)", 0.1, None),
    "pause":           ("game paused", 0.4, None),

    # ---- jingles -------------------------------------------------------------------------
    "game_over":       ("GAME OVER jingle (2-4s)", 0.8, None),
    "victory":         ("final victory fanfare (3-6s)", 0.8, None),
}

# music key: (file name without extension, description)
MUSIC = {
    "menu":    ("menu", "main menu & hero select (loop)"),
    "act1":    ("act1", "levels 1-10, the Undercroft (loop)"),
    "act2":    ("act2", "levels 11-20, the Hollow Deep - darker (loop)"),
    "boss":    ("boss", "boss fights (loop, intense)"),
    "shop":    ("shop", "Grizzle's shop - calm, a bit silly (loop)"),
    "story":   ("story", "cutscenes - atmospheric (loop)"),
    "ending":  ("ending", "ending / victory screen"),
}
MUSIC_FALLBACK = constants.asset_path("audio", "music.wav")
if constants.IS_WEB:
    # the browser build ships Ogg Vorbis copies of every sound
    EXTS = (".ogg", ".wav", ".mp3")
    MUSIC_FALLBACK = constants.asset_path("audio", "music.ogg")
ORIGINAL_FILES = {"shot": "arrow_shot.mp3", "hit": "arrow_hit.wav", "coin": "coin.wav", "heal": "heal.wav"}


class SoundBank:
    THROTTLE_MS = 45

    def __init__(self, settings, enabled=True):
        self.settings = settings
        self.enabled = enabled and pygame.mixer.get_init() is not None
        self.sounds = {}            # key -> pygame Sound actually loaded
        self.last_played = {}
        self.current_music = None
        if not self.enabled:
            return
        pygame.mixer.set_num_channels(32)
        for key in SFX:
            snd = self._load(key)
            if snd:
                self.sounds[key] = snd
        self.apply_volumes()

    # ------------------------------------------------------------------
    def _find(self, folder, name):
        for ext in EXTS:
            path = os.path.join(folder, name + ext)
            if os.path.exists(path):
                return path
        return None

    def _load(self, key):
        path = self._find(SFX_DIR, key)
        if path is None and key in ORIGINAL_FILES:
            name = ORIGINAL_FILES[key]
            if constants.IS_WEB:
                name = os.path.splitext(name)[0] + ".ogg"
            path = constants.asset_path("audio", name)
        if path is None:
            return None
        try:
            return pygame.mixer.Sound(path)
        except pygame.error:
            return None

    def resolve(self, key):
        """Follow the fallback chain until a loaded sound is found."""
        seen = set()
        while key and key not in self.sounds and key not in seen:
            seen.add(key)
            key = SFX.get(key, ("", 0, None))[2]
        return key if key in self.sounds else None

    def missing(self):
        return [k for k in SFX if k not in self.sounds]

    # ------------------------------------------------------------------
    def apply_volumes(self):
        if not self.enabled:
            return
        s = self.settings
        for key, snd in self.sounds.items():
            snd.set_volume(SFX[key][1] * s.master * s.sfx)
        pygame.mixer.music.set_volume(0.5 * s.master * s.music)

    def play(self, key, volume=1.0):
        if not self.enabled:
            return
        real = self.resolve(key)
        if real is None:
            return
        now = pygame.time.get_ticks()
        if now - self.last_played.get(key, -10_000) < self.THROTTLE_MS:
            return
        self.last_played[key] = now
        snd = self.sounds[real]
        ch = snd.play()
        if ch is not None and volume != 1.0:
            ch.set_volume(volume)

    def play_music(self, key, fade_ms=800):
        """Switch music track; keeps playing if it is already the current one."""
        if not self.enabled or key == self.current_music:
            return
        name = MUSIC.get(key, (key, ""))[0]
        path = self._find(MUSIC_DIR, name) or MUSIC_FALLBACK
        current_path = getattr(self, "_current_path", None)
        self.current_music = key
        if path == current_path:          # e.g. everything falls back to music.wav
            return
        self._current_path = path
        try:
            pygame.mixer.music.fadeout(fade_ms // 2)
            pygame.mixer.music.load(path)
            pygame.mixer.music.play(-1, 0.0, fade_ms)
            self.apply_volumes()
        except pygame.error:
            pass


def write_sound_list():
    """Generate assets/audio/sfx/SOUND_LIST.txt describing every slot."""
    os.makedirs(SFX_DIR, exist_ok=True)
    os.makedirs(MUSIC_DIR, exist_ok=True)
    lines = ["SOUND EFFECTS  ->  put files in assets/audio/sfx/  as <name>.wav (or .ogg / .mp3)",
             "Missing files are fine: the game falls back to a similar sound or stays silent.", ""]
    for key, (desc, _vol, fb) in SFX.items():
        if desc.startswith("(original)"):
            continue
        lines.append(f"{key + '.wav':28s} {desc}" + (f"   [fallback: {fb}]" if fb else ""))
    lines += ["", "MUSIC  ->  put files in assets/audio/music/  (loops, .ogg recommended)",
              "Missing tracks fall back to the original assets/audio/music.wav", ""]
    for key, (name, desc) in MUSIC.items():
        lines.append(f"{name + '.ogg':28s} {desc}")
    with open(os.path.join(SFX_DIR, "SOUND_LIST.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    write_sound_list()
    print("wrote", os.path.join(SFX_DIR, "SOUND_LIST.txt"))
