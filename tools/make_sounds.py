"""
tools/make_sounds.py - procedurally synthesise every sound effect and music
track the game uses (retro / chiptune style), from pure maths.

    python tools/make_sounds.py            # writes assets/audio/sfx/*.wav
                                           #    and assets/audio/music/*.ogg

Why synthesise?
---------------
* 100% original audio: no licences, no attribution, no download needed.
* Matches the 16-bit pixel-art look (think sfxr / bfxr style effects).
* Deterministic (fixed random seed) - re-running gives identical files.
* Any file can still be replaced by a "real" recording later: just overwrite
  it with the same name (see sounds.py / SOUND_LIST.txt).

Building blocks (all operate on numpy float arrays in [-1, 1]):
    osc()        oscillators: sine / square / saw / triangle, with a pitch
                 that may change over time (pass an array of Hz)
    noise()      white noise
    env_*()      amplitude envelopes (attack-decay, exponential decay)
    lowpass()/highpass()/bandpass()  simple one-pole IIR filters (fast
                 enough in numpy via scipy.signal.lfilter)
    pluck()      Karplus-Strong plucked string (bow strings!)
    metal()      inharmonic partials = bells, anvils, clangs
    whoosh()     band-passed noise with a swept centre = weapon swings
Music uses a tiny step sequencer: chord progression -> bass, arpeggio,
pad and drum voices, mixed and lightly echoed.
"""
import os
import sys
import wave
import numpy as np
from scipy.signal import lfilter, butter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SFX_DIR = os.path.join(ROOT, "assets", "audio", "sfx")
MUSIC_DIR = os.path.join(ROOT, "assets", "audio", "music")
SR = 22050                       # sample rate: plenty for retro sounds, small files
rng = np.random.default_rng(1234)


# ==========================================================================
# Primitive generators
# ==========================================================================
def t_axis(dur):
    return np.arange(int(SR * dur)) / SR


def osc(freq, dur, kind="sine", duty=0.5):
    """Oscillator. `freq` may be a number or an array (pitch sweep)."""
    n = int(SR * dur)
    f = np.full(n, float(freq)) if np.isscalar(freq) else np.resize(np.asarray(freq, float), n)
    phase = np.cumsum(f) / SR                     # integrate frequency -> phase
    frac = phase % 1.0
    if kind == "sine":
        return np.sin(2 * np.pi * phase)
    if kind == "square":
        return np.where(frac < duty, 1.0, -1.0)
    if kind == "saw":
        return 2.0 * frac - 1.0
    if kind == "tri":
        return 2.0 * np.abs(2.0 * frac - 1.0) - 1.0
    raise ValueError(kind)


def sweep(f0, f1, dur, curve="exp"):
    n = int(SR * dur)
    if curve == "exp":
        return f0 * (f1 / f0) ** np.linspace(0, 1, n)
    return np.linspace(f0, f1, n)


def noise(dur):
    return rng.uniform(-1, 1, int(SR * dur))


def env_ad(n_or_dur, attack=0.005, decay=None, curve=4.0):
    """Linear attack then exponential-ish decay to zero over the rest."""
    n = n_or_dur if isinstance(n_or_dur, int) else int(SR * n_or_dur)
    a = max(1, int(SR * attack))
    e = np.ones(n)
    e[:a] = np.linspace(0, 1, a)
    rest = n - a
    if rest > 0:
        e[a:] = (1 - np.linspace(0, 1, rest)) ** curve
    return e


def env_exp(dur, tau):
    return np.exp(-t_axis(dur) / tau)


def _filt(x, cutoff, btype, order=2):
    cutoff = np.clip(cutoff, 20, SR / 2 - 100)
    b, a = butter(order, cutoff / (SR / 2), btype=btype)
    return lfilter(b, a, x)


def lowpass(x, cutoff, order=2):
    return _filt(x, cutoff, "low", order)


def highpass(x, cutoff, order=2):
    return _filt(x, cutoff, "high", order)


def bandpass(x, lo, hi, order=2):
    b, a = butter(order, [max(30, lo) / (SR / 2), min(hi, SR / 2 - 200) / (SR / 2)], btype="band")
    return lfilter(b, a, x)


def swept_bandpass(x, f_start, f_end, q=0.35, chunks=24):
    """Approximate a moving band-pass by filtering consecutive chunks."""
    out = np.zeros_like(x)
    edges = np.linspace(0, len(x), chunks + 1).astype(int)
    for i in range(chunks):
        f = f_start * (f_end / f_start) ** (i / max(1, chunks - 1))
        seg = x[max(0, edges[i] - 200):edges[i + 1]]
        y = bandpass(seg, f * (1 - q), f * (1 + q))
        out[edges[i]:edges[i + 1]] = y[-(edges[i + 1] - edges[i]):]
    return out


def pluck(freq, dur, damp=0.996, bright=0.5):
    """Karplus-Strong: a noise burst circulating in a damped delay line."""
    n = int(SR * dur)
    period = int(SR / freq)
    buf = rng.uniform(-1, 1, period)
    out = np.zeros(n)
    for i in range(n):
        out[i] = buf[i % period]
        nxt = buf[(i + 1) % period]
        buf[i % period] = damp * (bright * buf[i % period] + (1 - bright) * nxt)
    return out


def metal(base, dur, ratios=(1.0, 2.76, 5.40, 8.93), tau=0.4, detune=0.0):
    """Inharmonic partials (bell / anvil). Higher partials decay faster."""
    t = t_axis(dur)
    out = np.zeros_like(t)
    for k, r in enumerate(ratios):
        f = base * r * (1 + detune * rng.uniform(-1, 1))
        out += np.sin(2 * np.pi * f * t) * np.exp(-t / (tau / (1 + 0.6 * k))) / (1 + k * 0.5)
    return out


def whoosh(dur, f0, f1, q=0.4, curve=1.5):
    """Weapon swing: band-passed noise sweeping f0 -> f1, swelling then fading."""
    x = swept_bandpass(noise(dur), f0, f1, q)
    n = len(x)
    e = np.sin(np.linspace(0, np.pi, n)) ** curve
    return x * e


def clicks(dur, rate, tone=2500, width=0.006):
    """Random short clicks (rattling bones, crackling ice/fire)."""
    out = np.zeros(int(SR * dur))
    for _ in range(int(rate * dur)):
        pos = rng.integers(0, len(out) - int(SR * width) - 1)
        c = bandpass(noise(width), tone * 0.6, tone * 1.6) * env_ad(int(SR * width), 0.0005)
        out[pos:pos + len(c)] += c * rng.uniform(0.4, 1.0)
    return out


def mix(*parts):
    n = max(len(p) for p in parts)
    out = np.zeros(n)
    for p in parts:
        out[:len(p)] += p
    return out


def msum(parts):
    """Mix a generator of sounds of different lengths (built-in sum() can't)."""
    return mix(*list(parts))


def at(x, offset):
    """Delay a sound by `offset` seconds (pad with silence)."""
    return np.concatenate([np.zeros(int(SR * offset)), x])


def echo(x, delay=0.12, fb=0.35, taps=4):
    out = x.copy()
    d = int(SR * delay)
    out = np.concatenate([out, np.zeros(d * taps)])
    for k in range(1, taps + 1):
        out[d * k:d * k + len(x)] += x * (fb ** k)
    return out


def drive(x, amount=2.0):
    """Soft clipping distortion (tanh) - grit for roars and explosions."""
    return np.tanh(x * amount) / np.tanh(amount)


def normalise(x, peak=0.89):
    m = np.max(np.abs(x)) or 1.0
    x = x / m * peak
    # 4 ms fade in/out to avoid clicks at the edges
    f = min(len(x) // 4, int(SR * 0.004))
    if f > 0:
        x[:f] *= np.linspace(0, 1, f)
        x[-f:] *= np.linspace(1, 0, f)
    return x


def save_wav(name, x, peak=0.89):
    x = normalise(np.asarray(x, float), peak)
    data = (x * 32767).astype(np.int16)
    with wave.open(os.path.join(SFX_DIR, name + ".wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data.tobytes())


def note(n):
    """MIDI note number -> Hz (A4 = 69 = 440 Hz)."""
    return 440.0 * 2 ** ((n - 69) / 12)


# ==========================================================================
# Sound effects
# ==========================================================================
def make_sfx():
    S = {}
    # ---- weapons ----------------------------------------------------------
    S["melee_whoosh"] = whoosh(0.18, 600, 2400)
    S["sword_swing"] = mix(whoosh(0.2, 800, 3200, 0.35), at(metal(1800, 0.25, tau=0.12) * 0.25, 0.05))
    S["spear_thrust"] = mix(whoosh(0.13, 1500, 4000, 0.3, 0.8),
                            at(osc(sweep(1500, 3000, 0.25), 0.25) * env_exp(0.25, 0.08) * 0.25, 0.04),
                            at(osc(sweep(2250, 4500, 0.25), 0.25) * env_exp(0.25, 0.06) * 0.15, 0.06))
    S["axe_swing"] = mix(lowpass(whoosh(0.3, 300, 1300, 0.45), 2500),
                         at(osc(sweep(140, 70, 0.2), 0.2) * env_exp(0.2, 0.06) * 0.4, 0.18))
    thud = osc(sweep(110, 45, 0.3), 0.3) * env_exp(0.3, 0.08)
    S["hammer_smash"] = mix(lowpass(whoosh(0.22, 250, 900), 1800) * 0.6,
                            at(thud + lowpass(noise(0.3), 600) * env_exp(0.3, 0.03) * 0.7, 0.17))
    S["bow_twang"] = mix(lowpass(pluck(196, 0.45, 0.994, 0.6), 4000),
                         highpass(noise(0.02), 3000) * env_ad(0.02) * 0.4,
                         at(whoosh(0.15, 2000, 5000) * 0.3, 0.02))
    S["bow_quick"] = mix(lowpass(pluck(294, 0.25, 0.99, 0.6), 5000),
                         at(whoosh(0.1, 3000, 6000) * 0.3, 0.01))
    S["knife_throw"] = mix(whoosh(0.14, 2500, 6000, 0.3, 0.7),
                           osc(sweep(3000, 1800, 0.14), 0.14) * env_exp(0.14, 0.05) * 0.2)
    S["blade_slash"] = mix(highpass(whoosh(0.1, 2500, 7000, 0.3, 0.6), 1500),
                           at(metal(3200, 0.12, tau=0.05) * 0.2, 0.03))
    fw = lowpass(noise(0.4), sweep(400, 2500, 0.4).mean()) * env_ad(0.4, 0.05, curve=2)
    S["fire_cast"] = mix(swept_bandpass(noise(0.4), 300, 1800, 0.6) * env_ad(0.4, 0.04, curve=2) * 1.2,
                         osc(sweep(90, 220, 0.4), 0.4, "saw") * env_ad(0.4, 0.02) * 0.15,
                         clicks(0.4, 40, 3000) * 0.3, fw * 0.3)
    S["frost_cast"] = mix(metal(1320, 0.5, ratios=(1, 1.5, 2.0, 3.01), tau=0.25) * 0.6,
                          at(metal(1980, 0.4, ratios=(1, 2.0, 3.0), tau=0.15) * 0.3, 0.05),
                          whoosh(0.2, 3000, 6000) * 0.25)
    S["melee_hit"] = mix(lowpass(noise(0.12), 1200) * env_exp(0.12, 0.025),
                         osc(sweep(180, 60, 0.12), 0.12) * env_exp(0.12, 0.04) * 0.8)

    # ---- abilities ------------------------------------------------------------
    S["ability_bulwark"] = mix(metal(330, 1.2, ratios=(1, 2.32, 4.25, 6.63), tau=0.6, detune=0.002),
                               lowpass(noise(0.05), 3000) * 0.5)
    chord = [note(n) for n in (60, 64, 67, 72)]
    t = t_axis(1.4)
    choir = sum(lowpass(osc(f * (1 + 0.004 * np.sin(2 * np.pi * 5 * t)), 1.4, "saw"), 1800) for f in chord)
    S["ability_consecration"] = mix(choir * env_ad(1.4, 0.25, curve=1.5) * 0.5,
                                    metal(1046, 1.2, ratios=(1, 2, 3), tau=0.4) * 0.3)
    w = noise(1.6)
    lfo = 0.5 + 0.5 * np.sin(2 * np.pi * 6 * t_axis(1.6))
    S["ability_whirlwind"] = swept_bandpass(w, 500, 1500, 0.5) * (0.4 + 0.6 * lfo) * env_ad(1.6, 0.15, curve=1)
    S["ability_powder_keg"] = mix(whoosh(0.25, 400, 1500),
                                  at(highpass(noise(0.6), 4000) * (0.5 + 0.5 * rng.uniform(0, 1, int(SR * 0.6)))
                                     * env_ad(0.6, 0.05, curve=1) * 0.35, 0.2))
    rain = np.zeros(int(SR * 0.9))
    for k in range(7):
        p = lowpass(pluck(rng.uniform(180, 300), 0.35, 0.99), 4000) * 0.5
        o = int(SR * rng.uniform(0, 0.4))
        rain[o:o + len(p)] += p
    S["ability_arrow_rain"] = mix(rain, whoosh(0.8, 2000, 6000) * 0.3)
    S["ability_focus"] = mix(osc(sweep(220, 880, 0.7), 0.7, "tri") * env_ad(0.7, 0.3, curve=1) * 0.4,
                             metal(1760, 0.6, ratios=(1, 2, 3), tau=0.3) * 0.25,
                             lowpass(noise(0.5), 800) * env_ad(0.5, 0.2, curve=1) * 0.3)
    poof = lowpass(noise(0.35), 1200) * env_exp(0.35, 0.07)
    S["ability_smoke_step"] = mix(poof, osc(sweep(900, 200, 0.3), 0.3) * env_exp(0.3, 0.08) * 0.3)
    bub = osc(140 + 60 * np.sin(2 * np.pi * 9 * t_axis(0.8)), 0.8) * 0.25
    S["ability_venom"] = mix(highpass(noise(0.8), 3500) * env_ad(0.8, 0.05, curve=1.5) * 0.6,
                             bub * env_ad(0.8, 0.1, curve=1.5))
    S["ability_meteor"] = mix(osc(sweep(2200, 250, 0.9), 0.9) * env_ad(0.9, 0.3, curve=0.5) * 0.4,
                              swept_bandpass(noise(0.9), 3000, 400, 0.5) * env_ad(0.9, 0.4, curve=0.6) * 0.6)
    shatter = msum(at(metal(rng.uniform(2000, 4500), 0.3, ratios=(1, 2.1, 3.3), tau=0.08) * 0.3,
                     rng.uniform(0, 0.25)) for _ in range(9))
    S["ability_frost_nova"] = mix(shatter, highpass(noise(0.5), 2500) * env_exp(0.5, 0.12) * 0.6,
                                  whoosh(0.5, 4000, 1500) * 0.4)

    # ---- player -------------------------------------------------------------------
    S["player_hurt"] = mix(osc(sweep(420, 140, 0.18), 0.18, "square", 0.3) * env_exp(0.18, 0.06) * 0.5,
                           lowpass(noise(0.1), 2000) * env_exp(0.1, 0.02) * 0.5)
    vib = 1 + 0.03 * np.sin(2 * np.pi * 7 * t_axis(1.1))
    S["player_death"] = mix(osc(sweep(520, 55, 1.1) * vib, 1.1, "square", 0.4) * env_ad(1.1, 0.01, curve=1.3) * 0.5,
                            lowpass(noise(1.1), 600) * env_exp(1.1, 0.3) * 0.3)
    S["dash"] = whoosh(0.16, 700, 3500, 0.45, 0.8)
    S["shield_block"] = mix(metal(2400, 0.6, ratios=(1, 1.5, 2.9), tau=0.25), lowpass(noise(0.03), 4000) * 0.3)
    S["ability_ready"] = mix(osc(note(84), 0.18, "tri") * env_exp(0.18, 0.06) * 0.6,
                             at(osc(note(91), 0.25, "tri") * env_exp(0.25, 0.08) * 0.6, 0.08))

    # ---- enemies -----------------------------------------------------------------
    S["enemy_death"] = mix(lowpass(noise(0.3), 1500) * env_exp(0.3, 0.06),
                           osc(sweep(320, 50, 0.3), 0.3, "square", 0.25) * env_exp(0.3, 0.08) * 0.35)
    S["enemy_shoot"] = mix(osc(sweep(900, 300, 0.15), 0.15, "square", 0.5) * env_exp(0.15, 0.05) * 0.3,
                           whoosh(0.15, 800, 2000) * 0.5)
    S["bones_rise"] = mix(clicks(0.7, 45, 1800), clicks(0.7, 25, 900) * 0.7)
    trem = 0.5 + 0.5 * np.sin(2 * np.pi * 30 * t_axis(0.35))
    S["teleport"] = mix(osc(sweep(300, 1600, 0.35), 0.35, "sine") * trem * env_ad(0.35, 0.02, curve=1) * 0.5,
                        lowpass(noise(0.3), 1500) * env_exp(0.3, 0.06) * 0.5)
    boom = lowpass(noise(1.2), 900) * env_exp(1.2, 0.25)
    S["explosion"] = drive(mix(boom, osc(sweep(80, 30, 1.0), 1.0) * env_exp(1.0, 0.3) * 0.9,
                               highpass(noise(0.08), 2000) * env_exp(0.08, 0.02) * 0.6), 1.8)
    S["bomb_throw"] = whoosh(0.2, 400, 1200, 0.5)
    S["splash"] = mix(highpass(noise(0.15), 3000) * env_exp(0.15, 0.03) * 0.6,
                      metal(2800, 0.2, ratios=(1, 1.7, 2.6), tau=0.05) * 0.3,
                      at(msum(at(osc(sweep(rng.uniform(300, 600), 900, 0.06), 0.06) * env_ad(0.06), rng.uniform(0, 0.3))
                             for _ in range(5)) * 0.4, 0.05))
    S["spikes"] = mix(highpass(noise(0.08), 2500) * env_exp(0.08, 0.02), metal(1500, 0.25, tau=0.08) * 0.4)
    S["freeze"] = mix(clicks(0.5, 70, 4000) * 0.8, metal(2600, 0.5, ratios=(1, 2.2), tau=0.2) * 0.3)

    # ---- bosses -------------------------------------------------------------------
    t = t_axis(1.4)
    pitch = 70 + 15 * np.sin(2 * np.pi * 3 * t) + sweep(90, 55, 1.4)
    roar = osc(pitch, 1.4, "saw") + 0.6 * lowpass(noise(1.4), 900)
    roar = bandpass(roar, 150, 1400) + 0.5 * bandpass(roar, 600, 1100)
    S["boss_roar"] = drive(roar * env_ad(1.4, 0.15, curve=1.4), 3.0)
    S["boss_slam"] = drive(mix(osc(sweep(70, 28, 1.0), 1.0) * env_exp(1.0, 0.25),
                               lowpass(noise(1.0), 500) * env_exp(1.0, 0.18) * 0.9,
                               highpass(noise(0.05), 1500) * env_exp(0.05, 0.01) * 0.5), 2.0)
    S["boss_defeated"] = mix(echo(S["explosion"], 0.18, 0.4, 4),
                             at(drive(osc(sweep(120, 35, 2.0), 2.0, "saw") * env_ad(2.0, 0.1, curve=1.2), 2) * 0.35, 0.2))

    # ---- world ----------------------------------------------------------------------
    creak = lowpass(osc(sweep(180, 260, 0.45) * (1 + 0.05 * rng.standard_normal(int(SR * 0.45)).cumsum() / 200),
                        0.45, "saw"), 900) * env_ad(0.45, 0.05, curve=1) * 0.5
    jingle = msum(at(metal(rng.uniform(2500, 4200), 0.25, ratios=(1, 2.4), tau=0.07) * 0.25, 0.35 + k * 0.06)
                 for k in range(5))
    S["chest_open"] = mix(creak, jingle)
    chomp = lambda: lowpass(noise(0.07), 2000) * env_exp(0.07, 0.015)
    growl = drive(bandpass(osc(sweep(95, 70, 0.6), 0.6, "saw") + lowpass(noise(0.6), 600), 120, 900), 3)
    S["mimic"] = mix(chomp(), at(chomp(), 0.12), at(growl * env_ad(0.6, 0.05, curve=1.5) * 0.7, 0.15))
    crack = msum(at(bandpass(noise(0.04), 500, 1600) * env_exp(0.04, 0.008) * rng.uniform(0.5, 1), rng.uniform(0, 0.12))
                for _ in range(6))
    S["crate_break"] = mix(crack, lowpass(noise(0.25), 800) * env_exp(0.25, 0.05) * 0.5)
    gulp = lambda f: osc(sweep(f, f * 1.6, 0.09), 0.09) * env_ad(0.09, 0.01, curve=2)
    S["potion_drink"] = mix(gulp(160), at(gulp(150), 0.16), at(gulp(170), 0.32),
                            at(metal(1700, 0.3, ratios=(1, 2.0), tau=0.1) * 0.25, 0.45))
    S["exit_unlock"] = mix(lowpass(noise(0.06), 3000) * env_exp(0.06, 0.015) * 0.6,      # latch click
                           at(metal(780, 0.3, ratios=(1, 2.4, 4.1), tau=0.1) * 0.5, 0.04),  # metal clank
                           *[at(osc(note(n), 0.5, "tri") * env_exp(0.5, 0.18) * 0.45, 0.12 + k * 0.1)
                             for k, n in enumerate((79, 83, 86, 91))])
    arp = [72, 76, 79, 84, 88]
    S["level_complete"] = mix(*[at(osc(note(n), 0.25, "square", 0.25) * env_exp(0.25, 0.09) * 0.4, k * 0.09)
                                for k, n in enumerate(arp)])

    # ---- UI ----------------------------------------------------------------------------
    S["ui_move"] = osc(1200, 0.03, "square", 0.25) * env_ad(0.03, 0.001)
    S["ui_confirm"] = mix(osc(note(76), 0.08, "square", 0.25) * env_ad(0.08),
                          at(osc(note(83), 0.12, "square", 0.25) * env_ad(0.12), 0.06))
    S["ui_back"] = mix(osc(note(76), 0.08, "square", 0.25) * env_ad(0.08),
                       at(osc(note(69), 0.12, "square", 0.25) * env_ad(0.12), 0.06))
    S["shop_buy"] = mix(osc(note(83), 0.07, "square", 0.5) * 0.5,
                        at(osc(note(88), 0.35, "square", 0.5) * env_exp(0.35, 0.1) * 0.5, 0.07))
    S["shop_deny"] = osc(110, 0.25, "square", 0.5) * env_ad(0.25, 0.005, curve=0.5) * 0.6
    S["forge"] = mix(metal(520, 1.0, ratios=(1, 2.43, 4.1, 6.8), tau=0.35) * 0.9,
                     at(metal(540, 0.8, ratios=(1, 2.43, 4.1), tau=0.25) * 0.6, 0.28),
                     lowpass(noise(0.04), 4000) * 0.5)
    S["text_blip"] = osc(880, 0.012, "square", 0.5) * env_ad(0.012, 0.001)
    S["pause"] = mix(osc(note(72), 0.1, "tri") * env_ad(0.1), at(osc(note(67), 0.15, "tri") * env_ad(0.15), 0.08))

    # ---- jingles ---------------------------------------------------------------------
    def melody(notes, step, kind="square", duty=0.25, length=None, tau=0.25):
        parts = []
        for k, (n, d) in enumerate(notes):
            dur = length or d * step * 1.2
            parts.append(at(osc(note(n), dur, kind, duty) * env_ad(dur, 0.01, curve=1.5), sum(x[1] for x in notes[:k]) * step))
        return mix(*parts)
    go = [(69, 1), (67, 1), (65, 1), (64, 2), (60, 1), (62, 1), (57, 4)]
    S["game_over"] = echo(mix(melody(go, 0.28, "square", 0.5) * 0.4,
                              melody([(45, 4), (43, 4), (41, 4)], 0.28, "tri") * 0.5), 0.2, 0.3, 3)
    vic = [(60, 1), (64, 1), (67, 1), (72, 2), (67, 1), (72, 4)]
    S["victory"] = echo(mix(melody(vic, 0.16, "square", 0.25) * 0.4,
                            at(melody([(72, 6), (76, 6), (79, 6)], 0.16, "tri"), 0.96) * 0.3,
                            melody([(48, 4), (43, 2), (48, 6)], 0.16, "tri") * 0.5), 0.15, 0.3, 3)
    return S


# ==========================================================================
# Music: a tiny step sequencer
# ==========================================================================
def kick(dur=0.25):
    return osc(sweep(150, 40, dur), dur) * env_exp(dur, 0.06)


def snare(dur=0.18):
    return mix(highpass(noise(dur), 1500) * env_exp(dur, 0.05) * 0.7, osc(190, dur, "tri") * env_exp(dur, 0.03) * 0.4)


def hat(dur=0.05):
    return highpass(noise(dur), 6000) * env_exp(dur, 0.012)


def render_track(bpm, bars, chords, style, seed=0):
    """
    chords: list of (root_midi, [intervals]) - one chord per bar, looped.
    style : dict of voice switches/levels.
    Returns a float array; length is an exact number of bars so the loop is
    seamless when pygame repeats it.
    """
    local = np.random.default_rng(seed)
    beat = 60.0 / bpm
    bar = beat * 4
    out = np.zeros(int(SR * bar * bars) + SR)
    step16 = beat / 4

    def put(sig, t, gain):
        i = int(t * SR)
        end = min(len(out), i + len(sig))
        out[i:end] += sig[:end - i] * gain

    for b in range(bars):
        root, ivs = chords[b % len(chords)]
        t0 = b * bar
        # ---- pad: soft detuned saws through a low-pass -----------------------------
        if style.get("pad"):
            for iv in ivs:
                f = note(root + 12 + iv)
                p = lowpass(osc(f, bar, "saw") + osc(f * 1.004, bar, "saw"), style.get("pad_cut", 1200))
                put(p * env_ad(int(SR * bar), 0.3, curve=0.6), t0, style["pad"] / len(ivs))
        # ---- bass ----------------------------------------------------------------------
        if style.get("bass"):
            pattern = style.get("bass_pattern", [0, None, 0, None, 7, None, 0, None])
            step = bar / len(pattern)
            for k, iv in enumerate(pattern):
                if iv is None:
                    continue
                d = step * 0.9
                put(osc(note(root - 12 + iv), d, "tri") * env_ad(d, 0.005, curve=1.2), t0 + k * step, style["bass"])
        # ---- arpeggio ----------------------------------------------------------------
        if style.get("arp"):
            notes = [root + 12 + iv for iv in ivs] + [root + 24 + ivs[0]]
            order = style.get("arp_order", "up")
            n_steps = style.get("arp_steps", 16)
            st = bar / n_steps
            for k in range(n_steps):
                if order == "up":
                    n = notes[k % len(notes)]
                elif order == "updown":
                    seq = notes + notes[-2:0:-1]
                    n = seq[k % len(seq)]
                else:
                    n = notes[local.integers(len(notes))]
                d = st * 0.8
                put(osc(note(n), d, "square", style.get("duty", 0.25)) * env_ad(d, 0.003, curve=2),
                    t0 + k * st, style["arp"])
        # ---- lead melody (simple random walk on chord tones, seeded) --------------
        if style.get("lead"):
            st = bar / 8
            for k in range(8):
                if local.random() < style.get("lead_rest", 0.35):
                    continue
                n = root + 24 + local.choice(ivs + [ivs[0] + 12])
                d = st * local.choice([1, 1, 2]) * 0.95
                vib = 1 + 0.006 * np.sin(2 * np.pi * 6 * t_axis(d))
                put(osc(note(n) * vib, d, "square", 0.5) * env_ad(d, 0.01, curve=1.2), t0 + k * st, style["lead"])
        # ---- drums ----------------------------------------------------------------------
        if style.get("drums"):
            g = style["drums"]
            kicks = style.get("kicks", [0, 8])
            snares = style.get("snares", [4, 12])
            for s in range(16):
                t = t0 + s * step16
                if s in kicks:
                    put(kick(), t, g)
                if s in snares:
                    put(snare(), t, g * 0.7)
                if style.get("hats", True) and s % 2 == 0:
                    put(hat(), t, g * 0.35)
    out = out[:int(SR * bar * bars)]
    if style.get("echo"):
        e = echo(out, beat * 0.75, 0.25, 3)
        # fold the echo tail back onto the start so the loop stays seamless
        tail = e[len(out):]
        e = e[:len(out)]
        e[:len(tail)] += tail
        out = e
    return out


def make_music():
    m = 3  # minor third shorthand
    tracks = {
        # mysterious A minor: Am - F - C - E
        "menu": render_track(92, 16, [(57, [0, m, 7]), (53, [0, 4, 7]), (60, [0, 4, 7]), (52, [0, 4, 7])],
                             dict(pad=0.35, bass=0.4, arp=0.12, arp_order="updown", arp_steps=8, echo=True), 1),
        # Act II: slow, dark E phrygian drone
        "act2": render_track(84, 16, [(52, [0, m, 7]), (53, [0, 4, 7]), (52, [0, m, 7]), (50, [0, m, 7])],
                             dict(pad=0.4, pad_cut=700, bass=0.45, bass_pattern=[0, None, None, 0, None, None, 1, None],
                                  arp=0.08, arp_order="random", arp_steps=8, drums=0.35, kicks=[0], snares=[8],
                                  hats=False, echo=True), 2),
        # Boss: fast C minor, driving
        "boss": render_track(150, 16, [(48, [0, m, 7]), (44, [0, 4, 7]), (46, [0, 4, 7]), (43, [0, 4, 7])],
                             dict(pad=0.2, pad_cut=1600, bass=0.5, bass_pattern=[0, 0, 12, 0, 0, 12, 0, 7] * 2,
                                  arp=0.14, arp_steps=16, lead=0.18, lead_rest=0.3, drums=0.6,
                                  kicks=[0, 3, 8, 11], snares=[4, 12]), 3),
        # Shop: bouncy F major
        "shop": render_track(112, 8, [(53, [0, 4, 7]), (58, [0, 4, 7]), (60, [0, 4, 7]), (53, [0, 4, 7])],
                             dict(bass=0.45, bass_pattern=[0, None, 7, None, 12, None, 7, None], arp=0.12,
                                  arp_steps=8, duty=0.125, lead=0.14, lead_rest=0.45, drums=0.3,
                                  kicks=[0, 8], snares=[4, 12]), 4),
        # Story: slow ambient pad
        "story": render_track(60, 8, [(50, [0, m, 7, 10]), (46, [0, 4, 7, 11]), (48, [0, 4, 7]), (45, [0, m, 7])],
                              dict(pad=0.55, pad_cut=900, arp=0.05, arp_order="random", arp_steps=4, echo=True), 5),
        # Ending: warm, hopeful C major
        "ending": render_track(84, 16, [(48, [0, 4, 7]), (55, [0, 4, 7]), (57, [0, m, 7]), (53, [0, 4, 7])],
                               dict(pad=0.4, bass=0.4, arp=0.1, arp_order="updown", arp_steps=8, lead=0.15,
                                    lead_rest=0.4, echo=True), 6),
    }
    return tracks


def main():
    os.makedirs(SFX_DIR, exist_ok=True)
    os.makedirs(MUSIC_DIR, exist_ok=True)
    only = set(sys.argv[1:])
    sfx = make_sfx()
    for name, sig in sfx.items():
        if not only or name in only:
            save_wav(name, sig)
    print(f"wrote {len(sfx)} sound effects to {SFX_DIR}")
    if not only or "music" in only:
        import soundfile as sf
        for name, sig in make_music().items():
            sig = normalise(sig, 0.8)
            sf.write(os.path.join(MUSIC_DIR, name + ".ogg"), sig, SR, format="OGG", subtype="VORBIS")
            print(f"  music {name}: {len(sig) / SR:.1f}s")
    # act1 intentionally not generated: it falls back to the original music.wav


if __name__ == "__main__":
    main()
