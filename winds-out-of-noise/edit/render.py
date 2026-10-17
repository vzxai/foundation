"""Render the film: decode shots, grade, composite, typeset, encode, mux the score.

Usage: python3 render.py <footage_cache> <score_dir> <out_dir> [--sections I,II] [--scale 0.5]
Each section renders in its own process to a segment, then segments are concatenated
and muxed with score.wav.
"""
import argparse
import json
import os
import subprocess
import sys
import textwrap
from multiprocessing import Pool

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "visuals"))
sys.path.insert(0, HERE)
import generative  # noqa: E402
from timeline import SECTION_STYLE, SHOTS, SOURCE_CROP, TEXT  # noqa: E402

FPS = 30
W, H = generative.W, generative.H
FONTS = {
    "light": "/usr/share/fonts/opentype/inter/InterDisplay-Light.otf",
    "thin": "/usr/share/fonts/opentype/inter/InterDisplay-Thin.otf",
    "black": "/usr/share/fonts/opentype/inter/InterDisplay-Black.otf",
    "mono": "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "monob": "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    "serifi": "/usr/share/fonts/truetype/freefont/FreeSerifItalic.ttf",
}
CACHE = None  # footage cache dir, set in main


# ================================================================ decoding

class Decoder:
    """Streams 30 fps RGB frames of one source range through ffmpeg."""

    def __init__(self, src, at, dur, speed=1.0, rev=False, crop="", fit=False):
        path = os.path.join(CACHE, src + ".mp4")
        geo = ("scale=%d:%d:force_original_aspect_ratio=decrease,pad=%d:%d:-1:-1" % (W, H, W, H)) if fit else \
              ("scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d" % (W, H, W, H))
        vf = SOURCE_CROP.get(src, "") + crop + geo + ",setsar=1"
        if speed != 1:
            vf += ",setpts=PTS/%g" % speed
        vf += ",fps=%d" % FPS
        if rev:
            vf += ",reverse"
        cmd = ["ffmpeg", "-v", "error", "-ss", "%.3f" % max(0, at), "-t", "%.3f" % (dur * speed + 0.6),
               "-i", path, "-vf", vf, "-an", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"]
        self.p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=W * H * 3 * 2)
        self.last = np.zeros((H, W, 3), np.uint8)

    def next(self):
        buf = self.p.stdout.read(W * H * 3)
        if len(buf) == W * H * 3:
            self.last = np.frombuffer(buf, np.uint8).reshape(H, W, 3)
        return self.last

    def close(self):
        self.p.kill()
        self.p.wait()


class DecoderFactory:
    def stream(self, src, at, dur):
        return Decoder(src, at, dur)

    def still(self, src, at):
        d = Decoder(src, at, 0.2)
        f = d.next().copy()
        d.close()
        return f


# ================================================================ looks

LUMA = np.array([0.299, 0.587, 0.114], np.float32)


def sat(img, s):
    y = (img @ LUMA)[..., None]
    return y + (img - y) * s


def contrast(img, k, pivot=0.5):
    return (img - pivot) * k + pivot


def look(img, name):
    if name == "dust":
        img = sat(img, 0.3) * np.array([0.86, 0.93, 1.0], np.float32)
        return np.clip(contrast(img, 0.95) + 0.03, 0, 1)
    if name == "amber":
        y = (img @ LUMA)[..., None]
        img = y ** 1.05 * np.array([1.0, 0.84, 0.6], np.float32) + 0.02
        return np.clip(contrast(img, 1.1, 0.45), 0, 1)
    if name == "silver":
        y = np.clip(contrast((img @ LUMA), 1.35), 0, 1)
        y = y * y * (3 - 2 * y)
        return np.repeat(y[..., None], 3, 2) * np.array([0.97, 0.98, 1.0], np.float32)
    if name == "neon":
        img = np.clip(contrast(sat(img, 1.7), 1.2), 0, 1)
        y = (img @ LUMA)[..., None]
        split = (1 - y) * np.array([0.05, 0.85, 1.0], np.float32) + y * np.array([1.0, 0.25, 0.75], np.float32)
        return np.clip(img * 0.7 + split * y * 0.45, 0, 1)
    if name == "acid":
        img = np.clip(contrast(sat(img, 1.4), 1.3), 0, 1)
        return img[..., [2, 0, 1]] * 0.6 + img * 0.4
    if name == "gold":
        img = sat(img, 0.9) * np.array([1.08, 0.98, 0.84], np.float32) + 0.025
        bloom = np.asarray(Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).resize((W // 8, H // 8))
                           .filter(ImageFilter.GaussianBlur(6)).resize((W, H))).astype(np.float32) / 255
        return np.clip(img + np.clip(bloom - 0.55, 0, 1) * 0.8, 0, 1)
    # natural
    return np.clip(contrast(img * np.array([1.03, 1.0, 0.96], np.float32), 1.05), 0, 1)


# ================================================================ effects

def zoom(frame, z, cx=0.5, cy=0.5):
    if abs(z - 1) < 1e-3:
        return frame
    w, h = W / z, H / z
    x0, y0 = (W - w) * cx, (H - h) * cy
    return np.asarray(Image.fromarray(frame).resize((W, H), Image.BILINEAR, box=(x0, y0, x0 + w, y0 + h)))


def glitch(img, amt, rng):
    if amt <= 0:
        return img
    dx = int(4 + 40 * amt)
    out = img.copy()
    out[..., 0] = np.roll(img[..., 0], dx, 1)
    out[..., 2] = np.roll(img[..., 2], -dx, 1)
    for _ in range(int(2 + 8 * amt)):
        y = int(rng.integers(0, H - 40))
        h = int(rng.integers(8, 90))
        out[y:y + h] = np.roll(out[y:y + h], int(rng.integers(-200, 200) * amt), 1)
    out[::3] *= 0.85
    return out


def crush(img, block=14, levels=5):
    small = img[::block, ::block]
    small = np.round(small * levels) / levels
    return np.repeat(np.repeat(small, block, 0), block, 1)[:H, :W]


def feedback(img, prev, t):
    if prev is None:
        return img
    a = Image.fromarray((np.clip(prev, 0, 1) * 255).astype(np.uint8))
    a = a.rotate(1.2 + 0.6 * np.sin(t), resample=Image.BILINEAR)
    m = 0.06
    a = a.resize((W, H), Image.BILINEAR, box=(W * m, H * m, W * (1 - m), H * (1 - m)))
    p = np.asarray(a).astype(np.float32) / 255
    return np.clip(img * 0.55 + p * 0.62, 0, 1)


# ================================================================ text

def font(name, size):
    return ImageFont.truetype(FONTS[name], size)


def shadowed(lines, fnt, fill=(255, 255, 255), spacing=1.32, glow=False, track=0, shadow=1.0):
    """Render centered lines into a tight RGBA array with a soft shadow."""
    asc, desc = fnt.getmetrics()
    lh = int((asc + desc) * spacing)

    def width(s):
        return fnt.getlength(s) + track * max(0, len(s) - 1)

    tw = int(max(width(s) for s in lines)) + 80
    th = lh * len(lines) + 80
    img = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for k, s in enumerate(lines):
        x = (tw - width(s)) / 2
        if track:
            for ch in s:
                d.text((x, 40 + k * lh), ch, font=fnt, fill=fill + (255,))
                x += fnt.getlength(ch) + track
        else:
            d.text((x, 40 + k * lh), s, font=fnt, fill=fill + (255,))
    a = np.asarray(img).astype(np.float32) / 255
    alpha = a[..., 3]
    sh = np.asarray(Image.fromarray((alpha * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(10 if glow else 6))).astype(np.float32) / 255
    rgb = a[..., :3]
    if glow:
        out_a = np.clip(alpha + sh * 0.6, 0, 1)
        out_rgb = (rgb * alpha[..., None] + 1.0 * sh[..., None] * 0.6) / np.maximum(out_a[..., None], 1e-4)
    else:
        out_a = np.clip(alpha + sh * 0.75 * shadow, 0, 1)
        out_rgb = rgb * alpha[..., None] / np.maximum(out_a[..., None], 1e-4)
    return np.dstack([np.clip(out_rgb, 0, 1), out_a])


_TXT = {}


def render_text(style, s, now, t0, t1, beat_idx):
    """Return (rgba, x, y, opacity) for a caption at time now, or None."""
    local = now - t0
    fade = min(1.0, local / 0.4, (t1 - now) / 0.4)
    if style == "foot":
        head, body = s.split("|")
        n = int(local * 48)
        shown = (head + "\n" + body)[:n]
        h_shown = shown.split("\n")[0]
        b_shown = shown.split("\n")[1] if "\n" in shown else ""
        key = (style, s, n)
        if key not in _TXT:
            img = Image.new("RGBA", (980, 260), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            d.rectangle([0, 0, 4, 250], fill=(255, 196, 120, 200))
            d.text((24, 0), h_shown, font=font("monob", 22), fill=(255, 200, 130, 255))
            y = 40
            for line in textwrap.wrap(b_shown, 62):
                d.text((24, y), line, font=font("mono", 25), fill=(240, 240, 240, 235))
                y += 34
            if n < len(head) + len(body) + 1 and int(now * 3) % 2 == 0:
                d.rectangle([24, y - (34 if b_shown else -2), 36, y - (8 if b_shown else -26)], fill=(255, 255, 255, 200))
            a = np.asarray(img).astype(np.float32) / 255
            bg = np.zeros_like(a)
            bg[..., 3] = np.clip(a[..., 3] * 0 + (a[..., 3] > 0) * 0, 0, 1)
            _TXT.clear() if len(_TXT) > 400 else None
            _TXT[key] = a
        return _TXT[key], 90, 76, fade
    key = (style, s)
    if key not in _TXT:
        if style in ("poem", "poem_big"):
            _TXT[key] = shadowed(s.split("|"), font("light", 58 if style == "poem" else 86), shadow=1.0 if style == "poem" else 1.6)
        elif style == "math":
            _TXT[key] = shadowed(s.split("\n"), font("serifi", 70), spacing=1.5, glow=True)
        elif style in ("hp", "hp_small"):
            _TXT[key] = shadowed([s], font("black", 172 if style == "hp" else 86), glow=True)
        elif style == "title":
            _TXT[key] = shadowed([s], font("thin", 92), track=18)
    rgba = _TXT[key]
    h, w = rgba.shape[:2]
    if style == "poem":
        y = int(H * 0.86 - h / 2)
    elif style == "math":
        y = int(H * 0.42 - h / 2)
    else:
        y = (H - h) // 2
    x = (W - w) // 2
    if style.startswith("hp"):
        palette = [(1.0, 0.25, 0.75), (0.2, 0.95, 1.0), (1.0, 1.0, 1.0), (0.85, 1.0, 0.2)]
        tint = np.array(palette[beat_idx % 4], np.float32)
        rgba = rgba.copy()
        rgba[..., :3] *= tint
        fade = 1.0
    return rgba, x, y, fade


def blit(frame, rgba, x, y, op):
    h, w = rgba.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(W, x + w), min(H, y + h)
    if x1 <= x0 or y1 <= y0:
        return
    sub = rgba[y0 - y:y1 - y, x0 - x:x1 - x]
    a = sub[..., 3:4] * op
    frame[y0:y1, x0:x1] = frame[y0:y1, x0:x1] * (1 - a) + sub[..., :3] * a


# ================================================================ timeline evaluation

def prepared_shots():
    shots = sorted(SHOTS, key=lambda s: (s["t"], s.get("blend", "normal") != "normal"))
    bases = [s for s in shots if s.get("blend", "normal") == "normal"]
    for i, s in enumerate(bases):
        nxt = bases[i + 1] if i + 1 < len(bases) else None
        xf = 0.0
        if nxt is not None:
            xf = nxt.get("xf", nxt.get("params", {}).get("xf", 0.0))
        s["tail"] = xf if nxt and nxt["t"] <= s["t"] + s["d"] + 1e-6 else 0.0
    for s in shots:
        s.setdefault("tail", 0.0)
    return shots


class Layer:
    def __init__(self, shot, dec):
        self.s = shot
        self.frames = 0
        src = shot["src"]
        self.gen = None
        self.over = None
        self.dec = None
        span = shot["d"] + shot["tail"]
        if src.startswith("gen:"):
            name = src[4:]
            if name in generative.GENERATORS:
                self.gen = generative.GENERATORS[name](span, shot.get("params", {}), dec)
        else:
            self.dec = Decoder(src, shot["at"], span, shot.get("speed", 1.0), shot.get("rev", False),
                               shot.get("crop", ""), shot.get("fit", False))
        if "over" in shot:
            name, params = shot["over"]
            self.over = generative.GENERATORS[name](span, params, dec)
        self.frozen = None

    def frame(self, local):
        s = self.s
        src = s["src"]
        if src == "gen:black":
            return np.zeros((H, W, 3), np.float32)
        if src == "gen:white":
            return np.full((H, W, 3), min(1.0, 0.4 + local), np.float32)
        if self.gen is not None:
            img = self.gen(local)
        else:
            raw = self.dec.next()
            if "freeze" in s.get("fx", []):
                if self.frozen is None or int(local * 8) % 3 == 0 and self.frames % 6 == 0:
                    self.frozen = raw.copy()
                raw = self.frozen
            z0, z1 = s.get("zoom", (1.0, 1.0))
            raw = zoom(raw, z0 + (z1 - z0) * local / max(s["d"], 1e-3))
            img = raw.astype(np.float32) / 255
            img = look(img, s.get("look", "natural"))
        if self.over is not None:
            o = self.over(local)
            img = 1 - (1 - img * 0.6) * (1 - o)
        self.frames += 1
        return img

    def close(self):
        if self.dec:
            self.dec.close()
        if self.gen is not None and hasattr(self.gen, "streams"):
            for st in self.gen.streams:
                st.close()


def section_of(t, sections):
    for name, a, b in sections:
        if a <= t < b:
            return name.split()[0]
    return sections[-1][0].split()[0]


def render_range(args):
    name, a, b, cache, cues_path, out_path, scale = args
    global CACHE
    CACHE = cache
    cues = json.load(open(cues_path))
    beats = np.array(cues["beats"])
    hits = np.array(cues["hits"])
    shots = prepared_shots()
    dec = DecoderFactory()
    rng = np.random.default_rng(int(a * 100))
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    vign = (1 - 0.32 * (((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2) ** 1.4)[..., None]
    ow, oh = int(W * scale) // 2 * 2, int(H * scale) // 2 * 2
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                            "-s", "%dx%d" % (W, H), "-r", str(FPS), "-i", "-",
                            "-vf", "scale=%d:%d" % (ow, oh), "-c:v", "libx264",
                            "-crf", "18", "-preset", "slow", "-pix_fmt", "yuv420p", out_path], stdin=subprocess.PIPE)
    live = {}
    prev = None
    f0, f1 = int(round(a * FPS)), int(round(b * FPS))
    for fi in range(f0, f1):
        now = fi / FPS
        sec = section_of(now, cues["sections"])
        style = SECTION_STYLE[sec]
        active = [s for s in shots if s["t"] - 1e-6 <= now < s["t"] + s["d"] + s["tail"]]
        ids = {id(s) for s in active}
        for k in list(live):
            if k not in ids:
                live.pop(k).close()
        frame = np.zeros((H, W, 3), np.float32)
        use_feedback = False
        glitch_amt = 0.0
        crush_on = False
        invert = False
        for s in active:
            if id(s) not in live:
                live[id(s)] = Layer(s, dec)
            local = now - s["t"]
            img = live[id(s)].frame(local)
            fx = s.get("fx", [])
            use_feedback |= "feedback" in fx
            crush_on |= "crush" in fx
            invert |= "invert" in fx
            if "glitch" in fx:
                glitch_amt = max(glitch_amt, 0.3)
            blend = s.get("blend", "normal")
            alpha = s.get("alpha", 1.0)
            xf = s.get("xf", s.get("params", {}).get("xf", 0.0))
            if xf > 0 and local < xf:
                alpha *= local / xf
            if blend == "screen":
                frame = frame * (1 - alpha) + (1 - (1 - frame) * (1 - img)) * alpha
            elif blend == "difference":
                frame = frame * (1 - alpha) + np.abs(frame - img) * alpha
            else:
                frame = frame * (1 - alpha) + img * alpha
        # beat-driven treatment
        past = beats[beats <= now]
        since_beat = now - past[-1] if len(past) else 9.0
        bidx = len(past)
        past_hits = hits[hits <= now]
        since_hit = now - past_hits[-1] if len(past_hits) else 9.0
        if glitch_amt > 0:
            glitch_amt += 0.7 * np.exp(-since_beat / 0.1) + 0.5 * np.exp(-since_hit / 0.08)
            frame = glitch(frame, min(glitch_amt, 1.0), rng)
        if crush_on and int(now * 8) % 2 == 0:
            frame = crush(frame)
        if invert and int(now * 6) % 2 == 0:
            frame = 1 - frame
        if use_feedback:
            frame = feedback(frame, prev, now)
        if style["flash"] > 0:
            frame = frame + style["flash"] * np.exp(-since_beat / 0.07) * 0.6
        # grain and vignette
        g = rng.standard_normal((H // 2, W // 2)).astype(np.float32) * style["grain"]
        frame = frame * vign + np.repeat(np.repeat(g, 2, 0), 2, 1)[..., None]
        frame = np.clip(frame, 0, 1)
        prev = frame
        # type
        for t0, t1, st, s in TEXT:
            if t0 <= now < t1:
                rgba, x, y, op = render_text(st, s, now, t0, t1, bidx)
                if st.startswith("hp"):
                    punch = 1 + 0.12 * np.exp(-(now - t0) / 0.06)
                    if punch > 1.01:
                        rgba = np.asarray(Image.fromarray((rgba * 255).astype(np.uint8)).resize(
                            (int(rgba.shape[1] * punch), int(rgba.shape[0] * punch)))).astype(np.float32) / 255
                        x, y = (W - rgba.shape[1]) // 2, (H - rgba.shape[0]) // 2
                blit(frame, rgba, x, y, op)
        # loop seam: fade from and to black at the very ends
        edge = min(1.0, now / 1.0, (cues["sections"][-1][2] - now) / 1.5)
        enc.stdin.write((np.clip(frame * edge, 0, 1) * 255).astype(np.uint8).tobytes())
        if fi % 150 == 0:
            print(f"[{name}] {now:6.1f}s", flush=True)
    for layer in live.values():
        layer.close()
    enc.stdin.close()
    enc.wait()
    return out_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cache")
    ap.add_argument("score")
    ap.add_argument("out")
    ap.add_argument("--sections", default="")
    ap.add_argument("--range", default="", help="render only start:end seconds (preview)")
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--jobs", type=int, default=4)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    cues_path = os.path.join(a.score, "cues.json")
    sections = json.load(open(cues_path))["sections"]
    jobs = []
    if a.range:
        s0, s1 = map(float, a.range.split(":"))
        jobs.append(("range", s0, s1, a.cache, cues_path, os.path.join(a.out, "range.mp4"), a.scale))
    else:
        want = set(a.sections.split(",")) if a.sections else None
        for name, s0, s1 in sections:
            key = name.split()[0]
            if want and key not in want:
                continue
            jobs.append((key, s0, s1, a.cache, cues_path, os.path.join(a.out, f"seg_{key}.mp4"), a.scale))
    # longest sections first so the pool finishes together
    jobs.sort(key=lambda j: j[1] - j[2])
    with Pool(a.jobs) as p:
        outs = p.map(render_range, jobs, chunksize=1)
    if a.range or a.sections:
        print("\n".join(outs))
        return
    order = [os.path.join(a.out, f"seg_{n.split()[0]}.mp4") for n, _, _ in sections]
    lst = os.path.join(a.out, "segments.txt")
    open(lst, "w").write("".join(f"file '{p}'\n" for p in order))
    final = os.path.join(a.out, "winds_out_of_noise.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst,
                    "-i", os.path.join(a.score, "score.wav"), "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "320k", "-movflags", "+faststart", "-shortest", final], check=True)
    print(final)


if __name__ == "__main__":
    main()
