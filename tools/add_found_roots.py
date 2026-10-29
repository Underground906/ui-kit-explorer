"""Add pages the screen explorer reached by URL (navigate edges with to_url) to a URL kit's states.json as new roots.
  python add_found_roots.py <kit_dir>     prints the new root ids (space separated), nothing when none are new"""
import json, re, sys, pathlib

KIT = pathlib.Path(sys.argv[1])
states = json.loads((KIT / "states.json").read_text(encoding="utf-8"))
db = json.loads((KIT / "screens.json").read_text(encoding="utf-8")) if (KIT / "screens.json").exists() else {"edges": []}
urls = [s["url"] for s in states if s.get("url")]
if not urls:
    sys.exit(0)
norm = lambda u: u.split("#")[0].split("?")[0].rstrip("/")
have = {norm(u) for u in urls}
origin = re.match(r"https?://[^/]+", urls[0]).group(0)
parts = [norm(u).split("/") for u in urls]   # the kit's own path = the common leading segments of all its page URLs
common = []
for seg in zip(*parts):
    if len(set(seg)) > 1:
        break
    common.append(seg[0])
base = "/".join(common)
new = []
# live sites have thousands of profile / post / project URLs: keep 2 examples per URL shape and at most MAX_NEW per round
MAX_NEW = int(__import__("os").environ.get("MAX_NEW_ROOTS", "40"))
def shape(u):
    segs = norm(u)[len(base):].strip("/").split("/")
    return "/".join(s if re.fullmatch(r"[a-z]+(-[a-z]+){0,2}", s) and len(s) < 24 else ":id" for s in segs)
per_shape = {}
for s in states:
    if s.get("url"):
        per_shape[shape(s["url"])] = per_shape.get(shape(s["url"]), 0) + 1
for e in db["edges"]:
    if len(new) >= MAX_NEW:
        break
    u0 = e.get("to_url")
    if u0 and norm(u0).startswith(base) and per_shape.get(shape(u0), 0) >= 2:
        continue
    if u0 and re.search(r"/[a-z]{2}-[A-Za-z]{2,4}(/|$)", u0[len(origin):]):   # language copies of the same page
        continue
    u = e.get("to_url")
    if not u or not norm(u).startswith(base) or norm(u) in have:   # only pages under the kit's own path
        continue
    have.add(norm(u))
    path = norm(u)[len(base):].strip("/") if norm(u).startswith(base) else norm(u)[len(origin):].strip("/")
    sid = re.sub(r"[^a-z0-9]+", "-", path.lower()).strip("-") or "home"
    while any(s["id"] == sid for s in states):
        sid += "-x"
    states.append({"id": sid, "q": "", "url": u.split("#")[0], "full": True, "found_by": e["from"]})
    per_shape[shape(u)] = per_shape.get(shape(u), 0) + 1
    new.append(sid)
(KIT / "states.json").write_text(json.dumps(states, indent=0), encoding="utf-8")
print(" ".join(new))
