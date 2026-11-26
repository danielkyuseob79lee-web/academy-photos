"""Hangle Academy — public-domain / CC0 photo collector (v4).
Photos only. Sources, in order: Openverse (category=photograph, CC0 / Public Domain Mark),
NASA Image Library (space only, US government public domain), Wikimedia Commons (PD/CC0, strict photo filter).
Each image: resized to max 640px, saved as WebP, with a credit record in meta.json."""
import json, os, re, time, io, shutil, requests
from PIL import Image
UA = {"User-Agent": "HangleAcademyPhotoBot/1.4 (https://github.com/danielkyuseob79lee-web/academy-photos; educational, public-domain only) python-requests"}
OUT = "images"; META = "meta.json"; PER = int(os.environ.get("PER", "6")); VER = 4
OK_LIC = re.compile(r"^(public domain|pd|cc0|cc-zero|cc0 1\.0)", re.I)
BAD = re.compile(r"(map|diagram|logo|flag|chart|drawing|illustration|coat of arms|stamp|poster|svg|engraving|lithograph|etching|woodcut|painting|sketch|print|plate \d|scan|page|book|newspaper|magazine|advert|cartoon|clipart|icon|museum|specimen label|label|text|manuscript|letter|postcard|card|portrait|president|minister|senator|obama|trump|biden|king|queen|prince|meeting|conference|ceremony|signing)", re.I)
BADCAT = re.compile(r"(paintings|drawings|engravings|illustrations|prints|maps|scans|lithographs|manuscripts|portraits|politicians|presidents|people of|men of|women of|book|newspapers|art)", re.I)
def slug(s): return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
def save(img_bytes, path):
    im = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    if min(im.size) < 180: raise ValueError("too small")
    im.thumbnail((640, 640)); im.save(path, "WEBP", quality=74)
def getj(url, params, tries=2):
    for k in range(tries):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=30)
            if r.status_code == 200: return r.json()
            print("  http", r.status_code, url.split("/")[2], r.text[:80].replace("\n", " "), flush=True)
            if r.status_code == 429: time.sleep(30)
        except Exception as e: print("  err", e)
        time.sleep(3)
    return {}
def toks(q): return [t for t in re.findall(r"[a-z]+", q.lower()) if t not in ("the", "of", "a", "on", "in", "with", "and", "united", "states", "coin")]
def relevant(title, q):
    t = title.lower(); ts = toks(q)
    return any(x[:5] in t for x in ts) if ts else True
OV_OFF = [False]
def openverse(q, n):
    if OV_OFF[0]: return []
    r = getj("https://api.openverse.org/v1/images/", {"q": q, "license": "cc0,pdm", "category": "photograph", "page_size": 30, "mature": "false"})
    if not r: OV_OFF[0] = True; print("openverse off for this run", flush=True); return []
    out = []
    for it in r.get("results", []):
        t = it.get("title") or ""
        if BAD.search(t) or not relevant(t + " " + " ".join(x.get("name", "") for x in (it.get("tags") or [])), q): continue
        out.append({"url": "https://api.openverse.org/v1/images/%s/thumb/" % it["id"], "page": it.get("foreign_landing_url"), "title": t[:120], "creator": (it.get("creator") or "")[:120],
                    "license": ("CC0" if it.get("license") == "cc0" else "Public Domain Mark"), "source": "Openverse / " + (it.get("source") or "")})
        if len(out) >= n: break
    return out
def commons(q, n):
    out = []; cont = {}
    for page in range(4):
        p = {"action": "query", "format": "json", "generator": "search", "gsrsearch": q + " filetype:bitmap", "gsrnamespace": 6, "gsrlimit": 50,
             "prop": "imageinfo", "iiprop": "url|extmetadata|mime", "iiurlwidth": 640}
        p.update(cont)
        r = getj("https://commons.wikimedia.org/w/api.php", p)
        pages = sorted((r.get("query") or {}).get("pages", {}).values(), key=lambda x: x.get("index", 999))
        for pg in pages:
            ii = (pg.get("imageinfo") or [{}])[0]; md = ii.get("extmetadata", {})
            lic = (md.get("LicenseShortName", {}) or {}).get("value", "")
            if not OK_LIC.match(lic.strip()) or ii.get("mime") != "image/jpeg": continue
            title = pg.get("title", "").replace("File:", ""); cats = (md.get("Categories", {}) or {}).get("value", "")
            if BAD.search(title) or BADCAT.search(cats) or not relevant(title, q): continue
            dt = (md.get("DateTimeOriginal", {}) or {}).get("value", "")
            m = re.search(r"(1[89]\d\d)", dt)
            if m and int(m.group(1)) < 1950: continue  # old scans are mostly art or documents
            out.append({"url": ii.get("thumburl") or ii.get("url"), "page": ii.get("descriptionurl"), "title": title[:120],
                        "creator": re.sub("<[^>]+>", "", (md.get("Artist", {}) or {}).get("value", ""))[:120], "license": lic, "source": "Wikimedia Commons"})
            if len(out) >= n: return out
        if "continue" not in r: break
        cont = dict(r["continue"])
    return out
def nasa(q, n):
    r = getj("https://images-api.nasa.gov/search", {"q": q, "media_type": "image"}); out = []
    for it in r.get("collection", {}).get("items", [])[:n * 3]:
        d = (it.get("data") or [{}])[0]; links = it.get("links") or []
        if not links or BAD.search(d.get("title", "")): continue
        out.append({"url": links[0]["href"], "page": "https://images.nasa.gov/details/" + d.get("nasa_id", ""), "title": d.get("title", "")[:120],
                    "creator": d.get("center", "NASA"), "license": "Public domain (NASA)", "source": "NASA Image and Video Library"})
        if len(out) >= n: break
    return out
def main():
    meta = json.load(open(META)) if os.path.exists(META) else {}
    kw = [l.strip() for l in open("keywords.txt") if l.strip() and not l.startswith("#")]
    t0 = time.time(); done = 0
    for line in kw:
        cat, q = line.split("|", 1) if "|" in line else ("misc", line)
        key = slug(q); old = meta.get(key, {})
        if old.get("v") == VER and len(old.get("items", [])) >= PER: continue
        if time.time() - t0 > float(os.environ.get("MAXSEC", "17000")): break
        if old.get("v") != VER:
            shutil.rmtree(os.path.join(OUT, key), ignore_errors=True); old = {}
        items = list(old.get("items", [])); have = {x.get("page") for x in items}
        need = PER - len(items)
        cands = (nasa(q, need * 2) if cat == "space" else []) or []
        if len(cands) < need * 2: cands += openverse(q, need * 2)
        if len(cands) < need * 2: cands += commons(q, need * 2)
        os.makedirs(os.path.join(OUT, key), exist_ok=True)
        for c in cands:
            if len(items) >= PER: break
            if c.get("page") in have: continue
            i = 0
            while os.path.exists(os.path.join(OUT, key, f"{i}.webp")): i += 1
            try:
                b = requests.get(c["url"], headers=UA, timeout=60).content; fn = f"{key}/{i}.webp"; save(b, os.path.join(OUT, fn)); c["file"] = fn; items.append(c); have.add(c.get("page"))
            except Exception as e: print("dl fail", str(c.get("url"))[:80], e)
            time.sleep(0.3)
        meta[key] = {"q": q, "cat": cat, "items": items, "v": VER}; done += 1
        print(f"{key}: {len(items)}", flush=True)
        if done % 20 == 0: json.dump(meta, open(META, "w"), ensure_ascii=False, indent=1)
        time.sleep(0.4)
    json.dump(meta, open(META, "w"), ensure_ascii=False, indent=1); print("total keys", len(meta), "items", sum(len(v["items"]) for v in meta.values()))
if __name__ == "__main__": main()
