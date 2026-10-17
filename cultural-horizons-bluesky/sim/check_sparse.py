"""Check that build_panel_sparse.py gives the same event cells as build_panel.py.

SYNTHETIC. simulate.py writes no direct blocks and gives each user one list, so
this script adds both before comparing: direct blocks at random times on
subscriber-target pairs, and second subscriptions to other lists. That exercises
the other-route exclusion and the multi-list join.

Usage: python -I check_sparse.py WORK_DIR [--seeds 3]
"""
import argparse
import os
import subprocess
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PIPE = os.path.join(HERE, "..", "pipeline")
sys.path.insert(0, PIPE)
from estimate import cells  # noqa: E402

FLAGS = ([], ["--h", "1", "--window", "7"], ["--control-gap", "30"], ["--placebo-shift", "14"])


def run(*args):
    subprocess.run([sys.executable, "-I", *args], check=True, stdout=subprocess.DEVNULL)


def perturb(d, rng):
    lb = pd.read_parquet(f"{d}/list_blocks.parquet")
    li = pd.read_parquet(f"{d}/list_items.parquet")
    lo, hi = lb.created_at.min(), lb.created_at.max()
    rand_t = lambda n: lo + (hi - lo) * rng.random(n)
    users, targets = lb.did_id.unique(), li.subject_id.unique()
    n = len(users) // 4
    blocks = pd.DataFrame(dict(did_id=rng.choice(users, n), rkey=[f"b{i}" for i in range(n)],
                               created_at=rand_t(n), subject_id=rng.choice(targets, n)))
    extra = lb.sample(n, random_state=int(rng.integers(1 << 31))).reset_index(drop=True)
    extra["subject"] = lb.subject.sample(n, random_state=int(rng.integers(1 << 31))).to_numpy()
    extra["rkey"] = [f"lbx{i}" for i in range(n)]
    extra["created_at"] = rand_t(n)
    pd.concat([lb, extra], ignore_index=True).to_parquet(f"{d}/list_blocks.parquet")
    blocks.to_parquet(f"{d}/blocks.parquet")


def table(path, ch):
    return cells(pd.read_parquet(path), ch).set_index("event_id")[["T0", "T1", "C0", "C1"]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work")
    ap.add_argument("--seeds", type=int, default=3)
    a = ap.parse_args()
    bad = 0
    for s in range(a.seeds):
        d = os.path.join(a.work, f"s{s}")
        run(os.path.join(HERE, "simulate.py"), d, "--seed", str(s))
        perturb(d, np.random.default_rng(s))
        for f in FLAGS:
            run(os.path.join(PIPE, "build_panel.py"), d, d + "/dense.parquet", *f)
            run(os.path.join(PIPE, "build_panel_sparse.py"), d, d + "/sparse.parquet", *f)
            for ch in ("y_direct", "y_copy"):
                x, y = table(d + "/dense.parquet", ch), table(d + "/sparse.parquet", ch)
                idx = x.index.union(y.index)
                x, y = x.reindex(idx, fill_value=0), y.reindex(idx, fill_value=0)
                m = int((x != y).any(axis=1).sum())
                bad += m
                print(f"seed {s} {' '.join(f) or 'default':22s} {ch:8s} events {len(idx):4d} "
                      f"mismatched {m}  total uptake {int(x.to_numpy().sum())}")
    print("OK: identical cells" if bad == 0 else f"FAIL: {bad} mismatched event tables")
    sys.exit(bad > 0)


if __name__ == "__main__":
    main()
