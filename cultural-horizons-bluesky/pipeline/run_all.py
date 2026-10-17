"""Run the frozen analysis set (PREREGISTRATION.md §§4, 5, 11) on an extracted data dir.

Builds: primary (W=14, H=3), placebo (shift 14), W in {7, 28}, H in {1, 7}, control gap 30.
Estimates on the primary panel: list-clustered (primary), target-clustered, T before /
on-or-after 2024-11-01, known modlist only, modlist with curator >= 50 subscribers,
linked artifacts in both periods. Each build and estimate is skipped if its output
already exists, so the script can be re-run after an interruption.

Usage: python -I run_all.py DATA_DIR OUT_DIR [--memory 11GB] [--temp-dir DIR] [--boot 999] [--buckets 16]
"""
import argparse
import json
import os
import subprocess
import sys

import duckdb

HERE = os.path.dirname(os.path.abspath(__file__))
BUILDS = {
    "primary": [],
    "placebo": ["--placebo-shift", "14"],
    "W7": ["--window", "7"],
    "W28": ["--window", "28"],
    "H1": ["--h", "1"],
    "H7": ["--h", "7"],
    "control_gap30": ["--control-gap", "30"],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data")
    ap.add_argument("out")
    ap.add_argument("--memory", default="11GB")
    ap.add_argument("--temp-dir")
    ap.add_argument("--boot", type=int, default=999)
    ap.add_argument("--buckets", type=int, default=16)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    o = a.out.rstrip("/")
    extra = ["--memory", a.memory, "--buckets", str(a.buckets)] + (["--temp-dir", a.temp_dir] if a.temp_dir else [])

    def py(*args, log):
        with open(log, "w") as f:
            subprocess.run([sys.executable, "-I", *args], check=True, stdout=f, stderr=subprocess.STDOUT)

    con = duckdb.connect()
    con.execute(f"""
      COPY (SELECT did_id::VARCHAR || '/' || rkey AS list_key FROM '{a.data}/lists.parquet'
            WHERE purpose LIKE '%modlist') TO '{o}/lists_modlist.parquet' (FORMAT parquet);
      COPY (WITH c AS (SELECT subject.did_id AS curator, COUNT(DISTINCT did_id) AS n
                       FROM '{a.data}/list_blocks.parquet' GROUP BY 1)
            SELECT l.did_id::VARCHAR || '/' || l.rkey AS list_key FROM '{a.data}/lists.parquet' l
            JOIN c ON c.curator = l.did_id WHERE l.purpose LIKE '%modlist' AND c.n >= 50)
        TO '{o}/lists_modlist_curator50.parquet' (FORMAT parquet);""")
    estimates = {
        "primary": ("primary", []),
        "cluster_target": ("primary", ["--cluster", "target"]),
        "T_before_2024-11-01": ("primary", ["--t-max", "2024-11-01"]),
        "T_from_2024-11-01": ("primary", ["--t-min", "2024-11-01"]),
        "modlist_only": ("primary", ["--lists", f"{o}/lists_modlist.parquet"]),
        "modlist_curator50": ("primary", ["--lists", f"{o}/lists_modlist_curator50.parquet"]),
        "linked_both_periods": ("primary", ["--linked-both"]),
        **{b: (b, []) for b in BUILDS if b != "primary"},
    }
    for b, flags in BUILDS.items():
        p = f"{o}/panel_{b}.parquet"
        if not os.path.exists(p):
            print("build", b, flush=True)
            py(os.path.join(HERE, "build_panel_sparse.py"), a.data, p + ".tmp", *flags, *extra,
               log=f"{o}/build_{b}.log")
            os.rename(p + ".tmp", p)
        for name, (src, eflags) in estimates.items():
            j = f"{o}/est_{name}.json"
            if src == b and not os.path.exists(j):
                print("estimate", name, flush=True)
                py(os.path.join(HERE, "estimate.py"), p, "--boot", str(a.boot), "--json", j, *eflags,
                   log=f"{o}/est_{name}.log")
    rows = {n: json.load(open(f"{o}/est_{n}.json")) for n in estimates if os.path.exists(f"{o}/est_{n}.json")}
    json.dump(rows, open(f"{o}/all_results.json", "w"), indent=2)
    for n, r in rows.items():
        print(f"{n:22s} events {r['events']:>9,}  " + "  ".join(
            f"{ch[2:]} {r[ch]['horizon_index']:6.3f} [{r[ch]['ci95'][0]:6.3f}, {r[ch]['ci95'][1]:6.3f}]"
            for ch in ("y_direct", "y_copy")))


if __name__ == "__main__":
    main()
