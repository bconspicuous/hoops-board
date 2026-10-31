// Kawhi return-date sensitivity with the recommended acquisition plan held fixed
const fs = require('fs'); const S = require('./sim2.js');
const { P, BY, ME, POST, NW, START, season } = S;
const PL = JSON.parse(fs.readFileSync(process.env.PLANF || 'stream_plan_core3J.json')), ret = S.RET['Kawhi Leonard'];
const mc = BY['Jared McCain'].id, plan = {};
for (const x of PL.log) { if (x.now) { let r = POST[ME].slice(); for (const m of x.moves) r = r.map(id => id === BY[m.drop].id ? BY[m.add].id : id); plan[S.CURW] = r; continue; } const w = x.week - 1; let r = x.roster.map(n => BY[n].id).filter(id => id !== mc); if (START[w] < ret && POST[ME].includes(mc)) r.push(mc); plan[w] = r; }
const own = new Set(POST.flat()); Object.values(plan).flat().forEach(id => { if (!own.has(id)) P[id].gp = Math.max(P[id].gp, 79.5); });   // same rule as the planner: added players play every game
S.setPlan(plan); const s = season(POST, POST, +(process.env.N || 8000), 20261027)[ME];
console.log(JSON.stringify({ ret, W: s.W, L: s.L, T: s.T, p4: s.p4, p1: s.p1, champ: s.champ }));
