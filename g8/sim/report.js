/* g8 scheduled simulation report: loads the built dashboard (index.html) headless, reads the 20k-run season simulation and the
   current-week projection, compares with the previous report (g8/sim/last.json) and writes g8/sim/report.md + last.json.
   usage (repo root): node g8/sim/report.js   env: CHROMIUM (default /opt/pw-browsers/chromium), PW (playwright module path) */
const fs = require('fs'), path = require('path');
const ROOT = path.resolve(__dirname, '..', '..');
let pw; try { pw = require(process.env.PW || '/opt/node-tools/node_modules/playwright'); } catch (e) { pw = require('playwright'); }
(async () => {
  const exe = process.env.CHROMIUM || (fs.existsSync('/opt/pw-browsers/chromium') ? '/opt/pw-browsers/chromium' : undefined);
  const b = await pw.chromium.launch(exe ? { executablePath: exe } : {}); const p = await b.newPage(); const errs = [];
  p.on('pageerror', e => errs.push(e.message));
  await p.route(/^https?:\/\/(?!cdn\.jsdelivr)/, r => r.abort());   // offline: fonts etc. are not needed
  await p.goto('file://' + path.join(ROOT, 'index.html'));
  await p.waitForFunction(() => typeof state !== 'undefined' && state.base && !state.busy, null, { timeout: 600000 });
  const d = await p.evaluate(() => {
    const R = state.base, cw = currentWeek(), o = oppOf(ME, cw), g = gameOf(R, ME, cw), L = liveFor(cw), tw = R.TW[ME + '|' + cw];
    const add = (iso, n) => { const t = new Date(iso + 'T00:00:00Z'); t.setUTCDate(t.getUTCDate() + n); return t.toISOString().slice(5, 10); };
    const season = REF.teams.map(t => { const s = R.season[t], r = record(t); return { team: t, rec: `${r.w}-${r.l}-${r.t}`, epct: s.epct, po: s.po, p1: s.p1, champ: s.champ }; }).sort((a, b) => b.epct - a.epct);
    const pc = Object.fromEntries(CATS.map(c => [c, g.a === ME ? g.pc[c] : 1 - g.pc[c]]));
    const plan = tw.plan ? tw.plan.segs.filter(s => !s.orig).map(s => ({ name: s.p.name, team: s.p.team, from: add(REF.starts[cw], s.a), to: add(REF.starts[cw], s.b) })) : [];
    const st = (state.docs['league/rosters'] || {}).status || {}, ros = rosterFor(ME, cw, null);
    return { asOf: (state.docs['league/rosters'] || {}).asOf, week: cw + 1, weekRange: [REF.starts[cw], REF.ends[cw]], opp: o.opp, through: L && L.through,
      live: L ? { me: L.cats[ME], opp: L.cats[o.opp], adds: L.adds[ME] } : null, wk: wkWLT(R, ME, cw), pc, plan, season,
      roster: ros, injured: ros.filter(n => st[n]).map(n => n + ' (' + st[n] + ')'), ir: (rosters()[ME] || {}).ir || [] };
  });
  await b.close();
  const lastP = path.join(__dirname, 'last.json'), prev = fs.existsSync(lastP) ? JSON.parse(fs.readFileSync(lastP, 'utf8')) : null;
  const me = d.season.find(s => s.team === 'Garak Twindragons'), pm = prev && prev.season.find(s => s.team === 'Garak Twindragons');
  const pct = x => (x * 100).toFixed(1) + '%', dp = (a, b) => b == null ? '' : ` (${a - b >= 0 ? '+' : ''}${((a - b) * 100).toFixed(1)}%p)`;
  const CAT = ['FG', 'FT', 'TPM', 'REB', 'AST', 'STL', 'BLK', 'TO', 'DD', 'PTS', 'PF'], LAB = { FG: 'FG%', FT: 'FT%', TPM: '3PM' };
  const swing = CAT.filter(c => d.pc[c] > 0.1 && d.pc[c] < 0.9).map(c => `${LAB[c] || c} ${Math.round(d.pc[c] * 100)}%`);
  const lines = [];
  lines.push(`# G League 시뮬레이션 — ${d.asOf}`);
  lines.push(`**우리 팀** 기대승률 ${pct(me.epct)}${dp(me.epct, pm && pm.epct)} · 정규 1위 ${pct(me.p1)}${dp(me.p1, pm && pm.p1)} · 우승 ${pct(me.champ)}${dp(me.champ, pm && pm.champ)}`);
  const top = d.season.slice().sort((a, b) => b.champ - a.champ)[0];
  if (top.team !== 'Garak Twindragons') lines.push(`⚠ 우승확률 1위: ${top.team} ${pct(top.champ)}`);
  lines.push(`**${d.week}주차 vs ${d.opp}** 예상 ${d.wk.map(x => x.toFixed(1)).join('-')}${prev && prev.week === d.week ? ` (직전 ${prev.wk.map(x => x.toFixed(1)).join('-')})` : ''} · 실적 ${d.through || '—'}까지 · 경합: ${swing.join(', ') || '없음'}`);
  if (d.live && d.live.me) lines.push(`현재 합계 PTS ${d.live.me.PTS}-${d.live.opp.PTS} · REB ${d.live.me.REB}-${d.live.opp.REB} · AST ${d.live.me.AST}-${d.live.opp.AST} · BLK ${d.live.me.BLK}-${d.live.opp.BLK} · FG% ${(+d.live.me.FG).toFixed(3)}-${(+d.live.opp.FG).toFixed(3)} · TO ${d.live.me.TO}-${d.live.opp.TO} · 영입 ${d.live.adds}회 사용`);
  if (d.plan.length) lines.push(`모델 스트리밍 계획: ${d.plan.map(s => `${s.name}(${s.team}) ${s.from}~${s.to}`).join(' → ')}`);
  if (d.injured.length) lines.push(`부상: ${d.injured.join(', ')}`);
  lines.push('', '| 팀 | 성적 | 기대승률 | PO | 1위 | 우승 |', '|---|---|---|---|---|---|');
  d.season.forEach(s => lines.push(`| ${s.team} | ${s.rec} | ${pct(s.epct)} | ${pct(s.po)} | ${pct(s.p1)} | ${pct(s.champ)} |`));
  const md = lines.join('\n');
  fs.writeFileSync(path.join(__dirname, 'report.md'), md + '\n'); fs.writeFileSync(lastP, JSON.stringify(Object.assign(d, { at: new Date().toISOString() }), null, 1));
  console.log(md); if (errs.length) console.log('page errors:', errs);
})();
