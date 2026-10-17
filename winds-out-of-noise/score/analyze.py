"""Score QA: per-section RMS of each stem, peak/clipping, and a spectrogram + envelope image."""
import json, os, sys
import numpy as np
from scipy.io import wavfile
from scipy import signal
from PIL import Image, ImageDraw

d = sys.argv[1]
cues = json.load(open(os.path.join(d, "cues.json")))
def load(name):
    sr, x = wavfile.read(os.path.join(d, name)); return sr, x.astype(float) / 32768
sr, master = load("score.wav")
print("master peak %.3f  clipped samples %d" % (np.abs(master).max(), np.sum(np.abs(master) > 0.999)))
stems = {k: load(f"stem_{k}.wav")[1] for k in ("noise", "classical", "hyperpop", "posthyperpop", "voice")}
print("%-24s %6s " % ("section", "master") + " ".join("%8s" % k[:8] for k in stems))
for name, a, b in cues["sections"]:
    seg = slice(int(a * sr), int(b * sr))
    db = lambda x: 20 * np.log10(np.sqrt(np.mean(x[seg] ** 2)) + 1e-9)
    print("%-24s %6.1f " % (name, db(master)) + " ".join("%8.1f" % db(x) for x in stems.values()))
# spectrogram image
mono = master.mean(1)[:: 2]
f, t, S = signal.spectrogram(mono, sr / 2, nperseg=2048, noverlap=1024)
S = 10 * np.log10(S + 1e-12)
keep = f < 8000
S = S[keep][::-1]
S = np.clip((S - S.max() + 80) / 80, 0, 1)
img = Image.fromarray((S ** 0.8 * 255).astype(np.uint8)).resize((1800, 400))
img = Image.merge("RGB", (img, img.point(lambda v: v * 0.7), img.point(lambda v: 255 - v if v > 0 else 0)))
canvas = Image.new("RGB", (1800, 520), "black"); canvas.paste(img, (0, 0))
dr = ImageDraw.Draw(canvas)
T = len(master) / sr
env = np.array(cues["envelope"]); env = env / env.max()
for i in range(1800):
    v = env[int(i / 1800 * len(env))]; dr.line([(i, 515), (i, 515 - v * 100)], fill=(120, 200, 255))
for name, a, b in cues["sections"]:
    x = a / T * 1800; dr.line([(x, 0), (x, 520)], fill="yellow"); dr.text((x + 3, 3), name, fill="yellow")
canvas.save(os.path.join(d, "spectrogram.png"))
