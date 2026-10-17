"""Stream the snapshot once and keep only the rows the panel builds can use.

Writes OUT_DIR in the same schema subset that build_panel_sparse.py reads, so every
main, placebo and sensitivity build runs on local files:

  list_items, list_blocks  lists known to be curatelist/referencelist dropped
                           (subscribing to them does not block; §11.3)
  lists                    copied
  blocks                   by list subscribers only (the exclusion only applies to them)
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
import io
import os
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import duckdb
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

UA = {"User-Agent": "cultural-horizons-extract/1.0 (research; pyarrow range reads)"}


class HTTPFile(io.RawIOBase):
    """Seekable read-only file over HTTP range requests."""

    def __init__(self, url, size=None):
        self.url, self.pos = url, 0
        self.size = size or int(urllib.request.urlopen(
            urllib.request.Request(url, method="HEAD", headers=UA)).headers["Content-Length"])

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, off, whence=0):
        self.pos = {0: off, 1: self.pos + off, 2: self.size + off}[whence]
        return self.pos

    def readinto(self, buf):
        n = min(len(buf), self.size - self.pos)
        if n <= 0:
            return 0
        for attempt in range(8):
            try:
                req = urllib.request.Request(self.url, headers={
                    **UA, "Range": f"bytes={self.pos}-{self.pos + n - 1}"})
                data = urllib.request.urlopen(req, timeout=120).read()
                break
            except OSError:
                if attempt == 7:
                    raise
                time.sleep(2 ** attempt)
        buf[:len(data)] = data
        self.pos += len(data)
        return len(data)


def filter_http_reposts(url, out, subs, targets, workers=16):
    """reposts by a subscriber of a possible target, read row group by row group.

    DuckDB's httpfs scan of reposts stalled near the end, twice at the same point,
    so this path reads row groups in parallel with pyarrow instead.
    """
    size = HTTPFile(url).size
    meta = pq.ParquetFile(HTTPFile(url, size)).metadata
    subs, targets = pa.array(subs, pa.int64()), pa.array(targets, pa.int64())

    def one(i):
        t = pq.ParquetFile(HTTPFile(url, size), metadata=meta).read_row_group(
            i, columns=["did_id", "created_at", "subject"])
        keep = pc.and_(pc.is_in(t["did_id"], subs),
                       pc.is_in(pc.struct_field(t["subject"], "did_id"), targets))
        return t.filter(keep)

    writer = None
    with ThreadPoolExecutor(workers) as ex:
        for k, t in enumerate(ex.map(one, range(meta.num_row_groups))):
            if writer is None:
                writer = pq.ParquetWriter(out, t.schema, compression="zstd")
            writer.write_table(t)
            if k % 500 == 0:
                print(f"  reposts row group {k}/{meta.num_row_groups}", flush=True)
    writer.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--memory", default="10GB")
    ap.add_argument("--temp-dir")
    ap.add_argument("--threads", type=int, default=16, help="more threads hide HTTP request latency")
    ap.add_argument("--steps", default="posts,reposts", help="which big files to (re)write; list files always are")
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
      CREATE TABLE subs AS SELECT DISTINCT did_id AS u FROM '{s}/list_blocks.parquet';
      COPY (SELECT * FROM '{s}/blocks.parquet' WHERE did_id IN (SELECT u FROM subs))
        TO '{o}/blocks.parquet' (FORMAT parquet, COMPRESSION zstd);
      COPY (SELECT * FROM '{s}/list_items.parquet'
            WHERE list.did_id::VARCHAR || '/' || list.rkey NOT IN (SELECT list_key FROM nonblock))
        TO '{o}/list_items.parquet' (FORMAT parquet, COMPRESSION zstd);
      COPY (SELECT * FROM '{s}/list_blocks.parquet'
            WHERE subject.did_id::VARCHAR || '/' || subject.rkey NOT IN (SELECT list_key FROM nonblock))
        TO '{o}/list_blocks.parquet' (FORMAT parquet, COMPRESSION zstd);
      DELETE FROM subs WHERE u NOT IN (SELECT did_id FROM '{o}/list_blocks.parquet');
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
    steps = a.steps.split(",")
    if "posts" in steps:
      step("posts", f"""
      COPY (SELECT did_id, rkey, created_at, embed_record, {link} AS embed_external_uri
            FROM '{s}/posts.parquet' p
            -- equality joins only, so the posts scan streams (a range join would sort it)
            LEFT JOIN tg ON tg.target = p.did_id
            LEFT JOIN subs ON subs.u = p.did_id
            WHERE p.created_at BETWEEN tg.lo AND tg.hi
               OR (subs.u IS NOT NULL
                   AND (embed_record.did_id IN (SELECT target FROM tg) OR {link} IS NOT NULL)))
        TO '{o}/posts.parquet' (FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE 1000000)""")
    if "reposts" in steps and s.startswith("http"):
        t = time.time()
        filter_http_reposts(f"{s}/reposts.parquet", f"{o}/reposts.parquet",
                            con.execute("SELECT u FROM subs").fetchnumpy()["u"],
                            con.execute("SELECT target FROM tg").fetchnumpy()["target"])
        print(f"reposts: {time.time() - t:.0f}s", flush=True)
    elif "reposts" in steps:
        step("reposts", f"""
      COPY (SELECT did_id, created_at, subject FROM '{s}/reposts.parquet'
            WHERE did_id IN (SELECT u FROM subs) AND subject.did_id IN (SELECT target FROM tg))
        TO '{o}/reposts.parquet' (FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE 1000000)""")
    for f in steps:
        print(f, con.execute(f"SELECT COUNT(*) FROM '{o}/{f}.parquet'").fetchone()[0], "rows")


if __name__ == "__main__":
    main()
