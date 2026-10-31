const fs = require('fs');
const S = require('./sim2.js');
const { P, TEAMS, ME, DOO, PRE, POST, CATS, SCHED, PAIRS, W1, lineup, weekSums, catMS, pwlt, week1, season, give, get, NW, filled, START } = S;
const W = __dirname + '/';
const PJ = JSON.parse(fs.readFileSync(W + (process.env.PROJ || 'proj_1023.json')));
const T = TEAMS.length;
// ---------- fast EC (weeks 2..22, vs all 9 opponents) with cached opponent weekly distributions
function msAll(rs) { const out = []; for (let w = 1; w < NW; w++) out.push(rs.map(r => catMS(weekSums(r, w)))); return out; }
function ecFrom(cache, i, ri, j, rj) {
  let tot = 0, n = 0;
  for (let k = 0; k < cache.length; k++) {
    const w = k + 1, mi = ri ? catMS(weekSums(ri, w)) : cache[k][i], mj = rj ? catMS(weekSums(rj, w)) : null;
    for (let o = 0; o < T; o++) { if (o === i) continue; const mo = o === j && mj ? mj : cache[k][o];
      for (const c of CATS) { const [pw, pt] = pwlt(mi, mo, c); tot += pw + pt / 2; n++; } }
  }
  return tot / n;
}
function ecTeam(cache, i, ri, j, rj) {    // EC for team j when j's roster changes (and i's)
  let tot = 0, n = 0;
  for (let k = 0; k < cache.length; k++) {
    const w = k + 1, mi = catMS(weekSums(ri, w)), mj = catMS(weekSums(rj, w));
    for (let o = 0; o < T; o++) { if (o === j) continue; const mo = o === i ? mi : cache[k][o];
      for (const c of CATS) { const [pw, pt] = pwlt(mj, mo, c); tot += pw + pt / 2; n++; } }
  }
  return tot / n;
}
const cache = msAll(POST), cacheNo = msAll(PRE);
const ec = TEAMS.map((t, i) => ecFrom(cache, i)), ecNo = TEAMS.map((t, i) => ecFrom(cacheNo, i));
// per-category season profile (avg weekly expected value and rank, avg weekly win prob vs league)
function profile(cacheX, i) {
  const allAvg = TEAMS.map((t, k) => { const a = {}; CATS.forEach(c => a[c] = cacheX.reduce((s, wk) => s + wk[k][c][0], 0) / cacheX.length); return a; });
  const avg = allAvg[i], rank = {}, per = {};
  for (const c of CATS) { let s = 0, n = 0; for (const wk of cacheX) for (let o = 0; o < T; o++) if (o !== i) { const [pw, pt] = pwlt(wk[i], wk[o], c); s += pw + pt / 2; n++; } per[c] = s / n; }
  CATS.forEach(c => { rank[c] = 1 + allAvg.filter((a, k) => k !== i && (c === 'TO' ? a[c] < avg[c] : a[c] > avg[c])).length; });
  return { avg, rank, per, league: Object.fromEntries(CATS.map(c => [c, allAvg.reduce((s, a) => s + a[c], 0) / T])) };
}
// ---------- seasons
const t0 = Date.now();
const SEA = season(POST, POST, 10000, 20261024), SEA0 = season(PRE, PRE, 10000, 20261024), SEAD = season(POST, POST, 4000, 7, false);
console.error('seasons', Date.now() - t0, 'ms');
// ---------- week 1 detail
const w1 = week1(POST, POST), w1No = week1(PRE, PRE);
const week1Out = PAIRS.map(([i, j]) => ({ a: i, b: j, rec: [W1.record[TEAMS[i].abbr], W1.record[TEAMS[j].abbr]],
  cats: CATS.map(c => { const [pw, pt] = pwlt(w1[i].ms, w1[j].ms, c); const cur = k => { const t = W1.totals[TEAMS[k].abbr]; return t[CATS.indexOf(c)]; };
    return { c, curA: cur(i), curB: cur(j), finA: w1[i].ms[c][0], finB: w1[j].ms[c][0], pw, pt }; }),
  pA: SEA[i].w1, pB: SEA[j].w1,
  remA: w1[i].rem.NPG, remB: w1[j].rem.NPG }));
// ---------- current matchup period (from ESPN API rosters): week-ahead projection
const RR = JSON.parse(fs.readFileSync(W + (process.env.ROSTERS || 'rosters_1024.json')));
let curOut = null;
if (RR.current && RR.current.period >= 2) { const wk = RR.current.period - 1, ms = POST.map((r, i) => catMS(weekSums(r, wk, null, i, S.FROM), S.BANK[i]));
  const conv = cats => { let dist = { 0: 1 }; for (const x of cats) { const pl = 1 - x.pw - x.pt, nd = {}; for (const [k, v] of Object.entries(dist)) { const y = +k; nd[y + 1] = (nd[y + 1] || 0) + v * x.pw; nd[y] = (nd[y] || 0) + v * x.pt; nd[y - 1] = (nd[y - 1] || 0) + v * pl; } dist = nd; }
    let a = 0, b = 0; for (const [k, v] of Object.entries(dist)) { if (+k > 0) a += v; if (+k < 0) b += v; } return [a, b]; };
  curOut = RR.current.pairs.map(([x, y]) => { const i = S.AB[x], j = S.AB[y];
    const cats = CATS.map(c => { const [pw, pt] = pwlt(ms[i], ms[j], c); const cv = (k, abbr) => { const v = (RR.current.cats[abbr] || {})[{ FG: 'FG%', FT: 'FT%', TPM: '3PM' }[c] || c]; return v == null ? 0 : v; };
      return { c, curA: cv(i, x), curB: cv(j, y), finA: ms[i][c][0], finB: ms[j][c][0], pw, pt }; });
    const [pA, pB] = conv(cats); return { a: i, b: j, rec: [RR.current.record[x] || '0-0-0', RR.current.record[y] || '0-0-0'], cats, pA, pB, remA: weekSums(POST[i], wk, null, i, S.FROM).NPG, remB: weekSums(POST[j], wk, null, j, S.FROM).NPG }; });
}
const myW1No = (() => { const [i, j] = PAIRS.find(p => p.includes(ME)); let e = 0, e2 = 0; for (const c of CATS) { const a = pwlt(w1No[i].ms, w1No[j].ms, c), b = pwlt(w1[i].ms, w1[j].ms, c); e += a[0] + a[1] / 2; e2 += b[0] + b[1] / 2; } return { noTrade: i === ME ? e : 11 - e, withTrade: i === ME ? e2 : 11 - e2 }; })();
// ---------- moves
const VS = P.filter(p => !p.virtual).map(p => p.value).sort((a, b) => b - a), RV = rk => VS[Math.min(rk || 300, VS.length) - 1];
const C4 = r => r.filter(id => P[id].pos === 'C').length <= 4;
const full10 = r => Object.keys(lineup(r).slots).length === 10;
const ok = r => C4(r) && full10(r);
const LOCK = new Set(Object.entries(S.WIN).filter(([n, w]) => w.to).map(([n]) => S.BY[n] && S.BY[n].id).filter(x => x != null));   // players already scheduled to leave
const FAtop = S.FA.filter(p => !POST.flat().includes(p.id)).sort((a, b) => b.value - a.value).slice(0, 60);
const teams = TEAMS.map((t, i) => {
  const r = POST[i], base = ec[i];
  const fa = [];
  for (const f of FAtop) { let best = null;
    for (const out of r) { if (LOCK.has(out)) continue; const nr = r.map(x => x === out ? f.id : x); if (!ok(nr)) continue; const v = ecFrom(cache, i, nr) - base; if (!best || v > best.d) best = { add: f.id, drop: out, d: v }; }
    if (best) fa.push(best); }
  fa.sort((a, b) => b.d - a.d);
  const drop = r.map(id => [id, ecFrom(cache, i, r.filter(x => x !== id)) - base]).sort((a, b) => b[1] - a[1]);
  const trades = [];
  if (i === ME) for (let j = 0; j < T; j++) { if (j === i) continue;
    for (const a of r) for (const b of POST[j]) { if (LOCK.has(a)) continue; if ((filled[j] || []).includes(b)) continue;
      if (RV(P[a].espnRank) < RV(P[b].espnRank) - 0.25) continue;
      const ri = r.map(x => x === a ? b : x), rj = POST[j].map(x => x === b ? a : x); if (!ok(ri) || !ok(rj)) continue;
      const di = ecTeam(cache, j, rj, i, ri) - base; if (di < 0.003) continue;
      trades.push({ give: a, get: b, to: j, di, dj: ecTeam(cache, i, ri, j, rj) - ec[j] }); } }
  trades.sort((a, b) => b.di - a.di);
  const tr = [], seen = new Set(), per = {};
  for (const x of trades) { if (seen.has(x.get) || seen.has('g' + x.give) || (per[x.to] || 0) >= 2) continue; seen.add(x.get); seen.add('g' + x.give); per[x.to] = (per[x.to] || 0) + 1; tr.push(x); if (tr.length >= 6) break; }
  const L = lineup(r), asg = {}; Object.entries(L.slots).forEach(([s, id]) => asg[id] = s.replace(/\d$/, '')); L.bench.forEach(id => asg[id] = 'BE');
  const prof = profile(cache, i);
  return { i, name: t.name, abbr: t.abbr, mgr: t.mgr, me: t.me, roster: r, ir: t.ir, filled: filled[i] || [], asg, ec: base, ecNo: ecNo[i], season: SEA[i], season0: SEA0[i], seasonDet: SEAD[i],
    profile: prof, fa: fa.slice(0, 8), drop, trades: tr,
    gpStart: L.start.reduce((a, id) => a + P[id].gp, 0) / L.start.length, risk: r.filter(id => P[id].status || P[id].gp < 60).map(id => P[id].name) };
});
// ---------- my action plans: FA first, then up to 3 ESPN-fair trades with different partners
function makePlan(keep) {
  let rs = POST.map(x => x.slice()); const steps = []; let curEc = ec[ME], cacheC = cache;
  const IRP = process.env.PLAN_IR ? S.BY[process.env.PLAN_IR].id : null;   // IR slot player who must be activated (no longer IR-eligible)
  if (IRP) { let best = null; for (const out of rs[ME]) { if (keep.has(out)) continue; const nr = rs[ME].map(x => x === out ? IRP : x); if (!ok(nr)) continue; const v = ecFrom(cacheC, ME, nr); if (!best || v > best.v) best = { v, out, nr }; }
    steps.push({ kind: 'ir', give: best.out, get: IRP, ec: best.v, d: best.v - curEc }); rs[ME] = best.nr; curEc = best.v; cacheC = msAll(rs); }
  for (let k = 0; k < (process.env.PLAN_NOFA ? 0 : 2); k++) {
    let best = null; const own = new Set(rs.flat());
    for (const f of FAtop) { if (own.has(f.id)) continue; for (const out of rs[ME]) { if (keep.has(out)) continue; const nr = rs[ME].map(x => x === out ? f.id : x); if (!ok(nr)) continue; const v = ecFrom(cacheC, ME, nr); if (!best || v > best.v) best = { v, out, add: f.id, nr }; } }
    if (!best || best.v - curEc < 0.003) break; steps.push({ kind: 'fa', give: best.out, get: best.add, ec: best.v, d: best.v - curEc }); rs[ME] = best.nr; curEc = best.v; cacheC = msAll(rs);
  }
  const used = new Set();
  for (let k = 0; k < 3; k++) {
    let best = null;
    for (let j = 0; j < T; j++) { if (j === ME || used.has(j)) continue;
      for (const a of rs[ME]) { if (keep.has(a)) continue; for (const b of rs[j]) { if ((filled[j] || []).includes(b)) continue; if (RV(P[a].espnRank) < RV(P[b].espnRank) - 0.25) continue;
        const ri = rs[ME].map(x => x === a ? b : x), rj = rs[j].map(x => x === b ? a : x); if (!ok(ri) || !ok(rj)) continue;
        const v = ecTeam(cacheC, j, rj, ME, ri); if (!best || v > best.v) best = { v, a, b, j, ri, rj }; } } }
    if (!best || best.v - curEc < 0.004) break;
    const dj = ecTeam(cacheC, ME, best.ri, best.j, best.rj) - ecFrom(cacheC, best.j);
    steps.push({ kind: 'trade', give: best.a, get: best.b, to: best.j, ec: best.v, d: best.v - curEc, dj }); used.add(best.j); rs[ME] = best.ri; rs[best.j] = best.rj; curEc = best.v; cacheC = msAll(rs);
  }
  const SP = season(POST, rs, 10000, 20261024);
  console.error('plan', steps.map(s => `${s.kind} ${P[s.give].name}->${P[s.get].name} ${(s.ec * 100).toFixed(1)}`).join(' | '), 'PO', SP[ME].p4, 'ch', SP[ME].champ);
  return { steps, ec: curEc, season: SP[ME], profile: profile(cacheC, ME), roster: rs[ME] };
}
const plan = makePlan(new Set(LOCK));
const planB = plan;   // B안 removed (user); kept as alias for the dashboard
// ---------- trade evaluation (Cade+Holmgren -> Giannis+Gobert)
const prof0 = profile(cacheNo, ME), prof1 = profile(cache, ME), profD0 = profile(cacheNo, DOO), profD1 = profile(cache, DOO);
const tradeEval = { give, get, me: { ecNo: ecNo[ME], ec: ec[ME], s0: SEA0[ME], s1: SEA[ME], p0: prof0, p1: prof1 }, doo: { ecNo: ecNo[DOO], ec: ec[DOO], s0: SEA0[DOO], s1: SEA[DOO], p0: profD0, p1: profD1 }, w1: myW1No };
// ---------- projection table (300 players)
const owner = {}; TEAMS.forEach((t, i) => { POST[i].forEach(id => owner[id] = t.abbr); t.ir.forEach(id => owner[id] = t.abbr + ' IR'); });
const proj = PJ.players.map((p, id) => ({ id, n: p.name, t: p.abbr, el: p.elig, r: p.espnRank, vr: P[id].vrank, v: +P[id].value.toFixed(2), gp: p.gp, m: p.method, ns: p.n,
  st: P[id].status, own: owner[id] || 'FA', e: p.espn, rg: p.reg || null, w: p.wReg ? p.wReg.PTS : null, wAll: p.wReg || null, b: p.blend, a: p.actual || null, f: p.final, dd: p.DDg, tw: +(p.TWg * 82).toFixed(1), h: p.hist, nc: p.ncaa || null }));
const out = { asOf: RR.asOf || '2026-10-26T13:42+09:00', cats: CATS, me: ME, doo: DOO, teams, week1: curOut || week1Out, period: (RR.current && RR.current.period) || 1, week1Final: week1Out, plan, planB, tradeEval, proj, summary: PJ.summary,
  sched: { starts: START.slice(0, 24), pairs: SCHED.map(w => w.map(([a, b]) => [a, b])) } };
fs.writeFileSync(W + (process.env.OUTF || 'league2_out.json'), JSON.stringify(out));
console.log(TEAMS.map((t, i) => `${t.abbr.padEnd(5)} EC ${(ec[i] * 100).toFixed(1)} (no-trade ${(ecNo[i] * 100).toFixed(1)}) W ${SEA[i].W.toFixed(0)}-${SEA[i].L.toFixed(0)}-${SEA[i].T.toFixed(0)} PO ${(SEA[i].p4 * 100).toFixed(0)} (nt ${(SEA0[i].p4 * 100).toFixed(0)}, det ${(SEAD[i].p4 * 100).toFixed(0)}) 1st ${(SEA[i].p1 * 100).toFixed(0)} ch ${(SEA[i].champ * 100).toFixed(0)} w1 ${(SEA[i].w1 * 100).toFixed(0)} | ${CATS.map(c => teams[i].profile.rank[c]).join(' ')}`).join('\n'));
console.log('FA', teams[ME].fa.slice(0, 5).map(f => `${P[f.add].name} for ${P[f.drop].name} ${(f.d * 100).toFixed(2)}`).join(' | '));
console.log('TR', teams[ME].trades.map(x => `${P[x.give].name}(#${P[x.give].espnRank})->${P[x.get].name}(#${P[x.get].espnRank}) ${TEAMS[x.to].abbr} ${(x.di * 100).toFixed(2)} / ${(x.dj * 100).toFixed(2)}`).join('\n   '));
console.log('drop', teams[ME].drop.slice(0, 5).map(([id, d]) => P[id].name + ' ' + (d * 100).toFixed(2)).join(' | '));
console.log('trade prof me', JSON.stringify(prof0.rank), '->', JSON.stringify(prof1.rank));
console.log('w1 my', JSON.stringify(myW1No));
console.log('planA rank', JSON.stringify(plan.profile.rank), 'planB rank', JSON.stringify(planB.profile.rank));
console.log('filled', JSON.stringify(Object.fromEntries(Object.entries(filled).map(([k, v]) => [TEAMS[k].abbr, v.map(id => P[id].name)]))));
