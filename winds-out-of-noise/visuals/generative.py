"""Programmatic scenes. Each is a class built with (duration, params, decoder_factory)
and called with local time t (seconds) to return a float32 RGB frame in [0, 1], HxWx3.

They are stateful where the process is (reaction-diffusion, rhizome growth), so the
renderer always plays them forward from their start.
"""
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from scipy import fft, ndimage

W, H = 1920, 1080
FONT = "/usr/share/fonts/opentype/inter/InterDisplay-Medium.otf"
MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
SERIF_I = "/usr/share/fonts/truetype/freefont/FreeSerifItalic.ttf"


def up(img, w=W, h=H, resample=Image.BILINEAR):
    """Upscale a float HxW(x3) array to the output size."""
    a = np.clip(img * 255, 0, 255).astype(np.uint8)
    out = np.asarray(Image.fromarray(a).resize((w, h), resample)).astype(np.float32) / 255
    return out if out.ndim == 3 else np.repeat(out[..., None], 3, 2)


def smooth_noise(shape, scale, rng):
    return ndimage.gaussian_filter(rng.standard_normal(shape), scale, mode="wrap")


# ------------------------------------------------------------------ flow

class Flow:
    """Static that organizes into wind. params: order=(a, b) ramps 0 (noise) -> 1 (flow)."""

    def __init__(self, dur, params, dec):
        self.dur = dur
        self.order = params.get("order", (0.0, 1.0))
        self.tint = np.array(params.get("tint", (0.75, 0.82, 0.9)), np.float32)
        self.rng = np.random.default_rng(params.get("seed", 5))
        self.h, self.w = 270, 480
        self.tex = self.rng.random((self.h, self.w)).astype(np.float32)
        self.pot = [smooth_noise((self.h, self.w), 40, self.rng) for _ in range(2)]
        yy, xx = np.mgrid[0:self.h, 0:self.w].astype(np.float32)
        self.yy, self.xx = yy, xx

    def field(self, t):
        p = self.pot[0] * np.cos(t * 0.15) + self.pot[1] * np.sin(t * 0.15)
        gy, gx = np.gradient(p)
        vx, vy = gy + 0.02, -gx  # curl plus a prevailing westerly
        mag = np.sqrt(vx ** 2 + vy ** 2) + 1e-6
        return vx / mag, vy / mag

    def __call__(self, t):
        a, b = self.order
        o = float(np.clip(a + (b - a) * t / self.dur, 0, 1))
        static = self.rng.random((self.h, self.w)).astype(np.float32)
        vx, vy = self.field(t)
        L = 18
        acc = np.zeros((self.h, self.w), np.float32)
        wsum = 0.0
        px, py = self.xx.copy(), self.yy.copy()
        for s in range(L):
            w = 0.5 + 0.5 * np.cos(2 * np.pi * (s / L - t * 0.9))
            acc += w * ndimage.map_coordinates(self.tex, [py % self.h, px % self.w], order=1)
            wsum += w
            px += vx * 1.5
            py += vy * 1.5
        lic = acc / wsum
        lic = (lic - lic.mean()) * 3.2 + 0.5
        img = static * (1 - o) + lic * o
        img = np.clip(img, 0, 1)
        return up(img)[..., :3] * self.tint


# ------------------------------------------------------------------ compression

class Compression:
    """A real frame rebuilt from its k largest DCT coefficients, k growing."""

    def __init__(self, dur, params, dec):
        self.dur = dur
        frame = dec.still(params["src"], params["at"])
        small = np.asarray(Image.fromarray(frame).resize((480, 270), Image.BILINEAR)).astype(np.float32) / 255
        self.coef = np.stack([fft.dctn(small[..., c], norm="ortho") for c in range(3)], -1)
        mag = np.abs(self.coef).sum(-1).ravel()
        self.order = np.argsort(-mag)
        self.total = mag.size
        self.font = ImageFont.truetype(MONO, 26)

    def __call__(self, t):
        x = np.clip(t / self.dur, 0, 1)
        k = int(np.clip(np.round(2 ** (x * np.log2(self.total * 0.12))), 1, self.total))
        mask = np.zeros(self.total, bool)
        mask[self.order[:k]] = True
        c = self.coef * mask.reshape(270, 480)[..., None]
        img = np.stack([fft.idctn(c[..., i], norm="ortho") for i in range(3)], -1)
        out = up(np.clip(img, 0, 1), resample=Image.BICUBIC)
        lab = Image.new("L", (W, 60), 0)
        ImageDraw.Draw(lab).text((90, 10), f"k = {k:,} of {self.total:,} coefficients", font=self.font, fill=255)
        a = np.asarray(lab).astype(np.float32)[..., None] / 255
        out[60:120] = out[60:120] * (1 - a * 0.9) + a
        return out


# ------------------------------------------------------------------ reaction-diffusion

class ReactionDiffusion:
    """Gray-Scott at the 'mitosis' parameters: spots that divide like cells."""

    def __init__(self, dur, params, dec):
        self.dur = dur
        self.h, self.w = 180, 320
        rng = np.random.default_rng(params.get("seed", 3))
        self.u = np.ones((self.h, self.w), np.float32)
        self.v = np.zeros((self.h, self.w), np.float32)
        for _ in range(14):
            y, x = rng.integers(10, self.h - 10), rng.integers(10, self.w - 10)
            self.u[y - 4:y + 4, x - 4:x + 4] = 0.5
            self.v[y - 4:y + 4, x - 4:x + 4] = 0.25
        self.v += rng.random(self.v.shape).astype(np.float32) * 0.02
        self.F, self.k = 0.0367, 0.0649
        self.t = 0.0
        self.steps_per_s = params.get("speed", 600)
        self.c1 = np.array(params.get("c1", (0.05, 0.03, 0.02)), np.float32)
        self.c2 = np.array(params.get("c2", (1.0, 0.78, 0.45)), np.float32)

    def step(self, n):
        u, v = self.u, self.v
        for _ in range(n):
            lu = np.roll(u, 1, 0) + np.roll(u, -1, 0) + np.roll(u, 1, 1) + np.roll(u, -1, 1) - 4 * u
            lv = np.roll(v, 1, 0) + np.roll(v, -1, 0) + np.roll(v, 1, 1) + np.roll(v, -1, 1) - 4 * v
            uvv = u * v * v
            u += 0.16 * lu - uvv + self.F * (1 - u)
            v += 0.08 * lv + uvv - (self.F + self.k) * v
        self.u, self.v = u, v

    def __call__(self, t):
        n = int((t - self.t) * self.steps_per_s)
        if n > 0:
            self.step(n)
            self.t += n / self.steps_per_s
        g = np.clip(self.v * 3.2, 0, 1)
        img = self.c1 + (self.c2 - self.c1) * g[..., None]
        return up(img, resample=Image.BICUBIC)


# ------------------------------------------------------------------ rhizome

class Rhizome:
    """A branching network with cross-links grows; then it is territorialized onto a grid.
    params: grow=(t_a, t_b) growth window, snap=(t_a, t_b) territorialization window."""

    def __init__(self, dur, params, dec):
        self.dur = dur
        rng = np.random.default_rng(params.get("seed", 9))
        self.grow = params.get("grow", (0, dur))
        self.snap = params.get("snap", (dur, dur + 1))
        nodes = [(W / 2 + rng.normal(0, 200), H / 2 + rng.normal(0, 120), 0.0, -1) for _ in range(5)]
        for i in range(700):
            p = int(rng.integers(len(nodes)))
            x, y, b, _ = nodes[p]
            ang = rng.uniform(0, 2 * np.pi)
            r = rng.uniform(25, 70)
            nx, ny = x + r * np.cos(ang), y + r * np.sin(ang)
            if not (40 < nx < W - 40 and 40 < ny < H - 40):
                continue
            nodes.append((nx, ny, b + rng.uniform(0.2, 1.0), p))
        self.nodes = np.array([(x, y, b) for x, y, b, _ in nodes], np.float32)
        self.nodes[:, 2] /= self.nodes[:, 2].max()
        self.edges = [(p, i) for i, (_, _, _, p) in enumerate(nodes) if p >= 0]
        for _ in range(90):  # any point can connect to any other
            i, j = rng.integers(len(nodes), size=2)
            if i != j and np.hypot(*(self.nodes[i, :2] - self.nodes[j, :2])) < 260:
                self.edges.append((int(i), int(j)))
        g = 72
        self.grid = np.round(self.nodes[:, :2] / g) * g

    def __call__(self, t):
        ga, gb = self.grow
        grown = np.clip((t - ga) / (gb - ga), 0, 1)
        sa, sb = self.snap
        s = float(np.clip((t - sa) / (sb - sa), 0, 1))
        s = s * s * (3 - 2 * s)
        pos = self.nodes[:, :2] * (1 - s) + self.grid * s
        img = Image.new("RGB", (W, H), (0, 0, 0))
        d = ImageDraw.Draw(img)
        col = tuple(int(c) for c in np.array((150, 230, 190)) * (1 - s) + np.array((235, 235, 235)) * s)
        alive = self.nodes[:, 2] <= grown
        for i, j in self.edges:
            if not (alive[i] and alive[j]):
                continue
            (x1, y1), (x2, y2) = pos[i], pos[j]
            if s > 0:  # orthogonal routing as the territory takes hold
                mx, my = x2 * s + x1 * (1 - s), y1 * s + (y1 + y2) / 2 * (1 - s)
                d.line([(x1, y1), (mx, my), (x2, y2)], fill=col, width=2)
            else:
                d.line([(x1, y1), (x2, y2)], fill=col, width=2)
        for (x, y), a in zip(pos, alive):
            if a:
                d.ellipse([x - 3, y - 3, x + 3, y + 3], fill=col)
        glow = img.filter(ImageFilter.GaussianBlur(8))
        out = (np.asarray(img).astype(np.float32) + np.asarray(glow).astype(np.float32) * 1.6) / 255
        return np.clip(out, 0, 1)


# ------------------------------------------------------------------ hyperstition loop

class Loop:
    """Expectation -> investment -> infrastructure -> behaviour -> expectation, accelerating.
    Drawn as an overlay (black background, screened onto footage)."""

    LABELS = ["EXPECTED FUTURE", "INVESTMENT", "INFRASTRUCTURE", "BEHAVIOUR"]

    def __init__(self, dur, params, dec):
        self.dur = dur
        self.font = ImageFont.truetype(FONT, 34)

    def __call__(self, t):
        img = Image.new("RGB", (W, H), (0, 0, 0))
        d = ImageDraw.Draw(img)
        cx, cy, r = W / 2, H / 2, 300
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(255, 60, 170), width=3)
        for k, lab in enumerate(self.LABELS):
            a = -np.pi / 2 + k * np.pi / 2
            x, y = cx + r * np.cos(a), cy + r * np.sin(a)
            d.ellipse([x - 9, y - 9, x + 9, y + 9], fill=(255, 255, 255))
            tw = d.textlength(lab, font=self.font)
            ox = {0: -tw / 2, 1: 30, 2: -tw / 2, 3: -tw - 30}[k]
            oy = {0: -60, 1: -18, 2: 26, 3: -18}[k]
            d.text((x + ox, y + oy), lab, font=self.font, fill=(255, 255, 255))
        phase = 0.25 * t + 0.08 * t ** 2  # accelerating
        for j in range(12):  # comet tail
            a = -np.pi / 2 + 2 * np.pi * (phase - j * 0.012)
            x, y = cx + r * np.cos(a), cy + r * np.sin(a)
            rr = 14 - j
            c = int(255 * (1 - j / 12))
            d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=(c, int(c * 0.9), 255))
        glow = img.filter(ImageFilter.GaussianBlur(10))
        return np.clip((np.asarray(img).astype(np.float32) + np.asarray(glow).astype(np.float32)) / 255, 0, 1)


# ------------------------------------------------------------------ venn of viability

class Venn:
    """Viability sets V1..V4, each filled with footage. Their intersection S glows.
    params: srcs=[(src, at, label)], phase: 'meet' (apart -> overlapping) or 'expand'."""

    def __init__(self, dur, params, dec):
        self.dur = dur
        self.phase = params.get("phase", "meet")
        self.streams = [dec.stream(src, at, dur + 1) for src, at, _ in params["srcs"]]
        self.labels = [lab for _, _, lab in params["srcs"]]
        self.font = ImageFont.truetype(SERIF_I, 40)
        self.h, self.w = H // 2, W // 2
        yy, xx = np.mgrid[0:self.h, 0:self.w].astype(np.float32)
        self.yy, self.xx = yy * 2, xx * 2

    def geometry(self, x):
        n = len(self.streams)
        if self.phase == "meet":
            spread = 520 * (1 - x) + 170 * x
            rad = 300 + 40 * x
        else:
            spread = 170 * (1 - x) + 60 * x
            rad = 340 + 900 * x ** 1.5
        cs = [(W / 2 + spread * np.cos(-np.pi / 4 + k * 2 * np.pi / n),
               H / 2 + spread * 0.75 * np.sin(-np.pi / 4 + k * 2 * np.pi / n)) for k in range(n)]
        return cs, rad

    def __call__(self, t):
        x = float(np.clip(t / self.dur, 0, 1))
        x = x * x * (3 - 2 * x)
        cs, rad = self.geometry(x)
        out = np.zeros((self.h, self.w, 3), np.float32)
        inside_all = np.ones((self.h, self.w), bool)
        edge = np.zeros((self.h, self.w), np.float32)
        for (cx, cy), st in zip(cs, self.streams):
            frame = st.next()[::2, ::2].astype(np.float32) / 255
            dist = np.sqrt((self.xx - cx) ** 2 + (self.yy - cy) ** 2)
            m = np.clip((rad - dist) / 6, 0, 1)
            out = out * (1 - m[..., None] * 0.55) + frame * m[..., None] * 0.55
            inside_all &= dist < rad
            edge = np.maximum(edge, np.clip(1 - np.abs(dist - rad) / 3, 0, 1))
        s = ndimage.gaussian_filter(inside_all.astype(np.float32), 6)
        gold = np.array((1.0, 0.86, 0.6), np.float32)
        out = out + s[..., None] * (gold * 0.3 + out * 0.45) + edge[..., None] * 0.6
        img = Image.fromarray(np.clip(out * 255, 0, 255).astype(np.uint8)).resize((W, H), Image.BILINEAR)
        d = ImageDraw.Draw(img)
        for (cx, cy), lab in zip(cs, self.labels):
            vx, vy = cx - W / 2, cy - H / 2
            nrm = np.hypot(vx, vy) + 1e-6
            lx, ly = cx + vx / nrm * rad * 0.6, cy + vy / nrm * rad * 0.6
            if 0 < lx < W - 200 and 0 < ly < H - 60:
                d.text((lx, ly), lab, font=self.font, fill=(255, 255, 255), anchor="mm")
        return np.asarray(img).astype(np.float32) / 255


GENERATORS = {"flow": Flow, "compression": Compression, "rd": ReactionDiffusion,
              "rhizome": Rhizome, "loop": Loop, "venn": Venn}
