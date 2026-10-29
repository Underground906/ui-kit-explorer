"""Turn a kit's sidebar into page roots, for apps whose pages have no URL (single-file bundles without screen props).
  python nav_roots.py <kit_dir> [query] [prefix] [login clicks, '|'-separated]
Loads source/app.html?<query>, reads the sidebar controls (left of the content, as explore_screens.py measures them)
and appends one root per nav item to states.json: {"id": <prefix><slug>, "q": <query>, "pre": [<nav label>]}.
The explorer then opens the app, clicks that nav item and explores the page from there."""
import asyncio, json, os, re, sys, pathlib
from playwright.async_api import async_playwright

KIT = pathlib.Path(sys.argv[1]).resolve()
Q = sys.argv[2] if len(sys.argv) > 2 else ""
PFX = sys.argv[3] if len(sys.argv) > 3 else ""
LOGIN = [x for x in (sys.argv[4] if len(sys.argv) > 4 else "").split("|") if x]   # clicks needed first, e.g. "Sign in"
PROBE = (pathlib.Path(__file__).parent / "explore_screens.py").read_text(encoding="utf-8").split('PROBE = r"""')[1].split('"""')[0]
SKIP = re.compile(r"(?i)sign ?out|log ?out|collapse|upgrade|^icon$|^lucide|^hgi|^\d+$")


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(channel=os.environ.get("PW_CHANNEL", "msedge") or None)
        pg = await b.new_page(viewport={"width": 1440, "height": 900})
        await pg.goto((KIT / "source" / "app.html").as_uri() + ("?" + Q if Q else ""), wait_until="load", timeout=180000)
        await pg.wait_for_timeout(2500)
        for lab in LOGIN:
            await pg.get_by_role("button", name=lab).first.click(timeout=15000)
            await pg.wait_for_timeout(2000)
        r = await pg.evaluate(PROBE)
        await b.close()
    nav = []
    for c in r["controls"]:
        lab = re.sub(r"\s+\d+$", "", c["label"]).strip()   # drop badge counts ("Approvals 12")
        if c["shell"] and c["x"] < r["x0"] and lab and len(lab) < 40 and not SKIP.search(lab) and lab not in nav:
            nav.append(lab)
    sp = KIT / "states.json"
    states = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else []
    have = {s["id"] for s in states}
    for lab in nav:
        sid = PFX + (re.sub(r"[^a-z0-9]+", "-", lab.lower()).strip("-") or "page")
        if sid not in have:
            states.append({"id": sid, "q": Q, "pre": LOGIN + [lab], "full": True})
            have.add(sid)
    sp.write_text(json.dumps(states, indent=0), encoding="utf-8")
    print(len(nav), "nav roots:", nav)

asyncio.run(main())
