/* g8 lineup planner: proposes today's (US Eastern) starting lineup for Garak Twindragons and writes g8/lineup/plan.json + plan.md.
   Loads the built dashboard (index.html) headless and scores every legal choice of starters with the full weekly model (the
   current matchup, live totals, availability, back-to-backs): benched players' games on the target day are removed and the
   expected category wins (tie = 0.5) are compared. The current ESPN lineup (Slot column of g8/data/players_2027.csv) is scored the
   same way. The plan is a PROPOSAL (status "pending"); nothing touches ESPN until the manager approves it and Claude runs the
   g8-lineup workflow in live mode.
   usage (repo root): node g8/sim/lineup.js      env: CHROMIUM, PW, DATE=YYYY-MM-DD (default: today US Eastern) */
const fs = require('fs'), path = require('path');
const ROOT = path.resolve(__dirname, '..', '..'), OUTD = path.join(ROOT, 'g8', 'lineup');
let pw; try { pw = require(process.env.PW || '/opt/node-tools/node_modules/playwright'); } catch (e) { pw = require('playwright'); }
const norm = s => (s || '').normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[.'`]/g, '').replace(/\b(jr|sr|ii|iii|iv)\b/g, '').replace(/[^a-z0-9]+/g, ' ').trim();
(async () => {
  const csv = fs.readFileSync(path.join(ROOT, 'g8', 'data', 'players_2027.csv'), 'utf8').trim().split('\n'), h = csv[0].split(',');
  const espn = csv.slice(1).map(r => { const c = r.split(','), o = {}; h.forEach((k, i) => o[k] = c[i]); return o; }).filter(o => o.Owner === 'Garak Twindragons');
  const cur = Object.fromEntries(espn.map(o => [norm(o.Player), { name: o.Player, slot: o.Slot }]));
  const exe = process.env.CHROMIUM || (fs.existsSync('/opt/pw-browsers/chromium') ? '/opt/pw-browsers/chromium' : undefined);
  const b = await pw.chromium.launch(exe ? { executablePath: exe } : {}); const p = await b.newPage();
  await p.route(/^https?:\/\//, r => r.abort());
  await p.goto('file://' + path.join(ROOT, 'index.html'));
  await p.waitForFunction(() => typeof state !== 'undefined' && state.base && !state.busy, null, { timeout: 600000 });
  const R = await p.evaluate(([cur, date]) => {
    const nrm = s => (s || '').normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[.'`]/g, '').replace(/\b(jr|sr|ii|iii|iv)\b/g, '').replace(/[^a-z0-9]+/g, ' ').trim();
    const day = date || todayStr(); let cw = currentWeek(); while (cw < NW - 1 && day > REF.ends[cw]) cw++;
    const d = dayOffset(cw, day), days = REF.sched[cw].length; if (d < 0 || d >= days) return { date: day, status: 'out-of-range' };
    const roster = rosterFor(ME, cw, null), oT = state.base.TW[oppOf(ME, cw).opp + '|' + cw];
    const curSlot = n => (cur[nrm(n)] || {}).slot || 'BE';
    const plays = roster.filter(n => state.PL[n] && REF.sched[cw][d].includes(state.PL[n].team) && statusOf(n) !== 'O' && !(state.restB2B.has(n) && REF.b2bd[cw][d].includes(state.PL[n].team)));
    const SL = ['PG', 'SG', 'SF', 'PF', 'C', 'G', 'F', 'UTIL', 'UTIL', 'UTIL'];
    if (!plays.length) return { date: day, week: cw + 1, status: 'no-games', roster: roster.map(n => ({ name: n, slot: curSlot(n) })) };
    const orig = playsOf; let MASK = {};
    playsOf = function (pl, w, D, pg, b2b) { const r = orig(pl, w, D, pg, b2b), m = MASK[pl.name]; if (!m || w !== cw) return r; const arr = r.arr.slice(); for (let k = 0; k < D; k++) m.forEach(x => arr[k * days + x] = 0); return Object.assign({}, r, { arr }); };
    const ev = (bench, D) => { MASK = {}; bench.forEach(n => MASK[n] = [d]); PLAYC = new Map(); const t = teamWeekL(ME, roster, cw, { draws: D, b2b: state.b2b, stream: null }), o = pcat3(t, oT); MASK = {}; PLAYC = new Map();
      return { W: CATS.reduce((s, c) => s + o[c].w + o[c].t / 2, 0), pc: Object.fromEntries(CATS.map(c => [c, +(o[c].w + o[c].t / 2).toFixed(3)])) }; };
    /* slot matching; `pref` = slot index tried first per player (keeps current slots where possible) */
    const match = (list, pref) => { const slotOf = new Array(10).fill(-1);
      const order = n => { const s = [...Array(10).keys()], c = pref && pref(n); return c != null ? [c, ...s.filter(x => x !== c)] : s; };
      const tryP = (i, seen) => { for (const s of order(list[i])) if ((state.PL[list[i]].mask & SLOTM[s]) && !seen[s]) { seen[s] = 1; if (slotOf[s] < 0 || tryP(slotOf[s], seen)) { slotOf[s] = i; return true; } } return false; };
      for (let i = 0; i < list.length; i++) if (!tryP(i, [])) return null; return slotOf; };
    /* every legal set of starters among today's players: as many as fit (max 10) */
    const N = plays.length; let size = Math.min(10, N), cands = [];
    while (size > 0 && !cands.length) { for (let m = 0; m < (1 << N); m++) { let c = 0; for (let i = 0; i < N; i++) if (m >> i & 1) c++; if (c !== size) continue; const L = plays.filter((_, i) => m >> i & 1); if (match(L)) cands.push(L); } if (!cands.length) size--; }
    const scored = cands.map(L => ({ L, bench: plays.filter(n => !L.includes(n)), W: ev(plays.filter(n => !L.includes(n)), 500).W })).sort((a, b) => b.W - a.W);
    const top = scored.slice(0, 6).map(s => Object.assign(s, ev(s.bench, 3000))).sort((a, b) => b.W - a.W), best = top[0];
    /* current ESPN lineup: playing players sitting in BE/IR are benched today */
    const curBench = plays.filter(n => ['BE', 'IR'].includes(curSlot(n))), curEv = ev(curBench, 3000);
    /* final slots: starters keep their current slot when legal; idle players fill leftover active slots (current ones first), rest BE */
    const slotIdx = n => { const c = curSlot(n), i = SL.indexOf(c); return i >= 0 ? i : null; };
    const sm = match(best.L, slotIdx), assign = {}; sm.forEach((i, s) => { if (i >= 0) assign[best.L[i]] = SL[s]; });
    const free = sm.map((i, s) => i < 0 ? s : null).filter(x => x != null);
    roster.filter(n => !best.L.includes(n) && !plays.includes(n)).sort((a, c) => (slotIdx(c) != null) - (slotIdx(a) != null)).forEach(n => {
      const k = free.findIndex(s => state.PL[n].mask & SLOTM[s]); if (k >= 0) { assign[n] = SL[free[k]]; free.splice(k, 1); } });
    roster.forEach(n => { if (!assign[n]) assign[n] = 'BE'; });
    const sameStarters = best.L.length === plays.length - curBench.length && best.L.every(n => !curBench.includes(n));
    const moves = roster.filter(n => assign[n] !== curSlot(n)).map(n => ({ name: n, from: curSlot(n), to: assign[n] }));
    const dtd = plays.filter(n => statusOf(n) === 'DTD');
    const alt = top.slice(1, 4).map(s => ({ bench: s.bench, W: +s.W.toFixed(3) }));
    return { date: day, week: cw + 1, opp: oppOf(ME, cw).opp, status: 'pending', playing: plays.length, starters: best.L, bench: best.bench, dtd,
      expected: { best: +best.W.toFixed(3), current: +curEv.W.toFixed(3), gain: +(best.W - curEv.W).toFixed(3), pcBest: best.pc, pcCurrent: curEv.pc }, alternatives: alt,
      currentBench: curBench, sameStarters, moves, slots: roster.map(n => ({ name: n, slot: assign[n] })).sort((a, c) => SL.concat(['BE']).indexOf(a.slot) - SL.concat(['BE']).indexOf(c.slot)) };
  }, [cur, process.env.DATE || null]);
  await b.close();
  fs.mkdirSync(OUTD, { recursive: true });
  const prevP = path.join(OUTD, 'plan.json'), prev = fs.existsSync(prevP) ? JSON.parse(fs.readFileSync(prevP, 'utf8')) : null;
  R.id = R.date + 'T' + new Date().toISOString().slice(11, 16).replace(':', '') + 'Z'; R.createdAt = new Date().toISOString();
  if (R.status === 'pending' && (!R.moves.length || (R.sameStarters && R.expected.gain < 0.005))) R.status = R.moves.length ? 'nochange-starters' : 'nochange';
  else if (R.status === 'pending' && R.expected.gain < 0.02) R.status = 'minor';   // < 0.02 expected category wins: not worth an approval request
  // keep an approval/execution already given for the same day and the same starters
  if (prev && prev.date === R.date && ['approved', 'executed'].includes(prev.status) && JSON.stringify([...prev.starters || []].sort()) === JSON.stringify([...R.starters || []].sort())) { R.status = prev.status; R.approvedAt = prev.approvedAt; R.executedAt = prev.executedAt; }
  fs.writeFileSync(prevP, JSON.stringify(R, null, 1));
  const L = [];
  if (R.status === 'no-games') L.push(`# 라인업 ${R.date} (미국 동부) — 우리 팀 경기 없음`);
  else if (R.status === 'out-of-range') L.push(`# 라인업 ${R.date} — 시즌 일정 밖`);
  else {
    L.push(`# 라인업 제안 ${R.date} (미국 동부) · ${R.week}주차 vs ${R.opp} · 상태: ${R.status}`);
    L.push(`출전 ${R.playing}명 · 기대 카테고리 승 ${R.expected.best.toFixed(2)} (현재 ESPN 라인업 ${R.expected.current.toFixed(2)}, ${R.expected.gain >= 0 ? '+' : ''}${R.expected.gain.toFixed(2)})`);
    L.push(`벤치(출전 선수 중): ${R.bench.join(', ') || '없음'}${R.dtd.length ? ` · DTD: ${R.dtd.join(', ')}` : ''}`);
    L.push(`변경: ${R.moves.map(m => `${m.name} ${m.from}→${m.to}`).join(', ') || '없음'}`);
    if (R.alternatives.length) L.push(`차선: ${R.alternatives.map(a => `벤치 ${a.bench.join('·')} ${a.W.toFixed(2)}`).join(' / ')}`);
    L.push('', '| 슬롯 | 선수 |', '|---|---|'); R.slots.forEach(s => L.push(`| ${s.slot} | ${s.name} |`));
  }
  fs.writeFileSync(path.join(OUTD, 'plan.md'), L.join('\n') + '\n');
  console.log(L.join('\n'));
})();
