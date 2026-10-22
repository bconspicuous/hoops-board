"""Load Basketball-Reference season per-game files (pipe-separated) and normalize names to the projection pool."""
import json, os, re, unicodedata
BR = os.environ.get("BR_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "br"))
TEAMMAP = {"BRK": "BKN", "CHO": "CHA", "NOP": "NOR", "PHX": "PHO", "UTAH": "UTA", "WSH": "WAS", "NO": "NOR", "SA": "SAS", "NY": "NYK", "GS": "GSW"}
COLS = ["G", "MP", "FGM", "FGA", "TPM", "FTM", "FTA", "REB", "AST", "STL", "BLK", "TO", "PF", "PTS"]

def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[.'`]", "", s)
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()

ALIAS = {"gg jackson": "gg jackson", "tristan da silva": "tristan da silva", "nicolas claxton": "nic claxton",
         "jimmy butler": "jimmy butler", "kenyon martin": "kj martin", "herb jones": "herbert jones"}

def pool_map(names):
    m = {}
    for n in names: m[ALIAS.get(norm(n), norm(n))] = n
    return m

def load_season(path, has_pos=False):
    rows = {}
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("Player|"): continue
        f = line.split("|")
        if has_pos:   # Player|Age|Team|Pos|G|GS|MP|FG|FGA|3P|FT|FTA|TRB|AST|STL|BLK|TOV|PF|PTS
            name, age, team = f[0], f[1], f[2]; v = f[4:5] + f[6:]
        else:         # Player|Age|Team|G|MP|FG|FGA|3P|FT|FTA|TRB|AST|STL|BLK|TOV|PF|PTS
            name, age, team = f[0], f[1], f[2]; v = f[3:]
        try: v = [float(x) for x in v]
        except ValueError: continue
        if len(v) != 14: raise ValueError(path + ": " + line)
        G, MP, FG, FGA, P3, FT, FTA, TRB, AST, STL, BLK, TOV, PF, PTS = v
        rows[name] = {"age": int(age) if age.isdigit() else None, "team": TEAMMAP.get(team, team), "G": G, "MP": MP, "FGM": FG, "FGA": FGA,
                      "TPM": P3, "FTM": FT, "FTA": FTA, "REB": TRB, "AST": AST, "STL": STL, "BLK": BLK, "TO": TOV, "PF": PF, "PTS": PTS}
    return rows

def load_all(pool):
    pm = pool_map(pool); out = {n: {} for n in pool}; unmatched = {}
    files = {2021: ("2021.txt", False), 2022: ("2022.txt", False), 2023: ("2023.txt", False), 2024: ("2024.txt", False), 2025: ("2025.txt", False), 2026: ("2026_a.txt", True)}
    for yr, (fn, hp) in files.items():
        p = os.path.join(BR, fn)
        if not os.path.exists(p): continue
        for name, r in load_season(p, hp).items():
            k = ALIAS.get(norm(name), norm(name))
            if k in pm: out[pm[k]][yr] = r
            else: unmatched.setdefault(yr, []).append(name)
    return out, unmatched
