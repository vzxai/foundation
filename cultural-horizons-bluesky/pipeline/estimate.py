"""Estimate the horizon index per uptake channel from the event panel.

Each event e gives a 2x2 table of uptake counts (arm x period). Under a Poisson
model with event-by-arm and event-by-period fixed effects and a common
treated:post rate ratio R, the Mantel-Haenszel estimator of the common odds
ratio of those count tables estimates R. Event-by-period effects absorb anything
that happens to the target at T (bursts, virality, deletion of the account's
posts) because both arms face the same target in the same days.

  horizon index HI = 1 - R   (1 = nothing crosses, 0 = boundary has no effect)

CIs: percentile cluster bootstrap. The default cluster is the list, since one
list's events share subscribers; --cluster target resamples targets instead
(one target can be added to many lists). The bootstrap draws multinomial
cluster weights over per-cluster sums of the MH terms, which is the same
resampling as drawing clusters with replacement.

Event filters (pre-specified subsets): --t-min / --t-max on the real addition
time, --lists FILE (parquet with a list_key column to keep), --linked-both
(target had >= 1 linked artifact in both periods).

Usage: python -I estimate.py PANEL.parquet [--boot 999] [--seed 0] [--cluster list|target] [--json OUT]
"""
import argparse
import json

import numpy as np
import pandas as pd

CHANNELS = ("y_direct", "y_copy")


def cells(panel, ch, by=("event_id", "target")):
    by = [c for c in by if c in panel]
    t = panel.pivot_table(index=by, columns=["treated", "post"],
                          values=ch, aggfunc="sum", fill_value=0)
    t.columns = [f"{'T' if tr else 'C'}{po}" for tr, po in t.columns]
    for c in ("T0", "T1", "C0", "C1"):
        if c not in t:
            t[c] = 0
    return t.reset_index()


def mh_terms(t):
    n = t[["T0", "T1", "C0", "C1"]].sum(axis=1).to_numpy(float)
    a, b, c, d = (t[k].to_numpy(float) for k in ("T1", "T0", "C1", "C0"))
    with np.errstate(invalid="ignore", divide="ignore"):
        num, den = np.where(n > 0, a * d / n, 0), np.where(n > 0, b * c / n, 0)
    return num, den


def mh_ratio(t):
    num, den = mh_terms(t)
    return np.nan if den.sum() == 0 else num.sum() / den.sum()


def naive_ratio(t):
    return t["T1"].sum() / t["T0"].sum() if t["T0"].sum() else np.nan


def bootstrap(t, cluster, boot, rng):
    num, den = mh_terms(t)
    g = pd.DataFrame(dict(k=t[cluster].to_numpy(), num=num, den=den)).groupby("k").sum()
    gn, gd, K = g.num.to_numpy(), g.den.to_numpy(), len(g)
    out = np.empty(boot)
    for i in range(boot):
        w = rng.multinomial(K, np.full(K, 1.0 / K))
        sd = w @ gd
        out[i] = (w @ gn) / sd if sd else np.nan
    return np.nanpercentile(out, [2.5, 97.5])


def filter_events(panel, a):
    keep = pd.Series(True, index=panel.index)
    if a.t_min or a.t_max:
        t = pd.to_datetime(panel.groupby("event_id").t_real.transform("max"), utc=True)
        if a.t_min:
            keep &= t >= pd.Timestamp(a.t_min, tz="UTC")
        if a.t_max:
            keep &= t < pd.Timestamp(a.t_max, tz="UTC")
    if a.lists:
        keep &= panel.list_key.isin(set(pd.read_parquet(a.lists).list_key))
    if a.linked_both:
        e = panel.groupby("event_id")[["n_url0", "n_url1"]].max()
        keep &= panel.event_id.isin(e.index[(e.n_url0 > 0) & (e.n_url1 > 0)])
    return panel[keep]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("panel")
    ap.add_argument("--boot", type=int, default=999)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--cluster", choices=("list", "target"), default="list")
    ap.add_argument("--t-min")
    ap.add_argument("--t-max")
    ap.add_argument("--lists")
    ap.add_argument("--linked-both", action="store_true")
    ap.add_argument("--json")
    a = ap.parse_args()
    panel = filter_events(pd.read_parquet(a.panel), a)
    cluster = {"list": "list_key", "target": "target"}[a.cluster]
    rng = np.random.default_rng(a.seed)
    if "n_treated" in panel:  # sparse panel from build_panel_sparse.py: pairs before exclusion
        pairs = int(panel.n_treated.sum() + panel.n_control.sum())
    else:
        pairs = int(panel[["event_id", "u"]].drop_duplicates().shape[0])
    res = {"events": int(panel.event_id.nunique()), "targets": int(panel.target.nunique()),
           "lists": int(panel.list_key.nunique()), "pairs": pairs, "cluster": a.cluster}
    for ch in CHANNELS:
        t = cells(panel, ch, by=("event_id", "target", "list_key"))
        r = mh_ratio(t)
        lo, hi = bootstrap(t, cluster, a.boot, rng)
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
