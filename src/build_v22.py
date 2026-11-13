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
# 감독 지정(2026-11-10): g8/config.json simBasis = "actual" -> dashboard simulates every player with 2026-27 games from his
# actual per-game line only (weight 1 for all weeks); meta.json itself stays untouched, the override is applied at build time
try:
    _cfg = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "g8", "config.json")))
except Exception:
    _cfg = {}
if _cfg.get("simBasis") == "actual" and docs.get("league/meta") is not None:
    docs["league/meta"] = dict(docs["league/meta"], actualWeights=[[1, 99, 1.0]],
                               actualWeightsNote="감독 지정(2026-11-10): 2026-27 실제 경기당 기록 100%(기록 없는 선수만 프로젝션) — g8/config.json simBasis=actual")
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
# 감독 지정(2026-11-13): external page (GitHub Pages) is titled "8인 리그 시즌 전망"; the claude.ai artifact keeps its own title
WEB_TITLE = "8인 리그 시즌 전망"
for a, b in [("<title>리그 팀별 대시보드 v2.2</title>", f"<title>{WEB_TITLE}</title>"),
             ('<h1><span id="h1-team">Twindragons</span> 시즌 대시보드 <small class="ver">v2.2</small></h1>', f'<h1>{WEB_TITLE} <small class="ver" id="h1-team">Twindragons</small></h1>'),
             ("document.title = `${sh(ME)} · 리그 팀별 대시보드 v2.2`;", f"document.title = \"{WEB_TITLE}\";")]:
    assert doc.count(a) == 1, a
    doc = doc.replace(a, b)
os.makedirs("web", exist_ok=True); open("web/index.html", "w", encoding="utf8").write(doc)
print("snapshot", emb["asOf"], "| artifact", len(page), "| web/index.html", len(doc))
