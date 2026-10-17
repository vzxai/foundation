"""Download source films listed in films.json into a local cache directory.

Usage: python3 fetch.py <cache_dir>
Prefers the HiRes edit when under 350 MB, then the h.264 derivative, then 512kb.
"""
import json, os, subprocess, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
UA = {"User-Agent": "winds-out-of-noise/0.1 (art film; https://github.com/vzxai/foundation)"}

def get_json(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return json.load(r)

def archive_url(ident):
    files = get_json(f"https://archive.org/metadata/{ident}/files")["result"]
    mp4 = [f for f in files if f["name"].endswith(".mp4")]
    def size(f): return int(f.get("size", 0))
    for pick in (
        [f for f in mp4 if f.get("format") == "HiRes MPEG4" and size(f) < 350e6],
        [f for f in mp4 if f.get("format") in ("h.264", "MPEG4")],
        [f for f in mp4 if f.get("format") == "512Kb MPEG4"],
        files and [f for f in files if f["name"].endswith((".ogv", ".webm"))],
    ):
        if pick:
            return f"https://archive.org/download/{ident}/{pick[0]['name']}"
    raise RuntimeError(f"no video file for {ident}")

def nasa_url(nasa_id):
    assets = get_json(f"https://images-api.nasa.gov/asset/{nasa_id}")["collection"]["items"]
    hrefs = [a["href"] for a in assets if a["href"].endswith(".mp4")]
    for tag in ("~medium.mp4", "~large.mp4", "~orig.mp4"):
        for h in hrefs:
            if h.endswith(tag):
                return h.replace("http://", "https://")
    return hrefs[0].replace("http://", "https://")

def fetch(cache, key, resolver):
    out = os.path.join(cache, key + ".mp4")
    if os.path.exists(out) and os.path.getsize(out) > 0:
        return key, "cached"
    url = resolver(key)
    tmp = out + ".part"
    subprocess.run(["curl", "-sSL", "--retry", "4", "-A", UA["User-Agent"], "-o", tmp, url], check=True)
    os.replace(tmp, out)
    return key, url

if __name__ == "__main__":
    cache = sys.argv[1]
    os.makedirs(cache, exist_ok=True)
    films = json.load(open(os.path.join(HERE, "films.json")))
    jobs = [(k, archive_url) for k in films["archive"]] + [(k, nasa_url) for k in films["nasa"]]
    with ThreadPoolExecutor(6) as ex:
        for f in [ex.submit(fetch, cache, k, r) for k, r in jobs]:
            try:
                print(*f.result())
            except Exception as e:
                print("FAILED", e)
