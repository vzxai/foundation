# Cultural horizons, stage 2: Bluesky moderation-list natural experiment

This tests whether a community boundary (a curator adding an account to a moderation list that many people subscribe to) stops that account's *fresh* artifacts from crossing in. It measures two channels: direct passing-on (repost or quote) and re-making (posting the same link). The full design is in `docs/PREREGISTRATION.md`.

**Status:** the pipeline is built and validated on synthetic data with a planted truth. **No real data has been analyzed yet.** The session that built this ran under a network policy that blocked Bluesky, Jetstream and the dataset host.

## Layout

| Path | What it does |
|---|---|
| `pipeline/build_panel.py` | DuckDB: raw parquet → stacked event panel (event × subscriber × period) |
| `pipeline/estimate.py` | Mantel–Haenszel horizon index per channel, with cluster-bootstrap CIs and the naive before/after for contrast |
| `sim/simulate.py` | Synthetic data in the real schema, with confounders and a known effect. SYNTHETIC. |
| `sim/validate.py` | Bias and coverage over many seeds |
| `collector/jetstream_collect.py` | Live capture of posts, reposts, blocks, lists, listitems, listblocks and follows, keeping deletions |
| `collector/to_parquet.py` | Collected JSONL → pipeline schema, with pseudonymized DIDs and intention-to-treat deletion handling |

## Run on the historical snapshot (from a machine that can reach the host)

```bash
pip install duckdb pandas numpy pyarrow
mkdir data && cd data
for f in list_items list_blocks lists blocks posts reposts follows; do
  curl -O https://bsky-data.leobalduf.com/$f.parquet; done
cd ..
python -I pipeline/build_panel.py data panel.parquet --memory 16GB
python -I pipeline/estimate.py panel.parquet --json result.json
python -I pipeline/build_panel.py data placebo.parquet --placebo-shift 14
python -I pipeline/estimate.py placebo.parquet
```

`posts.parquet` is the big one. DuckDB streams it, but give the job disk space and RAM.

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
```
