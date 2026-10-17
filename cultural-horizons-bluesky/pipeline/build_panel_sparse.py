"""Uptake-driven build of the event panel, for the full-network snapshot.

Same design, inputs and flags as build_panel.py, which stays the reference
implementation. build_panel.py materializes every event x subscriber pair. On the
2025-04-14 snapshot that is ~3.9M events and ~10.8B pairs, which does not fit on
disk or in memory. The estimator only needs each event's four uptake sums
(arm x period), and pairs with no uptake add nothing to them. So this build
starts from uptake rows (reposts, quotes, link posts by anyone), attaches each
uptaker's own list subscriptions, and keeps the rows that land in an event's
treated or control arm. It never forms the pair cross product.

Output rows:
  uptake rows    (event_id, target, u, treated, post, y_direct, y_copy), nonzero only
  placeholders   one per event that has any pair (u NULL, y 0), carrying n_treated
                 and n_control, so the bootstrap draws over the same targets as the
                 dense panel
estimate.py gives the same cells, estimate and naive ratio as on the dense panel.
One difference: an event whose pairs are all removed by the other-route exclusion
keeps its placeholder here, and adds an all-zero cluster to the bootstrap.

Usage: python -I build_panel_sparse.py DATA_DIR OUT.parquet [same flags as build_panel.py]
DATA_DIR may be an http(s) URL prefix; DuckDB then reads only the needed columns.
"""
import argparse
import os
import shutil

import duckdb


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data_dir")
    ap.add_argument("out")
    ap.add_argument("--window", type=float, default=14, help="W, days")
    ap.add_argument("--h", type=float, default=3, help="H, uptake horizon in days")
    ap.add_argument("--guard", type=float, default=7, help="treated must subscribe this long before T")
    ap.add_argument("--min-date", default="2023-02-01")
    ap.add_argument("--max-date", default="2025-04-14")
    ap.add_argument("--control-gap", type=float, default=0)
    ap.add_argument("--memory", default="8GB")
    ap.add_argument("--temp-dir", default=None, help="DuckDB spill directory")
    ap.add_argument("--placebo-shift", type=float, default=0)
    ap.add_argument("--buckets", type=int, default=1, help="run the per-target stages in this many target buckets")
    a = ap.parse_args()
    d = a.data_dir.rstrip("/")
    con = duckdb.connect()
    con.execute(f"SET memory_limit='{a.memory}'")
    con.execute("SET preserve_insertion_order=false")
    if a.temp_dir:
        con.execute(f"SET temp_directory='{a.temp_dir}'")
    if d.startswith("http"):
        con.execute("INSTALL httpfs; LOAD httpfs;")
    W, H, G, CG = (f"INTERVAL ({x} * 86400) SECOND" for x in (a.window, a.h, a.guard, a.control_gap))
    S = f"INTERVAL ({a.placebo_shift} * 86400) SECOND"
    ok = f"BETWEEN TIMESTAMPTZ '{a.min_date}' AND TIMESTAMPTZ '{a.max_date}'"
    ts = "TRY_CAST(created_at AS TIMESTAMPTZ)"

    q = f"""
    CREATE TEMP TABLE li AS
      SELECT list.did_id::VARCHAR || '/' || list.rkey AS list_key, subject_id AS target,
             MIN({ts}) AS t_add
      FROM '{d}/list_items.parquet' GROUP BY 1, 2;
    CREATE TEMP TABLE lb AS
      SELECT subject.did_id::VARCHAR || '/' || subject.rkey AS list_key, did_id AS u,
             MIN({ts}) AS t_sub
      FROM '{d}/list_blocks.parquet' GROUP BY 1, 2;
    CREATE TEMP TABLE events AS
      SELECT ROW_NUMBER() OVER (ORDER BY list_key, target) AS event_id, list_key, target,
             t_add AS t_real, t_add - {S} AS t_add
      FROM li WHERE t_add {ok}
        AND t_add - {W} >= TIMESTAMPTZ '{a.min_date}' AND t_add + {W} <= TIMESTAMPTZ '{a.max_date}'
        AND list_key IN (SELECT list_key FROM lb);
    -- arm sizes by counting, not by joining
    CREATE TEMP TABLE ev_n AS
      SELECT e.event_id, e.target, e.list_key, e.t_real, e.t_add,
        (SELECT COUNT(*) FROM lb WHERE lb.list_key = e.list_key AND lb.t_sub {ok}
           AND lb.u <> e.target AND lb.t_sub <= e.t_real - {G}) AS n_treated,
        (SELECT COUNT(*) FROM lb WHERE lb.list_key = e.list_key AND lb.t_sub {ok}
           AND lb.u <> e.target AND lb.t_sub > e.t_real + {W} + {CG}) AS n_control
      FROM events e;
    DELETE FROM ev_n WHERE n_treated + n_control = 0;
    DELETE FROM events WHERE event_id NOT IN (SELECT event_id FROM ev_n);
    -- only list subscribers can be in an arm, so only their uptake is read
    CREATE TEMP TABLE subs AS SELECT DISTINCT u FROM lb;
    """
    con.execute(q)
    # Everything below depends only on the target and the target's own links, so it
    # runs exactly per target bucket, which bounds memory and spill on the full snapshot.
    bucket_tables = ("ev_b", "events_b", "subj", "win", "art", "hit_direct", "art_url", "target_urls",
                     "first_url", "hit_copy", "hits", "hu", "cand", "cu", "other_block", "panel")
    parts = a.out + ".parts"
    os.makedirs(parts, exist_ok=True)
    for b in range(a.buckets):
        q = f"""
        CREATE TEMP TABLE ev_b AS SELECT * FROM ev_n WHERE target % {a.buckets} = {b};
        CREATE TEMP TABLE events_b AS SELECT * FROM events WHERE event_id IN (SELECT event_id FROM ev_b);
        CREATE TEMP TABLE subj AS SELECT DISTINCT target FROM events_b;
        CREATE TEMP TABLE win AS
          SELECT target, MIN(t_add) - {W} AS lo, MAX(t_add) + {W} AS hi FROM events_b GROUP BY 1;
        -- fresh artifacts at target level (event windows applied later)
        CREATE TEMP TABLE art AS
          SELECT p.did_id AS target, p.rkey, p.embed_external_uri AS url, TRY_CAST(p.created_at AS TIMESTAMPTZ) AS t_post
          FROM '{d}/posts.parquet' p JOIN win w ON p.did_id = w.target
          WHERE TRY_CAST(p.created_at AS TIMESTAMPTZ) >= w.lo AND TRY_CAST(p.created_at AS TIMESTAMPTZ) < w.hi;
        -- uptake within H of the artifact, by anyone (u, target, rkey, t_post)
        CREATE TEMP TABLE up_direct AS
          SELECT r.did_id AS u, r.subject.did_id AS target, r.subject.rkey AS rkey,
                 TRY_CAST(r.created_at AS TIMESTAMPTZ) AS t_up
          FROM '{d}/reposts.parquet' r
          WHERE r.subject.did_id IN (SELECT target FROM subj) AND r.did_id IN (SELECT u FROM subs)
          UNION ALL
          SELECT q.did_id, q.embed_record.did_id, q.embed_record.rkey, TRY_CAST(q.created_at AS TIMESTAMPTZ)
          FROM '{d}/posts.parquet' q
          WHERE q.embed_record IS NOT NULL AND q.embed_record.did_id IN (SELECT target FROM subj)
            AND q.did_id IN (SELECT u FROM subs);
        CREATE TEMP TABLE hit_direct AS
          SELECT DISTINCT d.u, a.target, a.rkey, a.t_post
          FROM up_direct d JOIN art a ON d.target = a.target AND d.rkey = a.rkey
          WHERE d.t_up BETWEEN a.t_post AND a.t_post + {H};
        DROP TABLE up_direct;
        CREATE TEMP TABLE art_url AS SELECT target, t_post, url FROM art WHERE url IS NOT NULL;
        CREATE TEMP TABLE target_urls AS SELECT DISTINCT url FROM art_url;
        CREATE TEMP TABLE up_copy AS
          SELECT q.did_id AS u, q.embed_external_uri AS url, TRY_CAST(q.created_at AS TIMESTAMPTZ) AS t_up
          FROM '{d}/posts.parquet' q
          WHERE q.embed_external_uri IN (SELECT url FROM target_urls) AND q.did_id IN (SELECT u FROM subs);
        CREATE TEMP TABLE first_url AS SELECT u, url, MIN(t_up) AS t_first FROM up_copy GROUP BY 1, 2;
        CREATE TEMP TABLE hit_copy AS
          SELECT DISTINCT c.u, a.target, a.rkey, a.t_post
          FROM up_copy c JOIN art a ON c.url = a.url
          JOIN first_url f ON f.u = c.u AND f.url = a.url
          WHERE c.t_up BETWEEN a.t_post AND a.t_post + {H} AND f.t_first >= a.t_post;
        DROP TABLE up_copy;
        CREATE TEMP TABLE hits AS
          SELECT u, target, rkey, t_post, 1 AS is_direct FROM hit_direct
          UNION ALL SELECT u, target, rkey, t_post, 0 FROM hit_copy;
        -- attach the uptaker's own subscriptions, then the events on those lists
        CREATE TEMP TABLE hu AS SELECT DISTINCT u, target FROM hits;
        CREATE TEMP TABLE cand AS
          SELECT e.event_id, e.target, e.t_add, e.t_real, h.u,
                 CASE WHEN lb.t_sub <= e.t_real - {G} THEN 1 ELSE 0 END AS treated
          FROM hu h JOIN lb ON lb.u = h.u JOIN events_b e ON e.list_key = lb.list_key AND e.target = h.target
          WHERE lb.t_sub {ok} AND h.u <> e.target
            AND (lb.t_sub <= e.t_real - {G} OR lb.t_sub > e.t_real + {W} + {CG});
        -- other-route blocks, only for candidate (u, target)
        CREATE TEMP TABLE cu AS SELECT DISTINCT u, target FROM cand;
        CREATE TEMP TABLE other_block AS
          SELECT b.did_id AS u, b.subject_id AS target, MIN(TRY_CAST(b.created_at AS TIMESTAMPTZ)) AS t
          FROM '{d}/blocks.parquet' b SEMI JOIN cu ON cu.u = b.did_id AND cu.target = b.subject_id
          GROUP BY 1, 2
          UNION ALL
          SELECT lb.u, li.target, GREATEST(lb.t_sub, li.t_add)
          FROM cu JOIN lb ON lb.u = cu.u JOIN li ON li.list_key = lb.list_key AND li.target = cu.target;
        DELETE FROM cand p WHERE EXISTS (
          SELECT 1 FROM other_block o WHERE o.u = p.u AND o.target = p.target
            AND o.t < p.t_add + {W} AND NOT (p.treated = 1 AND o.t >= p.t_add));
        -- place each hit in its event's pre or post artifact window
        CREATE TEMP TABLE panel AS
          SELECT c.event_id, c.target, c.u, c.treated,
                 CASE WHEN h.t_post < c.t_add THEN 0 ELSE 1 END AS post,
                 SUM(h.is_direct)::BIGINT AS y_direct, SUM(1 - h.is_direct)::BIGINT AS y_copy,
                 NULL::BIGINT AS n_treated, NULL::BIGINT AS n_control, NULL::VARCHAR AS list_key,
                 NULL::TIMESTAMPTZ AS t_real, NULL::BIGINT AS n_url0, NULL::BIGINT AS n_url1
          FROM cand c JOIN hits h ON h.u = c.u AND h.target = c.target
          WHERE (h.t_post >= c.t_add - {W} AND h.t_post < c.t_add - {H})
             OR (h.t_post >= c.t_add AND h.t_post < c.t_add + {W} - {H})
          GROUP BY 1, 2, 3, 4, 5
          UNION ALL
          SELECT event_id, target, NULL, 1, 0, 0, 0, n_treated, n_control, list_key, t_real,
            (SELECT COUNT(*) FROM art_url a WHERE a.target = ev_b.target
               AND a.t_post >= ev_b.t_add - {W} AND a.t_post < ev_b.t_add - {H}),
            (SELECT COUNT(*) FROM art_url a WHERE a.target = ev_b.target
               AND a.t_post >= ev_b.t_add AND a.t_post < ev_b.t_add + {W} - {H})
          FROM ev_b;
        -- carry the event's list and time onto its uptake rows
        UPDATE panel SET list_key = e.list_key, t_real = e.t_real
          FROM ev_b e WHERE panel.u IS NOT NULL AND panel.event_id = e.event_id;
        """
        con.execute(q)
        con.execute(f"COPY panel TO '{parts}/{b}.parquet' (FORMAT parquet)")
        for t in bucket_tables:
            con.execute(f"DROP TABLE {t}")
        print(f"bucket {b + 1}/{a.buckets} done", flush=True)
    con.execute(f"COPY (SELECT * FROM '{parts}/*.parquet') TO '{a.out}' (FORMAT parquet)")
    shutil.rmtree(parts)
    print(con.execute(f"""
      SELECT treated, post, SUM(y_direct) AS direct, SUM(y_copy) AS copied
      FROM '{a.out}' WHERE u IS NOT NULL GROUP BY 1, 2 ORDER BY 1, 2""").df().to_string(index=False))
    print(con.execute("""SELECT COUNT(*) AS events, SUM(n_treated) AS treated_pairs,
      SUM(n_control) AS control_pairs FROM ev_n""").df().to_string(index=False))


if __name__ == "__main__":
    main()
