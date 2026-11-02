// Calibrate the in-page Simul to the full season simulation (player variance, injuries): a season-long team strength shock
// (logit shift tau*(z_i - z_j) on every category win/no-loss probability) so the Simul gives the same playoff odds / wins as analyze2 (other 9 teams).
const fs = require('fs'); const W = __dirname + '/';
const SDF = process.argv[2] || 'simdata.json', OUTF = process.argv[3] || 'league2_out.json';
const SD = JSON.parse(fs.readFileSync(W + SDF)), LO = JSON.parse(fs.readFileSync(W + OUTF)), RO = JSON.parse(fs.readFileSync(W + '../data/rosters.json'));
const TM = LO.teams, ME = TM.findIndex(t => t.me);
const rec = TM.map(t => { const r = (RO.teams.find(x => x.abbr === t.abbr) || {}).record || {}; return [r.wins || 0, r.losses || 0, r.ties || 0]; });
const SK = Object.fromEntries(SD.keys.map((k, i) => [k, i])), CATS = ['FG', 'FT', 'TPM', 'REB', 'AST', 'STL', 'BLK', 'TO', 'DD', 'PTS', 'TW'];
const CV = { PTS: 0.40, REB: 0.45, AST: 0.55, STL: 0.85, BLK: 1.0, TPM: 0.75, TO: 0.60 }, INT = { TPM: 1, REB: 1, AST: 1, STL: 1, BLK: 1, TO: 1, DD: 1, PTS: 1, TW: 1 };
function ms(s, b) { const g = k => s[SK[k]] + (b ? b[SK[k]] : 0), o = {};
  const FGA = g('FGA'), FTA = g('FTA'), fgp = g('FGM') / Math.max(FGA, 1e-9), ftp = g('FTM') / Math.max(FTA, 1e-9);
  o.FG = [fgp, Math.sqrt(fgp * (1 - fgp) / Math.max(s[SK.FGA], 1)) * s[SK.FGA] / Math.max(FGA, 1e-9)]; o.FT = [ftp, Math.sqrt(ftp * (1 - ftp) / Math.max(s[SK.FTA], 1)) * s[SK.FTA] / Math.max(FTA, 1e-9)];
  const n = Math.max(s[SK.NPG], 1); ['TPM', 'REB', 'AST', 'STL', 'BLK', 'TO', 'PTS'].forEach(c => o[c] = [g(c), CV[c] * s[SK[c]] / Math.sqrt(n)]);
  o.DD = [g('DD'), Math.sqrt(Math.max(s[SK.DD], 1e-6))]; o.TW = [g('TW'), Math.sqrt(Math.max(s[SK.TW] * (1 - s[SK.TW] / n), 1e-6) * 1.3)]; return o; }
function ncdf(x) { const z = Math.abs(x) / Math.SQRT2, t = 1 / (1 + 0.3275911 * z); const y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-z * z); return x >= 0 ? 0.5 * (1 + y) : 0.5 * (1 - y); }
function pw(a, b, c, f) { const d = (c === 'TO' ? -1 : 1) * (a[c][0] - b[c][0]), s = (Math.sqrt(a[c][1] ** 2 + b[c][1] ** 2) || 1e-6) * f;
  if (!INT[c]) return [ncdf(d / s), 0]; return [1 - ncdf((0.5 - d) / s), ncdf((0.5 - d) / s) - ncdf((-0.5 - d) / s)]; }
const M = SD.weeks.map((w, k) => SD.pairs[k].map(([i, j]) => { const cur = w === SD.curw && SD.bank[0]; return [ms(SD.sums[i][k], cur ? SD.bank[i] : null), ms(SD.sums[j][k], cur ? SD.bank[j] : null)]; }));
const lg = p => Math.log(Math.max(1e-6, Math.min(1 - 1e-6, p)) / (1 - Math.max(1e-6, Math.min(1 - 1e-6, p)))), sg = x => 1 / (1 + Math.exp(-x));
const PR = M.map(wk => wk.map(([a, b]) => CATS.map(c => { const [w, t] = pw(a, b, c, 1); return [lg(w), lg(w + t)]; })));
function mc(tau, N) { const T = TM.length, p4 = new Array(T).fill(0), Wn = new Array(T).fill(0); let seed = 7;
  const rnd = () => { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296; };
  const gauss = () => Math.sqrt(-2 * Math.log(rnd() + 1e-12)) * Math.cos(2 * Math.PI * rnd());
  for (let n = 0; n < N; n++) { const Wt = rec.map(r => r[0]), L = rec.map(r => r[1]), Ti = rec.map(r => r[2]), z = TM.map(() => gauss() * tau);
    PR.forEach((wk, k) => wk.forEach((cats, q) => { const [i, j] = SD.pairs[k][q], sh = z[i] - z[j]; cats.forEach(([qa, qb]) => { const a = sg(qa + sh), nl = sg(qb + sh), r = rnd(); if (r < a) { Wt[i]++; L[j]++; } else if (r < nl) { Ti[i]++; Ti[j]++; } else { Wt[j]++; L[i]++; } }); }));
    const sc = Wt.map((w, i) => (w + Ti[i] / 2) / Math.max(1, w + L[i] + Ti[i]) + rnd() * 1e-9); sc.map((s, i) => i).sort((a, b) => sc[b] - sc[a]).slice(0, 4).forEach(i => p4[i]++); Wt.forEach((w, i) => Wn[i] += w); }
  return { p4: p4.map(x => x / N), W: Wn.map(x => x / N) }; }
let best = null;
for (let f = 0; f <= 1.501; f += 0.05) { const r = mc(f, 3000); let e = 0; TM.forEach((t, i) => { if (i === ME) return; e += (r.p4[i] - t.season.p4) ** 2 + ((r.W[i] - t.season.W) / 20) ** 2; }); if (!best || e < best.e) best = { f: +f.toFixed(2), e, r }; }
SD.cal = best.f; fs.writeFileSync(W + SDF, JSON.stringify(SD));
console.log('simcal', SDF, 'tau', best.f, 'rmse p4', Math.sqrt(best.e / 9).toFixed(3), TM.map((t, i) => `${t.abbr} ${(best.r.p4[i] * 100).toFixed(0)}/${(t.season.p4 * 100).toFixed(0)}`).join(' '));
