"""Prepare a single-file design-prototype bundle kit for capture: unpack its source and patch it so every prop and any
initial state can be set from the URL.
  python prep_bundle.py <kit_dir> <url>
Writes <kit_dir>/source/original.html (as served), template.html (markup + logic, readable) and app.html (patched):
  ?<propName>=<value>  overrides that prop (every this.props.X)        ?st=<url-encoded JSON>  merges into the initial state
Prints the props the kit declares (its own editor options often list every screen) so the page list can be written."""
import html, json, re, sys, pathlib, urllib.request

KIT, URL = pathlib.Path(sys.argv[1]), sys.argv[2]
SRC = KIT / "source"
SRC.mkdir(parents=True, exist_ok=True)
orig = SRC / "original.html"
if not orig.exists():
    orig.write_bytes(urllib.request.urlopen(urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"}), timeout=300).read())
s = orig.read_text(encoding="utf-8")
m = re.search(r'(<script type="__bundler/template">)(.*?)(</script>)', s, re.S)
t = json.loads(m.group(2))
(SRC / "template.html").write_text(t, encoding="utf-8")

assert t.count("class Component extends DCLogic") == 1, "not a single-component bundle"
t = t.replace("class Component extends DCLogic", "const __qp=Object.fromEntries(new URLSearchParams(location.search));\nclass Component extends DCLogic", 1)
t = re.sub(r"this\.props\.(\w+)", lambda p: f"(__qp.{p.group(1)}!=null?__qp.{p.group(1)}:this.props.{p.group(1)})", t)
# merge ?st= into the initial state right after the class's state field (works for `state = {...};` and `state = this.seed();`)
c = t.find("class Component")
sm = re.search(r"\n  state = ", t[c:])
if sm:
    i = c + sm.end()
    depth, j = 0, i
    while j < len(t):   # end of the state expression: the first ';' or newline at depth 0
        ch = t[j]
        if ch in "{([":
            depth += 1
        elif ch in "})]":
            depth -= 1
        elif depth == 0 and ch in ";\n":
            break
        j += 1
    t = t[:j] + ";\n  _qx = (__qp.st ? Object.assign(this.state, JSON.parse(__qp.st)) : 0)" + t[j:]
(SRC / "app.html").write_text(s[:m.start(2)] + json.dumps(t).replace("</", "<\\/") + s[m.end(2):], encoding="utf-8")

props = re.search(r'data-props="([^"]*)"', t)
print(html.unescape(props.group(1))[:3000] if props else "no declared props")
print("props used:", sorted(set(re.findall(r"this\.props\.(\w+)", t))))
