"""Convert collected Jetstream JSONL into the pipeline's parquet schema.

  * DIDs are pseudonymized with a keyed hash (keep the key off the shared data).
  * Records deleted later are KEPT, with deleted_at set: the pipeline then
    estimates an intention-to-treat effect (subscription/addition as assigned),
    instead of silently dropping people who later unsubscribed.
  * created_at = relay-observed time by default (client-asserted createdAt is
    kept as asserted_at; it can be backdated).

Usage: python -I to_parquet.py IN_DIR OUT_DIR --key-file KEY [--time observed|asserted]
"""
import argparse
import glob
import gzip
import hashlib
import hmac
import json
import os

import pandas as pd

NAMES = {
    "app.bsky.feed.post": "posts", "app.bsky.feed.repost": "reposts", "app.bsky.graph.block": "blocks",
    "app.bsky.graph.listblock": "list_blocks", "app.bsky.graph.listitem": "list_items",
    "app.bsky.graph.list": "lists", "app.bsky.graph.follow": "follows",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("in_dir")
    ap.add_argument("out_dir")
    ap.add_argument("--key-file", required=True)
    ap.add_argument("--time", choices=["observed", "asserted"], default="observed")
    a = ap.parse_args()
    key = open(a.key_file, "rb").read().strip()

    def pid(did):
        return None if did is None else hmac.new(key, did.encode(), hashlib.sha256).hexdigest()[:20]

    def ref(uri):  # at://did/collection/rkey -> struct
        if not uri or not uri.startswith("at://"):
            return None
        did, coll, rkey = (uri[5:].split("/") + [None, None])[:3]
        return dict(did_id=pid(did), collection=coll, rkey=rkey)

    rows = {n: {} for n in NAMES.values()}
    deleted = {}
    for path in sorted(glob.glob(os.path.join(a.in_dir, "js-*.jsonl.gz"))):
        with gzip.open(path, "rt") as f:
            for line in f:
                ev = json.loads(line)
                c = ev["commit"]
                name = NAMES.get(c["collection"])
                if not name:
                    continue
                k = (ev["did"], c["rkey"])
                obs = pd.Timestamp(ev["time_us"], unit="us", tz="UTC")
                if c["operation"] == "delete":
                    deleted[(name, *k)] = obs
                    continue
                r = c.get("record") or {}
                asserted = pd.to_datetime(r.get("createdAt"), utc=True, errors="coerce")
                base = dict(did_id=pid(ev["did"]), rkey=c["rkey"], observed_at=obs, asserted_at=asserted,
                            created_at=obs if a.time == "observed" else asserted)
                if name == "posts":
                    e = r.get("embed") or {}
                    t = e.get("$type")
                    rec = (e.get("record") or {})
                    rec_uri = rec.get("uri") or (rec.get("record") or {}).get("uri")
                    ext = (e.get("external") or (e.get("media") or {}).get("external") or {}).get("uri")
                    links = [ft.get("uri") for fc in r.get("facets") or [] for ft in fc.get("features", [])
                             if ft.get("$type") == "app.bsky.richtext.facet#link"]
                    base.update(embed_type=t, embed_record=ref(rec_uri), embed_external_uri=ext,
                                facet_links=links or None)
                elif name in ("reposts", "list_blocks"):
                    s = r.get("subject")
                    base.update(subject=ref(s.get("uri") if isinstance(s, dict) else s))
                elif name == "list_items":
                    base.update(list=ref(r.get("list")), subject_id=pid(r.get("subject")))
                elif name in ("blocks", "follows"):
                    base.update(subject_id=pid(r.get("subject")))
                elif name == "lists":
                    base.update(purpose=r.get("purpose"))
                rows[name].setdefault(k, base)  # first create wins
    os.makedirs(a.out_dir, exist_ok=True)
    for name, d in rows.items():
        df = pd.DataFrame(list(d.values()))
        if len(df):
            df["deleted_at"] = [deleted.get((name, did, rk)) for did, rk in d.keys()]
        df.to_parquet(os.path.join(a.out_dir, f"{name}.parquet"), index=False)
        print(f"{name:12s} {len(df):>10,d} rows, {df['deleted_at'].notna().sum() if len(df) else 0:,d} later deleted")


if __name__ == "__main__":
    main()
