"""Build the stacked event panel for the moderation-list natural experiment.

Input: a directory of parquet files in the schema of the Balduf et al. anonymized
Bluesky snapshot (https://bsky.leobalduf.com/datasets.html): list_items,
list_blocks, posts, reposts, blocks (follows optional). The synthetic files from
sim/simulate.py use the same schema.

Design (see docs/PREREGISTRATION.md):
  event       = target account a is added to moderation list L at time T
                (list_items.created_at). The curator chooses T, not the subscriber.
  treated     = accounts subscribed to L at least GUARD days before T
  control     = accounts who subscribe to L only after T + W (not-yet-treated)
  outcome     = number of a's fresh artifacts (created in the period) taken up by
                the subscriber within H days, by channel:
                  direct: repost or quote of the artifact itself
                  copy:   subscriber posts the same external link after a did
  periods     = pre [T-W, T) and post [T, T+W), artifacts created in the first
                W-H days of each, so all pre-period uptake precedes T.

Usage: python -I build_panel.py DATA_DIR OUT.parquet [--window 14] [--h 3] [--guard 7]
"""
import argparse

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
    ap.add_argument("--control-gap", type=float, default=0,
                    help="controls must subscribe this many days after T+W (sensitivity: rules out "
                         "controls whose subscription was a reaction to the post-window itself)")
    ap.add_argument("--memory", default="8GB")
    ap.add_argument("--placebo-shift", type=float, default=0,
                    help="days to move the analysis windows earlier while keeping real treatment "
                         "assignment; with shift >= W both periods precede the block (expect HI ~ 0)")
    a = ap.parse_args()
    d = a.data_dir.rstrip("/")
    con = duckdb.connect()
    con.execute(f"SET memory_limit='{a.memory}'")
    W, H, G, CG = (f"INTERVAL ({x} * 86400) SECOND" for x in (a.window, a.h, a.guard, a.control_gap))
    ok = f"BETWEEN TIMESTAMPTZ '{a.min_date}' AND TIMESTAMPTZ '{a.max_date}'"

    # created_at is client-asserted in AT Protocol; drop implausible values.
    q = f"""
    CREATE TEMP VIEW li AS
      SELECT list.did_id::VARCHAR || '/' || list.rkey AS list_key, subject_id AS target,
             MIN(TRY_CAST(created_at AS TIMESTAMPTZ)) AS t_add
      FROM '{d}/list_items.parquet' GROUP BY 1, 2;
    CREATE TEMP VIEW lb AS
      SELECT subject.did_id::VARCHAR || '/' || subject.rkey AS list_key, did_id AS u,
             MIN(TRY_CAST(created_at AS TIMESTAMPTZ)) AS t_sub
      FROM '{d}/list_blocks.parquet' GROUP BY 1, 2;
    CREATE TEMP TABLE events AS
      SELECT ROW_NUMBER() OVER (ORDER BY list_key, target) AS event_id, list_key, target,
             t_add AS t_real, t_add - INTERVAL ({a.placebo_shift} * 86400) SECOND AS t_add
      FROM li WHERE t_add {ok}
        AND t_add - {W} >= TIMESTAMPTZ '{a.min_date}' AND t_add + {W} <= TIMESTAMPTZ '{a.max_date}';
    CREATE TEMP TABLE pairs AS
      SELECT e.event_id, e.target, e.t_add, lb.u,
             CASE WHEN lb.t_sub <= e.t_real - {G} THEN 1
                  WHEN lb.t_sub >  e.t_real + {W} + {CG} THEN 0 END AS treated
      FROM events e JOIN lb USING (list_key)
      WHERE lb.t_sub {ok} AND lb.u <> e.target
        AND (lb.t_sub <= e.t_real - {G} OR lb.t_sub > e.t_real + {W} + {CG});
    -- drop pairs already blocking the target by another route before the window ends
    -- (direct block, or another list that already contained the target)
    CREATE TEMP TABLE other_block AS
      SELECT did_id AS u, subject_id AS target, MIN(TRY_CAST(created_at AS TIMESTAMPTZ)) AS t
      FROM '{d}/blocks.parquet' GROUP BY 1, 2
      UNION ALL
      SELECT lb.u, li.target, GREATEST(lb.t_sub, li.t_add) FROM lb JOIN li USING (list_key);
    DELETE FROM pairs p WHERE EXISTS (
      SELECT 1 FROM other_block o WHERE o.u = p.u AND o.target = p.target
        AND o.t < p.t_add + {W} AND NOT (p.treated = 1 AND o.t >= p.t_add));
    -- fresh artifacts of each target in each period
    CREATE TEMP TABLE art AS
      SELECT e.event_id, p.did_id AS target, p.rkey, p.embed_external_uri AS url,
             TRY_CAST(p.created_at AS TIMESTAMPTZ) AS t_post,
             CASE WHEN TRY_CAST(p.created_at AS TIMESTAMPTZ) < e.t_add THEN 0 ELSE 1 END AS post
      FROM '{d}/posts.parquet' p JOIN events e ON p.did_id = e.target
      WHERE (TRY_CAST(p.created_at AS TIMESTAMPTZ) >= e.t_add - {W}
             AND TRY_CAST(p.created_at AS TIMESTAMPTZ) <  e.t_add - {H})
         OR (TRY_CAST(p.created_at AS TIMESTAMPTZ) >= e.t_add
             AND TRY_CAST(p.created_at AS TIMESTAMPTZ) <  e.t_add + {W} - {H});
    CREATE TEMP TABLE n_art AS
      SELECT event_id, post, COUNT(*) AS n_art, COUNT(url) AS n_art_url FROM art GROUP BY 1, 2;
    CREATE TEMP TABLE subj AS SELECT DISTINCT target FROM events;
    CREATE TEMP TABLE up_direct AS
      SELECT r.did_id AS u, r.subject.did_id AS target, r.subject.rkey AS rkey,
             TRY_CAST(r.created_at AS TIMESTAMPTZ) AS t_up
      FROM '{d}/reposts.parquet' r WHERE r.subject.did_id IN (SELECT target FROM subj)
      UNION ALL
      SELECT q.did_id, q.embed_record.did_id, q.embed_record.rkey, TRY_CAST(q.created_at AS TIMESTAMPTZ)
      FROM '{d}/posts.parquet' q
      WHERE q.embed_record IS NOT NULL AND q.embed_record.did_id IN (SELECT target FROM subj);
    CREATE TEMP TABLE target_urls AS SELECT DISTINCT url FROM art WHERE url IS NOT NULL;
    CREATE TEMP TABLE up_copy AS
      SELECT q.did_id AS u, q.embed_external_uri AS url, TRY_CAST(q.created_at AS TIMESTAMPTZ) AS t_up
      FROM '{d}/posts.parquet' q
      WHERE q.embed_external_uri IN (SELECT url FROM target_urls);
    CREATE TEMP TABLE y AS
      SELECT pr.event_id, pr.u, a.post,
             COUNT(DISTINCT CASE WHEN d.t_up BETWEEN a.t_post AND a.t_post + {H} THEN a.rkey END) AS y_direct,
             0 AS y_copy
      FROM pairs pr JOIN art a ON a.event_id = pr.event_id
      JOIN up_direct d ON d.u = pr.u AND d.target = a.target AND d.rkey = a.rkey
      GROUP BY 1, 2, 3
      UNION ALL
      SELECT pr.event_id, pr.u, a.post, 0,
             COUNT(DISTINCT CASE WHEN c.t_up BETWEEN a.t_post AND a.t_post + {H} THEN a.rkey END)
      FROM pairs pr JOIN art a ON a.event_id = pr.event_id AND a.url IS NOT NULL
      JOIN up_copy c ON c.u = pr.u AND c.url = a.url
      WHERE NOT EXISTS (SELECT 1 FROM up_copy c0 WHERE c0.u = pr.u AND c0.url = a.url AND c0.t_up < a.t_post)
      GROUP BY 1, 2, 3;
    CREATE TEMP TABLE panel AS
      SELECT pr.event_id, pr.target, pr.u, pr.treated, per.post,
             COALESCE(SUM(y.y_direct), 0) AS y_direct, COALESCE(SUM(y.y_copy), 0) AS y_copy,
             COALESCE(MAX(n.n_art), 0) AS n_art, COALESCE(MAX(n.n_art_url), 0) AS n_art_url,
             ANY_VALUE(e.list_key) AS list_key, ANY_VALUE(e.t_real) AS t_real
      FROM pairs pr CROSS JOIN (VALUES (0), (1)) per(post)
      JOIN events e ON e.event_id = pr.event_id
      LEFT JOIN y ON y.event_id = pr.event_id AND y.u = pr.u AND y.post = per.post
      LEFT JOIN n_art n ON n.event_id = pr.event_id AND n.post = per.post
      GROUP BY 1, 2, 3, 4, 5;
    """
    con.execute(q)
    con.execute(f"COPY panel TO '{a.out}' (FORMAT parquet)")
    print(con.execute("""
      SELECT treated, post, COUNT(*) pairs, SUM(y_direct) AS direct, SUM(y_copy) AS copied, SUM(n_art) AS arts
      FROM panel GROUP BY 1, 2 ORDER BY 1, 2""").df().to_string(index=False))
    print("events:", con.execute("SELECT COUNT(*) FROM events").fetchone()[0])


if __name__ == "__main__":
    main()
