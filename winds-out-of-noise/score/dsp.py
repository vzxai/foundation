"""DSP primitives for the score: oscillators, noise, filters, envelopes, effects.

Everything works on float64 numpy arrays at SR. Stereo signals are shape (n, 2).
Per-sample filters are numba-compiled so time-varying sweeps stay cheap.
"""
import os
import subprocess
import tempfile

import numpy as np
from numba import njit
from scipy import signal

SR = 44100
RNG = np.random.default_rng(1729)


def secs(n):
    return int(round(n * SR))


def midi_hz(m):
    return 440.0 * 2.0 ** ((np.asarray(m, dtype=float) - 69.0) / 12.0)


# ---------------------------------------------------------------- noise

def white(n):
    return RNG.standard_normal(n)


def colored(n, slope):
    """Noise with power ~ 1/f^slope (1 = pink, 2 = brown), unit RMS."""
    spec = np.fft.rfft(RNG.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / SR)
    f[0] = f[1]
    spec *= f ** (-slope / 2)
    x = np.fft.irfft(spec, n)
    return x / (np.std(x) + 1e-12)


# ---------------------------------------------------------------- oscillators

@njit(cache=True)
def _polyblep(t, dt):
    if t < dt:
        t /= dt
        return t + t - t * t - 1.0
    if t > 1.0 - dt:
        t = (t - 1.0) / dt
        return t * t + t + t + 1.0
    return 0.0


@njit(cache=True)
def _saw(freq, phase0):
    n = freq.shape[0]
    out = np.empty(n)
    ph = phase0
    for i in range(n):
        dt = freq[i] / 44100.0
        out[i] = 2.0 * ph - 1.0 - _polyblep(ph, dt)
        ph += dt
        if ph >= 1.0:
            ph -= 1.0
    return out


@njit(cache=True)
def _square(freq, phase0, width):
    n = freq.shape[0]
    out = np.empty(n)
    ph = phase0
    for i in range(n):
        dt = freq[i] / 44100.0
        v = 1.0 if ph < width else -1.0
        v += _polyblep(ph, dt)
        ph2 = ph + 1.0 - width
        if ph2 >= 1.0:
            ph2 -= 1.0
        v -= _polyblep(ph2, dt)
        out[i] = v
        ph += dt
        if ph >= 1.0:
            ph -= 1.0
    return out


def as_curve(f, n):
    return np.full(n, float(f)) if np.isscalar(f) else np.asarray(f, dtype=float)


def saw(f, n, phase=None):
    return _saw(as_curve(f, n), RNG.random() if phase is None else phase)


def square(f, n, width=0.5):
    return _square(as_curve(f, n), RNG.random(), width)


def sine(f, n, phase=0.0):
    return np.sin(2 * np.pi * np.cumsum(as_curve(f, n)) / SR + phase)


def tri(f, n):
    return 2 * np.abs(2 * ((np.cumsum(as_curve(f, n)) / SR + RNG.random()) % 1) - 1) - 1


def supersaw(f, n, voices=7, detune=0.18, spread=1.0):
    """Stereo detuned saw stack (JP-8000 style)."""
    offs = np.linspace(-1, 1, voices) * detune
    out = np.zeros((n, 2))
    fc = as_curve(f, n)
    for i, o in enumerate(offs):
        v = saw(fc * 2 ** (o / 12), n)
        pan = 0.5 + 0.5 * spread * (i / (voices - 1) * 2 - 1)
        out[:, 0] += v * np.sqrt(1 - pan)
        out[:, 1] += v * np.sqrt(pan)
    return out / np.sqrt(voices)


# ---------------------------------------------------------------- filters

@njit(cache=True)
def _svf(x, cutoff, q, mode):
    """Topology-preserving state variable filter, per-sample cutoff.
    mode 0 low, 1 band, 2 high."""
    n = x.shape[0]
    out = np.empty(n)
    ic1 = 0.0
    ic2 = 0.0
    k = 1.0 / q
    for i in range(n):
        fc = cutoff[i]
        if fc > 20000.0:
            fc = 20000.0
        if fc < 10.0:
            fc = 10.0
        g = np.tan(np.pi * fc / 44100.0)
        a1 = 1.0 / (1.0 + g * (g + k))
        a2 = g * a1
        a3 = g * a2
        v3 = x[i] - ic2
        v1 = a1 * ic1 + a2 * v3
        v2 = ic2 + a2 * ic1 + a3 * v3
        ic1 = 2.0 * v1 - ic1
        ic2 = 2.0 * v2 - ic2
        if mode == 0:
            out[i] = v2
        elif mode == 1:
            out[i] = v1
        else:
            out[i] = x[i] - k * v1 - v2
    return out


def svf(x, cutoff, q=0.707, mode="low"):
    m = {"low": 0, "band": 1, "high": 2}[mode]
    if x.ndim == 2:
        return np.stack([svf(x[:, c], cutoff, q, mode) for c in range(x.shape[1])], 1)
    return _svf(np.ascontiguousarray(x, dtype=float), as_curve(cutoff, len(x)), float(q), m)


def butter(x, f, kind="low", order=4):
    sos = signal.butter(order, f, btype=kind, fs=SR, output="sos")
    return signal.sosfilt(sos, x, axis=0)


# ---------------------------------------------------------------- envelopes

def adsr(n, a=0.01, d=0.1, s=0.7, r=0.2, gate=None):
    """ADSR over n samples; gate (seconds) defaults to n minus release."""
    gate_n = n - secs(r) if gate is None else secs(gate)
    gate_n = max(1, min(gate_n, n))
    env = np.zeros(n)
    an, dn = max(1, secs(a)), max(1, secs(d))
    t = np.arange(gate_n)
    env[:gate_n] = np.where(t < an, t / an, s + (1 - s) * np.exp(-(t - an) / dn * 4))
    last = env[gate_n - 1]
    rn = n - gate_n
    if rn > 0:
        env[gate_n:] = last * np.exp(-np.arange(rn) / max(1, secs(r)) * 5)
    return env


def expdecay(n, t60):
    return np.exp(-np.arange(n) / SR * 6.9 / t60)


def ramp(n, a, b, curve=1.0):
    t = np.linspace(0, 1, n) ** curve
    return a + (b - a) * t


# ---------------------------------------------------------------- effects

def stereo(x, pan=0.0):
    if x.ndim == 2:
        return x
    l, r = np.sqrt((1 - pan) / 2), np.sqrt((1 + pan) / 2)
    return np.stack([x * l, x * r], 1)


def make_ir(seconds=4.0, damp=6000, predelay=0.02, seed=7):
    rng = np.random.default_rng(seed)
    n = secs(seconds)
    t = np.arange(n) / SR
    ir = rng.standard_normal((n, 2)) * np.exp(-t * 6.9 / seconds)[:, None]
    ir = butter(ir, damp, "low", 2)
    ir[: secs(0.08)] *= np.linspace(0, 1, secs(0.08))[:, None] ** 2
    ir = np.concatenate([np.zeros((secs(predelay), 2)), ir])
    return ir / np.sqrt(np.sum(ir ** 2))


_IRS = {}


def reverb(x, wet=0.3, seconds=4.0, damp=6000):
    key = (seconds, damp)
    if key not in _IRS:
        _IRS[key] = make_ir(seconds, damp)
    ir = _IRS[key]
    x = stereo(x)
    y = np.stack([signal.fftconvolve(x[:, c], ir[:, c])[: len(x)] for c in range(2)], 1)
    return x * (1 - wet) + y * wet * 2.0


def delay(x, t, fb=0.4, wet=0.3, pingpong=True):
    x = stereo(x)
    d = secs(t)
    y = np.zeros_like(x)
    tap = x.copy()
    for k in range(1, 8):
        tap = tap * fb
        sh = d * k
        if sh >= len(x):
            break
        ch = tap[:-sh]
        if pingpong and k % 2:
            ch = ch[:, ::-1]
        y[sh:] += ch
    return x + y * wet


def softclip(x, drive=1.0):
    return np.tanh(x * drive) / np.tanh(drive)


def bitcrush(x, bits=6, hold=4):
    q = 2 ** (bits - 1)
    y = np.round(x * q) / q
    if hold > 1:
        idx = (np.arange(len(y)) // hold) * hold
        y = y[idx]
    return y


def place(buf, x, start_s, gain=1.0):
    """Mix x into buf at start_s seconds, clipping to buffer bounds."""
    x = stereo(x)
    i = secs(start_s)
    if i >= len(buf):
        return
    if i < 0:
        x, i = x[-i:], 0
    j = min(len(buf), i + len(x))
    buf[i:j] += x[: j - i] * gain


def fade(x, fin=0.01, fout=0.01):
    x = x.copy()
    a, b = secs(fin), secs(fout)
    if a:
        x[:a] *= np.linspace(0, 1, a)[:, None] if x.ndim == 2 else np.linspace(0, 1, a)
    if b:
        x[-b:] *= np.linspace(1, 0, b)[:, None] if x.ndim == 2 else np.linspace(1, 0, b)
    return x


def sidechain(x, beats_s, depth=0.7, release=0.18):
    """Duck x at each beat time (seconds), like a kick-keyed compressor."""
    n = len(x)
    g = np.ones(n)
    rel = secs(release)
    shape = 1 - depth * (1 - np.linspace(0, 1, rel)) ** 2
    for b in beats_s:
        i = secs(b)
        if 0 <= i < n:
            j = min(n, i + rel)
            g[i:j] = np.minimum(g[i:j], shape[: j - i])
    return x * (g[:, None] if x.ndim == 2 else g)


def resample(x, ratio):
    """Change playback speed by ratio (>1 faster/higher)."""
    n = int(len(x) / ratio)
    src = np.arange(n) * ratio
    if x.ndim == 2:
        return np.stack([np.interp(src, np.arange(len(x)), x[:, c]) for c in range(2)], 1)
    return np.interp(src, np.arange(len(x)), x)


def tapestop(x, length_s):
    """Slow the tail of x to a halt over length_s seconds."""
    n = len(x)
    m = min(n, secs(length_s))
    speed = np.linspace(1, 0, m) ** 1.5
    pos = np.cumsum(speed)
    head = x[: n - m]
    src = (n - m) + pos
    src = np.clip(src, 0, n - 1)
    tail = np.stack([np.interp(src, np.arange(n), x[:, c]) for c in range(2)], 1) if x.ndim == 2 \
        else np.interp(src, np.arange(n), x)
    return np.concatenate([head, tail])


def granular(x, out_len_s, grain_s=0.08, density=60, pos_curve=None, pitch_jitter=0.0, seed=3):
    """Granular time-stretch: scatter Hann grains read along pos_curve (0..1 of x)."""
    rng = np.random.default_rng(seed)
    x = stereo(x)
    out_n = secs(out_len_s)
    out = np.zeros((out_n + secs(grain_s) * 2, 2))
    g = secs(grain_s)
    win = np.hanning(g)[:, None]
    count = int(out_len_s * density)
    for k in range(count):
        t = rng.random()
        p = pos_curve(t) if pos_curve else t
        src = int(p * (len(x) - g * 2))
        grain = x[src: src + g]
        if pitch_jitter:
            grain = resample(grain, 2 ** (rng.normal(0, pitch_jitter) / 12))
            grain = grain[: len(win)] if len(grain) >= len(win) else np.pad(grain, ((0, len(win) - len(grain)), (0, 0)))
        dst = int(t * out_n)
        out[dst: dst + len(grain)] += grain[: len(win)] * win[: len(grain)] * rng.uniform(0.4, 1)
    return out[:out_n] / np.sqrt(density * grain_s)


def normalize(x, peak=0.9):
    m = np.max(np.abs(x))
    return x * (peak / m) if m > 0 else x


def limiter(x, ceiling=0.95, release=0.08):
    """Look-ahead-free peak limiter with smoothed gain."""
    peak = np.max(np.abs(stereo(x)), axis=1)
    need = np.minimum(1.0, ceiling / np.maximum(peak, 1e-9))
    # instant attack, smooth release
    g = _release(need, np.exp(-1 / (release * SR)))
    return x * g[:, None]


@njit(cache=True)
def _release(need, coef):
    g = np.empty_like(need)
    cur = 1.0
    for i in range(need.shape[0]):
        if need[i] < cur:
            cur = need[i]
        else:
            cur = need[i] + (cur - need[i]) * coef
        g[i] = cur
    return g


# ---------------------------------------------------------------- voice

def speak(text, voice="en-us+f3", speed=120, pitch=50, amp=120):
    """Render text with espeak-ng; returns mono float array at SR."""
    with tempfile.TemporaryDirectory() as d:
        wav = os.path.join(d, "v.wav")
        subprocess.run(["espeak-ng", "-v", voice, "-s", str(speed), "-p", str(pitch), "-a", str(amp),
                        "-w", wav, text], check=True)
        from scipy.io import wavfile
        sr, y = wavfile.read(wav)
    y = y.astype(float) / 32768.0
    if sr != SR:
        y = signal.resample_poly(y, SR, sr)
    return y


def vocode(modulator, carrier, bands=32, lo=80, hi=12000, q=6.0, smooth=0.015):
    """Channel vocoder: speech envelope per band imposed on carrier (mono or stereo)."""
    n = min(len(modulator), len(carrier))
    m = modulator[:n]
    c = stereo(carrier[:n])
    edges = np.geomspace(lo, hi, bands)
    out = np.zeros((n, 2))
    lp = signal.butter(2, 1 / smooth, fs=SR, output="sos")
    for f in edges:
        sos = signal.butter(2, [f / (1 + 0.5 / q), f * (1 + 0.5 / q)], btype="band", fs=SR, output="sos")
        env = signal.sosfilt(lp, np.abs(signal.sosfilt(sos, m)))
        out += signal.sosfilt(sos, c, axis=0) * env[:, None]
    # keep sibilance intelligible
    hiss = butter(m, 5000, "high", 2)
    return out * 6.0 + stereo(hiss) * 0.3


FORMANTS = {  # F1..F4 Hz, rough female-ish vowel formants
    "a": (850, 1220, 2810, 3800),
    "e": (550, 2100, 2900, 3800),
    "i": (310, 2790, 3310, 4200),
    "o": (500, 900, 2800, 3600),
    "u": (330, 870, 2240, 3400),
}


def sing(f, n, vowel="a", breath=0.05, vib=5.5, vib_depth=0.25):
    """Formant-synth voice on pitch curve f (Hz)."""
    fc = as_curve(f, n)
    t = np.arange(n) / SR
    fc = fc * 2 ** (vib_depth * np.sin(2 * np.pi * vib * t) * np.clip(t / 0.3, 0, 1) / 12)
    src = saw(fc, n) * 0.6 + white(n) * breath
    out = np.zeros(n)
    for k, F in enumerate(FORMANTS[vowel]):
        out += svf(src, F, q=8 + 4 * k, mode="band") * (1.0, 0.6, 0.35, 0.2)[k]
    return out
