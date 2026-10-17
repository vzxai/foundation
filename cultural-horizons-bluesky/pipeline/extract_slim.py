"""Stream the snapshot once and keep only the rows the panel builds can use.

Writes OUT_DIR in the same schema subset that build_panel_sparse.py reads, so every
main, placebo and sensitivity build runs on local files:

  list_items, list_blocks  lists known to be curatelist/referencelist dropped
                           (subscribing to them does not block; §11.3)
  lists, blocks            copied
  posts                    did_id, rkey, created_at, embed_record, embed_external_uri,
                           for posts by any listed account (possible target), plus quotes
                           and link posts by any list subscriber (possible uptaker).
                           embed_external_uri falls back to the link card of a
                           quote-with-media post (§11.4).
  reposts                  by a list subscriber, of a possible target's post

Usage: python -I extract_slim.py SRC OUT_DIR [--memory 10GB] [--temp-dir DIR]
SRC is a local folder or an http(s) prefix such as https://bsky-data.leobalduf.com
"""
import argparse
import os
import time

import duckdb


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--memory", default="10GB")
    ap.add_argument("--temp-dir")
    ap.add_argument("--threads", type=int, default=16, help="more threads hide HTTP request latency")
    a = ap.parse_args()
    s, o = a.src.rstrip("/"), a.out.rstrip("/")
    os.makedirs(o, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"SET memory_limit='{a.memory}'; SET preserve_insertion_order=false; SET threads={a.threads}")
    if a.temp_dir:
        con.execute(f"SET temp_directory='{a.temp_dir}'")
    if s.startswith("http"):
        con.execute("INSTALL httpfs; LOAD httpfs;")
        con.execute("SET http_retries=10; SET http_retry_wait_ms=2000")

    def step(name, sql):
        t = time.time()
        con.execute(sql)
        print(f"{name}: {time.time() - t:.0f}s", flush=True)

    step("lists", f"""
      CREATE TABLE nonblock AS SELECT did_id::VARCHAR || '/' || rkey AS list_key FROM '{s}/lists.parquet'
        WHERE purpose LIKE '%curatelist' OR purpose LIKE '%referencelist';
      COPY (SELECT * FROM '{s}/lists.parquet') TO '{o}/lists.parquet' (FORMAT parquet);
      COPY (SELECT * FROM '{s}/blocks.parquet') TO '{o}/blocks.parquet' (FORMAT parquet);
      COPY (SELECT * FROM '{s}/list_items.parquet'
            WHERE list.did_id::VARCHAR || '/' || list.rkey NOT IN (SELECT list_key FROM nonblock))
        TO '{o}/list_items.parquet' (FORMAT parquet);
      COPY (SELECT * FROM '{s}/list_blocks.parquet'
            WHERE subject.did_id::VARCHAR || '/' || subject.rkey NOT IN (SELECT list_key FROM nonblock))
        TO '{o}/list_blocks.parquet' (FORMAT parquet);
      CREATE TABLE subs AS SELECT DISTINCT did_id AS u FROM '{o}/list_blocks.parquet';
      -- possible targets and the span any of their event windows can cover
      -- (W up to 28 days, placebo shift up to 14, so 45 days before and 30 after)
      CREATE TABLE tg AS SELECT subject_id AS target,
          MIN(created_at) - INTERVAL 45 DAY AS lo, MAX(created_at) + INTERVAL 30 DAY AS hi
        FROM '{o}/list_items.parquet'
        WHERE list.did_id::VARCHAR || '/' || list.rkey IN
          (SELECT DISTINCT subject.did_id::VARCHAR || '/' || subject.rkey FROM '{o}/list_blocks.parquet')
        GROUP BY 1;
    """)
    print("subscribers", con.execute("SELECT COUNT(*) FROM subs").fetchone()[0],
          "possible targets", con.execute("SELECT COUNT(*) FROM tg").fetchone()[0], flush=True)
    link = ("COALESCE(embed_external_uri, CASE WHEN embed_type LIKE '%recordWithMedia' "
            "THEN json_extract_string(embed_media, '$.external.uri') END)")
    step("posts", f"""
      COPY (SELECT did_id, rkey, created_at, embed_record, {link} AS embed_external_uri
            FROM '{s}/posts.parquet' p
            WHERE EXISTS (SELECT 1 FROM tg WHERE tg.target = p.did_id AND p.created_at BETWEEN tg.lo AND tg.hi)
               OR (did_id IN (SELECT u FROM subs)
                   AND (embed_record.did_id IN (SELECT target FROM tg) OR {link} IS NOT NULL)))
        TO '{o}/posts.parquet' (FORMAT parquet, ROW_GROUP_SIZE 1000000)""")
    step("reposts", f"""
      COPY (SELECT did_id, created_at, subject FROM '{s}/reposts.parquet'
            WHERE did_id IN (SELECT u FROM subs) AND subject.did_id IN (SELECT target FROM tg))
        TO '{o}/reposts.parquet' (FORMAT parquet, ROW_GROUP_SIZE 1000000)""")
    for f in ("posts", "reposts"):
        print(f, con.execute(f"SELECT COUNT(*) FROM '{o}/{f}.parquet'").fetchone()[0], "rows")


if __name__ == "__main__":
    main()
