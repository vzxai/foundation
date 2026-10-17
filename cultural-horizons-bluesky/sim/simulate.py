"""Known-answer simulation in the Balduf et al. anonymized Bluesky schema.

SYNTHETIC DATA. Nothing produced here is an empirical finding. Its only purpose
is to check that pipeline/build_panel.py + pipeline/estimate.py recover planted
effects when the confounders we expect in the real data are present:

  * curators add a target to a moderation list when the target is bursting
    (more posts, more engagement from everyone) -> naive before/after is biased;
  * engagement decays with calendar time -> naive before/after is biased;
  * people who subscribe to a list earlier differ in baseline interest.

Planted truth (per artifact, for a blocked subscriber):
  direct channel (repost/quote) uptake multiplied by (1 - DIRECT_EFFECT)
  copy channel (re-posting the same external link) multiplied by (1 - COPY_EFFECT)

  creation channel: each target a subscriber comes to block multiplies their rate
  of posting never-before-seen links by (1 + CREATE_EFFECT)

Usage: python -I simulate.py OUT_DIR [--seed N] [--copy-effect X] [--create-effect X]
"""
import argparse
import os

import numpy as np
import pandas as pd

DAY = 86400.0
T0 = pd.Timestamp("2024-06-01", tz="UTC")


def ts(seconds):
    return T0 + pd.to_timedelta(np.asarray(seconds), unit="s")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--lists", type=int, default=24)
    ap.add_argument("--targets-per-list", type=int, default=8)
    ap.add_argument("--subs-per-list", type=int, default=160)
    ap.add_argument("--days", type=int, default=240)
    ap.add_argument("--direct-effect", type=float, default=0.98)
    ap.add_argument("--copy-effect", type=float, default=0.50)
    ap.add_argument("--create-effect", type=float, default=0.30)
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    os.makedirs(a.out_dir, exist_ok=True)

    horizon = a.days * DAY
    next_id = iter(range(1, 10**9))
    posts, reposts, list_items, list_blocks, lists, follows = [], [], [], [], [], []
    url_counter = iter(range(1, 10**9))

    for li in range(a.lists):
        curator = next(next_id)
        list_rkey = f"list{li}"
        lists.append(dict(did_id=curator, rkey=list_rkey, purpose="app.bsky.graph.defs#modlist",
                          created_at=ts(0)))
        targets = [next(next_id) for _ in range(a.targets_per_list)]
        subs = np.array([next(next_id) for _ in range(a.subs_per_list)])
        t_sub = rng.uniform(0, horizon, len(subs))
        interest = rng.gamma(2.0, 0.5, len(subs)) * np.where(t_sub < horizon / 2, 1.3, 1.0)
        for s, tsub in zip(subs, t_sub):
            list_blocks.append(dict(did_id=int(s), rkey=f"lb{li}", created_at=ts(tsub),
                                    subject=dict(did_id=curator, collection="app.bsky.graph.list",
                                                 rkey=list_rkey)))
        t_adds = rng.uniform(30 * DAY, horizon - 30 * DAY, len(targets))
        for tgt, t_add in zip(targets, t_adds):
            list_items.append(dict(did_id=curator, rkey=f"li{tgt}", created_at=ts(t_add),
                                   list=dict(did_id=curator, collection="app.bsky.graph.list",
                                             rkey=list_rkey), subject_id=tgt))
            # posting process with a burst around the addition (the confounder)
            base = rng.poisson(0.6 * a.days)
            t_posts = rng.uniform(0, horizon, base)
            burst = rng.uniform(t_add - 3 * DAY, t_add + 11 * DAY, rng.poisson(25))
            t_posts = np.sort(np.concatenate([t_posts, burst]))
            in_burst = (t_posts > t_add - 3 * DAY) & (t_posts < t_add + 11 * DAY)
            virality = np.where(in_burst, 2.0, 1.0)
            decay = np.exp(-t_posts / (400 * DAY))
            has_url = rng.random(len(t_posts)) < 0.5
            urls = [f"https://example.org/a/{next(url_counter)}" if h else None for h in has_url]
            for k, tp in enumerate(t_posts):
                url = urls[k]
                posts.append(dict(did_id=tgt, rkey=f"p{tgt}_{k}", created_at=ts(tp),
                                  embed_type="app.bsky.embed.external" if url else None,
                                  embed_record=None, embed_external_uri=url))
            # subscriber responses: matrix subs x posts
            blocked = np.maximum(t_sub, t_add)[:, None] <= t_posts[None, :]
            lam = 0.004 * interest[:, None] * (virality * decay)[None, :]
            p_direct = lam * np.where(blocked, 1 - a.direct_effect, 1.0)
            p_copy = 1.6 * lam * has_url[None, :] * np.where(blocked, 1 - a.copy_effect, 1.0)
            for chan, p in (("repost", p_direct * 0.7), ("quote", p_direct * 0.3), ("copy", p_copy)):
                ui, pi = np.nonzero(rng.random(p.shape) < p)
                lag = rng.exponential(0.4 * DAY, len(ui))
                for u, k, d in zip(ui, pi, lag):
                    tu = t_posts[k] + d
                    if tu >= horizon:
                        continue
                    uid = int(subs[u])
                    src = dict(did_id=tgt, collection="app.bsky.feed.post", rkey=f"p{tgt}_{k}")
                    rk = f"r{chan}{tgt}_{k}_{uid}"
                    if chan == "repost":
                        reposts.append(dict(did_id=uid, rkey=rk, created_at=ts(tu), subject=src))
                    elif chan == "quote":
                        posts.append(dict(did_id=uid, rkey=rk, created_at=ts(tu),
                                          embed_type="app.bsky.embed.record", embed_record=src,
                                          embed_external_uri=None))
                    else:
                        posts.append(dict(did_id=uid, rkey=rk, created_at=ts(tu),
                                          embed_type="app.bsky.embed.external", embed_record=None,
                                          embed_external_uri=urls[k]))
        # original (network-first) links, by thinning a Poisson process
        r0, kmax = 0.15, len(targets)
        rmax = r0 * (1 + max(a.create_effect, 0)) ** kmax
        for s, tsub in zip(subs, t_sub):
            cand = rng.uniform(0, horizon, rng.poisson(rmax * a.days))
            k = (np.maximum(tsub, t_adds)[None, :] <= cand[:, None]).sum(axis=1)
            rate = r0 * np.exp(-cand / (400 * DAY)) * (1 + a.create_effect) ** k
            for j, tc in enumerate(cand[rng.random(len(cand)) < rate / rmax]):
                posts.append(dict(did_id=int(s), rkey=f"n{s}_{j}", created_at=ts(tc),
                                  embed_type="app.bsky.embed.external", embed_record=None,
                                  embed_external_uri=f"https://example.org/new/{next(url_counter)}"))
        for s in subs[: len(subs) // 3]:
            follows.append(dict(did_id=int(s), rkey=f"f{s}", created_at=ts(0),
                                subject_id=int(rng.choice(targets))))

    out = dict(posts=posts, reposts=reposts, list_items=list_items, list_blocks=list_blocks,
               lists=lists, follows=follows, blocks=[])
    for name, rows in out.items():
        df = pd.DataFrame(rows) if rows else pd.DataFrame(
            dict(did_id=pd.Series(dtype="int64"), rkey=pd.Series(dtype=str),
                 created_at=pd.Series(dtype="datetime64[ns, UTC]"),
                 subject_id=pd.Series(dtype="int64")))
        df.to_parquet(os.path.join(a.out_dir, f"{name}.parquet"), index=False)
        print(f"{name:12s} {len(df):>9,d} rows")
    with open(os.path.join(a.out_dir, "TRUTH.txt"), "w") as f:
        f.write(f"SYNTHETIC. direct_effect={a.direct_effect} copy_effect={a.copy_effect} create_effect={a.create_effect} seed={a.seed}\n")


if __name__ == "__main__":
    main()
