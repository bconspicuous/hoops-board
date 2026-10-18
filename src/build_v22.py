"""Build v2.2 outputs from the current league docs.
   in : v22/template.html, ref22.json, league docs (rosters/meta[/actuals/results/live]) as JSON files
   out: v22/dashboard.html (artifact page, live store + embedded snapshot fallback)
        web/index.html     (standalone page for static hosting: same code, embedded snapshot, noindex)
   usage: python3 build_v22.py [docs_dir]   (docs_dir holds rosters.json, meta.json, ... ; default = seed files)"""
import json, os, sys
D = sys.argv[1] if len(sys.argv) > 1 else None
def load(name, seed):
    p = os.path.join(D, name + ".json") if D else seed
    return json.load(open(p)) if p and os.path.exists(p) else None
docs = {"league/rosters": load("rosters", "seed_rosters.json"), "league/meta": load("meta", "seed_meta.json")}
for k in ("actuals", "results", "live", "fa", "rules"):
    v = load(k, None)
    if v is not None: docs["league/" + k] = v
emb = {"asOf": docs["league/rosters"]["asOf"], "docs": docs}
t = open("v22/template.html", encoding="utf8").read(); ref = open("ref22.json", encoding="utf8").read().strip()
es = json.dumps(emb, ensure_ascii=False, separators=(",", ":"))
assert "</script" not in es.lower() and "</script" not in ref.lower()
page = t.replace("__REF__", ref).replace("__EMBED__", es)
open("v22/dashboard.html", "w", encoding="utf8").write(page)
i = page.index("</style>") + len("</style>")
head = page[:i].replace('<meta name="claude:viewport-fit-sides" content="cover">\n', "").replace("<style>\n", "<style>\n[hidden] { display: none !important; }\n", 1)
doc = ('<!doctype html>\n<html lang="ko">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n'
       '<meta name="robots" content="noindex, nofollow">\n' + head + "\n</head>\n<body>\n" + page[i:].lstrip("\n") + "\n</body>\n</html>\n")
os.makedirs("web", exist_ok=True); open("web/index.html", "w", encoding="utf8").write(doc)
print("snapshot", emb["asOf"], "| artifact", len(page), "| web/index.html", len(doc))
