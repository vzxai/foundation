"""Prospective Bluesky collector (Jetstream) for the moderation-list experiment.

Records every create AND delete for the collections the design needs, with the
relay-observed time (time_us), so the later dataset does not inherit the
snapshot's survivorship problem (deleted list items / unsubscribed list blocks
are invisible in a snapshot).

Writes hourly gzip JSONL files plus a cursor file, and resumes from the cursor
after a disconnect (Jetstream replays a limited backlog).

Needs: pip install websockets
Usage: python -I jetstream_collect.py OUT_DIR [--host jetstream2.us-east.bsky.network]
"""
import argparse
import asyncio
import gzip
import json
import os
import time

import websockets

COLLECTIONS = [
    "app.bsky.feed.post", "app.bsky.feed.repost", "app.bsky.graph.block",
    "app.bsky.graph.listblock", "app.bsky.graph.listitem", "app.bsky.graph.list",
    "app.bsky.graph.follow",
]


class Sink:
    def __init__(self, out):
        self.out, self.hour, self.f = out, None, None
        os.makedirs(out, exist_ok=True)

    def write(self, line, t_us):
        hour = time.strftime("%Y%m%dT%H", time.gmtime(t_us / 1e6))
        if hour != self.hour:
            if self.f:
                self.f.close()
            self.f = gzip.open(os.path.join(self.out, f"js-{hour}.jsonl.gz"), "at")
            self.hour = hour
        self.f.write(line + "\n")


async def run(a):
    sink = Sink(a.out_dir)
    cur_path = os.path.join(a.out_dir, "cursor")
    q = "&".join(f"wantedCollections={c}" for c in COLLECTIONS)
    backoff = 1
    while True:
        cursor = open(cur_path).read().strip() if os.path.exists(cur_path) else None
        url = f"wss://{a.host}/subscribe?{q}" + (f"&cursor={int(cursor) - 5_000_000}" if cursor else "")
        try:
            async with websockets.connect(url, max_size=2**22, ping_interval=30) as ws:
                backoff, n = 1, 0
                async for msg in ws:
                    ev = json.loads(msg)
                    if ev.get("kind") != "commit":
                        continue
                    sink.write(msg if isinstance(msg, str) else msg.decode(), ev["time_us"])
                    n += 1
                    if n % 5000 == 0:
                        with open(cur_path + ".tmp", "w") as f:
                            f.write(str(ev["time_us"]))
                        os.replace(cur_path + ".tmp", cur_path)
        except (OSError, websockets.WebSocketException) as e:
            print(f"disconnected: {e!r}; retrying in {backoff}s", flush=True)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 120)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir")
    ap.add_argument("--host", default="jetstream2.us-east.bsky.network")
    asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    main()
