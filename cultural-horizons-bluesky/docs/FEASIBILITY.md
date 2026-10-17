# Feasibility check on the real snapshot (no outcomes computed)

Run on 17 October 2026 against the Balduf et al. snapshot (2025-04-14). The check read only `list_items`, `list_blocks`, `lists` and `blocks`, plus parquet metadata and a 2M-row sample of `posts` to learn its embed layout. It counted no reposts, quotes or link uptake, so the hypotheses in `PREREGISTRATION.md` are still untested and the plan can still be frozen as written, or amended first.

## 1. Schema

All seven files match the schema `build_panel.py` expects: column names, the `list` / `subject` / `embed_record` structs and `TIMESTAMP WITH TIME ZONE` created_at.

| File | Rows | Size |
|---|---|---|
| list_items | 43.5M | 0.44 GB |
| list_blocks | 4.29M | 0.06 GB |
| lists | 0.99M | 0.03 GB |
| blocks | 120M | 1.6 GB |
| posts | 1.29B | 46.9 GB (columns the pipeline reads: ~20 GB) |
| reposts | 888M | 16.9 GB (columns the pipeline reads: ~12 GB) |
| follows | 2.16B | 24.9 GB (not used) |

Quotes with media (`app.bsky.embed.recordWithMedia`) do fill `embed_record`, so the direct channel sees them.

## 2. Design size

Events: list item first-added between 2023-02-15 and 2025-03-31, on a list with at least one subscriber. Arms use the default W = 14 and guard = 7, counted **before** the other-route exclusion.

| | Count |
|---|---|
| Events with a subscriber in either arm | 8.84M |
| Events with both arms | **3.88M** |
| Targets in those events | 1.66M |
| Lists in those events | 7,877 |
| Treated pairs / control pairs | **8.18B / 2.62B** |
| Median treated / control subscribers per event | 22 / 23 |
| Share of pairs on the 10 largest lists | 75% (11% of events) |

Events with both arms, by quarter of T:

| Quarter | Events |
|---|---|
| 2023 Q4 | 12,698 |
| 2024 Q1 | 68,489 |
| 2024 Q2 | 60,213 |
| 2024 Q3 | 116,717 |
| 2024 Q4 | 1,531,733 |
| 2025 Q1 | 2,085,762 |

93% of events fall in the six months after the November 2024 influx.

## 3. Consequences for the pipeline

**`build_panel.py` cannot run on this snapshot.** It materializes the ~10.8B event × subscriber pairs. Its first join filled the 31 GB disk allowance of a 4-core, 15 GB machine within 7 minutes. The Mantel–Haenszel estimator and the target bootstrap need only each event's four uptake sums, so `pipeline/build_panel_sparse.py` builds them from uptake rows instead. It joins each repost, quote or link post to the uptaker's own subscriptions, and never forms the pair cross product. `sim/check_sparse.py` confirms that it gives identical per-event cells to `build_panel.py`. The check covered 3 seeds × 4 flag settings, with direct blocks and overlapping subscriptions added so the exclusion path runs. The original simulation has neither, so that path had not been tested before.

## 4. Issues to settle before freezing the plan

These are recommendations. None of them is applied to `PREREGISTRATION.md`.

1. **Clustering.** The bootstrap resamples targets. But one list's events share subscribers, and the ten largest lists hold 75% of pairs. Uptake by the same subscriber across many targets on one list is correlated, and resampling targets ignores that. Recommendation: resample lists (or list × target two-way) for the primary CI, and report target clustering as a sensitivity.
2. **Orphan subscriptions.** Of the 29,450 lists that have subscribers, 11,727 (40%) are missing from `lists.parquet`, most likely deleted. They account for 2.33M of 4.29M subscription records (54%). Sensitivity analysis 3 ("purpose = modlist") would silently drop all of them. Recommendation: state whether "purpose unknown" counts as in or out. Also exclude lists known to be `curatelist` (1,743 subscription records), since subscribing to one does not block.
3. **Time concentration.** With 93% of events in 2024 Q4–2025 Q1, the result is mostly about the post-influx network. Recommendation: add a pre-specified split at 2024-11-01.
4. **Copy channel coverage.** When a quote also carries a link card, the link sits inside the `embed_media` JSON and `embed_external_uri` is empty. Recommendation: either extract `embed_media.external.uri` (a small change) or list the omission alongside the facet-link loss in §7 of the plan.
5. **List mutes are private.** A control subscriber may have muted the same list before T. That makes the control arm partly treated, which biases HI toward 0 for both channels. Add it to the threats table.
6. **Ethics note.** The "anonymized" snapshot still contains image alt text in `embed_images` / `embed_media`. The pipeline never reads it, but the raw files need the same care as account-level data.

## 5. Running the real analysis

Do this after the plan is frozen. DuckDB reads only the needed columns, so the data can stay remote:

```bash
python -I pipeline/build_panel_sparse.py https://bsky-data.leobalduf.com panel.parquet \
  --memory 12GB --temp-dir /big/disk/tmp
python -I pipeline/estimate.py panel.parquet --json result.json
```

`posts` is scanned three times (artifacts, quotes, link copies), about 60 GB of transfer in all. A local copy of the five needed `posts` columns (~20 GB) is faster if disk allows.
