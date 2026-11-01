// Next matchup preview (used when the current matchup is about to end): every pairing of week CURW+1, GTD with and without the planned moves
const fs = require('fs'); const S = require('./sim2.js'); const { P, BY, TEAMS, ME, POST, CATS, catMS, weekSums, pwlt, SCHED, CURW, NW } = S;
const w = CURW + 1; if (w >= NW) { fs.writeFileSync('nextweek.json', 'null'); process.exit(0); }
const PL = JSON.parse(fs.readFileSync(process.env.PLANF || 'stream_plan_rec.json')); const L = PL.log.find(x => x.week === w + 1);
const planR = L ? L.roster.map(n => BY[n].id) : POST[ME];
function conv(cats) { let d = { 0: 1 }; for (const x of cats) { const pl = 1 - x.pw - x.pt, nd = {}; for (const [k, v] of Object.entries(d)) { const y = +k; nd[y + 1] = (nd[y + 1] || 0) + v * x.pw; nd[y] = (nd[y] || 0) + v * x.pt; nd[y - 1] = (nd[y - 1] || 0) + v * pl; } d = nd; }
  let a = 0, b = 0; for (const [k, v] of Object.entries(d)) { if (+k > 0) a += v; if (+k < 0) b += v; } return [a, b]; }
const out = SCHED[w].map(([i, j]) => {
  const ra = i === ME ? planR : POST[i], rb = j === ME ? planR : POST[j];
  const sa = weekSums(ra, w, null, i), sb = weekSums(rb, w, null, j), a = catMS(sa), b = catMS(sb);
  const a0 = catMS(weekSums(POST[i], w, null, i)), b0 = catMS(weekSums(POST[j], w, null, j));
  const cats = CATS.map(c => { const [pw, pt] = pwlt(a, b, c), [pw0, pt0] = pwlt(a0, b0, c); return { c, curA: 0, curB: 0, finA: a[c][0], finB: b[c][0], pw, pt, pw0, pt0 }; });
  const [pA, pB] = conv(cats), [pA0, pB0] = conv(cats.map(x => ({ pw: x.pw0, pt: x.pt0 })));
  return { a: i, b: j, rec: ['0-0-0', '0-0-0'], cats, pA, pB, pA0, pB0, remA: sa.NPG, remB: sb.NPG, me: i === ME || j === ME };
});
fs.writeFileSync('nextweek.json', JSON.stringify({ week: w + 1, start: S.SC.starts[w], matchups: out, moves: L ? L.moves : [], forced: L ? L.forced : null }));
const m = out.find(x => x.me); console.log('next week', w + 1, TEAMS[m.a].abbr, 'vs', TEAMS[m.b].abbr, 'pA', m.pA.toFixed(2), '(before', m.pA0.toFixed(2) + ')');
