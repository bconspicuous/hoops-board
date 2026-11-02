"""Read-only check: do the stored ESPN cookies belong to an owner of our team (i.e. could lineup/roster moves be authorised)?
Prints only booleans and public league info. Never prints cookie values. Makes no write requests."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_espn as F
d = F.get(["mTeam", "mRoster", "mSettings"])
swid = (os.environ.get("ESPN_SWID") or "").strip().upper()
teams = d.get("teams", [])
me = next((t for t in teams if f"{t.get('location', '')} {t.get('nickname', '')}".strip() == F.MY_TEAM or t.get("name") == F.MY_TEAM), None)
owners = [o.upper() for o in (me or {}).get("owners", [])]
rs = d.get("settings", {}).get("rosterSettings", {})
slots = {}
for e in (me or {}).get("roster", {}).get("entries", []):
    slots[e.get("lineupSlotId")] = slots.get(e.get("lineupSlotId"), 0) + 1
out = {"team_found": bool(me), "team_id": (me or {}).get("id"), "cookie_is_team_owner": bool(swid) and swid in owners,
       "owners_count": len(owners), "lineup_slot_counts_on_roster": slots, "lineupLocktimeType": rs.get("lineupLocktimeType"),
       "rosterLocktimeType": rs.get("rosterLocktimeType"), "moveLimit": rs.get("moveLimit")}
print(json.dumps(out))
print(f"::notice title=ESPN auth check::{json.dumps(out)}")
