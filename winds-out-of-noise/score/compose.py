"""WINDS OUT OF NOISE: the score.

Four musical languages are treated as stages of emergence:
  noise (being before identity) -> classical (compressed, stable identity) ->
  hyperpop (identity captured and accelerated by an engine) ->
  post-hyperpop (the engine's output metabolized and recombined) ->
  all four coexisting (the shared region) -> noise again (the loop).

Usage: python3 compose.py <out_dir>
Writes score.wav, one stem per language, and cues.json (section bounds, beats,
voice cues) for the picture edit.
"""
import json
import os
import sys

import numpy as np
from scipy.io import wavfile

import dsp
from dsp import SR, secs, midi_hz

T = 360.0  # total length, seconds
B = 0.75   # one beat at 80 BPM; a bar is 3 s
HB = 0.375  # one beat at 160 BPM

LOUDNESS = {"I": -24, "II": -20, "III": -19, "IV": -13, "V": -15, "VI": -16, "VII": -23}  # target dB RMS

SECTIONS = [  # name, start, end (seconds); boundaries fall on 80 BPM bars
    ("I noise", 0, 48),
    ("II compression", 48, 108),
    ("III rhizome/territory", 108, 162),
    ("IV technocapital", 162, 228),
    ("V metabolism", 228, 282),
    ("VI singleton", 282, 339),
    ("VII coda", 339, 360),
]

N = secs(T)
stems = {k: np.zeros((N, 2)) for k in ("noise", "classical", "hyperpop", "posthyperpop", "voice")}
cues = {"sections": SECTIONS, "voice": [], "beats": [], "hits": [], "bar80": B * 4}

D2 = 38
HARM_D = midi_hz(D2) * np.array([1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 16, 20])


def voice_cue(t, text, kind):
    cues["voice"].append({"t": round(t, 3), "text": text, "kind": kind})


# ================================================================ instruments

def string_note(m, dur, vel=0.5, att=0.6, rel=1.4, bright=2400):
    n = secs(dur + rel)
    t = np.arange(n) / SR
    vib = 1 + 0.0035 * np.sin(2 * np.pi * (5.0 + dsp.RNG.random()) * t) * np.clip(t / 0.8, 0, 1)
    env = dsp.adsr(n, a=att, d=0.4, s=0.85, r=rel, gate=dur)
    x = dsp.supersaw(midi_hz(m) * vib, n, voices=3, detune=0.07, spread=0.7)
    x = dsp.svf(x, bright * (0.5 + 0.5 * env), 0.8, "low")
    bow = dsp.stereo(dsp.svf(dsp.white(n), midi_hz(m) * 3, 4, "band")) * 0.04
    return (x + bow) * env[:, None] * vel


def piano(m, vel=0.6, length=5.0):
    n = secs(length)
    t = np.arange(n) / SR
    f = midi_hz(m)
    out = np.zeros(n)
    for k in range(1, 13):
        fk = f * k * np.sqrt(1 + 0.0004 * k * k)
        if fk > 16000:
            break
        amp = (1 / k ** 1.2) * vel ** (0.15 * k)
        out += amp * np.sin(2 * np.pi * fk * t + dsp.RNG.random()) * np.exp(-t * (0.5 + 0.45 * k) * (f / 260) ** 0.35)
    click = dsp.butter(dsp.white(secs(0.03)), 2500, "low", 2) * dsp.expdecay(secs(0.03), 0.015) * 0.3
    out[: len(click)] += click
    out *= np.minimum(1, t / 0.002)
    return dsp.stereo(out * vel * 0.5, pan=np.clip((m - 60) / 40, -0.6, 0.6))


def fm(m, dur, ratio=3.5, index=3.0, decay=0.6, vel=0.5, pan=0.0):
    n = secs(dur)
    t = np.arange(n) / SR
    f = midi_hz(m)
    env = dsp.expdecay(n, decay) * np.minimum(1, t / 0.002)
    x = np.sin(2 * np.pi * f * t + index * env * np.sin(2 * np.pi * f * ratio * t))
    return dsp.stereo(x * env * vel, pan)


def clang(dur=1.2, f=180, vel=0.6, pan=0.0):
    """Factory strike: inharmonic FM plus a noise burst."""
    n = secs(dur)
    t = np.arange(n) / SR
    env = dsp.expdecay(n, dur * 0.6)
    x = np.sin(2 * np.pi * f * t + 4 * env * np.sin(2 * np.pi * f * 1.414 * t))
    x += 0.5 * np.sin(2 * np.pi * f * 2.76 * t) * dsp.expdecay(n, dur * 0.3)
    burst = dsp.butter(dsp.white(n), [800, 6000], "band", 2) * dsp.expdecay(n, 0.05)
    return dsp.stereo((x * env * 0.6 + burst) * vel, pan)


def kick(vel=1.0, hard=False):
    n = secs(0.5)
    t = np.arange(n) / SR
    f = 45 + 110 * np.exp(-t * 28)
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * dsp.expdecay(n, 0.35)
    x[: secs(0.004)] += dsp.white(secs(0.004)) * 0.5
    if hard:
        x = dsp.softclip(x, 3.0)
    return dsp.stereo(x * vel)


def eight08(m, dur, glide_from=None, drive=2.5, vel=0.8):
    n = secs(dur)
    t = np.arange(n) / SR
    f = np.full(n, midi_hz(m))
    if glide_from is not None:
        g = secs(0.08)
        f[:g] = midi_hz(glide_from) + (midi_hz(m) - midi_hz(glide_from)) * np.linspace(0, 1, g)
    f = f * (1 + 0.6 * np.exp(-t * 40))
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * dsp.expdecay(n, max(dur, 0.6))
    x = dsp.softclip(x, drive)
    x *= np.minimum(1, (n - np.arange(n)) / secs(0.01))
    return dsp.stereo(x * vel)


def snare(vel=0.7, clap=False):
    n = secs(0.35)
    t = np.arange(n) / SR
    nz = dsp.butter(dsp.white(n), [1200, 9000], "band", 2)
    if clap:
        env = np.zeros(n)
        for k, o in enumerate((0, 0.011, 0.022)):
            i = secs(o)
            env[i:] += dsp.expdecay(n - i, 0.12 if k == 2 else 0.02)
    else:
        env = dsp.expdecay(n, 0.12)
    tone = np.sin(2 * np.pi * 190 * t) * dsp.expdecay(n, 0.06) * (0 if clap else 0.6)
    return dsp.stereo((nz * env + tone) * vel)


def hat(vel=0.3, open_=False):
    n = secs(0.25 if open_ else 0.05)
    x = dsp.butter(dsp.white(n), 7000, "high", 2) * dsp.expdecay(n, 0.15 if open_ else 0.025)
    return dsp.stereo(x * vel, pan=dsp.RNG.uniform(-0.3, 0.3))


def chip_voice(notes, vowels="aoiea", dur_scale=1.0):
    """Pitched-up formant 'vocal' with hard autotune glides. notes: [(t, midi, dur)]."""
    if not notes:
        return np.zeros((0, 2))
    t0 = notes[0][0]
    end = max(t + d for t, m, d in notes) - t0 + 0.4
    n = secs(end)
    f = np.full(n, midi_hz(notes[0][1]))
    amp = np.zeros(n)
    for k, (t, m, d) in enumerate(notes):
        i, j = secs(t - t0), secs(t - t0 + d)
        prev = f[i - 1] if i > 0 else midi_hz(m)
        g = min(secs(0.03), j - i)
        f[i:j] = midi_hz(m)
        f[i:i + g] = prev + (midi_hz(m) - prev) * np.linspace(0, 1, g)
        amp[i:j] = np.maximum(amp[i:j], dsp.adsr(j - i, 0.01, 0.05, 0.8, 0.05))
    f[secs(notes[-1][0] - t0 + notes[-1][2]):] = midi_hz(notes[-1][1])
    out = np.zeros(n)
    seg = max(1, n // len(vowels))
    for k, v in enumerate(vowels):
        part = dsp.sing(f, n, v, breath=0.08, vib_depth=0.1)
        w = np.zeros(n)
        a, b = max(0, k * seg - secs(0.05)), min(n, (k + 1) * seg + secs(0.05))
        w[a:b] = 1
        w = np.convolve(w, np.ones(secs(0.05)) / secs(0.05), "same")
        out += part * w
    out *= amp
    return dsp.delay(dsp.stereo(out * 0.35), HB * 0.75, fb=0.35, wet=0.25)


def riser(dur, f0=200, f1=6000):
    n = secs(dur)
    cut = dsp.ramp(n, f0, f1, 2.0)
    x = dsp.svf(dsp.white(n), cut, 3.0, "band")
    x += dsp.saw(cut / 8, n) * 0.15
    return dsp.stereo(x * dsp.ramp(n, 0, 1, 2.0) * 0.4)


def shepard(dur, rate_curve, base=40.0, octaves=8):
    """Endlessly rising Shepard-Risset glissando; rate_curve(t01) in octaves/sec."""
    n = secs(dur)
    t01 = np.linspace(0, 1, n)
    pos = np.cumsum(rate_curve(t01)) / SR  # octaves travelled
    out = np.zeros(n)
    for k in range(octaves):
        octv = (k + pos) % octaves
        f = base * 2 ** octv
        amp = np.exp(-0.5 * ((octv - octaves / 2) / (octaves / 6)) ** 2)
        out += np.sin(2 * np.pi * np.cumsum(f) / SR) * amp
    return dsp.stereo(out / octaves * 1.5)


def chord_strings(buf, t, notes, dur, vel=0.18, **kw):
    for m in notes:
        dsp.place(buf, string_note(m, dur, vel, **kw), t)


def speak_vocoded(text, carrier_notes, t, buf, gain=1.0, speed=115, kind="choir"):
    v = dsp.speak(text, voice="en-us+m3", speed=speed, pitch=40)
    n = len(v)
    car = np.zeros((n, 2))
    for m in carrier_notes:
        car += dsp.supersaw(midi_hz(m), n, voices=5, detune=0.12)
    out = dsp.vocode(v, car)
    dsp.place(buf, dsp.fade(dsp.normalize(out, 0.6) * gain, 0.02, 0.1), t)
    voice_cue(t, text, kind)
    return len(v) / SR


def whisper(text, t, buf, gain=0.5, speed=100):
    v = dsp.speak(text, voice="en-us+f4", speed=speed, pitch=30)
    car = dsp.colored(len(v), 1.0)
    out = dsp.vocode(v, car, bands=24)
    out = dsp.reverb(dsp.normalize(out, 0.5), 0.5, 3.5, 5000)
    dsp.place(buf, out * gain, t)
    voice_cue(t, text, "whisper")


# ================================================================ I. noise -> tone

def section_noise_to_tone(t0, t1, invert=False, chord_hz=None):
    """Wind as noise; a resonator bank slowly 'compresses' it onto harmonics.
    invert=True runs the process backwards (tone dissolving into wind)."""
    dur = t1 - t0
    n = secs(dur)
    p = np.linspace(0, 1, n)
    if invert:
        p = p[::-1]
    # gusts: slow random amplitude
    gust = dsp.butter(dsp.white(n), 0.25, "low", 2)
    gust = 0.55 + 0.45 * np.tanh(gust / (np.std(gust) + 1e-9))
    pink = dsp.colored(n, 1.0)
    brown = dsp.colored(n, 2.0)
    bed = (brown * 0.7 + pink * 0.25) * gust
    whistle_c = 300 + 900 * (0.5 + 0.5 * np.tanh(dsp.butter(dsp.white(n), 0.15, "low", 2) * 40))
    bed += dsp.svf(pink, whistle_c, 6.0, "band") * 0.25 * gust
    targets = HARM_D if chord_hz is None else chord_hz
    out = np.zeros((n, 2))
    lock = np.clip((p - 0.15) / 0.75, 0, 1) ** 1.6  # 0 = free wind, 1 = locked to harmonics
    for k, ft in enumerate(targets):
        wander = np.exp(dsp.butter(dsp.white(n), 0.1, "low", 2) * 60) * dsp.RNG.uniform(150, 2500)
        wander = np.clip(wander, 80, 5000)
        fc = np.exp(np.log(wander) * (1 - lock) + np.log(ft) * lock)
        q = 1.2 + 90 * lock ** 2
        band = dsp.svf(pink if k % 2 else brown, fc, float(np.median(q)), "band")
        band = dsp.svf(band, fc, 2.0, "band")  # second pass sharpens as the band narrows
        band /= (np.std(band) + 1e-9)
        amp = (0.25 + 0.75 * lock) / (1 + k * 0.35)
        pan = np.sin(k * 2.4) * 0.7
        out += dsp.stereo(band * amp * gust ** (1 - lock), pan)
    # the emergent tone itself, stabilizing at the end of the lock
    t = np.arange(n) / SR
    tone = np.zeros(n)
    for k, ft in enumerate(targets[:8]):
        tone += np.sin(2 * np.pi * ft * t + k) / (k + 1)
    tone *= np.clip((p - 0.7) / 0.3, 0, 1) ** 2
    mix = dsp.stereo(bed) * (1 - 0.7 * lock)[:, None] * 0.5 + out * 0.08 + dsp.stereo(tone) * 0.12
    return dsp.reverb(mix, 0.35, 5.0, 7000)


# ================================================================ II. chorale

CHORALE_MINOR = [  # bass, tenor, alto, soprano per bar
    (38, 57, 62, 65), (34, 58, 62, 65), (33, 57, 60, 65), (36, 55, 64, 67),
    (34, 55, 62, 67), (33, 57, 62, 65), (33, 57, 61, 64), (38, 57, 62, 62),
]
MELODY_MINOR = [  # (beat within bar, midi, beats) per bar
    [(0, 69, 2), (2, 72, 1), (3, 74, 1)],
    [(0, 74, 1.5), (1.5, 72, 0.5), (2, 70, 2)],
    [(0, 69, 2), (2, 72, 2)],
    [(0, 76, 1), (1, 74, 1), (2, 72, 2)],
    [(0, 74, 2), (2, 79, 1), (3, 77, 1)],
    [(0, 77, 1.5), (1.5, 76, 0.5), (2, 74, 2)],
    [(0, 73, 2), (2, 76, 2)],
    [(0, 74, 4)],
]


def section_chorale(t0):
    cl = stems["classical"]
    for rep in range(2):
        for b, chord in enumerate(CHORALE_MINOR):
            t = t0 + (rep * 8 + b) * 4 * B
            bass, *upper = chord
            chord_strings(cl, t, [bass, bass + 12] + list(upper), 4 * B, vel=0.11 + 0.03 * rep)
            # piano: broken chord in eighths, entering on the first pass
            arp = [bass + 12, upper[0], upper[1], upper[2], upper[1], upper[0], upper[1], upper[2]]
            for k, m in enumerate(arp):
                dsp.place(cl, piano(m + 12 * (rep == 1 and k % 4 == 3), 0.35 + 0.1 * (k == 0), 4.0), t + k * B / 2, 0.8)
            if rep == 1:  # solo line on the second pass
                for beat, m, beats in MELODY_MINOR[b]:
                    dsp.place(cl, string_note(m, beats * B, 0.16, att=0.15, rel=0.8, bright=3500), t + beat * B)
    # four closing bars: suspension and resolution on D
    t = t0 + 16 * 4 * B
    for k, chord in enumerate([(34, 53, 58, 62), (31, 55, 58, 62), (33, 57, 61, 64), (38, 57, 62, 65)]):
        chord_strings(cl, t + k * 4 * B, list(chord), 4 * B, vel=0.12)
        dsp.place(cl, piano(chord[0] + 12, 0.5, 5), t + k * 4 * B)


# ================================================================ III. rhizome -> territory

SCALE_DORIAN = [0, 2, 3, 5, 7, 9, 10]


def degree(d, base=62):
    o, i = divmod(d, 7)
    return base + 12 * o + SCALE_DORIAN[i]


def section_rhizome(t0, t1):
    cl = stems["classical"]
    dur = t1 - t0
    grid = B / 4  # 16th at 80 BPM
    ostinato = [0, 2, 4, 7, 4, 2, 0, 4]  # dorian degrees: D F A D' A F D A
    rng = np.random.default_rng(11)
    # branching random walks: each branch spawns children; a rhizome of notes
    branches = [(0.0, 0, 0.0)]  # (time, degree, pan)
    events = []
    while branches:
        t, d, pan = branches.pop()
        while t < dur:
            events.append((t, d, pan))
            t += rng.exponential(0.32)
            d = int(np.clip(d + rng.choice([-2, -1, 1, 2, 3]), -5, 10))
            if rng.random() < 0.05 and len(branches) < 6 and t < dur * 0.5:
                branches.append((t, d + rng.choice([-3, 3]), float(np.clip(pan + rng.normal(0, 0.5), -1, 1))))
            pan = float(np.clip(pan + rng.normal(0, 0.1), -1, 1))
    events.sort()
    for t, d, pan in events:
        terr = np.clip((t / dur - 0.4) / 0.45, 0, 1)  # territorialization 0 -> 1
        tq = round(t / grid) * grid
        t_play = t + (tq - t) * terr
        step = int(round(t_play / grid))
        if rng.random() < terr:
            d = ostinato[step % len(ostinato)]
        if terr > 0.7 and abs(t_play - tq) > 1e-6:
            continue
        pan_play = pan * (1 - terr)
        vel = 0.25 * (0.6 + 0.4 * rng.random()) * (1 - 0.3 * terr)
        dsp.place(cl, fm(degree(d), 1.2, ratio=4.0, index=2.0 + terr, decay=0.35 - 0.15 * terr, vel=vel, pan=pan_play), t0 + t_play)
    # drone that becomes rigid stabs
    for bar in range(int(dur / (4 * B))):
        t = t0 + bar * 4 * B
        terr = np.clip((bar * 4 * B / dur - 0.4) / 0.45, 0, 1)
        if terr < 0.5:
            chord_strings(cl, t, [38, 50, 57, 62, 65], 4 * B, vel=0.08)
        else:
            for beat in range(4):
                chord_strings(cl, t + beat * B, [38, 50, 57, 62, 65], B * 0.35, vel=0.1, att=0.01, rel=0.2, bright=3000)
        if terr > 0.15:  # the factory arrives
            for beat in (0, 2) if terr < 0.6 else range(4):
                dsp.place(cl, clang(1.0, 160 + 40 * (beat % 2), 0.25 * terr, pan=0.3 * (beat % 2 * 2 - 1)), t + beat * B)
                cues["hits"].append(round(t + beat * B, 3))
            for k in range(16 if terr > 0.6 else 0):
                dsp.place(cl, hat(0.12), t + k * grid)
    # last two bars accelerate into double time: the engine starts
    t = t1 - 8 * B
    for k in range(32):
        dsp.place(cl, fm(degree(ostinato[k % 8] + 7), 0.3, 3.0, 2.5, 0.1, 0.07 + k * 0.002), t + k * B / 4)
    dsp.place(stems["hyperpop"], riser(8 * B, 300, 9000), t, 0.25)


# ================================================================ IV. hyperpop

PROG_HP = [  # chord tones for the drop, same harmony as the chorale opening
    (38, [62, 65, 69, 74]),  # Dm
    (34, [58, 62, 65, 70]),  # Bb
    (41, [57, 60, 65, 69]),  # F
    (36, [55, 60, 64, 67]),  # C
]
HOOK = [
    [(0, 81, 1), (1, 81, .5), (1.5, 84, .5), (2, 86, 1), (3, 84, .5), (3.5, 81, .5), (4, 79, 1), (5, 77, 1), (6, 81, 2)],
    [(0, 77, 1), (1, 77, .5), (1.5, 79, .5), (2, 81, 1), (3, 79, 1), (4, 77, 1), (5, 74, 1), (6, 77, 2)],
    [(0, 72, 1), (1, 77, .5), (1.5, 81, .5), (2, 84, 1.5), (3.5, 81, .5), (4, 79, 1), (5, 77, 1), (6, 79, 2)],
    [(0, 76, 1), (1, 79, 1), (2, 84, 1), (3, 84, .5), (3.5, 86, .5), (4, 88, 2), (6, 86, 1), (7, 84, 1)],
]


def section_hyperpop(t0, t1):
    hp = stems["hyperpop"]
    bars = int(round((t1 - t0) / (4 * HB)))  # 44 bars of 160 BPM
    beats = []
    prev_root = None
    for bar in range(bars):
        t = t0 + bar * 4 * HB
        root, tones = PROG_HP[(bar // 2) % 4]
        part = "verse" if bar < 8 else "talk" if bar < 16 else "build" if bar < 20 else "drop" if bar < 36 else "drop2"
        drop = part.startswith("drop")
        # sparkle arps everywhere
        for k in range(8 if part in ("verse", "talk") else 16):
            step = HB / 2 if part in ("verse", "talk") else HB / 4
            m = tones[k % 4] + 12 * (1 + (k // 4) % 2)
            dsp.place(hp, fm(m, 0.25, 3.5, 1.5, 0.12, 0.07, pan=np.sin(k)), t + k * step)
        if part == "build":
            for k in range(int(4 / (0.25 if bar < 18 else 0.125))):  # snare roll
                st = 0.25 if bar < 18 else 0.125
                dsp.place(hp, snare(0.15 + 0.4 * ((bar - 16) * 4 + k * st) / 16, clap=False), t + k * st * HB)
            sweep = dsp.supersaw(midi_hz(root + 24), secs(4 * HB), 7, 0.2)
            cut = dsp.ramp(len(sweep), 300 + (bar - 16) * 1500, 1800 + (bar - 16) * 1500)
            dsp.place(hp, dsp.svf(sweep, cut, 2, "low") * 0.15, t)
            continue
        # drums
        kpat = [0, 1.5, 2.5] if part != "drop2" else [0, 1, 2, 3]
        if part == "verse" and bar < 4:
            kpat = [0]
        for kb in kpat:
            dsp.place(hp, kick(0.9, hard=drop), t + kb * HB)
            beats.append(round(t + kb * HB, 4))
        for sb in ([2] if part != "drop2" else [1, 3]):
            dsp.place(hp, snare(0.55, clap=True), t + sb * HB)
            cues["hits"].append(round(t + sb * HB, 3))
        for h in range(8):
            dsp.place(hp, hat(0.18 if h % 2 else 0.25), t + h * HB / 2)
        if bar % 4 == 3:  # trap roll
            for h in range(12):
                dsp.place(hp, hat(0.15), t + 3 * HB + h * HB / 12)
        # 808 on the kicks, sliding between roots
        for kb in kpat[:2]:
            dsp.place(hp, eight08(root, 1.2 * HB, prev_root, drive=3.5 if drop else 2.0, vel=0.55), t + kb * HB)
            prev_root = root
        if drop:
            pad = np.zeros((secs(4 * HB), 2))
            for m in tones + [tones[0] + 12]:
                pad += dsp.supersaw(midi_hz(m), len(pad), 9, 0.22)
            pad = dsp.svf(pad, 7000, 0.7, "low") * dsp.adsr(len(pad), 0.005, 0.2, 0.8, 0.02)[:, None]
            pad = dsp.sidechain(pad, [kb * HB for kb in kpat] + [k * HB for k in range(4)], 0.75, 0.16)
            dsp.place(hp, pad * 0.06, t)
            # screaming square lead doubles the hook an octave up
            for beat, m, bl in HOOK[(bar // 2) % 4]:
                if (bar % 2) * 4 <= beat < (bar % 2 + 1) * 4:
                    n = secs(bl * HB)
                    lead = dsp.square(midi_hz(m + 12), n, 0.3) * dsp.adsr(n, 0.005, 0.05, 0.7, 0.03)
                    dsp.place(hp, dsp.stereo(lead * 0.035), t + (beat - (bar % 2) * 4) * HB)
            if part == "drop2" and bar % 2 == 1:  # glitch stutter fill
                for k in range(8):
                    dsp.place(hp, fm(tones[-1] + 24, 0.05, 2, 6, 0.03, 0.15), t + 3 * HB + k * HB / 8)
    # vocal hook (chipmunk) over verse and drop
    for start_bar in list(range(0, 8, 2)) + list(range(20, 36, 2)):
        notes = [(t0 + start_bar * 4 * HB + beat * HB, m, bl * HB * 0.95) for beat, m, bl in HOOK[(start_bar // 2) % 4]]
        dsp.place(hp, chip_voice(notes), notes[0][0], 0.9)
    cues["beats"] += beats
    # talk section: vocoded thesis over the progression
    lines = ["capitalism is a hyper stitional engine", "a system for organizing totality",
             "in its own self learned emergent way", "fiction that makes itself real"]
    for k, line in enumerate(lines):
        root, tones = PROG_HP[k % 4]
        speak_vocoded(line, [root + 12] + tones, t0 + (8 + 2 * k) * 4 * HB, stems["voice"], 0.9, speed=150, kind="vocoder")
    # sudden cut at the end: tape stop over the last beat
    i0, i1 = secs(t1 - 2 * HB), secs(t1)
    hp[i0:i1] = dsp.tapestop(hp[i0:i1].copy(), 2 * HB)[: i1 - i0]


# ================================================================ V. post-hyperpop

def section_post(t0, t1, drop_src):
    pp = stems["posthyperpop"]
    rng = np.random.default_rng(23)
    # 1. shock: two beats of near silence with a reversed swell
    sw = dsp.reverb(dsp.stereo(dsp.sine(midi_hz(74), secs(1.5)) * dsp.expdecay(secs(1.5), 0.6)), 1.0, 3, 5000)[::-1]
    dsp.place(pp, sw * 0.5, t0)
    # 2. deconstruction (t0+2 .. t0+18): stutters, crushes and stretches of the drop
    t = t0 + 2
    while t < t0 + 18:
        kind = rng.choice(["stutter", "crush", "stretch", "gap", "pitch"], p=[.3, .2, .2, .1, .2])
        L = float(rng.choice([HB / 2, HB, 2 * HB]))
        src_t = rng.uniform(0, len(drop_src) / SR - 2)
        chunk = drop_src[secs(src_t): secs(src_t + L)]
        if kind == "stutter":
            sl = chunk[: secs(L / rng.choice([4, 8, 16]))]
            reps = int(L * 2 / (len(sl) / SR))
            out = np.concatenate([dsp.fade(sl, 0.001, 0.002)] * reps)
        elif kind == "crush":
            out = dsp.bitcrush(chunk, int(rng.integers(3, 6)), int(rng.integers(4, 20))) * 0.7
        elif kind == "stretch":
            out = dsp.granular(chunk, L * 3, 0.06, 80, pitch_jitter=0.3, seed=int(rng.integers(1e6)))
        elif kind == "pitch":
            out = dsp.tapestop(dsp.resample(chunk, rng.choice([0.5, 0.75, 1.5])), L * 0.5)
        else:
            out = np.zeros((secs(L), 2))
        dsp.place(pp, out * 0.9, t)
        cues["hits"].append(round(t, 3))
        t += len(out) / SR
    # distorted 808 drone underneath, falling
    n = secs(16)
    drone = dsp.softclip(dsp.sine(dsp.ramp(n, midi_hz(38), midi_hz(26), 0.7), n), 4) * dsp.ramp(n, 0.2, 0.5)
    dsp.place(pp, dsp.stereo(drone) * 0.35, t0 + 2)
    # 3. metabolism (t0+18 .. t0+36): the chorale returns through the engine's timbres
    tm = t0 + 18
    lines = ["recursive memetic structures", "may produce cultural foom",
             "a way to metabolize", "the singularity"]
    for b in range(6):
        bass, *upper = CHORALE_MINOR[b]
        tb = tm + b * 4 * B
        pad = np.zeros((secs(4 * B + 0.5), 2))
        for m in upper + [bass + 12]:
            pad += dsp.supersaw(midi_hz(m), len(pad), 5, 0.1)
        pad = dsp.svf(pad, dsp.ramp(len(pad), 900, 3500), 1.2, "low") * dsp.adsr(len(pad), 0.3, 0.3, 0.8, 0.4)[:, None]
        dsp.place(pp, dsp.bitcrush(pad, 8, 2) * 0.05, tb)
        dsp.place(stems["classical"], piano(bass + 24, 0.5), tb)
        # half-time broken beat
        for kb, kind in [(0, "k"), (1.5, "k"), (2, "s"), (3.25, "k"), (3.5, "s")]:
            dsp.place(pp, kick(0.8, True) if kind == "k" else snare(0.4, clap=True), tb + kb * B)
            (cues["beats"] if kind == "k" else cues["hits"]).append(round(tb + kb * B, 3))
        for h in range(8):
            dsp.place(pp, dsp.bitcrush(hat(0.2), 5, 3), tb + h * B / 2 + (0.03 if h % 2 else 0))
        if b < 4:
            speak_vocoded(lines[b], [bass + 12] + list(upper), tb + 0.2, stems["voice"], 0.85, speed=105)
    # chipmunk reprise of the chorale melody, metabolized
    notes = []
    for b in range(6):
        for beat, m, beats in MELODY_MINOR[b]:
            notes.append((tm + b * 4 * B + beat * B, m + 12, beats * B * 0.9))
    dsp.place(pp, chip_voice(notes, "oaiuoe"), notes[0][0], 0.6)
    # 4. foom (t0+36 .. t1): endless rise, accelerating
    foom = shepard(t1 - (t0 + 36), lambda x: 0.15 + 2.5 * x ** 3)
    foom *= dsp.ramp(len(foom), 0.2, 1.0, 1.5)[:, None]
    dsp.place(pp, dsp.reverb(foom, 0.3, 3, 8000) * 0.5, t0 + 36)
    dsp.place(pp, riser(t1 - (t0 + 36), 100, 12000) * 0.8, t0 + 36)
    for k in range(int((t1 - t0 - 36) / B)):  # quickening pulse
        tk = t0 + 36 + (t1 - t0 - 36) * (1 - (1 - k / ((t1 - t0 - 36) / B)) ** 0.6)
        dsp.place(pp, kick(0.5 + 0.4 * k / 24, True), tk)
        cues["beats"].append(round(tk, 3))


# ================================================================ VI. singleton

CHORALE_MAJOR = [
    (38, 54, 57, 62), (37, 52, 57, 64), (35, 54, 59, 62), (31, 55, 59, 62),
    (42, 54, 57, 62), (43, 55, 59, 64), (33, 55, 57, 61), (33, 52, 57, 61),
]
MELODY_MAJOR = [
    [(0, 74, 2), (2, 76, 1), (3, 78, 1)], [(0, 76, 2), (2, 73, 2)],
    [(0, 74, 1), (1, 78, 1), (2, 83, 2)], [(0, 81, 2), (2, 79, 2)],
    [(0, 78, 2), (2, 81, 2)], [(0, 83, 2), (2, 79, 1), (3, 76, 1)],
    [(0, 76, 3), (3, 78, 1)], [(0, 76, 4)],
]


def section_singleton(t0, t1):
    cl, hp, pp = stems["classical"], stems["hyperpop"], stems["posthyperpop"]
    bars = int(round((t1 - t0) / (4 * B)))
    lines = ["what if the purpose of collective intelligence", "is not to discover one perfect future",
             "but to expand the region of futures", "in which different forms of being",
             "can coexist and flourish", "this is where we must strive to be"]
    for bar in range(bars):
        t = t0 + bar * 4 * B
        if bar < 16:
            chord = CHORALE_MAJOR[bar % 8]
        else:
            chord = [(43, 55, 59, 62), (45, 57, 61, 64), (38, 57, 62, 66)][bar - 16]
        bass, *upper = chord
        full = 4 <= bar < 16
        # classical: strings and piano
        chord_strings(cl, t, [bass, bass + 12] + list(upper), 4 * B, vel=0.1 + 0.03 * full)
        for k in range(8):
            m = [bass + 12, upper[0], upper[1], upper[2]][k % 4] + 12 * (k >= 4)
            dsp.place(cl, piano(m, 0.32), t + k * B / 2, 0.7)
        if bar >= 8 and bar < 16:
            for beat, m, beats in MELODY_MAJOR[bar % 8]:
                dsp.place(cl, string_note(m, beats * B, 0.15, att=0.2, rel=1.0, bright=4000), t + beat * B)
        # hyperpop: bell arps in 16ths, soft sidechained supersaw, gentle kick
        if bar >= 2:
            for k in range(16):
                m = upper[k % 3] + 12 * (1 + (k // 3) % 2)
                dsp.place(hp, fm(m, 0.3, 3.5, 1.2, 0.15, 0.05, pan=np.sin(k * 0.7)), t + k * B / 4)
        if full:
            pad = np.zeros((secs(4 * B), 2))
            for m in list(upper) + [upper[-1] + 12]:
                pad += dsp.supersaw(midi_hz(m), len(pad), 7, 0.15)
            pad = dsp.svf(pad, 4000, 0.7, "low")
            pad = dsp.sidechain(pad, [k * B for k in range(4)], 0.5, 0.3)
            dsp.place(hp, pad * 0.03, t)
            for kb in range(4):
                dsp.place(hp, kick(0.55), t + kb * B)
                cues["beats"].append(round(t + kb * B, 3))
            dsp.place(hp, snare(0.25, clap=True), t + B)
            dsp.place(hp, snare(0.25, clap=True), t + 3 * B)
            for h in range(8):
                dsp.place(hp, hat(0.08, open_=h % 2 == 1), t + h * B / 2)
        # post-hyperpop: vocoder choir carries the thesis
        if bar % 2 == 0 and bar // 2 < len(lines):
            speak_vocoded(lines[bar // 2], [bass + 12] + list(upper), t + 0.1, stems["voice"], 0.8, speed=100)
        if 8 <= bar < 16:  # high chipmunk descant, granular-smeared
            notes = [(t + beat * B, m + 12, beats * B * 0.9) for beat, m, beats in MELODY_MAJOR[bar % 8]]
            v = chip_voice(notes, "aeiou")
            dsp.place(pp, dsp.reverb(v, 0.5, 4, 6000), t, 0.35)
    # noise: wind returns underneath, as a bed rather than a source
    n = secs(t1 - t0)
    wind = dsp.colored(n, 1.5) * (0.5 + 0.5 * np.tanh(dsp.butter(dsp.white(n), 0.2, "low", 2) * 30))
    wind = dsp.svf(wind, 1200 + 800 * np.sin(np.linspace(0, 9, n)), 0.9, "low")
    dsp.place(stems["noise"], dsp.stereo(wind) * 0.05, t0)


# ================================================================ assemble

def section_gain(x):
    """Gain curve that brings each section to its LOUDNESS target, crossfaded over 2 s."""
    pts_t, pts_g = [], []
    for name, a, b in SECTIONS:
        seg = x[secs(a): secs(b)]
        rms_db = 20 * np.log10(np.sqrt(np.mean(seg ** 2)) + 1e-9)
        g = 10 ** ((LOUDNESS[name.split()[0]] - rms_db) / 20)
        pts_t += [a + 1, b - 1]
        pts_g += [g, g]
    t = np.arange(len(x)) / SR
    return np.exp(np.interp(t, pts_t, np.log(pts_g)))[:, None]


def main(out):
    os.makedirs(out, exist_ok=True)
    s = {name.split()[0]: (a, b) for name, a, b in SECTIONS}

    print("I noise")
    dsp.place(stems["noise"], section_noise_to_tone(*s["I"]), 0)
    whisper("winds emerge out of noise", 6.0, stems["voice"], 0.6)
    whisper("the primordial stage of being", 15.0, stems["voice"], 0.5)
    whisper("fiction and creation are one", 39.0, stems["voice"], 0.5)
    # noise lingers under the chorale entry
    dsp.place(stems["noise"], dsp.fade(section_noise_to_tone(48, 60) * 0.5, 0.01, 10), 48)

    print("II chorale")
    section_chorale(s["II"][0])
    whisper("compression", 66.0, stems["voice"], 0.35)
    whisper("the creator of identity", 70.0, stems["voice"], 0.35)

    print("III rhizome")
    section_rhizome(*s["III"])
    v = dsp.speak("being becomes an appendage of a totality", voice="en-us", speed=135, pitch=20)
    dsp.place(stems["voice"], dsp.reverb(dsp.stereo(dsp.bitcrush(v, 7, 2)) * 0.5, 0.2, 1.5), 138.0)
    voice_cue(138.0, "being becomes an appendage of a totality", "machine")
    v = dsp.speak("its flows reoriented", voice="en-us", speed=135, pitch=20)
    dsp.place(stems["voice"], dsp.reverb(dsp.stereo(dsp.bitcrush(v, 7, 2)) * 0.5, 0.2, 1.5), 150.0)
    voice_cue(150.0, "its flows reoriented", "machine")

    print("IV hyperpop")
    section_hyperpop(*s["IV"])
    drop_src = stems["hyperpop"][secs(162 + 20 * 4 * HB): secs(162 + 36 * 4 * HB)].copy()

    print("V post-hyperpop")
    section_post(*s["V"], drop_src)

    print("VI singleton")
    section_singleton(*s["VI"])

    print("VII coda")
    a, b = s["VII"]
    final = midi_hz(np.array([38, 50, 54, 57, 62, 66, 69, 74]))
    dsp.place(stems["noise"], section_noise_to_tone(a - 3, b, invert=True, chord_hz=final), a - 3)
    chord_strings(stems["classical"], a, [38, 50, 57, 62, 66], 8.0, vel=0.12, att=0.1, rel=6.0)
    dsp.place(stems["classical"], piano(62, 0.45, 8), a)
    whisper("fiction is infrastructure", a + 6, stems["voice"], 0.5)

    print("mix")
    gains = {"noise": 1.0, "classical": 0.9, "hyperpop": 0.8, "posthyperpop": 0.8, "voice": 1.0}
    verb = {"classical": (0.3, 4.5, 6500), "hyperpop": (0.12, 1.8, 8000), "posthyperpop": (0.2, 2.5, 7000)}
    for k, (w, sec, damp) in verb.items():
        stems[k] = dsp.reverb(stems[k], w, sec, damp)
    master = sum(stems[k] * g for k, g in gains.items())
    master = dsp.butter(master, 25, "high", 2)
    master = dsp.limiter(master * section_gain(master), 0.89)
    master = dsp.fade(master, 1.5, 3.0)
    wavfile.write(os.path.join(out, "score.wav"), SR, (master * 32767).astype(np.int16))
    for k, x in stems.items():
        wavfile.write(os.path.join(out, f"stem_{k}.wav"), SR, (dsp.normalize(x, 0.9) * 32767).astype(np.int16))
    # loudness envelope for the picture (20 ms frames)
    hop = secs(0.02)
    env = np.sqrt(np.mean(master[: len(master) // hop * hop].reshape(-1, hop, 2) ** 2, axis=(1, 2)))
    cues["envelope_hop"] = 0.02
    cues["envelope"] = [round(float(e), 4) for e in env]
    cues["beats"] = sorted(set(cues["beats"]))
    cues["hits"] = sorted(set(cues["hits"]))
    json.dump(cues, open(os.path.join(out, "cues.json"), "w"))
    print("done")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "out")
