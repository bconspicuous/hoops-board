// Compact data for the in-page Simul: weekly team stat sums (current week = remaining days + banked), per-player weekly games, per-game lines
const fs = require('fs'); const S = require('./sim2.js'); const { P, TEAMS, ME, POST, SCHED, NW, CURW, FROM, BANK, weekSums, weekWeights, dayA0, START, SC, VIRT, RET, WIN } = S;
const RJ = JSON.parse(fs.readFileSync(__dirname + '/' + (process.env.ROSTERS || 'rosters_1024.json')));
const KEYS = ['FGM', 'FGA', 'FTM', 'FTA', 'TPM', 'REB', 'AST', 'STL', 'BLK', 'TO', 'PTS', 'DD', 'TW', 'NPG'];
const W0 = Math.max(1, CURW), weeks = []; for (let w = W0; w < NW; w++) weeks.push(w);
const pat = w => w < SC.sched.length ? SC.sched[w] : SC.sched[((w - 1) % (SC.sched.length - 1)) + 1];
const start = w => SC.starts[w] || START[w];
const dates = w => pat(w).map((_, d) => new Date(Date.parse(start(w)) + d * 864e5).toISOString().slice(0, 10));
const r1 = x => Math.round(x * 100) / 100;
const sums = TEAMS.map((t, i) => weeks.map(w => { const s = weekSums(POST[i], w, null, i, w === CURW ? FROM : null); return KEYS.map(k => r1(s[k])); }));
const bank = TEAMS.map((t, i) => BANK ? KEYS.map(k => r1(BANK[i][k] || 0)) : null);
const own = new Map(); TEAMS.forEach((t, i) => weeks.forEach((w, k) => weekWeights(POST[i], w, i, w === CURW ? FROM : null).forEach(([id, g]) => { if (!own.has(id)) own.set(id, weeks.map(() => 0)); own.get(id)[k] = r1(g); })));
const teamOf = new Map(); TEAMS.forEach((t, i) => POST[i].forEach(id => teamOf.set(id, i)));
const rostered = [...teamOf.keys()], fa = S.FA.filter(p => !teamOf.has(p.id)).sort((a, b) => b.value - a.value).slice(0, 160).map(p => p.id);
const players = rostered.concat(fa).map(id => { const p = P[id], f = p.f;
  const all = [], games = [];
  weeks.forEach(w => { let a = 0, g = 0; dates(w).forEach((dt, d) => { if ((w === CURW && FROM && dt < FROM) || !pat(w)[d].includes(p.sc)) return; const v = dayA0(p, dt); if (v > 0) { a += v; g++; } }); all.push(r1(a)); games.push(g); });
  return { n: p.name, tm: teamOf.has(id) ? teamOf.get(id) : -1, pos: (p.elig || []).filter(x => ['PG', 'SG', 'SF', 'PF', 'C'].includes(x)).join(','), nba: p.sc, r: p.espnRank || null, st: p.status || '', v: r1(p.value),
    f: ['FGM', 'FGA', 'FTM', 'FTA', 'TPM', 'REB', 'AST', 'STL', 'BLK', 'TO', 'PTS'].map(k => r1(f[k] || 0)), dd: r1(p.DDg || 0), tw: r1(p.TWg || 0), own: own.get(id) || weeks.map(() => 0), all, games }; });
// daily data for the in-page engine (daily 10-starter lineup, 13-active cap, generic streaming)
const NBA = Object.keys(VIRT), NI = Object.fromEntries(NBA.map((t, i) => [t, i]));
const enc = a => String.fromCharCode(65 + Math.max(0, Math.min(20, Math.round(a * 20))));
const days = weeks.map(w => pat(w).map(day => day.filter(t => NI[t] != null).map(t => NI[t])));
const fromIdx = weeks.map(w => w === CURW && FROM ? dates(w).filter(dt => dt < FROM).length : 0);
const capOf = (p, w) => { const ws = start(w), we = dates(w)[6]; return !(RET[p.name] && RET[p.name] > ws) && !(WIN[p.name] && WIN[p.name].to && WIN[p.name].to < ws) && !(WIN[p.name] && WIN[p.name].from && WIN[p.name].from > we); };
const byName = Object.fromEntries(P.filter(p => !p.virtual).map(p => [p.name, p]));
players.forEach(q => { const p = byName[q.n];
  q.av = weeks.map(w => dates(w).map((dt, d) => pat(w)[d].includes(p.sc) ? enc(dayA0(p, dt)) : 'A').join(''));
  q.cap = weeks.map(w => capOf(p, w) ? '1' : '0').join(''); });
const SV = P[VIRT[NBA[0]]];
const stream = { f: ['FGM', 'FGA', 'FTM', 'FTA', 'TPM', 'REB', 'AST', 'STL', 'BLK', 'TO', 'PTS'].map(k => r1(SV.f[k] || 0)), dd: r1(SV.DDg), v: r1(SV.value), a: 0.92, el: SV.elig, tw: Object.fromEntries(NBA.map(t => [t, Math.round(P[VIRT[t]].TWg * 1000) / 1000])) };
const SF = RJ.streamFromWeek != null ? RJ.streamFromWeek : 99, SN = RJ.streamPerWeek || 0, SO = RJ.streamOverride || {};
const kNode = TEAMS.map(t => weeks.map(w => w >= SF ? ((SO[t.abbr] || {})[w] != null ? SO[t.abbr][w] : SN) : 0));
const out = { nba: NBA, days, fromIdx, stream, kNode, streamPerWeek: SN, curw: CURW, from: FROM, weeks, starts: weeks.map(start), pairs: weeks.map(w => SCHED[w]), sums, bank, players, keys: KEYS };
fs.writeFileSync(process.argv[2] || 'simdata.json', JSON.stringify(out));
console.log('simdata', weeks.length, 'weeks', players.length, 'players', JSON.stringify(out).length, 'bytes');
