/* Runs in a signed-in https://voicenotes.com/app tab. Replace BRIDGE_URL with the contents of WORK/url.
 * Makes one API call at a time, pauses on 429 and settles on the pace the API accepts. Sends listing
 * pages and audio links to browser_bridge.py. The login token never leaves the tab. */
(async () => {
  const B = 'BRIDGE_URL', A = 'https://api.voicenotes.com/api';
  const H = { Authorization: 'Bearer ' + JSON.parse(localStorage.auth_token), Accept: 'application/json' };
  const S = (window.__bridge = { calls: 0, limited: 0, gap: 600, phase: 'start', done: false, err: null });
  const zz = (ms) => new Promise((r) => setTimeout(r, ms));
  const post = async (p, o) => { for (let n = 0; n < 8; n++) { try { if ((await fetch(B + p, { method: 'POST', body: JSON.stringify(o) })).ok) return; } catch {} await zz(1000 * 2 ** n); } throw new Error('bridge unreachable'); };
  const scrub = (o) => Array.isArray(o) ? o.map(scrub) : o && typeof o === 'object' ? Object.fromEntries(Object.entries(o).filter(([k]) => k !== 'firebase_token').map(([k, v]) => [k, scrub(v)])) : o;
  let good = 0;
  const get = async (path) => {
    for (let n = 0; n < 12; n++) {
      await zz(S.gap); S.calls++;
      let r; try { r = await fetch(A + path, { headers: H }); } catch { await zz(2000 * 2 ** Math.min(n, 5)); continue; }
      if (r.status === 429) { S.limited++; good = 0; S.gap = Math.min(5000, Math.round(S.gap * 1.25)); await zz(20000); continue; }
      if (r.status >= 500) { await zz(2000 * 2 ** Math.min(n, 5)); continue; }
      if (r.status === 401) throw new Error('signed out');
      if (++good % 100 === 0) S.gap = Math.max(250, Math.round(S.gap * 0.95));
      return { status: r.status, json: r.status === 200 ? await r.json().catch(() => null) : null };
    }
    return { status: 0, json: null };
  };
  const beat = () => post('/beat', S);
  try {
    const todo = await (await fetch(B + '/todo')).json();
    const have = new Set(todo.pages);
    S.phase = 'links'; let out = [], last = Date.now();
    for (const rid of todo.ids) {
      const x = await get(`/recordings/${rid}/signed-url`);
      out.push({ rid, status: x.status, url: x.json?.url || null });
      if (out.length >= 20) { await post('/links', out); out = []; }
      if (Date.now() - last > 15000) { last = Date.now(); await beat(); }
    }
    if (out.length) await post('/links', out);
    S.phase = 'listing';
    for (let p = 1; ; p++) {
      if (have.has(p) && have.has(p + 1)) continue;
      const x = await get('/recordings?page=' + p);
      if (x.status !== 200 || !x.json) throw new Error(`listing page ${p}: ${x.status}`);
      const more = !!(x.json.links || {}).next;
      await post('/page', { page: p, more, data: scrub(x.json.data) });
      if (p % 10 === 0) await beat();
      if (!more) break;
    }
    S.phase = 'done';
  } catch (e) { S.err = String(e); }
  S.done = true; await beat();
})(); 'started';
