"""Estimate the horizon index per uptake channel from the event panel.

Each event e gives a 2x2 table of uptake counts (arm x period). Under a Poisson
model with event-by-arm and event-by-period fixed effects and a common
treated:post rate ratio R, the Mantel-Haenszel estimator of the common odds
ratio of those count tables estimates R. Event-by-period effects absorb anything
that happens to the target at T (bursts, virality, deletion of the account's
posts) because both arms face the same target in the same days.

  horizon index HI = 1 - R   (1 = nothing crosses, 0 = boundary has no effect)

CIs: percentile bootstrap resampling targets (clusters), since one target can be
added to many lists.

Usage: python -I estimate.py PANEL.parquet [--boot 999] [--seed 0] [--json OUT]
"""
import argparse
import json

import numpy as np
import pandas as pd

CHANNELS = ("y_direct", "y_copy")


def cells(panel, ch):
    t = panel.pivot_table(index=["event_id", "target"], columns=["treated", "post"],
                          values=ch, aggfunc="sum", fill_value=0)
    t.columns = [f"{'T' if tr else 'C'}{po}" for tr, po in t.columns]
    for c in ("T0", "T1", "C0", "C1"):
        if c not in t:
            t[c] = 0
    return t.reset_index()


def mh_ratio(t):
    n = t[["T0", "T1", "C0", "C1"]].sum(axis=1).to_numpy(float)
    keep = n > 0
    a, b, c, d = (t[k].to_numpy(float)[keep] for k in ("T1", "T0", "C1", "C0"))
    n = n[keep]
    den = (b * c / n).sum()
    return np.nan if den == 0 else (a * d / n).sum() / den


def naive_ratio(t):
    return t["T1"].sum() / t["T0"].sum() if t["T0"].sum() else np.nan


def bootstrap(t, fn, boot, rng):
    by = {k: g for k, g in t.groupby("target")}
    keys = np.array(list(by))
    out = []
    for _ in range(boot):
        s = pd.concat([by[k] for k in rng.choice(keys, len(keys))], ignore_index=True)
        out.append(fn(s))
    return np.nanpercentile(out, [2.5, 97.5])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("panel")
    ap.add_argument("--boot", type=int, default=999)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--json")
    a = ap.parse_args()
    panel = pd.read_parquet(a.panel)
    rng = np.random.default_rng(a.seed)
    if "n_treated" in panel:  # sparse panel from build_panel_sparse.py: pairs before exclusion
        pairs = int(panel.n_treated.sum() + panel.n_control.sum())
    else:
        pairs = int(panel[["event_id", "u"]].drop_duplicates().shape[0])
    res = {"events": int(panel.event_id.nunique()), "targets": int(panel.target.nunique()),
           "pairs": pairs}
    for ch in CHANNELS:
        t = cells(panel, ch)
        r = mh_ratio(t)
        lo, hi = bootstrap(t, mh_ratio, a.boot, rng)
        nv = naive_ratio(t)
        res[ch] = dict(horizon_index=1 - r, ci95=[1 - hi, 1 - lo], naive_before_after=1 - nv,
                       counts={k: int(t[k].sum()) for k in ("T0", "T1", "C0", "C1")})
        print(f"{ch:9s} HI={1 - r:6.3f}  95% CI [{1 - hi:6.3f}, {1 - lo:6.3f}]   naive={1 - nv:7.3f}  "
              f"counts {res[ch]['counts']}")
    if a.json:
        with open(a.json, "w") as f:
            json.dump(res, f, indent=2)


if __name__ == "__main__":
    main()
