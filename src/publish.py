"""One-shot daily publish for the GitHub Pages site.
   usage (from src/): python3 publish.py [new_rosters.json] [--msg "commit message"]
   1) validate + stage the roster snapshot into data/ (apply_rosters.py)
   2) build v22/dashboard.html + web/index.html (build_v22.py)
   3) copy web/index.html to the repository root, commit index.html + src/data, push to main
   Prints the sha256 of the published index.html for the Pages check."""
import subprocess, sys, shutil, hashlib, datetime as dt, os
args = [a for a in sys.argv[1:] if not a.startswith("--")]
msg = sys.argv[sys.argv.index("--msg") + 1] if "--msg" in sys.argv else None
if msg and msg in args: args.remove(msg)
src = args[0] if args else "data/rosters.json"
run = lambda *c, **k: subprocess.run(c, check=True, **k)
r = subprocess.run(["python3", "apply_rosters.py", src, "data"], capture_output=True, text=True); print(r.stdout.strip())
if r.returncode or "staged ->" not in r.stdout: sys.exit("roster validation failed - nothing published")
run("python3", "build_v22.py", "data")
shutil.copyfile("web/index.html", "../index.html")
sha = hashlib.sha256(open("../index.html", "rb").read()).hexdigest()
today = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime("%Y-%m-%d")
os.chdir("..")
run("git", "add", "index.html", "src/data")
if subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode == 0: print("no changes to publish"); sys.exit(0)
body = (msg or f"{today} roster") + "\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01SoBWrxGL2fWvP6cis7mtb1\n"
run("git", "commit", "-q", "-F", "-", input=body.encode())
run("git", "fetch", "-q", "origin", "main"); run("git", "rebase", "-q", "origin/main"); run("git", "push", "-q", "origin", "main")
print("published", subprocess.run(["git", "log", "--oneline", "-1"], capture_output=True, text=True).stdout.strip(), "| index.html sha256", sha)
