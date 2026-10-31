// Season simulator v3 (2026-10-23): projections from proj_1023.json, real NBA daily schedule (weeks 1-14), trade effective Oct 23
const fs = require('fs');
const W = __dirname + '/';
const PJ = JSON.parse(fs.readFileSync(W + (process.env.PROJ || 'proj_1023.json')));
const R = JSON.parse(fs.readFileSync(W + (process.env.ROSTERS || 'rosters_1024.json')));
const SC = JSON.parse(fs.readFileSync(W + 'nba_sched.json'));
const WT = JSON.parse(fs.readFileSync(W + 'players10.json')).winTotals;
const CATS = ['FG', 'FT', 'TPM', 'REB', 'AST', 'STL', 'BLK', 'TO', 'DD', 'PTS', 'TW'];
const INTC = { TPM: 1, REB: 1, AST: 1, STL: 1, BLK: 1, TO: 1, DD: 1, PTS: 1, TW: 1 };
const CV = { PTS: 0.40, REB: 0.45, AST: 0.55, STL: 0.85, BLK: 1.0, TPM: 0.75, TO: 0.60 };
const KEYS = ['FGM', 'FGA', 'FTM', 'FTA', 'TPM', 'REB', 'AST', 'STL', 'BLK', 'TO', 'PTS', 'DD', 'TW', 'NPG'];
const T = 10, NW = 22, BENCHU = 0.95, AVG_G = 3.45;
const TCODE = { SA: 'SAS', NY: 'NYK', GS: 'GSW', NO: 'NOR', UTAH: 'UTA', WSH: 'WAS', PHX: 'PHO' };
// ---------- players
const P = PJ.players.map((p, id) => ({ id, name: p.name, abbr: p.abbr, sc: TCODE[p.abbr] || p.abbr, pos: p.pos, elig: p.elig.split(/[,\/]/).map(s => s.trim()),
  gp: p.gp, TWg: p.TWg, DDg: p.DDg, f: p.final, espnRank: p.espnRank, method: p.method, status: '' }));
const BY = {}; P.forEach(p => BY[p.name] = p);
const O = new Set(R.status.O), DTD = new Set(R.status.DTD);
P.forEach(p => { p.status = O.has(p.name) ? 'O' : DTD.has(p.name) ? 'DTD' : ''; });
// role boost (user): a player inherits another player's per-game line (e.g. Ajay Mitchell takes Jalen Williams's role)
for (const [to, from] of Object.entries(R.boost || {})) if (BY[to] && BY[from]) { BY[to].f = { ...BY[from].f }; BY[to].DDg = BY[from].DDg; BY[to].boosted = from; }
// value (lineup order): z-sum of 11 categories, 50% per game + 50% season total, on the top-130 pool
function values() {
  const raw = (p, tot) => { const k = tot ? p.gp : 1, f = p.f;
    return { FGM: f.FGM * k, FGA: f.FGA * k, FTM: f.FTM * k, FTA: f.FTA * k, TPM: f.TPM * k, REB: f.REB * k, AST: f.AST * k, STL: f.STL * k, BLK: f.BLK * k, TO: f.TO * k, DD: p.DDg * k, PTS: f.PTS * k, TW: p.TWg * k }; };
  let base = P.filter(p => p.gp > 0).sort((a, b) => (a.espnRank || 999) - (b.espnRank || 999)).slice(0, 130);
  for (let it = 0; it < 3; it++) {
    const z = {};
    for (const tot of [false, true]) {
      const Rr = base.map(p => raw(p, tot)), fg = Rr.reduce((a, r) => a + r.FGM, 0) / Rr.reduce((a, r) => a + r.FGA, 0), ft = Rr.reduce((a, r) => a + r.FTM, 0) / Rr.reduce((a, r) => a + r.FTA, 0);
      const st = (r, c) => c === 'FG' ? r.FGM - fg * r.FGA : c === 'FT' ? r.FTM - ft * r.FTA : r[c];
      const ms = {}; CATS.forEach(c => { const v = Rr.map(r => st(r, c)), m = v.reduce((a, b) => a + b, 0) / v.length; ms[c] = [m, Math.sqrt(v.reduce((a, b) => a + (b - m) ** 2, 0) / v.length) || 1]; });
      P.forEach(p => { const r = raw(p, tot); z[p.id] = z[p.id] || [0, 0]; z[p.id][tot ? 1 : 0] = CATS.reduce((a, c) => a + (st(r, c) - ms[c][0]) / ms[c][1] * (c === 'TO' ? -1 : 1), 0); if (!tot) p.z = Object.fromEntries(CATS.map(c => [c, +(((st(r, c) - ms[c][0]) / ms[c][1]) * (c === 'TO' ? -1 : 1)).toFixed(2)])); });
    }
    const sd = a => { const m = a.reduce((x, y) => x + y, 0) / a.length; return Math.sqrt(a.reduce((x, y) => x + (y - m) ** 2, 0) / a.length) || 1; };
    const sc = sd(base.map(p => z[p.id][0])) / sd(base.map(p => z[p.id][1]));
    P.forEach(p => { p.value = p.gp > 0 ? 0.5 * z[p.id][0] + 0.5 * z[p.id][1] * sc : -20; });
    base = P.filter(p => p.gp > 0).sort((a, b) => b.value - a.value).slice(0, 130);
  }
  P.slice().sort((a, b) => b.value - a.value).forEach((p, i) => p.vrank = i + 1);
}
values();
// ---------- lineup (ESPN multi-position, greedy on transversal matroid)
const SLN = ['PG', 'SG', 'SF', 'PF', 'C', 'G', 'F', 'UTIL', 'UTIL2', 'UTIL3'];
const okS = (el, s) => s.startsWith('UTIL') ? true : s === 'G' ? (el.includes('PG') || el.includes('SG')) : s === 'F' ? (el.includes('SF') || el.includes('PF')) : el.includes(s);
function lineup(ids) {
  const order = ids.slice().sort((a, b) => P[b].value - P[a].value), slotOf = new Array(10).fill(-1), start = [], bench = [];
  const tryP = (id, seen) => { for (let s = 0; s < 10; s++) { if (seen[s] || !okS(P[id].elig, SLN[s])) continue; seen[s] = 1; if (slotOf[s] < 0 || tryP(slotOf[s], seen)) { slotOf[s] = id; return true; } } return false; };
  for (const id of order) { const snap = slotOf.slice(); if (start.length < 10 && tryP(id, new Array(10).fill(0))) start.push(id); else { for (let k = 0; k < 10; k++) slotOf[k] = snap[k]; bench.push(id); } }
  const slots = {}; slotOf.forEach((id, s) => { if (id >= 0) slots[SLN[s]] = id; });
  return { slots, start, bench };
}
// ---------- schedule: games per NBA team per league week (weeks 1-14 real, 15-24 average)
const START = ['2026-10-20']; for (let w = 1; w < 24; w++) { const d = new Date('2026-10-26T00:00:00Z'); d.setUTCDate(d.getUTCDate() + 7 * (w - 1)); START.push(d.toISOString().slice(0, 10)); }
const GAMES = []; for (let w = 0; w < 24; w++) { const g = {}; if (w < SC.sched.length) SC.sched[w].forEach(day => day.forEach(t => g[t] = (g[t] || 0) + 1)); GAMES.push(g); }
const games = (p, w) => p.sc === 'FA' ? 0 : (w < SC.sched.length ? (GAMES[w][p.sc] || 0) : AVG_G);
// ---------- roster states
const OS = new Set((R.status && R.status.OS) || []);   // out for season: treated like IR, slot left empty (no FA fill)
const TEAMS = R.teams.map(t => ({ name: t.name, abbr: t.abbr, mgr: t.mgr, me: !!t.me, players: t.players.filter(n => !OS.has(n)).map(n => BY[n].id), ir: t.ir.concat(t.players.filter(n => OS.has(n))).map(n => BY[n].id), os: t.players.filter(n => OS.has(n)).length }));
const AB = Object.fromEntries(TEAMS.map((t, i) => [t.abbr, i]));
const ME = TEAMS.findIndex(t => t.me), DOO = AB['Doo'];
const TR = R.trade, give = TR.give.map(n => BY[n].id), get = TR.get.map(n => BY[n].id);
function postTrade(rs) { const r = rs.map(x => x.slice()); r[ME] = r[ME].filter(x => !give.includes(x)).concat(get); r[DOO] = r[DOO].filter(x => !get.includes(x)).concat(give); return r; }
function undoTrade(rs) { const r = rs.map(x => x.slice()); r[ME] = r[ME].filter(x => !get.includes(x)).concat(give); r[DOO] = r[DOO].filter(x => !give.includes(x)).concat(get); return r; }
const rostered = new Set(); TEAMS.forEach(t => t.players.concat(t.ir).forEach(id => rostered.add(id)));
const FA = P.filter(p => !rostered.has(p.id) && !OS.has(p.name) && p.gp > 0 && (p.status !== 'O' || (R.returns || {})[p.name]) && p.espnRank && p.sc !== 'FA');
// fill empty roster spots with the best FA by ESPN rank (assumption shown in the dashboard)
const RES = new Set((R.reserveFA || []).map(n => BY[n].id));   // FA targets in our plan: not used to fill other teams' empty slots
const filled = {}; const faRank = FA.filter(p => !RES.has(p.id)).sort((a, b) => (a.espnRank || 999) - (b.espnRank || 999)), usedFA = new Set();
const CUR = TEAMS.map((t, i) => { const r = t.players.slice().concat(((R.adds || {})[t.abbr] || []).map(n => BY[n].id)).concat(t.ir.filter(id => (R.returns || {})[P[id].name])); /* IR players with a return date rejoin from that date */ while (r.length < 13 && false) { const f = faRank.find(p => !usedFA.has(p.id)); usedFA.add(f.id); r.push(f.id); (filled[i] = filled[i] || []).push(f.id); } return r; });
const POST = TR.processed ? CUR : postTrade(CUR), PRE = TR.processed ? undoTrade(CUR) : CUR;
const BASEROS = POST.map(r => new Set(r)); const TEAMIDX = new Map(POST.map((r, i) => [r.slice().sort((a, b) => a - b).join(','), i]));
// ---------- daily engine: availability by date, back-to-back rule, roster windows, 10-starter cap, weekly streaming
const RET = R.returns || {};                       // first game date a player can play (ESPN injury report / user override)
const WIN = R.windows || {};                       // planned roster moves: { name: {from, to} } inclusive dates
const B2B = new Set(R.b2bOne || []);              // players who play only one game of any back-to-back
const STREAM_FROM = R.streamFromWeek != null ? R.streamFromWeek : 99, STREAM_N = R.streamPerWeek || 0, STREAM_OVR = Object.fromEntries(Object.entries(R.streamOverride || {}).map(([a, v]) => [AB[a], v]));
const addDays = (iso, n) => { const x = new Date(iso + 'T00:00:00Z'); x.setUTCDate(x.getUTCDate() + n); return x.toISOString().slice(0, 10); };
const weekStart = w => SC.starts[w] || START[w];
const dayDate = (w, d) => addDays(weekStart(w), d);
const pattern = w => w < SC.sched.length ? SC.sched[w] : SC.sched[((w - 1) % (SC.sched.length - 1)) + 1];   // weeks 15+ reuse the real day patterns of weeks 2-14
const TEAMDATES = {}; for (let w = 0; w < NW + 2; w++) pattern(w).forEach((day, d) => day.forEach(t => (TEAMDATES[t] = TEAMDATES[t] || []).push(dayDate(w, d))));
const SKIP = {}, BASE = {};
for (const n of B2B) { const p = BY[n]; if (!p) continue; const ds = TEAMDATES[p.sc] || [], sk = new Set(); let prev = null, prevPlayed = false;
  for (const d of ds) { const b2b = prev && addDays(prev, 1) === d; const play = !(b2b && prevPlayed); if (!play) sk.add(d); prev = d; prevPlayed = play; }
  SKIP[n] = sk; const gtot = ds.length || 82; BASE[n] = Math.min(1, p.gp / Math.max(1, 82 - sk.size * 82 / gtot)); }
function baseOf(p) { return p.virtual ? 0.92 : (BASE[p.name] != null ? BASE[p.name] : Math.min(1, p.gp / 82)); }
function dayA0(p, date) {
  if (p.virtual) return 0.92;
  const r = RET[p.name]; if (r && date < r) return 0;
  const wn = WIN[p.name]; if (wn && ((wn.from && date < wn.from) || (wn.to && date > wn.to))) return 0;
  if (!r && p.status === 'O' && date < weekStart(2)) return 0;
  if (SKIP[p.name] && SKIP[p.name].has(date)) return 0;
  return baseOf(p);
}
const dayA = dayA0;
function avail(p, w) { const days = pattern(w); let g = 0, a = 0; days.forEach((day, d) => { if (day.includes(p.sc)) { g++; a += dayA(p, dayDate(w, d)); } }); return g ? a / g : 0; }
// virtual streamers: one per NBA team, per-game line = average of free agents ranked 6-30 by value
const FAV = FA.slice().sort((a, b) => b.value - a.value).slice(5, 30);
const SL = {}; ['FGM', 'FGA', 'FTM', 'FTA', 'TPM', 'REB', 'AST', 'STL', 'BLK', 'TO', 'PTS', 'MP'].forEach(k => SL[k] = FAV.reduce((a, p) => a + (p.f[k] || 0), 0) / Math.max(1, FAV.length));
const SLDD = FAV.reduce((a, p) => a + p.DDg, 0) / Math.max(1, FAV.length), SLV = FAV.reduce((a, p) => a + p.value, 0) / Math.max(1, FAV.length);
const VIRT = {};
Object.keys(TEAMDATES).forEach(t => { const wk = Object.keys(WT).find(k => (TCODE[k] || k) === t); const id = P.length;
  P.push({ id, name: 'Streamer ' + t, abbr: t, sc: t, pos: 'SF', elig: ['SG', 'SF'], gp: 75, TWg: wk ? WT[wk] / 82 : 0.5, DDg: SLDD, f: SL, value: SLV, status: '', virtual: true }); VIRT[t] = id; });
// expected games counted per player for a roster-week (daily top-10 lineup), cached
const CURP = R.current && R.current.period >= 2 ? R.current : null, CURW = CURP ? CURP.period - 1 : -1, FROM = CURP ? CURP.fromDate : null;
const BANKC = { FGM: 'FGM', FGA: 'FGA', FTM: 'FTM', FTA: 'FTA', TPM: '3PM', REB: 'REB', AST: 'AST', STL: 'STL', BLK: 'BLK', TO: 'TO', DD: 'DD', PTS: 'PTS', TW: 'TW' };
const BANK = CURP ? TEAMS.map(t => { const c = (CURP.cats || {})[t.abbr] || {}; return Object.fromEntries(Object.entries(BANKC).map(([k, e]) => [k, +(c[e] || 0)])); }) : null;
const WCACHE = new Map();
const TWIN = Object.fromEntries(Object.entries(R.teamWindows || {}).map(([a, v]) => [AB[a], v])), CUREX = Object.fromEntries(Object.entries(R.curExtra || {}).map(([a, v]) => [AB[a], v.map(n => BY[n].id)]));
function weekWeights(ids, w, teamIdx, fromDate) {
  const key = w + '|' + teamIdx + '|' + (fromDate || '') + '|' + ids.slice().sort((a, b) => a - b).join(',');
  if (WCACHE.has(key)) return WCACHE.get(key);
  const days = pattern(w), dates = days.map((_, d) => dayDate(w, d));
  const tw = TWIN[teamIdx]; if (w === CURW && CUREX[teamIdx]) ids = ids.concat(CUREX[teamIdx].filter(x => !ids.includes(x)));
  { const ws = weekStart(w), act = ids.filter(id => !(RET[P[id].name] && RET[P[id].name] > ws) && !(WIN[P[id].name] && WIN[P[id].name].to && WIN[P[id].name].to < ws) && !(WIN[P[id].name] && WIN[P[id].name].from && WIN[P[id].name].from > dayDate(w, 6)));
    if (!process.env.NOCAP && act.length > 13 && !P[act[0]].virtual) { const lo = act.slice().sort((x, y) => P[x].value - P[y].value).slice(0, act.length - 13); ids = ids.filter(id => !lo.includes(id)); } }   // IR returns: a 14th active player forces the lowest-value one out   // mid-week trade: outgoing players count for us until the effective date
  const dayA = (p, dt) => { const z = tw && tw[p.name]; if (z && ((z.from && dt < z.from) || (z.to && dt > z.to))) return 0; return dayA0(p, dt); };
  let core = ids.filter(id => dates.some((dt, d) => days[d].includes(P[id].sc) && dayA(P[id], dt) > 0));
  // weekly streaming: drop the k lowest-value players, add k streamers on the NBA teams that fill the most open lineup slots
  const k = w >= STREAM_FROM ? ((STREAM_OVR[teamIdx] || {})[w] != null ? STREAM_OVR[teamIdx][w] : STREAM_N) : 0;
  const streamers = [];
  if (k > 0 && core.length > k) {
    const keep = core.slice().sort((a, b) => P[b].value - P[a].value);
    const dropped = keep.slice(keep.length - k); core = keep.slice(0, keep.length - k);
    for (let s = 0; s < k; s++) {
      const busy = dates.map((dt, d) => core.concat(streamers).filter(id => days[d].includes(P[id].sc) && dayA(P[id], dt) > 0).length);
      let best = null; for (const t of Object.keys(VIRT)) { if (streamers.includes(VIRT[t])) continue; let free = 0, g = 0; days.forEach((day, d) => { if (day.includes(t)) { g++; if (busy[d] < 10) free++; } }); const sc = free * 10 + g; if (!best || sc > best[1]) best = [VIRT[t], sc]; }
      if (best) streamers.push(best[0]);
    }
    void dropped;
  }
  const act = core.concat(streamers), wt = new Map(act.map(id => [id, 0]));
  dates.forEach((dt, d) => {
    if (fromDate && dt < fromDate) return;   // already banked (current week)
    let playing = act.filter(id => days[d].includes(P[id].sc) && dayA(P[id], dt) > 0);
    if (playing.length > 13 + streamers.length) playing = playing.sort((a, b) => P[b].value - P[a].value).slice(0, 13 + streamers.length);
    const L = lineup(playing), st = new Set(L.start); let slack = 0;
    L.start.forEach(id => { const a = dayA(P[id], dt); wt.set(id, wt.get(id) + a); slack += 1 - a; });
    playing.filter(id => !st.has(id)).sort((a, b) => P[b].value - P[a].value).forEach(id => { if (slack <= 1e-9) return; const a = dayA(P[id], dt), x = a * Math.min(1, slack); wt.set(id, wt.get(id) + x); slack -= x; });
  });
  const out = [...wt.entries()].filter(([, g]) => g > 0);
  WCACHE.set(key, out); return out;
}
// ---------- weekly expected sums for a roster in week w
function weekSums(ids, w, scale, teamIdx, fromDate) {
  const s = Object.fromEntries(KEYS.map(k => [k, 0]));
  if (teamIdx == null) { const sig = ids.slice().sort((a, b) => a - b).join(','); teamIdx = TEAMIDX.get(sig); if (teamIdx == null) { let best = -1, bo = -1; TEAMS.forEach((t, i) => { const o = ids.filter(x => BASEROS[i].has(x)).length; if (o > bo) { bo = o; best = i; } }); teamIdx = best; } }
  for (const [id, g0] of weekWeights(ids, w, teamIdx, fromDate)) { const p = P[id], g = g0 * (scale && scale[id] != null ? scale[id] : 1); if (!g) continue; const f = p.f;
    s.FGM += f.FGM * g; s.FGA += f.FGA * g; s.FTM += f.FTM * g; s.FTA += f.FTA * g; s.TPM += f.TPM * g; s.REB += f.REB * g; s.AST += f.AST * g; s.STL += f.STL * g;
    s.BLK += f.BLK * g; s.TO += f.TO * g; s.PTS += f.PTS * g; s.DD += p.DDg * g; s.TW += (scale && scale.tw ? scale.tw[p.sc] : p.TWg) * g; s.NPG += g; }
  return s;
}
// category mean/sd from sums (cur = already-banked totals for week 1)
function catMS(s, cur) {
  const o = {};
  const FGM = s.FGM + (cur ? cur.FGM : 0), FGA = s.FGA + (cur ? cur.FGA : 0), FTM = s.FTM + (cur ? cur.FTM : 0), FTA = s.FTA + (cur ? cur.FTA : 0);
  const fgp = FGM / Math.max(FGA, 1e-9), ftp = FTM / Math.max(FTA, 1e-9), rf = s.FGA / Math.max(FGA, 1e-9), rt = s.FTA / Math.max(FTA, 1e-9);
  o.FG = [fgp, Math.sqrt(fgp * (1 - fgp) / Math.max(s.FGA, 1)) * rf]; o.FT = [ftp, Math.sqrt(ftp * (1 - ftp) / Math.max(s.FTA, 1)) * rt];
  const n = Math.max(s.NPG, 1);
  for (const c of ['TPM', 'REB', 'AST', 'STL', 'BLK', 'TO', 'PTS']) o[c] = [s[c] + (cur ? cur[c] : 0), CV[c] * s[c] / Math.sqrt(n)];
  o.DD = [s.DD + (cur ? cur.DD : 0), Math.sqrt(Math.max(s.DD, 1e-6))];
  o.TW = [s.TW + (cur ? cur.TW : 0), Math.sqrt(Math.max(s.TW * (1 - s.TW / n), 1e-6) * 1.3)];
  return o;
}
function ncdf(x) { const z = Math.abs(x) / Math.SQRT2, t = 1 / (1 + 0.3275911 * z); const y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-z * z); return x >= 0 ? 0.5 * (1 + y) : 0.5 * (1 - y); }
function pwlt(a, b, c) {   // P(win), P(tie) for team a vs b in category c
  const d = (c === 'TO' ? -1 : 1) * (a[c][0] - b[c][0]), s = Math.sqrt(a[c][1] ** 2 + b[c][1] ** 2) || 1e-6;
  if (!INTC[c]) { const pw = ncdf(d / s); return [pw, 0]; }
  const pw = 1 - ncdf((0.5 - d) / s), pt = ncdf((0.5 - d) / s) - ncdf((-0.5 - d) / s); return [pw, pt];
}
// ---------- week 1: banked totals + remaining days (Oct 22 pre-trade, Oct 23-25 post-trade)
const W1 = R.week1, PAIRS = W1.pairs.map(([a, b]) => [AB[a], AB[b]]);
function cur0(i) {
  const t = W1.totals[TEAMS[i].abbr], s = weekSums(POST[i], 0); const fgaPerPt = s.FGA / s.PTS, ftaPerPt = s.FTA / s.PTS;
  let FTA = t[9] * ftaPerPt, FTM = t[1] * FTA, FGM = (t[9] - t[2] - FTM) / 2, FGA = FGM / t[0];
  const mk = W1.made && W1.made[TEAMS[i].abbr]; if (mk) [FGM, FGA, FTM, FTA] = mk;   // exact makes/attempts from ESPN API
  return { FGM, FGA, FTM, FTA, TPM: t[2], REB: t[3], AST: t[4], STL: t[5], BLK: t[6], TO: t[7], DD: t[8], PTS: t[9], TW: t[10] };
}
function remainWeek1(i, rosterPre, rosterPost) {
  const s = Object.fromEntries(KEYS.map(k => [k, 0]));
  const from = W1.remFrom || 2;
  for (let d = from; d < 6; d++) {          // remaining days of matchup 1 (Oct 20-25)
    const ids = TR.processed ? rosterPre : (d === 2 ? rosterPre : rosterPost), today = SC.sched[0][d];
    const playing = ids.filter(id => today.includes(P[id].sc)), L = lineup(playing);
    for (const id of L.start) { const p = P[id], g = avail(p, 0), f = p.f; if (!g) continue;
      s.FGM += f.FGM * g; s.FGA += f.FGA * g; s.FTM += f.FTM * g; s.FTA += f.FTA * g; s.TPM += f.TPM * g; s.REB += f.REB * g; s.AST += f.AST * g; s.STL += f.STL * g;
      s.BLK += f.BLK * g; s.TO += f.TO * g; s.PTS += f.PTS * g; s.DD += p.DDg * g; s.TW += p.TWg * g; s.NPG += g; }
  }
  return s;
}
function week1(rPre, rPost) {
  return TEAMS.map((t, i) => { const c = cur0(i), r = remainWeek1(i, rPre[i], rPost[i]); return { cur: c, rem: r, ms: catMS(r, c) }; });
}
// ---------- round-robin schedule consistent with week-1 pairs
function schedule() {
  if (R.schedule && R.schedule.length) { const out = R.schedule.map(wk => wk.map(([a, b]) => [AB[a], AB[b]])); while (out.length < NW) out.push(out[out.length % R.schedule.length]); return out; }   // real ESPN schedule
  const ids = [PAIRS[0][0], PAIRS[1][0], PAIRS[2][0], PAIRS[3][0], PAIRS[4][0], PAIRS[4][1], PAIRS[3][1], PAIRS[2][1], PAIRS[1][1], PAIRS[0][1]], out = [];
  for (let r = 0; r < NW; r++) { const m = []; for (let k = 0; k < 5; k++) m.push([ids[k], ids[9 - k]]); out.push(m); ids.splice(1, 0, ids.pop()); }
  return out;
}
const SCHED = schedule();
// ---------- deterministic metrics: expected category win share vs all opponents, weeks 2..22
function ecRest(rs, i, wFrom = 1, wTo = NW) {
  let tot = 0, n = 0;
  for (let w = wFrom; w < wTo; w++) {
    const ms = rs.map(r => catMS(weekSums(r, w)));
    for (let j = 0; j < T; j++) if (j !== i) for (const c of CATS) { const [pw, pt] = pwlt(ms[i], ms[j], c); tot += pw + pt / 2; n++; }
  }
  return tot / n;
}
// ---------- Monte Carlo season (player production ±10%, injury shocks, NBA team wins ±6)
function rng(seed) { let s = seed >>> 0; return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; }; }
function gauss(r) { let u = 0; while (u === 0) u = r(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * r()); }
const NBA = Object.keys(WT);
let PLANW = null; function setPlan(m) { PLANW = m; }
function season(rPre, rPost, S, seed, noisy = true) {
  const r = rng(seed), W1R = week1(rPre, rPost);
  const fin = Array.from({ length: T }, () => new Array(T).fill(0)), po = new Array(T).fill(0), ch = new Array(T).fill(0), fz = new Array(T).fill(0);
  const W = new Array(T).fill(0), L = new Array(T).fill(0), Ti = new Array(T).fill(0), w1win = new Array(T).fill(0);
  const ids = [...new Set(rPost.flat().concat(PLANW ? Object.values(PLANW).flat() : []))];
  for (let s = 0; s < S; s++) {
    const scale = {}; if (noisy) { scale.tw = {}; NBA.forEach(t => scale.tw[TCODE[t] || t] = Math.min(0.9, Math.max(0.1, (WT[t] + 6 * gauss(r)) / 82)));
      for (const id of ids) { const f = Math.max(0.6, 1 + 0.10 * gauss(r)), a = r() < 0.2 ? 0.35 + 0.5 * r() : 1; scale[id] = f * a; } }
    const w = new Array(T).fill(0), l = new Array(T).fill(0), t = new Array(T).fill(0);
    const play = (msA, msB, i, j) => { let wi = 0, wj = 0;
      for (const c of CATS) { const d = (c === 'TO' ? -1 : 1) * (msA[c][0] - msB[c][0]), sd = Math.sqrt(msA[c][1] ** 2 + msB[c][1] ** 2), x = d + sd * gauss(r);
        if (INTC[c] ? x > 0.5 : x > 0) wi++; else if (INTC[c] ? x < -0.5 : x < 0) wj++; else { t[i]++; t[j]++; } }
      w[i] += wi; l[i] += wj; w[j] += wj; l[j] += wi; return [wi, wj]; };
    // week 1 (banked + remaining; production noise applied only to the remaining part)
    for (const [i, j] of PAIRS) { const [a, b] = play(W1R[i].ms, W1R[j].ms, i, j); if (a > b) w1win[i]++; else if (b > a) w1win[j]++; }
    for (let wk = 1; wk < NW; wk++) { const ms = rPost.map((ro0, ti) => { const ro = (ti === ME && PLANW && PLANW[wk]) ? PLANW[wk] : ro0; return wk === CURW ? catMS(weekSums(ro, wk, noisy ? scale : null, ti, FROM), BANK[ti]) : catMS(weekSums(ro, wk, noisy ? scale : null, ti)); });
      for (const [i, j] of SCHED[wk]) play(ms[i], ms[j], i, j); }
    const pct = i => (w[i] + t[i] / 2) / (w[i] + l[i] + t[i]);
    const order = [...Array(T).keys()].map(i => [i, pct(i) + r() * 1e-6]).sort((a, b) => b[1] - a[1]).map(x => x[0]);
    order.forEach((tm, k) => { fin[tm][k]++; W[tm] += w[tm]; L[tm] += l[tm]; Ti[tm] += t[tm]; if (k < 4) po[tm]++; });
    const ms23 = rPost.map(ro => catMS(weekSums(ro, 22, noisy ? scale : null))), ms24 = rPost.map(ro => catMS(weekSums(ro, 23, noisy ? scale : null)));
    const g = (ms, i, j) => { let a = 0, b = 0; for (const c of CATS) { const d = (c === 'TO' ? -1 : 1) * (ms[i][c][0] - ms[j][c][0]), sd = Math.sqrt(ms[i][c][1] ** 2 + ms[j][c][1] ** 2), x = d + sd * gauss(r);
      if (INTC[c] ? x > 0.5 : x > 0) a++; else if (INTC[c] ? x < -0.5 : x < 0) b++; } return a >= b ? i : j; };
    const f1 = g(ms23, order[0], order[3]), f2 = g(ms23, order[1], order[2]); fz[f1]++; fz[f2]++; ch[g(ms24, f1, f2)]++;
  }
  return [...Array(T).keys()].map(i => ({ fin: fin[i].map(x => x / S), p4: po[i] / S, p1: fin[i][0] / S, final: fz[i] / S, champ: ch[i] / S,
    W: W[i] / S, L: L[i] / S, T: Ti[i] / S, avgRank: fin[i].reduce((a, x, k) => a + x * (k + 1), 0) / S, w1: w1win[i] / S }));
}
module.exports = { weekWeights, setPlan, CURW, FROM, BANK, WIN, RET, VIRT, P, BY, TEAMS, AB, ME, DOO, PRE, POST, FA, filled, CATS, SCHED, PAIRS, W1, lineup, weekSums, catMS, pwlt, week1, ecRest, season, postTrade, give, get, games, avail, START, GAMES, NW, SC };
if (require.main === module) {
  const t0 = Date.now();
  const w1 = week1(PRE, POST);
  for (const [i, j] of PAIRS) {
    let ew = 0, el = 0; const per = {};
    for (const c of CATS) { const [pw, pt] = pwlt(w1[i].ms, w1[j].ms, c); per[c] = [pw.toFixed(2), pt.toFixed(2)]; ew += pw + pt / 2; }
    console.log(TEAMS[i].abbr, 'vs', TEAMS[j].abbr, 'exp cat wins', ew.toFixed(1), JSON.stringify(per));
  }
  const ecPost = TEAMS.map((t, i) => ecRest(POST, i)), noTr = PRE, ecNo = TEAMS.map((t, i) => ecRest(noTr, i));
  console.log('EC (weeks 2-22) post-trade:', TEAMS.map((t, i) => t.abbr + ' ' + (ecPost[i] * 100).toFixed(1)).join(' | '));
  console.log('EC no-trade:', TEAMS.map((t, i) => t.abbr + ' ' + (ecNo[i] * 100).toFixed(1)).join(' | '));
  console.log('ms', Date.now() - t0);
  const S = season(PRE, POST, 2000, 1);
  console.log('season 2000:', TEAMS.map((t, i) => `${t.abbr} W${S[i].W.toFixed(0)} PO${(S[i].p4 * 100).toFixed(0)} ch${(S[i].champ * 100).toFixed(0)} w1 ${(S[i].w1 * 100).toFixed(0)}`).join(' | '), Date.now() - t0, 'ms');
}
