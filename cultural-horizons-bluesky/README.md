# Cultural horizons, stage 2: Bluesky moderation-list natural experiment

This tests whether a community boundary (a curator adding an account to a moderation list that many people subscribe to) stops that account's *fresh* artifacts from crossing in. It measures two channels: direct passing-on (repost or quote) and re-making (posting the same link). The full design is in `docs/PREREGISTRATION.md`.

**Status:** the pipeline is built and validated on synthetic data with a planted truth. The real snapshot has been checked for schema and design size only (`docs/FEASIBILITY.md`). **No outcomes have been computed on real data.** The plan says to freeze it before they are.

## Layout

| Path | What it does |
|---|---|
| `pipeline/build_panel.py` | DuckDB: raw parquet → stacked event panel (event × subscriber × period). Reference version; too large for the full snapshot |
| `pipeline/extract_slim.py` | Streams the snapshot once and keeps only rows a build can use (target posts in their windows; quotes, links and reposts by list subscribers) |
| `pipeline/build_panel_sparse.py` | Same panel cells, built from uptake rows so the ~10.8B pairs are never formed. Use this on the real snapshot |
| `pipeline/estimate.py` | Mantel–Haenszel horizon index per channel, with cluster-bootstrap CIs and the naive before/after for contrast |
| `sim/simulate.py` | Synthetic data in the real schema, with confounders and a known effect. SYNTHETIC. |
| `sim/validate.py` | Bias and coverage over many seeds |
| `sim/check_sparse.py` | Sparse and dense builds give identical event cells (with blocks and overlapping lists added) |
| `collector/jetstream_collect.py` | Live capture of posts, reposts, blocks, lists, listitems, listblocks and follows, keeping deletions |
| `collector/to_parquet.py` | Collected JSONL → pipeline schema, with pseudonymized DIDs and intention-to-treat deletion handling |

## Run on the historical snapshot (after freezing the plan)

```bash
pip install duckdb pandas numpy pyarrow
URL=https://bsky-data.leobalduf.com     # or a local folder of the parquet files
python -I pipeline/build_panel_sparse.py $URL panel.parquet --memory 12GB --temp-dir /big/tmp
python -I pipeline/estimate.py panel.parquet --json result.json
python -I pipeline/build_panel_sparse.py $URL placebo.parquet --placebo-shift 14 --memory 12GB --temp-dir /big/tmp
python -I pipeline/estimate.py placebo.parquet
```

DuckDB reads only the needed columns over HTTP (about 20 GB of `posts` and 12 GB of `reposts`). `posts` is scanned three times, so a local copy is faster. `follows` is not used.

## Run the prospective collection

```bash
pip install websockets pandas pyarrow
python -I collector/jetstream_collect.py raw/        # leave running for 8+ weeks
head -c 32 /dev/urandom | base64 > ../hash.key       # keep outside the data folder
python -I collector/to_parquet.py raw/ data_live/ --key-file ../hash.key
python -I pipeline/build_panel.py data_live panel_live.parquet --min-date <start> --max-date <end>
```

## Reproduce the validation

```bash
python -I sim/validate.py /tmp/val --seeds 20 --copy-effects 0.5,0.0,0.9
python -I sim/check_sparse.py /tmp/chk
```
