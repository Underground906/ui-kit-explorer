"""Find every page of a site, so no capture misses one.
Reads sitemap.xml, then crawls the site in a real browser (so links drawn by JavaScript count too), following
every same-site link breadth first. Repeated page types (/listings/<x>, /blog/<x>) keep 2 examples each.
Writes kits/<kit>/pages_found.json and adds any page not already in states.json (unless DRY=1).
Usage: python tools/discover_pages.py kits/<kit>  [MAX_PAGES env, default 400]"""
import json, os, re, sys, urllib.request
from collections import defaultdict
from pathlib import Path
from urllib.parse import urljoin, urlparse
from playwright.sync_api import sync_playwright

K = Path(sys.argv[1])
STATES = json.loads((K / "states.json").read_text())
START = next(s["url"] for s in STATES if s.get("url"))
HOST = urlparse(START).netloc
MAX = int(os.environ.get("MAX_PAGES", "400"))
SKIP = re.compile(r"\.(css|js|mjs|png|jpe?g|gif|svg|ico|woff2?|ttf|webp|avif|mp4|webm|pdf|zip|xml|json|txt|webmanifest)$|/_next/|/cdn-cgi/|/404|,html", re.I)


def norm(u):
    p = urlparse(u)
    if p.scheme not in ("http", "https") or p.netloc != HOST or SKIP.search(p.path):
        return None
    return p.path.rstrip("/") or "/"


def pattern(path):
    # /listings/14-chestnut-st -> /listings/*  ;  /blog.html stays itself
    parts = path.strip("/").split("/")
    return "/" + "/".join(parts[:-1] + ["*"]) if len(parts) > 1 else path


def sitemap():
    out = set()
    for sm in ("/sitemap.xml", "/sitemap-0.xml", "/sitemap_index.xml"):
        try:
            x = urllib.request.urlopen(urllib.request.Request(f"https://{HOST}{sm}", headers={"User-Agent": "Mozilla/5.0"}), timeout=20).read().decode("utf-8", "ignore")
        except Exception:
            continue
        out |= {n for n in (norm(u) for u in re.findall(r"<loc>\s*([^<\s]+)", x)) if n}
    return out


def main():
    seen, queue, per = set(), [], defaultdict(int)
    order = []

    def add(path):
        if path in seen:
            return
        pat = pattern(path)
        if pat != path and per[pat] >= 2:
            return
        seen.add(path); order.append(path); queue.append(path)
        if pat != path:
            per[pat] += 1

    for s in STATES:
        n = norm(s.get("url", "")) if s.get("url") else None
        if n:
            add(n)
    from_sitemap = sitemap()
    for n in sorted(from_sitemap):
        add(n)
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": 1440, "height": 900})
        visited = 0
        while queue and visited < MAX:
            path = queue.pop(0)
            visited += 1
            try:
                pg.goto(f"https://{HOST}{path}", wait_until="load", timeout=30000)
                pg.wait_for_timeout(1200)
                hrefs = pg.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
            except Exception as e:
                print("FAIL", path, str(e)[:80]); continue
            for h in hrefs:
                n = norm(urljoin(f"https://{HOST}{path}", h))
                if n:
                    add(n)
        b.close()
    have = {norm(s["url"]) for s in STATES if s.get("url")}
    new = [p for p in order if p not in have]
    (K / "pages_found.json").write_text(json.dumps({"host": HOST, "pages": order, "new": new, "from_sitemap": len(from_sitemap), "visited": visited}, indent=1))
    print(f"PAGES {K.name}: {len(order)} found, {len(new)} new, sitemap {len(from_sitemap)}, visited {visited}")
    if os.environ.get("DRY") != "1" and new:
        ids = {s["id"] for s in STATES}
        for p in new:
            pid = re.sub(r"[^a-z0-9]+", "-", p.lower().replace(".html", "")).strip("-")[:40] or "index"
            while pid in ids:
                pid += "-x"
            ids.add(pid)
            STATES.append({"id": pid, "q": "", "url": f"https://{HOST}{p}", "full": True})
        (K / "states.json").write_text(json.dumps(STATES, indent=1))


main()
