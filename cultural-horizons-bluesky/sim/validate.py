"""Repeat simulate -> build_panel -> estimate over seeds; report bias and CI coverage.

SYNTHETIC. Usage: python -I validate.py WORK_DIR [--seeds 20] [--copy-effects 0.5,0.0]
"""
import argparse
import json
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PIPE = os.path.join(HERE, "..", "pipeline")


def run(*args):
    subprocess.run([sys.executable, "-I", *args], check=True, stdout=subprocess.DEVNULL)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work")
    ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--copy-effects", default="0.5,0.0")
    ap.add_argument("--extra", default="", help="extra simulate.py args, space-separated")
    a = ap.parse_args()
    summary = {}
    for ce in map(float, a.copy_effects.split(",")):
        est, cover = [], []
        for s in range(a.seeds):
            d = os.path.join(a.work, f"ce{ce}_s{s}")
            run(os.path.join(HERE, "simulate.py"), d, "--seed", str(s), "--copy-effect", str(ce),
                *a.extra.split())
            run(os.path.join(PIPE, "build_panel.py"), d, d + "/panel.parquet")
            run(os.path.join(PIPE, "estimate.py"), d + "/panel.parquet", "--boot", "199",
                "--seed", str(s), "--json", d + "/est.json")
            r = json.load(open(d + "/est.json"))["y_copy"]
            est.append(r["horizon_index"])
            cover.append(r["ci95"][0] <= ce <= r["ci95"][1])
        summary[ce] = dict(mean=float(np.mean(est)), sd=float(np.std(est)),
                           bias=float(np.mean(est) - ce), coverage=float(np.mean(cover)))
        print(f"true copy effect {ce:.2f}: mean est {np.mean(est):.3f} (sd {np.std(est):.3f}), "
              f"bias {np.mean(est) - ce:+.3f}, 95% CI coverage {np.mean(cover):.0%} over {a.seeds} seeds")
    json.dump(summary, open(os.path.join(a.work, "validation.json"), "w"), indent=2)


if __name__ == "__main__":
    main()
