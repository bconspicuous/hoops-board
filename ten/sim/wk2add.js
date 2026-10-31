// current-week (matchup 2) add/drop search for GTD vs its opponent, remaining days from FROM, banked totals included
const S = require('./sim2.js'); const { P, BY, TEAMS, ME, POST, CATS, catMS, weekSums, pwlt, CURW, FROM, BANK } = S;
const pairs = S.SCHED[CURW]; const pr = pairs.find(p => p.includes(ME)); const O = pr[0] === ME ? pr[1] : pr[0];
const own = new Set(POST.flat()); TEAMS.forEach(t => t.ir.forEach(x => own.add(x)));
const pool = S.FA.filter(p => !own.has(p.id)).sort((a, b) => b.value - a.value).slice(0, 120); pool.forEach(p => { p.gp = Math.max(p.gp, 79.5); });
const CORE = new Set((process.env.CORE_NAMES || '').split('|').filter(n => BY[n]).map(n => BY[n].id));
const DROPS = process.env.DROPS ? process.env.DROPS.split('|').map(n => BY[n].id) : (() => { const live = new Set(S.weekWeights(POST[ME], CURW, ME, FROM).filter(([, g]) => g > 0).map(([id]) => id)); return POST[ME].filter(id => !CORE.has(id) && live.has(id)); })().sort((a, b) => P[a].value - P[b].value).slice(0, 5);
const opp = catMS(weekSums(POST[O], CURW, null, O, FROM), BANK[O]);
function ev(r) { const a = catMS(weekSums(r, CURW, null, ME, FROM), BANK[ME]); let dist = { 0: 1 }, e = 0; const per = {};
  for (const c of CATS) { const [pw, pt] = pwlt(a, opp, c); per[c] = pw + pt / 2; e += per[c]; const pl = 1 - pw - pt, nd = {}; for (const [k, v] of Object.entries(dist)) { const y = +k; nd[y + 1] = (nd[y + 1] || 0) + v * pw; nd[y] = (nd[y] || 0) + v * pt; nd[y - 1] = (nd[y - 1] || 0) + v * pl; } dist = nd; }
  let win = 0, tie = 0; for (const [k, v] of Object.entries(dist)) { if (+k > 0) win += v; if (+k === 0) tie += v; } return { e, win, tie, per }; }
const gl = (id) => { const days = S.SC.sched[CURW]; let g = 0; days.forEach((day, d) => { const dt = new Date(Date.parse(S.SC.starts[CURW]) + d * 864e5).toISOString().slice(0, 10); if (dt >= FROM && day.includes(P[id].sc)) g++; }); return g; };
const cur = POST[ME], base = ev(cur);
console.log('vs', TEAMS[O].abbr, 'base cats', base.e.toFixed(2), 'win', (base.win * 100).toFixed(1), 'tie', (base.tie * 100).toFixed(1), CATS.map(c => c + ' ' + (base.per[c] * 100).toFixed(0)).join(' '));
console.log('drops remaining games', DROPS.map(d => P[d].name + ' ' + gl(d) + 'g').join(', '));
const singles = [];
for (const f of pool) for (const d of DROPS) { const r = cur.map(x => x === d ? f.id : x); const s = ev(r); singles.push({ f: f.id, d, ...s }); }
singles.sort((a, b) => b.win - a.win);
const fmt = x => `${x.moves.map(([d, f]) => P[d].name.split(' ').pop() + '→' + P[f].name + '(' + P[f].sc + ' ' + gl(f) + 'g)').join(' + ')} | cats ${x.e.toFixed(2)} win ${(x.win * 100).toFixed(1)} | ` + CATS.filter(c => Math.abs(x.per[c] - base.per[c]) >= 0.03).map(c => c + (x.per[c] > base.per[c] ? '+' : '') + ((x.per[c] - base.per[c]) * 100).toFixed(0)).join(' ');
console.log('== singles'); singles.slice(0, 15).forEach(x => console.log(fmt({ ...x, moves: [[x.d, x.f]] })));
const top = singles.slice(0, 40), dbl = [];
for (let i = 0; i < top.length; i++) for (let j = i + 1; j < top.length; j++) { const a = top[i], b = top[j]; if (a.f === b.f || a.d === b.d) continue; const r = cur.map(x => x === a.d ? a.f : x === b.d ? b.f : x); dbl.push({ moves: [[a.d, a.f], [b.d, b.f]], ...ev(r) }); }
dbl.sort((a, b) => b.win - a.win); console.log('== doubles'); dbl.slice(0, 10).forEach(x => console.log(fmt(x)));
const named = (process.env.NAMED || '').split(';').filter(Boolean);
for (const nm of named) { const mv = nm.split(',').map(s => s.split('>').map(n => BY[n].id)); const r = cur.map(x => { const m = mv.find(([d]) => d === x); return m ? m[1] : x; }); console.log('NAMED', fmt({ moves: mv, ...ev(r) })); }

const pack = x => ({ moves: x.moves.map(([d, f]) => ({ drop: P[d].name, add: P[f].name, team: P[f].sc, g: gl(f), gDrop: gl(d) })), e: x.e, win: x.win, per: x.per });
const remDays = S.SC.sched[CURW].filter((_, d) => new Date(Date.parse(S.SC.starts[CURW]) + d * 864e5).toISOString().slice(0, 10) >= FROM).length;
require('fs').writeFileSync(process.env.WKOUT || 'wk_now.json', JSON.stringify({ week: CURW + 1, opp: TEAMS[O].abbr, oppName: TEAMS[O].name, from: FROM, remDays, base: { e: base.e, win: base.win, tie: base.tie, per: base.per },
  singles: singles.slice(0, 5).map(x => pack({ ...x, moves: [[x.d, x.f]] })), doubles: dbl.slice(0, 3).map(pack) }));
