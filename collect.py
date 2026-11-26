"""Hangle Academy — public-domain / CC0 photo collector.
Sources: Wikimedia Commons (only Public domain / CC0 files), NASA Image Library (US government, public domain).
Each image: resized to max 640px, saved as WebP, with a credit record in meta.json."""
import json, os, re, sys, time, io, hashlib, urllib.parse, requests
from PIL import Image
UA = {"User-Agent": "HangleAcademyPhotoCollector/1.0 (educational; contact via GitHub repo)"}
OUT = "images"; META = "meta.json"; PER = int(os.environ.get("PER", "4"))
OK_LIC = re.compile(r"^(public domain|pd|cc0|cc-zero|cc0 1\.0)", re.I)
def slug(s): return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
def save(img_bytes, path):
    im = Image.open(io.BytesIO(img_bytes)).convert("RGB"); im.thumbnail((640, 640)); im.save(path, "WEBP", quality=72)
def commons(q, n):
    p = {"action": "query", "format": "json", "generator": "search", "gsrsearch": q + " filetype:bitmap", "gsrnamespace": 6, "gsrlimit": 40,
         "prop": "imageinfo", "iiprop": "url|extmetadata|mime", "iiurlwidth": 640}
    r = requests.get("https://commons.wikimedia.org/w/api.php", params=p, headers=UA, timeout=30).json()
    pages = sorted((r.get("query") or {}).get("pages", {}).values(), key=lambda x: x.get("index", 99)); out = []
    for pg in pages:
        ii = (pg.get("imageinfo") or [{}])[0]; md = ii.get("extmetadata", {})
        lic = (md.get("LicenseShortName", {}) or {}).get("value", "")
        if not OK_LIC.match(lic.strip()) or ii.get("mime") not in ("image/jpeg", "image/png"): continue
        title = pg.get("title", "")
        if re.search(r"(map|diagram|logo|flag|chart|drawing|illustration|coat of arms|stamp|poster)", title, re.I): continue
        out.append({"url": ii.get("thumburl") or ii.get("url"), "page": ii.get("descriptionurl"), "title": title.replace("File:", ""),
                    "creator": re.sub("<[^>]+>", "", (md.get("Artist", {}) or {}).get("value", ""))[:120], "license": lic, "source": "Wikimedia Commons"})
        if len(out) >= n: break
    return out
def nasa(q, n):
    r = requests.get("https://images-api.nasa.gov/search", params={"q": q, "media_type": "image"}, headers=UA, timeout=30).json(); out = []
    for it in r.get("collection", {}).get("items", [])[:n * 3]:
        d = (it.get("data") or [{}])[0]; links = it.get("links") or []
        if not links: continue
        out.append({"url": links[0]["href"], "page": "https://images.nasa.gov/details/" + d.get("nasa_id", ""), "title": d.get("title", ""),
                    "creator": d.get("center", "NASA"), "license": "Public domain (NASA)", "source": "NASA Image and Video Library"})
        if len(out) >= n: break
    return out
def main():
    meta = json.load(open(META)) if os.path.exists(META) else {}
    kw = [l.strip() for l in open("keywords.txt") if l.strip() and not l.startswith("#")]
    t0 = time.time(); done = 0
    for line in kw:
        cat, q = line.split("|", 1) if "|" in line else ("misc", line)
        key = slug(q)
        if key in meta and len(meta[key]["items"]) >= PER: continue
        if time.time() - t0 > float(os.environ.get("MAXSEC", "17000")): break
        try: cands = (nasa(q, PER) if cat == "space" else []) or commons(q, PER)
        except Exception as e: print("search fail", q, e); continue
        items = []; os.makedirs(os.path.join(OUT, key), exist_ok=True)
        for i, c in enumerate(cands):
            try:
                b = requests.get(c["url"], headers=UA, timeout=60).content; fn = f"{key}/{i}.webp"; save(b, os.path.join(OUT, fn)); c["file"] = fn; items.append(c)
            except Exception as e: print("dl fail", c.get("url"), e)
            time.sleep(0.3)
        meta[key] = {"q": q, "cat": cat, "items": items}; done += 1
        print(f"{key}: {len(items)}", flush=True)
        if done % 20 == 0: json.dump(meta, open(META, "w"), ensure_ascii=False, indent=1)
        time.sleep(0.5)
    json.dump(meta, open(META, "w"), ensure_ascii=False, indent=1); print("total keys", len(meta))
if __name__ == "__main__": main()
