// Weekly acquisition strategy for Garak Twindragons (no trades): each week pick 2-3 FA adds that maximise expected category wins vs that week's opponent
const fs = require('fs'); const S = require('./sim2.js');
const { P, BY, TEAMS, ME, POST, CATS, lineup, weekSums, catMS, pwlt, SCHED, NW, START, season } = S;
const MAXW = +(process.env.MAXW || 3), T3 = +(process.env.T3 || 0.12), T12 = +(process.env.T12 || 0.03), FIRST = +(process.env.FIRST || (S.CURW + 1)), BUDGET = +(process.env.BUDGET || 65);
const ok = r => r.filter(x => P[x].pos === 'C').length <= 4 && Object.keys(lineup(r).slots).length === 10;
// pool: free agents (healthy or with a return date), added players assumed to play every game (no back-to-back rest)
const own = new Set(POST.flat()); TEAMS.forEach(t => t.ir.forEach(x => own.add(x)));
const pool = S.FA.filter(p => !own.has(p.id)).sort((a, b) => b.value - a.value).slice(0, 90);
pool.forEach(p => { p.gp = Math.max(p.gp, 79.5); });
const pre = new Set((process.env.PRE_DROP || '').split('|').filter(Boolean).map(n => BY[n].id));
let cur = POST[ME].filter(x => !pre.has(x));              // week-3 roster (Kawhi on IR, rejoins from his return date)
// players with a planned exit date (McCain: dropped when Kawhi comes off IR) are kept until then and never used as a drop slot
const PRE_ADD = (process.env.PRE_ADD || '').split('|').filter(Boolean).map(x => x.split('>').map(n => BY[n].id));
for (const [d, f] of PRE_ADD) cur = cur.map(x => x === d ? f : x);   // moves made in the current matchup (count against the budget)
const LEAVE = {}; Object.entries(S.WIN).forEach(([n, z]) => { if (z.to && BY[n] && cur.includes(BY[n].id)) { let w = 0; while (w < NW && START[w] <= z.to) w++; LEAVE[BY[n].id] = w; } });
const dropable = x => !CORE.has(x) && LEAVE[x] == null;
const CORE = process.env.CORE_NAMES ? new Set(process.env.CORE_NAMES.split('|').map(n => BY[n].id).filter(id => cur.includes(id))) : new Set(+(process.env.CORE || 0) ? cur.filter(x => LEAVE[x] == null).sort((a, b) => P[b].value - P[a].value).slice(0, +process.env.CORE) : []);   // protected core (never dropped)
console.log('core', [...CORE].map(x => P[x].name).join(', '));
const plan = {}, log = []; let used = PRE_ADD.length; if (PRE_ADD.length) plan[S.CURW] = cur.slice(); const usedFA = new Set();
const oppOf = w => { const pr = SCHED[w].find(p => p.includes(ME)); return pr[0] === ME ? pr[1] : pr[0]; };
const games = (id, w) => S.avail ? (S.SC ? 0 : 0) : 0;
function exp(r, w, o) { const a = catMS(weekSums(r, w, null, ME)), b = catMS(weekSums(POST[o], w, null, o)); let e = 0; const per = {}; let dist = { 0: 1 };
  for (const c of CATS) { const [pw, pt] = pwlt(a, b, c); per[c] = pw + pt / 2; e += pw + pt / 2; const pl = 1 - pw - pt, nd = {}; for (const [k, v] of Object.entries(dist)) { const y = +k; nd[y + 1] = (nd[y + 1] || 0) + v * pw; nd[y] = (nd[y] || 0) + v * pt; nd[y - 1] = (nd[y - 1] || 0) + v * pl; } dist = nd; }
  let win = 0; for (const [k, v] of Object.entries(dist)) if (+k > 0) win += v; let bonus = 0; for (const c in FOC) bonus += FOC[c] * per[c]; return { e: e + bonus, eTrue: e, win, per }; }
const gcount = (id, w) => { const p = P[id]; let g = 0; const days = S.SC.sched[w] || S.SC.sched[((w - 1) % (S.SC.sched.length - 1)) + 1]; days.forEach(day => { if (day.includes(p.sc)) g++; }); return g; };
const LOOK = +(process.env.LOOK || 0);
const FOC = Object.fromEntries((process.env.FOCUS || '').split(',').filter(Boolean).map(x => { const [c, w] = x.split(':'); return [c, +w]; }));   // extra objective weight per category win prob
const PRE3 = w => 0;   // no pre-committed week-3 add any more (Wiggins → Bey already made)
const obj = (r, w) => exp(r, w, oppOf(w)).e + (LOOK && w + 1 < NW ? exp(r, w + 1, oppOf(w + 1)).e : 0);
// ---- joint search for weeks 3-4 (indices 2,3): maximise E3 + E4 - LAMBDA * moves
// IR players come back on their return date; if the active roster then exceeds 13, the lowest-value non-core player is dropped (a drop costs no acquisition)
function fitRoster(w) { const act = cur.filter(id => !(S.RET[P[id].name] && S.RET[P[id].name] > START[w])); if (act.length <= 13) return null;
  const lo = act.filter(x => !CORE.has(x)).sort((a, b) => P[a].value - P[b].value)[0]; cur = cur.filter(x => x !== lo); console.log('IR return: free drop', P[lo].name); return P[lo].name; }
const LAMBDA = +(process.env.LAMBDA || 0.08); let FIX = null;
if (process.env.JOINT34 && FIRST + 1 < NW) {
  const E = (r, w) => exp(r, w, oppOf(w)).e; const J0 = FIRST, J1 = FIRST + 1;
  const drops0 = r => r.filter(dropable).sort((a, b) => P[a].value - P[b].value).slice(0, 5);
  const singles = [];
  for (const f of pool) { if (cur.includes(f.id)) continue; for (const d of drops0(cur)) { const r2 = cur.map(x => x === d ? f.id : x); if (!ok(r2)) continue; singles.push({ f: f.id, d, v: E(r2, J0) + E(r2, J1) }); } }
  singles.sort((a, b) => b.v - a.v); const top = singles.slice(0, 16);
  const w3sets = [[]].concat(top.map(x => [x]));
  for (let i = 0; i < top.length; i++) for (let j = i + 1; j < top.length; j++) if (top[i].f !== top[j].f && top[i].d !== top[j].d) w3sets.push([top[i], top[j]]);
  function greedy4(r) { let cr = r, moves = [], val = E(cr, J1);
    for (let k = 0; k < 3; k++) { let best = null; for (const f of pool) { if (cr.includes(f.id)) continue; for (const d of drops0(cr)) { const r2 = cr.map(x => x === d ? f.id : x); if (!ok(r2)) continue; const v = E(r2, J1); if (!best || v > best.v) best = { f: f.id, d, v, r2 }; } }
      if (!best || best.v - val < LAMBDA) break; moves.push(best); cr = best.r2; val = best.v; }
    return { cr, moves, val }; }
  let bestAll = null;
  for (const set of w3sets) { let r = cur; for (const m of set) r = r.map(x => x === m.d ? m.f : x); if (!ok(r)) continue;
    const e3 = E(r, J0), g4 = greedy4(r), score = e3 + g4.val - LAMBDA * (set.length + g4.moves.length);
    if (!bestAll || score > bestAll.score) bestAll = { set, r3: r, e3, g4, score }; }
  FIX = { [J0]: bestAll.set.map(m => [m.d, m.f]), [J1]: bestAll.g4.moves.map(m => [m.d, m.f]) };
  console.log('joint34 score', bestAll.score.toFixed(2), 'w' + (J0 + 1), FIX[J0].map(([d, f]) => P[d].name + '->' + P[f].name).join(', ') || '-', '| w' + (J1 + 1), FIX[J1].map(([d, f]) => P[d].name + '->' + P[f].name).join(', ') || '-', '| evaluated', w3sets.length);
}
for (let w = FIRST; w < NW; w++) {
  cur = cur.filter(x => !(LEAVE[x] != null && w >= LEAVE[x]));
  const forced = fitRoster(w);
  const o = oppOf(w), base = exp(cur, w, o); let now = base, nowObj = obj(cur, w), moves = [];
  if (FIX && FIX[w]) { for (const [d, f] of FIX[w]) { const r2 = cur.map(x => x === d ? f : x); const s2 = exp(r2, w, o); moves.push({ drop: P[d].name, add: P[f].name, g: gcount(f, w), gDrop: gcount(d, w), gain: s2.e - now.e }); cur = r2; now = s2; usedFA.add(f); }
    used += moves.length + PRE3(w); plan[w] = cur.slice();
    log.push({ week: w + 1, start: START[w], opp: TEAMS[o].abbr, oppName: TEAMS[o].name, moves, nMoves: moves.length + PRE3(w), before: base.eTrue, after: now.eTrue, perBefore: base.per, winBefore: base.win, winAfter: now.win, per: now.per, roster: cur.map(x => P[x].name), joint: true, forced });
    console.log(`W${w + 1} vs ${TEAMS[o].abbr.padEnd(5)} cats ${base.eTrue.toFixed(2)}→${now.eTrue.toFixed(2)} win ${(base.win * 100).toFixed(0)}→${(now.win * 100).toFixed(0)}% | ${moves.map(m => `${m.drop}→${m.add}(${m.g}g)`).join(', ')} [joint]`);
    continue; }
  const maxMoves = Math.min(MAXW - PRE3(w), BUDGET - used - PRE3(w) - 2 * Math.max(0, NW - 1 - w));   // keep >= 2/week for the remaining weeks
  for (let k = 0; k < Math.max(0, maxMoves); k++) {
    const drops = cur.filter(dropable).sort((a, b) => P[a].value - P[b].value).slice(0, 5); let best = null;
    for (const f of pool) { if (cur.includes(f.id) || usedFA.has(f.id) && !moves.length && false) continue; if (cur.includes(f.id)) continue;
      for (const d of drops) { const r2 = cur.map(x => x === d ? f.id : x); if (!ok(r2)) continue; const s = exp(r2, w, o), j = obj(r2, w); if (!best || j > best.j) best = { f: f.id, d, s, r2, j }; } }
    const need = (moves.length + PRE3(w)) >= 2 ? T3 : T12;
    if (!best || best.j - nowObj < need) break;
    moves.push({ drop: P[best.d].name, add: P[best.f].name, g: gcount(best.f, w), gDrop: gcount(best.d, w), gain: best.s.e - now.e, gain2: best.j - nowObj }); cur = best.r2; now = best.s; nowObj = best.j; usedFA.add(best.f);
  }
  used += moves.length + PRE3(w);
  plan[w] = cur.slice();
  log.push({ week: w + 1, start: START[w], opp: TEAMS[o].abbr, oppName: TEAMS[o].name, moves, nMoves: moves.length + PRE3(w), before: base.eTrue, after: now.eTrue, perBefore: base.per, winBefore: base.win, winAfter: now.win, per: now.per, roster: cur.map(x => P[x].name), forced });
  console.log(`W${w + 1} vs ${TEAMS[o].abbr.padEnd(5)} cats ${base.eTrue.toFixed(2)}→${now.eTrue.toFixed(2)} win ${(base.win * 100).toFixed(0)}→${(now.win * 100).toFixed(0)}% | ${moves.map(m => `${m.drop}→${m.add}(${m.g}g)`).join(', ')}`);
}
console.log('acquisitions used weeks ' + (FIRST + 1) + '-22:', used, 'of budget', BUDGET);
// season comparison: baseline (no further moves after week 3) vs plan
const static3 = {}; { let r = POST[ME].filter(x => !pre.has(x)); for (let w = FIRST; w < NW; w++) { r = r.filter(x => !(LEAVE[x] != null && w >= LEAVE[x])); const act = r.filter(id => !(S.RET[P[id].name] && S.RET[P[id].name] > START[w])); if (act.length > 13) { const lo = act.filter(x => !CORE.has(x)).sort((a, b) => P[a].value - P[b].value)[0]; r = r.filter(x => x !== lo); } static3[w] = r; } }
const N = +(process.env.N || 8000), SEED = 20261027;
S.setPlan(static3); const s0 = season(POST, POST, N, SEED)[ME];
S.setPlan(plan); if (PRE_ADD.length) console.log('current-week roster override', plan[S.CURW].map(x => P[x].name).join(', ')); const s1 = season(POST, POST, N, SEED)[ME];
const catAvg = c => log.reduce((a, x) => a + x.per[c], 0) / log.length;
const sum = { catWin: Object.fromEntries(CATS.map(c => [c, catAvg(c)])), focus: FOC, base: { W: s0.W, L: s0.L, T: s0.T, p4: s0.p4, champ: s0.champ, p1: s0.p1, fin: s0.fin }, plan: { W: s1.W, L: s1.L, T: s1.T, p4: s1.p4, champ: s1.champ, p1: s1.p1, fin: s1.fin }, used, budget: BUDGET, maxw: MAXW, core: [...CORE].map(x => P[x].name), leave: Object.keys(LEAVE).map(x => P[x].name) };
console.log('season base', s0.W.toFixed(0) + '-' + s0.L.toFixed(0), 'PO', (s0.p4 * 100).toFixed(0), 'ch', (s0.champ * 100).toFixed(1), '| plan', s1.W.toFixed(0) + '-' + s1.L.toFixed(0), 'PO', (s1.p4 * 100).toFixed(0), 'ch', (s1.champ * 100).toFixed(1));
fs.writeFileSync(process.env.PLANOUT || 'stream_plan.json', JSON.stringify({ log, sum }));
