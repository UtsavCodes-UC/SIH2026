// Regenerates the screenshots used by the in-app Guide (frontend/public/guide/*.webp).
//
//   1. build the UI and start the app on some port, e.g.   cd backend && python -m uvicorn app.main:app --port 8010
//   2. run                                                  cd frontend && npm run guide:screenshots
//
// It drives a headless Chrome (a throwaway profile; nothing of yours is touched) through the same steps a user would take:
// a plan on the synthetic map, the benchmark, MG Road with the recorded traffic, a shortest path and a closed road.
// Needs Node 22+ (built-in WebSocket) and Google Chrome. Environment variables:
//   BASE         where the app is running       (default http://127.0.0.1:8010)
//   CHROME_PATH  the Chrome executable          (default: the usual Windows / macOS / Linux locations)
// The steps look buttons up by their labels, so if a label in the UI changes, update the matching text here.
import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const BASE = process.env.BASE || "http://127.0.0.1:8010";
const OUT = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "public", "guide");
const CHROME =
  process.env.CHROME_PATH ||
  ["C:/Program Files/Google/Chrome/Application/chrome.exe", "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/usr/bin/google-chrome", "/usr/bin/chromium"].find((p) => fs.existsSync(p));
if (!CHROME) throw new Error("Chrome not found: set CHROME_PATH");
const PORT = 9333;
fs.mkdirSync(OUT, { recursive: true });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const profile = path.join(os.tmpdir(), "guide-cdp-profile-" + Date.now());
const chrome = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`, "--window-size=1440,900", "--hide-scrollbars", "--no-first-run", "--no-default-browser-check", "about:blank"], { stdio: "ignore" });

let ws, nextId = 1;
const pending = new Map();
async function connect() {
  for (let i = 0; i < 60; i++) {
    try {
      const targets = await (await fetch(`http://127.0.0.1:${PORT}/json`)).json();
      const page = targets.find((t) => t.type === "page");
      if (page) {
        ws = new WebSocket(page.webSocketDebuggerUrl);
        await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
        ws.onmessage = (m) => {
          const msg = JSON.parse(m.data);
          if (msg.id && pending.has(msg.id)) { const { res, rej } = pending.get(msg.id); pending.delete(msg.id); msg.error ? rej(new Error(JSON.stringify(msg.error))) : res(msg.result); }
        };
        return;
      }
    } catch { /* not up yet */ }
    await sleep(250);
  }
  throw new Error("could not reach Chrome");
}
const send = (method, params = {}) => new Promise((res, rej) => { const id = nextId++; pending.set(id, { res, rej }); ws.send(JSON.stringify({ id, method, params })); });
async function ev(expression) {
  const r = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw new Error("page error: " + (r.exceptionDetails.exception?.description || r.exceptionDetails.text));
  return r.result.value;
}
async function until(expression, timeout = 20000, label = expression) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeout) { if (await ev(`(() => { try { return !!(${expression}); } catch { return false; } })()`)) return; await sleep(200); }
  throw new Error("timed out waiting for: " + label.slice(0, 120));
}
async function click(x, y) {
  await send("Input.dispatchMouseEvent", { type: "mouseMoved", x, y });
  await send("Input.dispatchMouseEvent", { type: "mousePressed", x, y, button: "left", clickCount: 1 });
  await send("Input.dispatchMouseEvent", { type: "mouseReleased", x, y, button: "left", clickCount: 1 });
}
async function shot(name, rect, pad = 6) {
  const wide = rect.w > 800; // big captures are stored at about 1x, small crops at 2x so text stays sharp
  const clip = { x: Math.max(0, rect.x - pad), y: Math.max(0, rect.y - pad), width: Math.min(1440, rect.w + 2 * pad), height: Math.min(900, rect.h + 2 * pad), scale: wide ? 0.55 : 1 };
  const { data } = await send("Page.captureScreenshot", { format: "webp", quality: 82, clip });
  fs.writeFileSync(path.join(OUT, name + ".webp"), Buffer.from(data, "base64"));
  console.log("saved", name, Math.round(clip.width), "x", Math.round(clip.height), Math.round(data.length * 0.75 / 1024) + " KB");
}
const R = (expr) => ev(`(() => { const el = ${expr}; if (!el) return null; const r = el.getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height }; })()`);

const HELPERS = `
window.__g = {
  wait: (ms) => new Promise((r) => setTimeout(r, ms)),
  btn: (t) => [...document.querySelectorAll('button')].find((b) => b.innerText.trim() === t),
  fibers: () => { const el = document.querySelector('.leaflet-container'); const k = Object.keys(el).find((x) => x.startsWith('__reactFiber')); return [el[k], el[k].alternate].filter(Boolean); },
  prop: (name) => { for (const root of window.__g.fibers()) { let f = root; while (f) { const p = f.memoizedProps; if (p && p[name] !== undefined && p[name] !== null && typeof p[name] === 'object') return p[name]; f = f.return; } } return null; },
  map: () => { for (const root of window.__g.fibers()) { const st = [root]; let n = 0; while (st.length && n++ < 8000) { const f = st.pop(); const v = f.memoizedProps && f.memoizedProps.value; if (v && v.map && v.map.latLngToContainerPoint) return v.map; if (f.sibling) st.push(f.sibling); if (f.child) st.push(f.child); } } return null; },
  setSelect: (sel, value) => { Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(sel, value); sel.dispatchEvent(new Event('change', { bubbles: true })); },
  hl: (els) => { window.__g.unhl(); [].concat(els).filter(Boolean).forEach((e) => e.classList.add('g-hl')); },
  unhl: () => document.querySelectorAll('.g-hl').forEach((e) => e.classList.remove('g-hl')),
  focus: (el, gap = 14) => { const sb = document.querySelector('.sidebar'); const hb = document.querySelector('.sidebar-sticky-header').getBoundingClientRect().bottom; sb.scrollTop += el.getBoundingClientRect().top - hb - gap; },
  nodePixel: (id) => { const g = window.__g.prop('graph'); const n = g.nodes.find((x) => x[0] === id); const p = window.__g.map().latLngToContainerPoint([n[1], n[2]]); const r = document.querySelector('.leaflet-container').getBoundingClientRect(); return { x: r.left + p.x, y: r.top + p.y }; },
};
const st = document.createElement('style');
st.textContent = '*{transition:none !important;animation:none !important} .g-hl{outline:3px solid #d1495b !important;outline-offset:2px !important;border-radius:6px !important} .g-num{position:fixed;z-index:99999;width:28px;height:28px;border-radius:50%;background:#d1495b;color:#fff;font:700 15px/28px system-ui,sans-serif;text-align:center;border:2px solid #fff;box-shadow:0 1px 5px rgba(0,0,0,.5)}';
document.head.appendChild(st); true;`;

async function main() {
  await connect();
  await send("Page.enable");
  await send("Emulation.setDeviceMetricsOverride", { width: 1440, height: 900, deviceScaleFactor: 2, mobile: false });
  await send("Page.navigate", { url: BASE });
  await until(`document.querySelector('.sidebar') && [...document.querySelectorAll('button')].some((b) => b.innerText.trim() === 'Optimize routes' && !b.disabled)`, 30000, "app ready");
  await ev(HELPERS);
  await sleep(2500); // map tiles

  // ---- 1. a plan on the synthetic map
  await ev(`window.__g.btn('Optimize routes').click(); true`);
  await until(`document.querySelector('.kpi')`, 30000, "first plan");
  await sleep(2500);

  // overview with numbered callouts
  const side = await R(`document.querySelector('.sidebar')`), tb = await R(`document.querySelector('.map-toolbar')`), bottom = await R(`document.querySelector('section.bottom')`), mapArea = await R(`document.querySelector('.map-area')`);
  const h1 = await R(`document.querySelector('#section-road-network h2')`);
  const badges = [[side.x + side.w - 44, h1.y - 6, "1"], [tb.x + tb.w + 10, tb.y + 4, "2"], [mapArea.x + mapArea.w / 2 + 120, mapArea.y + 150, "3"], [bottom.x + 760, bottom.y + 7, "4"]];
  await ev(`(${JSON.stringify(badges)}).forEach(([x, y, n]) => { const d = document.createElement('div'); d.className = 'g-num'; d.style.left = x + 'px'; d.style.top = y + 'px'; d.textContent = n; document.body.appendChild(d); }); true`);
  await shot("overview", { x: 0, y: 0, w: 1440, h: 900 }, 0);
  await ev(`document.querySelectorAll('.g-num').forEach((e) => e.remove()); true`);

  // map toolbar
  await ev(`window.__g.hl([...document.querySelectorAll('.map-toolbar .chip')].find((c) => c.innerText === 'block road')); true`);
  await shot("toolbar", await R(`document.querySelector('.map-toolbar')`), 10);
  await ev(`window.__g.unhl(); true`);

  // what to minimize
  await ev(`window.__g.focus([...document.querySelectorAll('#section-solver .subhead')].find((h) => h.innerText.includes('What to minimize'))); true`); await sleep(300);
  const sub = await R(`[...document.querySelectorAll('#section-solver .subhead')].find((h) => h.innerText.includes('What to minimize'))`);
  const hint = await R(`[...document.querySelectorAll('#section-solver .hint')].find((h) => h.innerText.includes('Time is minutes driven'))`);
  const solver = await R(`document.querySelector('#section-solver')`);
  await ev(`window.__g.hl([...document.querySelectorAll('#section-solver .presets button')].find((b) => b.innerText === 'Avoid jams')); true`);
  await shot("weights", { x: solver.x, y: sub.y, w: solver.w, h: hint.y + hint.h - sub.y }, 8);
  await ev(`window.__g.unhl(); true`);

  // route search option
  await ev(`(() => { const sel = [...document.querySelectorAll('#section-solver select')].find((s) => [...s.options].some((o) => o.text.includes('QPSO'))); window.__g.setSelect(sel, 'route_search'); window.__g.hl([sel]); return true; })()`); await sleep(400);
  await ev(`window.__g.focus([...document.querySelectorAll('#section-solver label')].find((l) => l.innerText.trim().startsWith('Algorithm'))); true`); await sleep(300);
  const algLabel = await R(`[...document.querySelectorAll('#section-solver label')].find((l) => l.innerText.trim().startsWith('Algorithm'))`);
  const opt = await R(`window.__g.btn('Optimize routes')`); // route search hides the swarm settings, so the Optimize button is the lower edge
  await shot("route-search", { x: solver.x, y: algLabel.y, w: solver.w, h: opt.y - algLabel.y - 6 }, 8);
  await ev(`(() => { window.__g.unhl(); const sel = [...document.querySelectorAll('#section-solver select')].find((s) => [...s.options].some((o) => o.text.includes('QPSO'))); window.__g.setSelect(sel, 'qpso'); return true; })()`);

  // time windows
  await ev(`window.__g.focus(document.querySelector('#section-delivery-problem')); true`); await sleep(300);
  await ev(`document.querySelector('#section-delivery-problem label.check input').click(); true`); await sleep(500);
  await ev(`window.__g.hl([document.querySelector('#section-delivery-problem label.check')]); true`);
  await shot("time-windows", await R(`document.querySelector('#section-delivery-problem')`), 8);
  await ev(`window.__g.unhl(); document.querySelector('#section-delivery-problem label.check input').click(); true`); await sleep(300);

  // results panel + benchmark tab
  await ev(`window.__g.btn('Optimize routes').click(); true`);
  await until(`document.querySelector('.kpi') && !document.querySelector('.banner.busy')`, 30000, "second plan"); await sleep(600);
  await shot("results", await R(`document.querySelector('section.bottom')`), 0);
  await ev(`window.__g.btn('Benchmark').click(); true`);
  await until(`document.querySelector('section.bottom .table') && !document.querySelector('.banner.busy')`, 60000, "benchmark"); await sleep(600);
  await shot("benchmark", await R(`document.querySelector('section.bottom')`), 0);
  await ev(`[...document.querySelectorAll('.bottom .tab')].find((t) => t.innerText === 'Route plan').click(); true`);

  // ---- 2. a real city with recorded traffic
  await ev(`[...document.querySelectorAll('#section-road-network [role=tab]')].find((t) => t.innerText === 'Real city').click(); true`); await sleep(400);
  await ev(`(() => { const sel = document.querySelector('#section-road-network select'); const o = [...sel.options].find((x) => x.text.includes('MG Road')); window.__g.setSelect(sel, o.value); return true; })()`); await sleep(300);
  await ev(`window.__g.btn('Load road network').click(); true`);
  await until(`document.querySelector('#section-road-network .graph-info')?.innerText.includes('MG Road')`, 60000, "city loaded"); await sleep(2500);
  await ev(`window.__g.btn('Optimize routes').click(); true`);
  await until(`document.querySelector('.kpi') && !document.querySelector('.banner.busy')`, 30000, "city plan"); await sleep(800);

  await ev(`window.__g.focus(document.querySelector('#section-traffic')); true`); await sleep(300);
  await ev(`window.__g.btn('Replay').click(); true`);
  await until(`document.querySelector('.map-badge .traffic-recorded') && !document.querySelector('.banner.busy')`, 40000, "recorded traffic"); await sleep(2000);
  const tsec = await R(`document.querySelector('#section-traffic')`), replay = await R(`window.__g.btn('Replay')`);
  await ev(`window.__g.hl([window.__g.btn('Replay')]); true`);
  await shot("traffic", { x: tsec.x, y: tsec.y, w: tsec.w, h: replay.y + replay.h - tsec.y }, 8);
  await ev(`window.__g.unhl(); true`);

  // ---- 3. shortest path on the real map: pick two intersections far apart with real clicks
  const pick = await ev(`(() => { const g = window.__g.prop('graph'); const rect = document.querySelector('.leaflet-container').getBoundingClientRect(); const tb = document.querySelector('.map-toolbar').getBoundingClientRect(); const lg = document.querySelector('.map-legend').getBoundingClientRect();
    const pts = g.nodes.map((n) => ({ id: n[0], ...window.__g.nodePixel(n[0]) })).filter((p) => p.x > rect.left + 60 && p.x < rect.right - 60 && p.y > tb.bottom + 25 && p.y < lg.top - 25);
    const a = pts.reduce((m, p) => (p.x - p.y < m.x - m.y ? p : m), pts[0]); const b = pts.reduce((m, p) => (p.x - p.y > m.x - m.y ? p : m), pts[0]); return { a, b }; })()`);
  const chip = (t) => ev(`(() => { const c = [...document.querySelectorAll('.map-toolbar .chip')].find((x) => x.innerText === '${t}'); const r = c.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; })()`);
  let c = await chip("set A"); await click(c.x, c.y); await sleep(200); await click(pick.a.x, pick.a.y); await sleep(300);
  c = await chip("set B"); await click(c.x, c.y); await sleep(200); await click(pick.b.x, pick.b.y); await sleep(400);
  await ev(`window.__g.btn('Compare all four').click(); true`);
  await until(`document.querySelector('section.bottom .table') && [...document.querySelectorAll('.bottom .tab-active')].some((t) => t.innerText === 'Shortest path') && !document.querySelector('.banner.busy')`, 60000, "path result"); await sleep(2500);
  c = await chip("set B"); await click(c.x, c.y); await sleep(200); // turn the picking mode off again: no node dots
  await send("Input.dispatchMouseEvent", { type: "mouseMoved", x: 760, y: 820 }); await sleep(800); // and no hover tooltip
  await shot("shortest-path-map", await R(`document.querySelector('.map-area')`), 0);
  await ev(`document.querySelector('.bottom-scroll').scrollTop = 150; true`); await sleep(400);
  await shot("shortest-path-table", await R(`document.querySelector('section.bottom')`), 0);
  await ev(`document.querySelector('.bottom-scroll').scrollTop = 0; true`);
  await ev(`[...document.querySelectorAll('.bottom .tab')].find((t) => t.innerText === 'Route plan').click(); true`); await sleep(300);

  // ---- 4. close a road that the plan uses, and show the what-if banner
  c = await chip("block road"); await click(c.x, c.y); await sleep(300);
  const cands = await ev(`(() => { const g = window.__g.prop('graph'), res = window.__g.prop('result'); const at = new Map(g.nodes.map((n) => [n[0], [n[1], n[2]]]));
    const key = (la, lo) => la.toFixed(6) + ',' + lo.toFixed(6); const byPos = new Map(g.nodes.map((n) => [key(n[1], n[2]), n[0]])); const roads = new Set(g.edges.map(([u, v]) => Math.min(u, v) + '-' + Math.max(u, v))); const use = new Map();
    for (const r of res.routes) { const seq = r.path.map(([la, lo]) => byPos.get(key(la, lo))).filter((x) => x !== undefined); for (let i = 0; i + 1 < seq.length; i++) { const k = Math.min(seq[i], seq[i + 1]) + '-' + Math.max(seq[i], seq[i + 1]); if (seq[i] !== seq[i + 1] && roads.has(k)) use.set(k, (use.get(k) || 0) + 1); } }
    const rect = document.querySelector('.leaflet-container').getBoundingClientRect(), tb = document.querySelector('.map-toolbar').getBoundingClientRect(), lg = document.querySelector('.map-legend').getBoundingClientRect();
    return [...use.entries()].sort((a, b) => b[1] - a[1]).map(([k]) => k.split('-').map(Number)).map(([u, v]) => { const p = window.__g.nodePixel(u), q = window.__g.nodePixel(v); return { u, v, x: (p.x + q.x) / 2, y: (p.y + q.y) / 2, len: Math.hypot(p.x - q.x, p.y - q.y) }; })
      .filter((r) => r.x > rect.left + 40 && r.x < rect.right - 40 && r.y > tb.bottom + 20 && r.y < lg.top - 20 && r.len > 40).slice(0, 8); })()`);
  console.log("closure candidates:", cands.length);
  let done = false;
  for (const cnd of cands) {
    await click(cnd.x, cnd.y);
    try { await until(`document.querySelector('.banner.whatif') && !document.querySelector('.banner.busy')`, 20000, "what-if banner"); } catch { console.log("no banner for", cnd.u, cnd.v); }
    await sleep(2200);
    const text = await ev(`document.querySelector('.banner.whatif')?.innerText || ''`);
    const err = await ev(`document.querySelector('.banner.error')?.innerText || ''`);
    console.log("closed", cnd.u, "-", cnd.v, "->", (text || err).replace(/\n/g, " | ").slice(0, 160));
    if (text && !err && /\+\d/.test(text)) { done = true; break; }
    await click(cnd.x, cnd.y); await sleep(2500); // reopen and try the next one
  }
  if (!done) console.log("WARNING: no closure produced a positive change; using the last state");
  await send("Input.dispatchMouseEvent", { type: "mouseMoved", x: 760, y: 820 }); await sleep(600);
  await shot("closures", await R(`document.querySelector('.map-area')`), 0);

  await send("Browser.close").catch(() => {});
}

try { await main(); } catch (e) { console.error("FAILED:", e.message); process.exitCode = 1; } finally { try { chrome.kill(); } catch { /* ignore */ } }
