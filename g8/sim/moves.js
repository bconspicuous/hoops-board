/* g8 roster-move planner (add/drop and IR) for Garak Twindragons -> g8/moves/plan.json + plan.md. PROPOSALS ONLY: nothing reaches
   ESPN until the manager approves a numbered item and Claude runs the g8-moves workflow in live mode.
   - add/drop: every free agent in the projection pool x every droppable player (not an ESPN undroppable, not in the top PROTECT by
     season value). Screen: this week's expected category wins (full weekly model, live totals, opponent as simulated). Then the
     best few are re-scored on the whole season (20k-season simulation): title / 1st / win% deltas. Proposed when week gain >= WK_MIN
     or title gain >= TITLE_MIN, and adds remain this week. Max C 4 and the weekly add limit are respected.
   - IR: an active player whose ESPN status is O and a free IR slot -> "move to IR" (frees a roster spot; paired with the best add).
     A player on IR who is no longer O -> flagged (ESPN may block adds until he is activated); activation needs a drop -> proposed.
   usage (repo root): node g8/sim/moves.js      env: CHROMIUM, PW, PROTECT (8), MAXP (3) */
const fs = require('fs'), path = require('path');
const ROOT = path.resolve(__dirname, '..', '..'), OUTD = path.join(ROOT, 'g8', 'moves');
let pw; try { pw = require(process.env.PW || '/opt/node-tools/node_modules/playwright'); } catch (e) { pw = require('playwright'); }
const PROTECT = +(process.env.PROTECT || 8), MAXP = +(process.env.MAXP || 3), WK_MIN = .05, TITLE_MIN = .01;
/* proposal basis (g8/config.json proposalBasis): "actual" = every player with 2026-27 games projected from his actual per-game line
   (weight 1, players without games keep the projection); the league simulation is recomputed on that basis before scoring */
const BASIS = (() => { try { return JSON.parse(fs.readFileSync(path.join(ROOT, 'g8', 'config.json'), 'utf8')).proposalBasis || 'model'; } catch (e) { return 'model'; } })();
(async () => {
  const csv = fs.readFileSync(path.join(ROOT, 'g8', 'data', 'players_2027.csv'), 'utf8').trim().split('\n'), h = csv[0].split(',');
  const rows = csv.slice(1).map(r => { const c = r.split(','), o = {}; h.forEach((k, i) => o[k] = c[i]); return o; });
  const ros = JSON.parse(fs.readFileSync(path.join(ROOT, 'g8', 'data', 'rosters.json'), 'utf8')), me = ros.teams.find(t => t.me);
  const sb = JSON.parse(fs.readFileSync(path.join(ROOT, 'g8', 'data', 'scoreboard.json'), 'utf8')), acqUsed = +((me.acqByPeriod || {})[String(sb.currentMatchupPeriod)] || 0);
  /* manager settings (g8/moves/config.json): dropCandidates = the only players that may be proposed for release (empty = model picks
     among droppable, unprotected players); unsigned players (ESPN team FA) are never proposed */
  const cfgP = path.join(ROOT, 'g8', 'moves', 'config.json'), cfg = fs.existsSync(cfgP) ? JSON.parse(fs.readFileSync(cfgP, 'utf8')) : {};
  const unsignedCsv = rows.filter(r => r.Team === 'FA').map(r => r.Player);
  const exe = process.env.CHROMIUM || (fs.existsSync('/opt/pw-browsers/chromium') ? '/opt/pw-browsers/chromium' : undefined);
  const b = await pw.chromium.launch(exe ? { executablePath: exe } : {}); const p = await b.newPage();
  await p.route(/^https?:\/\//, r => r.abort());
  await p.goto('file://' + path.join(ROOT, 'index.html'));
  await p.waitForFunction(() => typeof state !== 'undefined' && state.base && !state.busy, null, { timeout: 600000 });
  const R = await p.evaluate(([rows, acqUsed, P, cfg, unsignedCsv, BASIS]) => {
    if (BASIS === 'actual') { actWeight = () => 1; buildPlayers(); PLAYC = new Map(); state.base = computeAll(null); }
    const cw = currentWeek(), oT = state.base.TW[oppOf(ME, cw).opp + '|' + cw], roster = rosterFor(ME, cw, null), ir = (rosters()[ME].ir || []);
    const nrm = s => (s || '').normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[.'`]/g, '').replace(/\b(jr|sr|ii|iii|iv)\b/g, '').replace(/[^a-z0-9]+/g, ' ').trim();
    const espnRow = n => rows.find(r => nrm(r.Player) === nrm(n)) || {};
    const acqLeft = Math.max(0, acqFor(cw) - acqUsed), und = undroppable();
    const wk = names => { PLAYC = new Map(); const t = teamWeekL(ME, names, cw, { draws: 700, b2b: state.b2b, perGame: new Set(names.filter(n => !roster.includes(n))), stream: null }), o = pcat3(t, oT); return CATS.reduce((s, c) => s + o[c].w + o[c].t / 2, 0); };
    const season = (out, inn) => { const moves = { [ME]: { out: new Set(out), in: new Set(inn) } }; const S = computeAll({ team: ME, drop: new Set(out), add: new Set(inn), moves, partners: [], trade: false, from: cw, perGame: true }); const s = S.season[ME]; return { epct: s.epct, p1: s.p1, champ: s.champ }; };
    const base = { wk: wk(roster), ...(() => { const s = state.base.season[ME]; return { epct: s.epct, p1: s.p1, champ: s.champ }; })() };
    const byVal = roster.slice().sort((a, c) => state.PL[c].value - state.PL[a].value), protect = new Set(byVal.slice(0, P.PROTECT));
    const want = (cfg.dropCandidates || []).map(nrm), drops = want.length ? roster.filter(n => want.includes(nrm(n)) && !und.has(n)) : roster.filter(n => !und.has(n) && !protect.has(n));
    const unsigned = new Set(unsignedCsv.map(nrm));
    const held = new Set(); REF.teams.forEach(t => rosterFor(t, cw, null).forEach(n => held.add(n))); Object.values(rosters()).forEach(x => (x.ir || []).forEach(n => held.add(n)));
    const fa = Object.keys(state.PL).filter(n => !held.has(n) && !state.seasonOut.has(n) && state.PL[n].team && !state.PL[n].unsigned && !unsigned.has(nrm(n)) && (statusOf(n) !== 'O' || returnIdx(n, cw))).sort((a, c) => state.PL[c].sw - state.PL[a].sw).slice(0, 45);
    const cCount = names => names.filter(n => state.PL[n] && state.PL[n].pos === 'C').length;
    const flags = [], items = [];
    /* IR housekeeping */
    const irFree = 2 - ir.length, outActive = roster.filter(n => statusOf(n) === 'O');
    ir.forEach(n => { const st = statusOf(n); if (st !== 'O') flags.push({ kind: 'ir-ineligible', player: n, status: st || '정상', note: 'IR 선수가 O가 아님 — ESPN이 영입을 막을 수 있음(감독 판단: DTD는 영입 가능). 첫 사례에서 실제 동작을 기록' }); });
    /* add/drop screen (this week) */
    const scr = [];
    for (const d of drops) for (const a of fa) { const names = roster.filter(n => n !== d).concat([a]); if (cCount(names) > 4) continue; scr.push({ add: a, drop: d, wk: wk(names) - base.wk }); }
    /* IR move + add (no drop) when an active player is O and an IR slot is free */
    if (irFree > 0) for (const o of outActive) for (const a of fa.slice(0, 25)) { const names = roster.filter(n => n !== o).concat([a]); if (cCount(names) > 4) continue; scr.push({ add: a, drop: null, ir: o, wk: wk(names) - base.wk }); }
    scr.sort((x, y) => y.wk - x.wk);
    /* keep the shortlist compatible: distinct adds and drops, and at most one extra C beyond the current count (max C 4) */
    const isC = n => n && state.PL[n] && state.PL[n].pos === 'C', c0r = cCount(roster);
    const top = []; for (const s of scr) { if (top.length >= 6) break; if (top.some(t => t.add === s.add || (!want.length && s.drop && t.drop === s.drop))) continue;   // with a manager drop list, alternatives for the same drop are shown
      if (want.length && isC(s.add) && top.filter(t => isC(t.add)).length >= 2) continue;            // keep the alternatives varied
      const extraC = want.length ? 0 : top.filter(t => isC(t.add) && !isC(t.drop)).length; if (isC(s.add) && !isC(s.drop) && c0r + extraC + 1 > 4) continue; top.push(s); }
    top.forEach(s => { const z = season(s.drop ? [s.drop] : [s.ir], [s.add]); s.title = z.champ - base.champ; s.p1 = z.p1 - base.p1; s.epct = z.epct - base.epct; });
    top.sort((x, y) => (y.title + y.wk / 10) - (x.title + x.wk / 10));
    let left = acqLeft;
    for (const s of top) {
      if (items.length >= P.MAXP || left <= 0) break;
      if (!(s.wk >= P.WK_MIN || s.title >= P.TITLE_MIN) || s.title < -0.005) continue;
      const r = espnRow(s.add);
      items.push({ n: items.length + 1, kind: s.ir ? 'ir+add' : 'add/drop', add: s.add, addEspnId: r.espnId ? +r.espnId : null, addOwner: r.Owner || 'FA', drop: s.drop, ir: s.ir || null,
        weekGain: +s.wk.toFixed(3), titleGain: +s.title.toFixed(4), p1Gain: +s.p1.toFixed(4), epctGain: +s.epct.toFixed(4), addTeam: state.PL[s.add].team, addPos: state.PL[s.add].elig, dropValue: s.drop ? +state.PL[s.drop].value.toFixed(2) : null, status: 'proposed' });
      left--;
    }
    const c0 = cCount(roster); items.forEach(i => { i.conflicts = items.filter(j => j !== i && j.add && i.add && ((state.PL[i.add].pos === 'C' && state.PL[j.add].pos === 'C' && c0 - (i.drop && state.PL[i.drop].pos === 'C' ? 1 : 0) - (j.drop && state.PL[j.drop].pos === 'C' ? 1 : 0) + 2 > 4) || (i.drop && i.drop === j.drop))).map(j => j.n); });
    /* IR player no longer O: best drop to activate him (optional — manager rule: a DTD player on IR does not block adds) */
    ir.filter(n => statusOf(n) !== 'O' && state.PL[n]).forEach(n => { let best = null;
      for (const d of drops) { const names = roster.filter(x => x !== d).concat([n]); if (cCount(names) > 4) continue; const g = wk(names) - base.wk; if (!best || g > best.wk) best = { d, wk: g }; }
      if (!best) return; const z = season([best.d], [n]);
      items.push({ n: items.length + 1, kind: 'activate', ir: n, drop: best.d, weekGain: +best.wk.toFixed(3), titleGain: +(z.champ - base.champ).toFixed(4), p1Gain: +(z.p1 - base.p1).toFixed(4), epctGain: +(z.epct - base.epct).toFixed(4), dropValue: +state.PL[best.d].value.toFixed(2), status: 'proposed', note: `IR 복귀(상태 ${statusOf(n) || '정상'})` }); });
    if (irFree > 0) outActive.filter(o => !items.some(i => i.ir === o)).forEach(o => items.push({ n: items.length + 1, kind: 'ir', ir: o, status: 'proposed', note: 'O 상태 — IR로 이동하면 로스터 1자리가 빔(영입 없이)' }));
    return { week: cw + 1, opp: oppOf(ME, cw).opp, acqLeft, dropCandidates: drops, base: { wk: +base.wk.toFixed(3), champ: +base.champ.toFixed(4), p1: +base.p1.toFixed(4), epct: +base.epct.toFixed(4) }, protect: [...protect], droppable: drops, flags, items,
      screened: top.map(s => ({ add: s.add, drop: s.drop, ir: s.ir || null, wk: +s.wk.toFixed(3), title: +(s.title || 0).toFixed(4) })) };
  }, [rows, acqUsed, { PROTECT, MAXP, WK_MIN, TITLE_MIN }, cfg, unsignedCsv, BASIS]);
  await b.close();
  /* health line per proposal: ESPN fantasy status, injury report (estimated return), games and minutes so far */
  const inj = (JSON.parse(fs.readFileSync(path.join(ROOT, 'g8', 'data', 'injuries.json'), 'utf8')).injuries || []), rawSt = JSON.parse(fs.readFileSync(path.join(ROOT, 'g8', 'data', 'rosters.json'), 'utf8')).status || {};
  const nrmN = s => (s || '').normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[.'`]/g, '').replace(/\b(jr|sr|ii|iii|iv)\b/g, '').replace(/[^a-z0-9]+/g, ' ').trim();
  const health = n => { if (!n) return null; const st = Object.keys(rawSt).find(k => (rawSt[k] || []).some(x => nrmN(x) === nrmN(n))) || '', i = inj.find(x => nrmN(x.player) === nrmN(n)), r = rows.find(x => nrmN(x.Player) === nrmN(n)) || {};
    return { status: st || '정상', injury: i ? i.injury : null, returnDate: i ? i.returnDate : null, report: i ? i.short : null, g: r.G ? +r.G : null, min: r.MP ? +(+r.MP).toFixed(1) : null }; };
  R.items.forEach(i => { i.addHealth = health(i.add); i.irHealth = i.ir ? health(i.ir) : undefined; });
  fs.mkdirSync(OUTD, { recursive: true });
  const prevP = path.join(OUTD, 'plan.json'), prev = fs.existsSync(prevP) ? JSON.parse(fs.readFileSync(prevP, 'utf8')) : null;
  R.createdAt = new Date().toISOString(); R.id = R.createdAt.slice(0, 16).replace(/[-:]/g, '');
  R.rosterSig = [...me.players].sort().join('|') + '#' + [...me.ir].sort().join('|');
  // an item already proposed (same add/drop/ir) keeps its status and is not re-asked
  R.items.forEach(it => { const q = prev && prev.rosterSig === R.rosterSig && (prev.items || []).find(x => x.add === it.add && x.drop === it.drop && x.ir === it.ir); if (q) { it.status = q.status; it.firstProposedAt = q.firstProposedAt || prev.createdAt; } else it.firstProposedAt = R.createdAt; });
  R.newItems = R.items.filter(i => i.firstProposedAt === R.createdAt).map(i => i.n);
  fs.writeFileSync(prevP, JSON.stringify(R, null, 1));
  const pc = x => (x >= 0 ? '+' : '') + (x * 100).toFixed(1) + '%p';
  const L = [`# 로스터 이동 제안 · ${R.week}주차 vs ${R.opp} · 이번 주 남은 영입 ${R.acqLeft}회 · 기준: ${BASIS === 'actual' ? '현재 스탯(2026-27 실제 100%)' : '프로젝션'}`];
  R.flags.forEach(f => L.push(`⚠ ${f.player}: IR인데 상태 ${f.status} — ${f.note}`));
  if (!R.items.length) L.push('제안 없음 (기준: 이번 주 +0.05승 또는 우승 +1%p 이상)');
  R.items.forEach(i => L.push(i.kind === 'ir' ? `${i.n}. IR 이동: ${i.ir} (${i.note})` : i.kind === 'activate' ? `${i.n}. IR 복귀 ${i.ir} / 방출 ${i.drop} — 이번 주 ${i.weekGain >= 0 ? '+' : ''}${i.weekGain.toFixed(2)}승 · 우승 ${pc(i.titleGain)} [${i.status}]` :
    `${i.n}. ${i.ir ? `IR 이동 ${i.ir} + ` : ''}영입 ${i.add}(${i.addTeam} ${i.addPos}${i.addOwner === 'FA' ? '' : ' · ' + i.addOwner})${i.drop ? ` / 방출 ${i.drop}` : ''} — 이번 주 ${i.weekGain >= 0 ? '+' : ''}${i.weekGain.toFixed(2)}승 · 우승 ${pc(i.titleGain)} · 1위 ${pc(i.p1Gain)}${i.conflicts && i.conflicts.length ? ` · ${i.conflicts.join('·')}번과 동시 불가(택1: 같은 방출 대상 또는 C 한도)` : ''} [${i.status}]`));
  R.items.filter(i => i.addHealth).forEach(i => { const h = i.addHealth; L.push(`   ${i.n}번 ${i.add} 상태: ${h.status}${h.injury ? ` (${h.injury}${h.returnDate ? ', 복귀 예상 ' + h.returnDate : ''})` : ''} · 올 시즌 ${h.g ?? '—'}경기 ${h.min ?? '—'}분${h.report ? ' · ' + h.report : ''}`); });
  L.push('', (cfg.dropCandidates || []).length ? `방출 대상(감독 지정): ${R.dropCandidates.join(', ') || '없음 — 로스터에 없음'}` : `보호(방출 후보 제외): ${R.protect.join(', ')}`);
  fs.writeFileSync(path.join(OUTD, 'plan.md'), L.join('\n') + '\n');
  console.log(L.join('\n'));
})();
