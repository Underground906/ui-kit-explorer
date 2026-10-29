"""Screen explorer: walk a kit's interaction tree and capture every distinct SCREEN, not just pages.
  python explore_screens.py <kit_dir> <root_id> [<root_id> ...]      (roots are ids in <kit_dir>/states.json)
From each root page it clicks every control. A click that yields a new screen (structure changed, or an overlay /
dialog / drawer opened) is saved: screenshot, measured layout (extract_layout.js) and the exact click path that reaches
it. Then that screen is explored too, but only through controls that are new on it (the parent already tried the
rest), up to MAX_DEPTH. A click that lands on another page is recorded as an edge, not explored (that page is its own
root). Toasts and no-ops are recorded as edges. Dedupe is by layout structure, not text, so a pill that swaps the
component set below it is a new screen while a number changing is not.
Writes <kit_dir>/screens/<root>/<n>.png + .json and <kit_dir>/screens.json (screens + edges). Resumable per root."""
import os, asyncio, gzip, hashlib, json, re, sys, pathlib
sys.stdout.reconfigure(encoding="utf-8")
from playwright.async_api import async_playwright

KIT = pathlib.Path(sys.argv[1]).resolve()
ROOTS = sys.argv[2:]
APP = (KIT / "source" / "app.html").as_uri() if (KIT / "source" / "app.html").exists() else ""
EXTRACT = (pathlib.Path(__file__).parent / "extract_layout.js").read_text(encoding="utf-8")
STATES = {s["id"]: s for s in json.loads((KIT / "states.json").read_text(encoding="utf-8"))}
MAX_DEPTH, MAX_SCREENS, MAX_CONTROLS = 4, 80, 60
SKIP_LABEL = ("sign out", "log out", "logout", "delete workspace")
# real accounts (SAFE_MODE=1): never click anything with a consequence: only look, open, switch and navigate
SAFE_RE = __import__("re").compile(r"(?i)(send|post|publish|reply|comment|message|follow|unfollow|subscribe|unsubscribe|join|leave|apply|hire|"
    r"invite|accept|decline|reject|approve|pay|buy|purchase|checkout|upgrade|downgrade|cancel|delete|remove|archive|report|block|mute|"
    r"save|submit|confirm|create|add|upload|connect|disconnect|like|share|tip|pledge|claim|withdraw|transfer|book|request|start|end|"
    r"sign ?out|log ?out|deactivate|close account)")
SAFE = os.environ.get("SAFE_MODE") == "1"

# content box (right of the sidebar, below the top bar), controls with stable keys, structure signature, overlays
PROBE = r"""() => {
  const W = innerWidth, H = innerHeight
  const vis = (e) => { const r = e.getBoundingClientRect(); if (r.width < 2 || r.height < 2 || r.right <= 0 || r.left >= W || r.bottom <= 0) return false
    const s = getComputedStyle(e); return s.display !== 'none' && s.visibility !== 'hidden' && +s.opacity > 0.05 }
  let x0 = 0, y0 = 0
  document.querySelectorAll('[data-r=sidebar], [data-r=rail], aside, nav, [class*=sidebar], [class*=Sidebar]').forEach(e => { if (!vis(e)) return; const r = e.getBoundingClientRect()
    if (r.height > H * 0.6 && r.width < 420 && r.left < 120) x0 = Math.max(x0, r.right) })
  if (!x0) document.querySelectorAll('body *').forEach(e => { if (!vis(e)) return; const r = e.getBoundingClientRect()   // any full-height left column
    if (r.left < 30 && r.top < 30 && r.height > H * 0.8 && r.width >= 150 && r.width <= 420) x0 = Math.max(x0, r.right) })
  document.querySelectorAll('[data-r=topbar], header').forEach(e => { if (!vis(e)) return; const r = e.getBoundingClientRect(); if (r.width > W * 0.4 && r.height < 110 && r.top < 60) y0 = Math.max(y0, r.bottom) })
  const overlays = [...document.querySelectorAll('body *')].filter(e => { if (!vis(e)) return false; const s = getComputedStyle(e); const r = e.getBoundingClientRect()
      return (s.position === 'absolute' || s.position === 'fixed') && +s.zIndex >= 10 && r.width >= 120 && r.height >= 40 && (e.innerText || '').trim() })
    .filter((e, _, a) => !a.some(o => o !== e && o.contains(e)))
  const ovKind = (e) => { const r = e.getBoundingClientRect(); return r.width > W * 0.85 && r.height > H * 0.85 ? (getComputedStyle(e).backgroundColor.includes('0.') ? 'modal' : 'page-overlay')
    : r.height > H * 0.7 && (r.left < 10 || r.right > W - 10) ? 'drawer' : r.width > W * 0.3 && r.height > H * 0.3 ? 'dialog' : r.height < 64 ? 'toast' : 'menu' }
  const inOverlay = (e) => overlays.some(o => o.contains(e))
  const seen = {}, controls = []
  document.querySelectorAll('body *').forEach(e => {
    if (!vis(e)) return; const s = getComputedStyle(e)
    const clickable = s.cursor === 'pointer' || /^(BUTTON|A|SELECT|SUMMARY)$/.test(e.tagName) || e.getAttribute('role') === 'button' || e.getAttribute('role') === 'tab'
    if (!clickable || /^(INPUT|TEXTAREA)$/.test(e.tagName)) return
    if (e.tagName === 'A' && e.href && !e.href.startsWith('javascript') && !e.href.startsWith('#') && new URL(e.href, location.href).origin !== location.origin) return   // never leave the demo
    const p = e.parentElement; if (p && p.tagName !== 'BODY' && getComputedStyle(p).cursor === 'pointer') return
    const r = e.getBoundingClientRect(); const shell = !inOverlay(e) && (r.left + r.width / 2 < x0 || r.top + r.height / 2 < y0)
    const label = ((e.innerText || '').replace(/\s+/g, ' ').trim() || e.getAttribute('aria-label') || e.getAttribute('title') || (e.querySelector('i,svg,[class*=icon]')?.getAttribute('class') || 'icon')).slice(0, 50)
    const k = e.tagName + '|' + label; seen[k] = (seen[k] || 0) + 1
    controls.push({ key: k + '|' + seen[k], label, tag: e.tagName.toLowerCase(), shell, overlay: inOverlay(e), x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height), bg: [s.backgroundColor, p ? getComputedStyle(p).backgroundColor : '', e.firstElementChild ? getComputedStyle(e.firstElementChild).backgroundColor : '', s.color, s.fontWeight].join(' ') })
  })
  // structure: tag + children count + display of every visible element of real size, text ignored
  const parts = []
  document.querySelectorAll('body *').forEach(e => { if (!vis(e)) return; const r = e.getBoundingClientRect(); if (r.width * r.height < 900) return
    const t = e.tagName + getComputedStyle(e).display[0] + (r.left + r.width / 2 < x0 ? 'S' : ''); if (parts[parts.length - 1] !== t) parts.push(t) })
  // active section = the sidebar item whose background differs from all the others
  const navBg = controls.filter(c => c.shell && c.x < x0).map(c => c.bg)
  const mode = navBg.sort((a, b) => navBg.filter(v => v === b).length - navBg.filter(v => v === a).length)[0]
  const act = { label: controls.filter(c => c.shell && c.x < x0 && c.bg !== mode).map(c => c.label.replace(/\d+/g, '').trim()).sort().join(' + ') || null }   // counts in nav badges change; ignore them
  const h1 = [...document.querySelectorAll('[data-r=h1], h1, h2')].find(vis)
  // what the screen is about: headings, table heads, field labels and bold titles, digits removed (rows of data excluded)
  const fp = new Set()
  document.querySelectorAll('h1,h2,h3,h4,h5,h6,th,label,legend,[data-r=h1],*').forEach(e => {
    if (!vis(e) || e.children.length > 1) return; const t = (e.innerText || '').replace(/\s+/g, ' ').trim(); if (!t || t.length > 60) return
    const s = getComputedStyle(e), heading = /^(H\d|TH|LABEL|LEGEND)$/.test(e.tagName) || (+s.fontWeight >= 600 && parseFloat(s.fontSize) >= 14)
    if (!heading || e.closest('tr td, li li')) return
    const r = e.getBoundingClientRect(); if (r.left + r.width / 2 < x0 || r.top < y0) return
    fp.add(t.replace(/[\d.,:%$£€+\-]+/g, '#')) })
  return { fingerprint: [...fp].sort().join('|').slice(0, 4000), x0, y0, controls, active: act ? act.label : null, structure: parts.join(','), h1: h1 ? h1.innerText.trim().slice(0, 80) : '',
    overlays: overlays.map(o => ({ kind: ovKind(o), lines: o.innerText.split('\n').map(t => t.trim()).filter(Boolean).slice(0, 10) })) }
}"""
CLICK = r"""(key) => { const [tag, label, nth] = key.split('|'); let n = 0
  const vis = (e) => { const r = e.getBoundingClientRect(); return r.width >= 2 && r.height >= 2 && r.right > 0 && r.left < innerWidth && getComputedStyle(e).display !== 'none' && getComputedStyle(e).visibility !== 'hidden' }
  for (const e of document.querySelectorAll('body *')) {
    if (e.tagName !== tag || !vis(e)) continue
    const l = ((e.innerText || '').replace(/\s+/g, ' ').trim() || e.getAttribute('aria-label') || e.getAttribute('title') || (e.querySelector('i,svg,[class*=icon]')?.getAttribute('class') || 'icon')).slice(0, 50)
    if (l !== label) continue
    const s = getComputedStyle(e); const p = e.parentElement
    if (!(s.cursor === 'pointer' || /^(BUTTON|A|SELECT|SUMMARY)$/.test(e.tagName) || e.getAttribute('role'))) continue
    if (p && p.tagName !== 'BODY' && getComputedStyle(p).cursor === 'pointer') continue
    if (++n === +nth) { e.scrollIntoView({ block: 'center' }); e.click(); return true } }
  return false }"""

async def save_html(path):
    """rendered DOM of this screen; scripts dropped, the app's styles kept once in source/app_styles.css, inline base64 dropped"""
    h = await pg_ref[0].content()
    h = re.sub(r"<script\b.*?</script>", "", h, flags=re.S)
    css = KIT / "source" / "app_styles.css"      # the app's styles are identical on every screen: keep them once
    if not css.exists():
        css.parent.mkdir(parents=True, exist_ok=True)
        css.write_text("\n".join(re.findall(r"<style\b[^>]*>(.*?)</style>", h, flags=re.S)), encoding="utf-8")
    h = re.sub(r"<style\b[^>]*>.*?</style>", "", h, flags=re.S).replace("</head>", '<link rel="stylesheet" href="../../source/app_styles.css"></head>', 1)
    h = re.sub(r"data:[\w/+.-]+;base64,[A-Za-z0-9+/=]{200,}", "data:,", h)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write(h)


pg_ref = []


async def shoot(path):
    """screenshot that survives a throttled or busy tab: bring it forward, retry once, then log and carry on"""
    pg = pg_ref[0]
    for attempt in (1, 2):
        try:
            await pg.screenshot(path=str(path), animations="disabled", timeout=45000)
            return True
        except Exception as ex:
            try:
                await pg.bring_to_front()
            except Exception:
                pass
            if attempt == 2:
                print("   no screenshot:", path, str(ex)[:60], flush=True)
    return False
sig = lambda p: hashlib.md5((p["structure"] + "|" + p.get("fingerprint", "") + "|" + "|".join(o["kind"] for o in p["overlays"] if o["kind"] != "toast")).encode()).hexdigest()[:12]


async def main():
    out_p = KIT / "screens.json"
    db = json.loads(out_p.read_text(encoding="utf-8")) if out_p.exists() else {"screens": [], "edges": [], "roots_done": []}
    titles = {}
    for sid in STATES:
        p = KIT / "states" / f"{sid}.json"
        if p.exists() and "__" not in sid:
            titles[json.loads(p.read_text(encoding="utf-8"))["title"]] = sid
    async with async_playwright() as pw:
        if os.environ.get("CDP_URL"):   # drive a browser the user is already logged into (their sessions, their home connection)
            cdp = os.environ["CDP_URL"]
            if cdp.startswith("http"):   # Chrome 156 hangs on the http handshake: use the browser's websocket directly
                import urllib.request
                cdp = json.loads(urllib.request.urlopen(cdp.rstrip("/") + "/json/version").read())["webSocketDebuggerUrl"]
            b = await pw.chromium.connect_over_cdp(cdp, timeout=60000)
            pg = await b.contexts[0].new_page()
            await pg.set_viewport_size({"width": 1440, "height": 900})
            await pg.bring_to_front()   # Chrome stops drawing background tabs: screenshots would never complete
        else:
            b = await pw.chromium.launch(channel=os.environ.get("PW_CHANNEL", "msedge") or None)
            pg = await b.new_page(viewport={"width": 1440, "height": 900})
        pg_ref.append(pg)

        async def goto(root, path):
            st = STATES[root]
            await pg.set_viewport_size({"width": 1440, "height": 900})
            await pg.goto(st.get("url") or APP + "?" + st["q"], wait_until="load", timeout=120000)
            if not path and not os.environ.get("CDP_URL"):   # each page starts clean (not in a logged-in browser: that would sign it out): a theme toggle or saved filter from another page must not leak in
                await pg.evaluate("() => { try { localStorage.clear(); sessionStorage.clear() } catch (e) {} }")
                await pg.reload(wait_until="load", timeout=120000)
                for label in st.get("pre", []):   # login / setup steps: "fill:<placeholder>=<value>" or a label to click
                    try:
                        if label.startswith("press:"):   # e.g. press:Enter when a submit button is animated / unclickable
                            await pg.keyboard.press(label[6:])
                            await pg.wait_for_timeout(1500)
                            continue
                        if label.startswith("fill:"):
                            ph, val = label[5:].split("=", 1)
                            await pg.get_by_placeholder(ph).first.fill(val, timeout=10000)
                            continue
                        for how in (lambda: pg.get_by_text(label, exact=True).first, lambda: pg.get_by_role("button", name=label).first,
                                    lambda: pg.get_by_text(label).first):
                            try:
                                await how().click(timeout=8000)
                                break
                            except Exception:
                                continue
                        else:
                            print("   pre step not found:", label, flush=True)
                    except Exception as ex:
                        print("   pre step failed:", label, str(ex)[:80], flush=True)
                    await pg.wait_for_timeout(1500)
                if st.get("pre") and st.get("after_url"):
                    await pg.goto(st["after_url"], wait_until="load", timeout=120000)
            await pg.wait_for_timeout(900)
            for k in path:
                if not await pg.evaluate(CLICK, k):
                    return None
                await pg.wait_for_timeout(450)
            return await pg.evaluate(PROBE)

        for n_root, root in enumerate(ROOTS):
            if root in db["roots_done"]:
                continue
            d = KIT / "screens" / root
            d.mkdir(parents=True, exist_ok=True)
            screens = [s for s in db["screens"] if s["root"] == root]
            known = {s["sig"]: s["id"] for s in db["screens"]}
            base = await goto(root, [])
            root_title = base["h1"]
            # page templates: pages whose layout structure (text ignored) matches a page already seen are instances of one
            # template (freelancer profiles, blog posts, job posts...). Explore 2 examples; record the rest with one shot only.
            tsig = hashlib.md5(base["structure"].encode()).hexdigest()[:12]
            tdb = db.setdefault("templates", {})
            if len(tdb.get(tsig, [])) >= int(os.environ.get("TEMPLATE_EXAMPLES", "2")) and root not in tdb[tsig]:
                await shoot(d / "0.png")
                db["screens"].append({"id": f"{root}/0", "root": root, "depth": 0, "path": [], "parent": None, "via": None, "kind": "page",
                                      "h1": base["h1"], "overlays": [], "sig": sig(base), "shot": f"screens/{root}/0.png",
                                      "template_of": tdb[tsig][0], "template_sig": tsig})
                tdb[tsig].append(root)
                db["roots_done"].append(root)
                out_p.write_text(json.dumps(db, ensure_ascii=False, indent=1), encoding="utf-8")
                print("TEMPLATE", root, "= instance of", tdb[tsig][0], f"({len(tdb[tsig])} pages share this layout)", flush=True)
                continue
            if root not in tdb.setdefault(tsig, []):
                tdb[tsig].append(root)
            queue = [{"id": f"{root}/0", "path": [], "depth": 0, "parent": None, "probe": base}]
            if not screens:
                await shoot(d / "0.png")
                (d / "0.json").write_text(json.dumps(await pg.evaluate(EXTRACT), ensure_ascii=False), encoding="utf-8")
                await save_html(d / "0.html.gz")
                screens.append({"id": f"{root}/0", "root": root, "depth": 0, "path": [], "parent": None, "via": None, "kind": "page", "h1": base["h1"],
                                "overlays": base["overlays"], "sig": sig(base), "shot": f"screens/{root}/0.png"})
                db["screens"].append(screens[-1])
                known[sig(base)] = f"{root}/0"
            while queue:
                cur = queue.pop(0)
                parent_keys = set()
                if cur["parent"]:
                    pp = next(s for s in db["screens"] if s["id"] == cur["parent"])
                    parent_keys = set(pp.get("controls", []))
                probe = cur["probe"]
                me = next(s for s in db["screens"] if s["id"] == cur["id"])
                me["controls"] = [c["key"] for c in probe["controls"]]
                todo = [c for c in probe["controls"] if c["key"] not in parent_keys and not any(w in c["label"].lower() for w in SKIP_LABEL)
                        and not (SAFE and SAFE_RE.search(c["label"]))
                        and (not c["shell"] or (n_root == 0 and cur["depth"] == 0))][:MAX_CONTROLS]
                # list rows: 5+ controls with the same tag, x, width and height are instances of one row; try the first 3 (short lists: all)
                groups = {}
                for c in todo:
                    groups.setdefault((c["tag"], c["x"], c["w"], c["h"]), []).append(c)
                todo = [c for c in todo if len(groups[(c["tag"], c["x"], c["w"], c["h"])]) <= 4 or groups[(c["tag"], c["x"], c["w"], c["h"])].index(c) < 3]
                dirty = True   # the page is wherever the last screen left it: always restore this screen first
                for c in todo:
                    if len(screens) >= int(STATES[root].get("max_screens", MAX_SCREENS)):   # hubs can carry 200+
                        break
                    edge = {"from": cur["id"], "control": c["label"], "key": c["key"], "shell": c["shell"]}
                    try:
                        if dirty:
                            probe_now = await goto(root, cur["path"])
                            if probe_now is None:
                                break
                        ok = await pg.evaluate(CLICK, c["key"])
                        await pg.wait_for_timeout(550)
                        after = await pg.evaluate(PROBE) if ok else None
                    except Exception as ex:   # a click that navigates the browser mid-measurement (real URL sites)
                        try:
                            await pg.wait_for_load_state("load", timeout=30000)
                        except Exception:
                            pass
                        edge.update(outcome="navigate", to_url=pg.url, note=str(ex)[:80]); dirty = True
                        db["edges"].append(edge)
                        continue
                    if not after:
                        edge["outcome"] = "missing"; dirty = False
                    else:
                        s2 = sig(after)
                        toast = [o for o in after["overlays"] if o["kind"] == "toast" and o not in probe["overlays"]]
                        if STATES[root].get("url") and pg.url.split("?")[0].split("#")[0].rstrip("/") != STATES[root]["url"].rstrip("/") and not any(o["kind"] != "toast" for o in after["overlays"]) and (c["shell"] or after["h1"] != probe["h1"]):
                            edge.update(outcome="navigate", to_url=pg.url); dirty = True
                        elif after["h1"] != root_title and after["h1"] in titles and titles[after["h1"]] != root and not any(o["kind"] != "toast" for o in after["overlays"]):
                            edge.update(outcome="navigate", to_page=titles[after["h1"]]); dirty = True
                        elif c["shell"] and not c["overlay"] and after["h1"] != probe["h1"] and not any(o["kind"] != "toast" for o in after["overlays"]):
                            edge.update(outcome="navigate", to_title=after["h1"]); dirty = True
                        elif s2 == sig(probe):
                            edge.update(outcome="toast" if toast else "no-change", shows=toast[0]["lines"] if toast else None); dirty = bool(toast)
                        elif s2 in known:
                            edge.update(outcome="screen", to=known[s2]); dirty = True
                        else:
                            n = len(screens)
                            sid = f"{root}/{n}"
                            new_ov = [o for o in after["overlays"] if o not in probe["overlays"] and o["kind"] != "toast"]
                            kind = new_ov[0]["kind"] if new_ov else ("page-switch" if after["h1"] != probe["h1"] else "inline")
                            await shoot(d / f"{n}.png")
                            (d / f"{n}.json").write_text(json.dumps(await pg.evaluate(EXTRACT), ensure_ascii=False), encoding="utf-8")
                            await save_html(d / f"{n}.html.gz")
                            rec = {"id": sid, "root": root, "depth": cur["depth"] + 1, "path": cur["path"] + [c["key"]], "parent": cur["id"], "via": c["label"],
                                   "kind": kind, "h1": after["h1"], "overlays": after["overlays"], "sig": s2, "shot": f"screens/{root}/{n}.png"}
                            screens.append(rec); db["screens"].append(rec); known[s2] = sid
                            edge.update(outcome="screen", to=sid, new=True)
                            print(f"{sid:28} {kind:12} via {c['label'][:40]!r} depth {rec['depth']}", flush=True)
                            # another section only if the nav highlight AND the page title both changed (status rows in a nav restyle themselves)
                            if after["active"] and base["active"] and after["active"] != base["active"] and after["h1"] and after["h1"] != probe["h1"]:
                                rec["kind"] = "cross-page"; rec["section"] = after["active"]   # another section: its own root explores it
                            elif rec["depth"] < MAX_DEPTH:
                                queue.append({"id": sid, "path": rec["path"], "depth": rec["depth"], "parent": cur["id"], "probe": after})
                            dirty = True
                    db["edges"].append(edge)
                out_p.write_text(json.dumps(db, ensure_ascii=False, indent=1), encoding="utf-8")
            db["roots_done"].append(root)
            out_p.write_text(json.dumps(db, ensure_ascii=False, indent=1), encoding="utf-8")
            print("ROOT DONE", root, len(screens), "screens", flush=True)
        if os.environ.get("CDP_URL"):
            await pg.close()   # leave the user's browser running
        else:
            await b.close()

asyncio.run(main())
