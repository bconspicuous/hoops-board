// In-page weekly engine (port of sim2.js weekWeights/lineup): daily top-10 lineup on ESPN slots, 13-active cap for IR returns,
// generic weekly streaming (drop the k lowest-value players, add k virtual streamers on the NBA teams that fill the most open slots).
// Shared by the dashboard (inlined by combine.py) and node checks (require('./simeng.js')).
(function (root) {
  const SLN = ['PG', 'SG', 'SF', 'PF', 'C', 'G', 'F', 'UTIL', 'UTIL2', 'UTIL3'];
  const okS = (el, s) => s.startsWith('UTIL') ? true : s === 'G' ? (el.includes('PG') || el.includes('SG')) : s === 'F' ? (el.includes('SF') || el.includes('PF')) : el.includes(s);
  function make(SD) {
    const NB = SD.nba, ST = SD.stream, NK = SD.weeks.length;
    const has = SD.days.map(wk => wk.map(day => new Set(day)));
    const AV = new Map();   // decoded availability per player
    const avOf = p => { let a = AV.get(p.n); if (!a) { a = p.av.map(s => [...s].map(c => (c.charCodeAt(0) - 65) / 20)); AV.set(p.n, a); } return a; };
    const unit = (p, full) => { const a = avOf(p); return { key: p.n, v: p.v, el: (p.pos || 'SF').split(','), f: p.f, dd: p.dd, tw: p.tw, a: full ? a.map(w => w.map(x => x > 0 ? 1 : 0)) : a, cap: p.cap }; };
    const SU = NB.map((t, i) => ({ key: 'S:' + t, v: ST.v, el: ST.el || ['SG', 'SF'], f: ST.f, dd: ST.dd, tw: ST.tw[t] != null ? ST.tw[t] : 0.5, virtual: true,
      a: SD.days.map((wk, k) => wk.map((day, d) => has[k][d].has(i) ? ST.a : 0)), cap: '1'.repeat(NK) }));
    function lineup(us) {
      const order = us.slice().sort((a, b) => b.v - a.v), slotOf = new Array(10).fill(null), start = [], bench = [];
      const tryP = (u, seen) => { for (let s = 0; s < 10; s++) { if (seen[s] || !okS(u.el, SLN[s])) continue; seen[s] = 1; if (!slotOf[s] || tryP(slotOf[s], seen)) { slotOf[s] = u; return true; } } return false; };
      for (const u of order) { const snap = slotOf.slice(); if (start.length < 10 && tryP(u, new Array(10).fill(0))) start.push(u); else { for (let s = 0; s < 10; s++) slotOf[s] = snap[s]; bench.push(u); } }
      return start;
    }
    // expected counted games per unit for one roster-week; ns = streamers this week
    function weekW(units, k, ns) {
      const from = SD.fromIdx[k] || 0; let ids = units.slice();
      const act = ids.filter(u => u.cap[k] === '1');
      if (act.length > 13) { const lo = new Set(act.slice().sort((x, y) => x.v - y.v).slice(0, act.length - 13)); ids = ids.filter(u => !lo.has(u)); }
      let core = ids.filter(u => u.a[k].some(x => x > 0)); const str = [];
      if (ns > 0 && core.length > ns) {
        core = core.slice().sort((a, b) => b.v - a.v).slice(0, core.length - ns);
        for (let s = 0; s < ns; s++) {
          const busy = [0, 1, 2, 3, 4, 5, 6].map(d => core.concat(str).filter(u => u.a[k][d] > 0).length);
          let best = null; SU.forEach((u, i) => { if (str.includes(u)) return; let free = 0, g = 0; for (let d = 0; d < 7; d++) if (has[k][d] && has[k][d].has(i)) { g++; if (busy[d] < 10) free++; } const sc = free * 10 + g; if (!best || sc > best[1]) best = [u, sc]; });
          if (best) str.push(best[0]);
        }
      }
      const all = core.concat(str), wt = new Map(all.map(u => [u, 0]));
      for (let d = from; d < 7; d++) {
        let playing = all.filter(u => u.a[k][d] > 0);
        if (playing.length > 13 + str.length) playing = playing.sort((a, b) => b.v - a.v).slice(0, 13 + str.length);
        const st = lineup(playing), S = new Set(st); let slack = 0;
        st.forEach(u => { const a = u.a[k][d]; wt.set(u, wt.get(u) + a); slack += 1 - a; });
        playing.filter(u => !S.has(u)).sort((a, b) => b.v - a.v).forEach(u => { if (slack <= 1e-9) return; const a = u.a[k][d], x = a * Math.min(1, slack); wt.set(u, wt.get(u) + x); slack -= x; });
      }
      return wt;
    }
    function row(units, k, ns) {
      const r = new Array(14).fill(0);
      for (const [u, g] of weekW(units, k, ns)) { if (!g) continue; for (let x = 0; x < 11; x++) r[x] += u.f[x] * g; r[11] += u.dd * g; r[12] += u.tw * g; r[13] += g; }
      return r;
    }
    return { unit, weekW, row, lineup, SU };
  }
  root.SimEng = { make };
})(typeof module !== 'undefined' ? module.exports : window);
