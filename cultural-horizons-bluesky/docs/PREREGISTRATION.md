# Cultural horizons, stage 2: do community boundaries trap fresh artifacts?

Draft analysis plan, written 17 October 2026 **before any real data was analyzed**. It is not an external preregistration until deposited (e.g. OSF) with a timestamp. Freeze it there before running `build_panel.py` on real files.

## 1. Question

The stage-1 Lemmy pilot showed that declared blocks grew while a mutually reachable posting core persisted. It could not answer the causal question, because the released graphs have no artifact timestamps or sharing ancestry:

> When a community adopts a boundary against a source, do fresh artifacts from that source stop crossing into the community, or do they cross anyway by being copied?

The cultural event horizon idea makes this a measurable quantity. For channel *c*:

**Horizon index HI_c = 1 − R_c**, where R_c is the ratio of boundary-crossing uptake under the boundary to the uptake that would have happened without it.
HI = 1 means nothing crosses. HI = 0 means the boundary does nothing. HI < 0 means the boundary attracts attention.

## 2. Why Bluesky moderation lists

| Requirement | Bluesky provides |
|---|---|
| Community-level rule adopted by many people at once | Moderation lists: one curator adds account *a* to list *L* and every subscriber blocks *a* from that moment |
| Exact treatment time, set by someone other than the subscriber | `listitem.createdAt`, chosen by the curator |
| Exact artifact identity and ancestry | Reposts and quotes reference the exact post URI. External links are kept in embeds. |
| Public, at full-network scale | All of these are public records. Balduf et al. released an anonymized full-network snapshot. |

Fediverse defederation is the closer analog to autonomous units (see §9). It lacks artifact-level ancestry at scale, so it is a replication target, not the primary test.

## 3. Design: stacked staggered difference-in-differences

- **Event:** target *a* first added to moderation list *L* at time *T*. Events need full windows inside the data range.
- **Treated:** subscribers of *L* whose subscription predates *T* by at least 7 days (guard). Their exposure changes at *T* because of the curator's choice, not their own.
- **Control (not-yet-treated):** subscribers of the same list *L* who subscribe only after *T + W*. They have the same taste for the list and face the same target in the same days.
- **Exclusions:** pairs already blocking *a* by another route (a direct block, or another list) before the relevant time.
- **Periods:** pre [T−W, T), post [T, T+W), W = 14 days. Fresh artifacts are posts by *a* created in the first W−H days of each period. Uptake counts only within H = 3 days of creation, so all pre-period uptake precedes *T*.
- **Channels (outcomes):**
  - `direct`: the subscriber reposts or quotes the artifact. Clients enforce blocks, so this is a **manipulation check**.
  - `copy`: the subscriber posts the same external link within H, not having posted it before *a* did. The artifact crosses by being re-made rather than by being passed on. **This is the primary scientific outcome.**
- **Estimator:** Mantel–Haenszel common ratio across event 2×2 count tables. This is equivalent to Poisson with event×arm and event×period fixed effects. Event×period effects absorb everything that happens to the target at *T*. CI: percentile bootstrap over targets (999 draws).

## 4. Hypotheses and decision rules (fixed in advance)

- **H1 (manipulation check):** HI_direct ≥ 0.9. If this fails, the data does not measure what we think it measures, and copy-channel results are not interpreted.
- **H2 (primary):** HI_copy. Read using the 95% CI:
  - lower bound > 0.8 → **strong horizon**: boundaries trap fresh artifacts even through copying
  - upper bound < 0.5 → **porous boundary**: most copying continues
  - CI includes 0 → **no detectable copy-channel effect**
  - otherwise → **partial horizon**, report the point estimate
- **Placebo:** shift windows back by W (`--placebo-shift 14`). Both periods then precede the block. Expected HI ≈ 0 for both channels. A placebo CI that excludes 0 is treated as evidence of differential trends, and the main result is downgraded to descriptive.

## 5. Pre-specified sensitivity analyses

1. W ∈ {7, 14, 28}, H ∈ {1, 3, 7}.
2. `--control-gap 30`: controls whose subscription might itself react to the post-window are dropped.
3. Restrict to lists with purpose `modlist` and to curators with ≥ 50 subscribers.
4. Restrict to events where the target had ≥ 1 linked artifact in both periods.
5. Exclude targets later suspended or deleted. Report how many there were.

## 6. Validation done before real data (synthetic, `sim/`)

The planted-truth simulation uses the real schema and includes the expected confounders: a target burst at addition, calendar decay, and early subscribers with higher interest. With 20 seeds per scenario (192 events each):

| True copy effect | Mean estimate | SD | 95% CI coverage |
|---|---|---|---|
| 0.50 | 0.496 | 0.049 | 95% |
| 0.00 | −0.053 | 0.111 | 95% |
| 0.90 | 0.898 | 0.014 | 95% |

On one run, the naive before/after estimate of the copy effect was **−2.55**: the confounding burst made blocking look as if it *increased* copying. The design-based estimate was 0.58 (CI 0.45–0.66) against a truth of 0.50. The placebo gave copy HI 0.14 (CI −0.20 to 0.37).

The simulation checks the code and the identification logic **under its own assumptions only**. It is not evidence about Bluesky.

## 7. Known threats

| Threat | Direction | Mitigation |
|---|---|---|
| Snapshot survivorship: deleted list items and listblocks are absent | Unknown. It hides treated people who later unsubscribed. | Prospective collector keeps deletions (intention-to-treat). Compare the two estimates. |
| `createdAt` is client-asserted and can be backdated | Noise or bias in T | Plausible-date filter. The prospective data uses relay-observed time. |
| Early and late subscribers trend differently | Either | Placebo test; event-study over several lags |
| Copy channel under-measured: the anonymized snapshot drops text and facet links | Attenuates counts, not the ratio, unless missingness differs by arm | Prospective data keeps facet links. Report both. |
| Common news shocks make everyone post a link | Absorbed: both arms face the same URL in the same days | Not applicable |
| Interference: treated people's followees keep reposting | This is part of the estimand ("does it cross?") | Not applicable |
| External validity: individual subscription to a list is not federation-level defederation | Not applicable | Replication in §9 |

## 8. Data

- **Historical:** Balduf et al. anonymized snapshot, 2025-04-14. These are public parquet files: `list_items`, `list_blocks`, `lists`, `blocks`, `posts`, `reposts`, `follows` at `https://bsky-data.leobalduf.com/<name>.parquet`. Cite their WWW '26 paper. Their paper studies the visibility and popularity of blocked accounts; artifact-level crossing is not, to our knowledge, analyzed there.
- **Prospective:** `collector/jetstream_collect.py` run continuously for ≥ 8 weeks, then `collector/to_parquet.py`, which pseudonymizes DIDs with a keyed hash.
- **Ethics:** Report aggregates only. Never publish account-level block relations. Keep the hash key separate from the data.

## 9. Stage 3: replication at the federation level

Use Mastodon/Pleroma defederation events with timestamps, from Colglazier, TeBlunthuis & Shaw (arXiv:2404.02109), or fresh scrapes of `/api/v1/instance/domain_blocks`. The outcome is boosts and link re-posts of the blocked server's fresh statuses, using the same estimator with servers in place of subscribers. This gives the closest test of autonomous units with boundaries, at the cost of lower artifact coverage.

## 10. What this design still cannot establish

- Whether ideas cross without a shared link (paraphrase, memes, images). The extension is image blob CIDs and embedding similarity, to be specified separately before use.
- Long-run cultural divergence. HI is a two-week, single-artifact quantity.
- Any *law* of horizons. A strong HI in one platform is a measured property of that boundary type, not a universal.
