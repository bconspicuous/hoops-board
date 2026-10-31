const fs = require('fs'); const S = require('./sim2.js');
const { P, BY, TEAMS, AB, ME, POST, CATS, lineup, weekSums, catMS, pwlt, season, NW } = S;
const T = TEAMS.length, id = n => BY[n].id;
const GIVE = (process.env.GIVE || 'Giannis Antetokounmpo').split('|').map(id), GET = (process.env.GET || 'Karl-Anthony Towns').split('|').map(id), J = AB[process.env.TO || 'TBG'];
function msAll(rs) { const out = []; for (let w = 1; w < NW; w++) out.push(rs.map(r => catMS(weekSums(r, w)))); return out; }
const ok = r => r.filter(x => P[x].pos === 'C').length <= 4 && Object.keys(lineup(r).slots).length === 10;
function profile(c, i) { const allAvg = TEAMS.map((t, k) => { const a = {}; CATS.forEach(x => a[x] = c.reduce((s, wk) => s + wk[k][x][0], 0) / c.length); return a; });
  const avg = allAvg[i], rank = {}, per = {}; let tot = 0, n = 0;
  for (const x of CATS) { let s = 0, m = 0; for (const wk of c) for (let o = 0; o < T; o++) if (o !== i) { const [pw, pt] = pwlt(wk[i], wk[o], x); s += pw + pt / 2; m++; } per[x] = s / m; tot += s; n += m; }
  CATS.forEach(x => { rank[x] = 1 + allAvg.filter((a, k) => k !== i && (x === 'TO' ? a[x] < avg[x] : a[x] > avg[x])).length; });
  return { avg, rank, per, ec: tot / n }; }
const R1 = POST.map(x => x.slice()); R1[ME] = R1[ME].filter(x => !GIVE.includes(x)).concat(GET); R1[J] = R1[J].filter(x => !GET.includes(x)).concat(GIVE);
console.log('valid', ok(R1[ME]), ok(R1[J]));
const c0 = msAll(POST), c1 = msAll(R1);
const N = 10000, SEED = 20261024, s0 = season(POST, POST, N, SEED), s1 = season(POST, R1, N, SEED);
const pick = s => ({ p4: s.p4, champ: s.champ, p1: s.p1, W: s.W, L: s.L, T: s.T, fin: s.fin });
const side = i => ({ i, p0: profile(c0, i), p1: profile(c1, i), s0: pick(s0[i]), s1: pick(s1[i]) });
const out = { give: GIVE, get: GET, to: J, me: side(ME), partner: side(J), all: TEAMS.map((t, i) => ({ abbr: t.abbr, ec0: profile(c0, i).ec, ec1: profile(c1, i).ec, p40: s0[i].p4, p41: s1[i].p4 })) };
fs.writeFileSync(process.env.TSOUT || 'tsim_out.json', JSON.stringify(out));
const f = v => (v * 100).toFixed(1);
for (const k of ['me', 'partner']) { const x = out[k]; console.log(TEAMS[x.i].abbr, 'EC', f(x.p0.ec), '->', f(x.p1.ec), 'PO', f(x.s0.p4), '->', f(x.s1.p4), 'ch', f(x.s0.champ), '->', f(x.s1.champ));
  console.log('  ', CATS.map(c => `${c} ${f(x.p0.per[c])}->${f(x.p1.per[c])} (#${x.p0.rank[c]}->#${x.p1.rank[c]})`).join(' | ')); }
for (const n of ['Giannis Antetokounmpo', 'Karl-Anthony Towns']) { const p = P[id(n)], q = p.f; console.log(n, p.sc, 'ESPN#', p.espnRank, 'gp', Math.round(p.gp), 'PTS', q.PTS.toFixed(1), 'REB', q.REB.toFixed(1), 'AST', q.AST.toFixed(1), 'STL', q.STL.toFixed(1), 'BLK', q.BLK.toFixed(1), '3PM', q.TPM.toFixed(1), 'TO', q.TO.toFixed(1), 'FG', (q.FGM / q.FGA).toFixed(3), 'FGA', q.FGA.toFixed(1), 'FT', (q.FTM / q.FTA).toFixed(3), 'FTA', q.FTA.toFixed(1), 'DD', p.DDg.toFixed(2)); }
