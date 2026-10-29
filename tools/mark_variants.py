"""Mark data variants in a kit's screens.json: a screen whose measured layout matches a sibling's (same parent, same
kind, same rows / column ratios / block count / overlay kinds) differs only in its data, so it becomes
`variant_of` that sibling instead of a screen state of its own. Raw captures are kept.
  python mark_variants.py <kit_dir>"""
import json, re, sys, pathlib

KIT = pathlib.Path(sys.argv[1])
p = KIT / "screens.json"
db = json.loads(p.read_text(encoding="utf-8"))


def shape(s):
    f = KIT / (s["shot"][:-4] + ".json")
    if not f.exists():
        return None
    m = json.loads(f.read_text(encoding="utf-8"))
    rows = [(r["cols"], tuple(round(x, 2) for x in r["ratios"])) for r in m["layout"]["rows"]]
    # per block: how much content (empty / little / some / lots), controls present, and which kinds of repeated rows it holds,
    # so an empty state ("no items") stays a state of its own while the same list with other rows is a data variant
    amount = lambda n: 0 if n == 0 else 1 if n <= 4 else 2 if n <= 20 else 3
    blocks = [(amount(len(b["slots"])), b["primitives"].get("button", 0) > 0, tuple(sorted({r["kind"] for r in b["repeats"]}))) for b in m["blocks"]]
    return json.dumps([s["kind"], rows, blocks, sorted(o["kind"] for o in s["overlays"] if o["kind"] != "toast")])


byid = {s["id"]: s for s in db["screens"]}
ctrl_cache = {}


def control_box(parent_id, label):
    """where the control that opened this screen sits on its parent screen (from the parent's measured controls)"""
    if parent_id not in ctrl_cache:
        f = KIT / (byid[parent_id]["shot"][:-4] + ".json")
        ctrl_cache[parent_id] = json.loads(f.read_text(encoding="utf-8")).get("controls", []) if f.exists() else []
    for c in ctrl_cache[parent_id]:
        if c["label"][:40] == (label or "")[:40]:
            return c["tag"], c["bbox"]
    return None


def siblings(a, b):
    """controls in one set: same tag and height, lined up in a row (same y) or a column (same x and width)"""
    if not a or not b or a[0] != b[0]:
        return False
    (_, p), (_, q) = a, b
    return abs(p["h"] - q["h"]) <= 2 and (abs(p["y"] - q["y"]) <= 3 or (abs(p["x"] - q["x"]) <= 3 and abs(p["w"] - q["w"]) <= 3))


heading = lambda s: re.sub(r"[\d.,:%$£€+\-]+", "#", next((o["lines"][0] for o in s["overlays"] if o["kind"] != "toast" and o["lines"]), ""))
first = {}
n = 0
for s in db["screens"]:
    s.pop("variant_of", None)
    if s["depth"] == 0:
        continue
    k = (s["parent"], shape(s), heading(s))
    if k[1] is None:
        continue
    match = next((f for f in first.get(k, []) if siblings(control_box(s["parent"], s["via"]), control_box(s["parent"], byid[f]["via"]))), None)
    if match:
        s["variant_of"] = match
        n += 1
    else:
        first.setdefault(k, []).append(s["id"])
p.write_text(json.dumps(db, ensure_ascii=False, indent=1), encoding="utf-8")
states = sum(1 for s in db["screens"] if s["depth"] > 0 and "variant_of" not in s)
print(f"{n} screens marked as data variants; {states} distinct screen states remain")
