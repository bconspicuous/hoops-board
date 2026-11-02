// Daily start/sit recommendation for our team in the matchup shown on the dashboard (current week, or next week when the current one is over).
// Players are ranked per day by matchup leverage: sum over categories of (how much one more unit moves our win probability in that category) x (player's per-game line).
const fs = require('fs'); const S = require('./sim2.js'); const { P, BY, TEAMS, ME, POST, CATS, catMS, weekSums, pwlt, SCHED, CURW, FROM, lineup, dayA0 } = S;
const WK = JSON.parse(fs.readFileSync('wk_now.json')); const next = WK.remDays <= 1;
const w = next ? CURW + 1 : CURW;
const PL = JSON.parse(fs.readFileSync(process.env.PLANF || 'stream_plan_rec.json')); const L = PL.log.find(x => x.week === w + 1);
const useP = process.env.ROSTER_MODE !== 'current' && L;
const roster = useP ? L.roster.map(n => BY[n].id) : POST[ME];
const pr = SCHED[w].find(p => p.includes(ME)), O = pr[0] === ME ? pr[1] : pr[0];
const a = catMS(weekSums(roster, w, null, ME, next ? null : FROM), next ? null : S.BANK[ME]), b = catMS(weekSums(POST[O], w, null, O, next ? null : FROM), next ? null : S.BANK[O]);
const phi = x => Math.exp(-x * x / 2) / Math.sqrt(2 * Math.PI);
const sAll = weekSums(roster, w, null, ME, next ? null : FROM);
const lev = {}; for (const c of CATS) { const sg = Math.sqrt(a[c][1] ** 2 + b[c][1] ** 2) || 1e-6, d = (c === 'TO' ? -1 : 1) * (a[c][0] - b[c][0]); lev[c] = phi(d / sg) / sg; }
const score = id => { const p = P[id], f = p.f;
  return lev.FG * (f.FGM - a.FG[0] * f.FGA) / Math.max(sAll.FGA, 1) + lev.FT * (f.FTM - a.FT[0] * f.FTA) / Math.max(sAll.FTA, 1) + lev.TPM * f.TPM + lev.REB * f.REB + lev.AST * f.AST + lev.STL * f.STL + lev.BLK * f.BLK - lev.TO * f.TO + lev.DD * p.DDg + lev.PTS * f.PTS + lev.TW * p.TWg; };
const days = S.SC.sched[w], start = S.SC.starts[w], out = [];
const keep = new Map(roster.map(id => [id, P[id].value]));
roster.forEach(id => { P[id].value = score(id); });
days.forEach((day, d) => { const dt = new Date(Date.parse(start) + d * 864e5).toISOString().slice(0, 10);
  if (!next && dt < FROM) return;
  const teamPlay = roster.filter(id => day.includes(P[id].sc)), playing = teamPlay.filter(id => dayA0(P[id], dt) > 0), outP = teamPlay.filter(id => dayA0(P[id], dt) === 0);
  const Lu = lineup(playing), ord = ['PG', 'SG', 'SF', 'PF', 'C', 'G', 'F', 'UTIL', 'UTIL2', 'UTIL3'];
  out.push({ date: dt, n: playing.length, start: Object.entries(Lu.slots).map(([s, id]) => ({ slot: s.replace(/\d$/, ''), name: P[id].name, team: P[id].sc })).sort((x, y) => ord.indexOf(x.slot) - ord.indexOf(y.slot)),
    bench: Lu.bench.map(id => ({ name: P[id].name, team: P[id].sc })), out: outP.map(id => P[id].name), idle: roster.filter(id => !day.includes(P[id].sc)).map(id => P[id].name) }); });
const rank = roster.slice().sort((x, y) => P[y].value - P[x].value).map(id => ({ name: P[id].name, score: P[id].value }));
roster.forEach(id => { P[id].value = keep.get(id); });
fs.writeFileSync('lineup_week.json', JSON.stringify({ week: w + 1, opp: TEAMS[O].abbr, rosterMode: useP ? 'plan' : 'current', lev, rank, days: out }));
for (const x of out) console.log(x.date, x.n + '명', x.n > 10 ? '벤치: ' + x.bench.map(b => b.name).join(', ') : '전원 출전', x.out.length ? '| 결장: ' + x.out.join(', ') : '');
console.log('priority', rank.map(r => r.name.split(' ').pop() + ' ' + r.score.toFixed(3)).join(' > '));
