"""Search public archives for candidate footage. Prints identifier, title, license."""
import json, sys, urllib.parse, urllib.request

UA = {"User-Agent": "winds-out-of-noise/0.1 (art film footage research; https://github.com/vzxai/foundation)"}

def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
        return json.load(r)

def archive(q, rows=8):
    url = "https://archive.org/advancedsearch.php?" + urllib.parse.urlencode(
        {"q": q, "fl[]": ["identifier", "title", "licenseurl", "year"], "rows": rows, "output": "json"}, doseq=True)
    for d in get(url)["response"]["docs"]:
        print("IA", d["identifier"], "|", d.get("title"), "|", d.get("year"), "|", d.get("licenseurl"))

def nasa(q, rows=8):
    url = "https://images-api.nasa.gov/search?" + urllib.parse.urlencode({"q": q, "media_type": "video"})
    for it in get(url)["collection"]["items"][:rows]:
        d = it["data"][0]
        print("NASA", d["nasa_id"], "|", d["title"][:80])

def commons(q, rows=8):
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(
        {"action": "query", "list": "search", "srsearch": q + " filetype:video", "srnamespace": 6, "format": "json", "srlimit": rows})
    for d in get(url)["query"]["search"]:
        print("WC", d["title"])

if __name__ == "__main__":
    src, q = sys.argv[1], sys.argv[2]
    {"ia": archive, "nasa": nasa, "wc": commons}[src](q)
