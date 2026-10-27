/**
 * HypGraph — the research record, every profile, live. Framework-free, read-only, offline-first; no build step.
 *
 *   <link rel="stylesheet" href="hypgraph.css">
 *   <script src="vendor/cytoscape.min.js"></script>  (+ layout-base, cose-base, cytoscape-fcose for the fcose layout)
 *   <script src="hypgraph.js"></script>
 *   <div id="app" style="height:100vh"></div>
 *   <script>
 *     HypGraph.mount(document.getElementById('app'), { source: HypGraph.HttpSource('/api/graph'), hash: true });
 *     // or, with no server at all:  { source: HypGraph.BundleSource(bundleJson) }
 *   </script>
 *
 * Views (docs/ui-plan.md): Overview · Live · Pipeline · Graph · Evidence · Work orders · Audit log · Report, each in
 * the investigation's profile's own words (Requirement, Thesis, Solution…). Nothing here writes. Standing, stages and
 * gates come from the engine; a BundleSource shows what the bundle was exported with and re-verifies its hash chain
 * in the browser. An HttpSource follows the record live (GET /stream), falling back to polling on older hosts, and
 * hides what a host's API doesn't serve.
 *
 * Options: source (required) · theme ('light' | 'dark') · hash (keep the view in location.hash) · title · live ·
 * play (open on the Live view and replay the run from its first event; also `#view=live&play=1`, and skipped when
 * the visitor asks for reduced motion) · onTheme(t) · operatorUrl · fileUrl(path). Keys: 1–8 views · ⌘K / Ctrl+K or / search · Esc close · t theme.
 * `HypAtlas` is kept as an alias of `HypGraph` for one release.
 */
'use strict';
(function (global) {
  const VERSION = '0.6.0';
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const RISKY = ['requires', 'derived_from', 'based_on'];
  const cap = (t) => (t ? t[0].toUpperCase() + t.slice(1) : '');

  // ── hashing (WebCrypto, with a small fallback for insecure contexts) ─────
  async function sha256(text) {
    const bytes = new TextEncoder().encode(text);
    if (global.crypto && global.crypto.subtle) {
      const d = await global.crypto.subtle.digest('SHA-256', bytes);
      return [...new Uint8Array(d)].map((b) => b.toString(16).padStart(2, '0')).join('');
    }
    return sha256Fallback(bytes);
  }
  function sha256Fallback(bytes) {
    const K = new Uint32Array([0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
      0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786,
      0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
      0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb,
      0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
      0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f,
      0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2]);
    const H = new Uint32Array([0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19]);
    const l = bytes.length, n = ((l + 9 + 63) >> 6) << 6, m = new Uint8Array(n);
    m.set(bytes); m[l] = 0x80;
    const dv = new DataView(m.buffer); dv.setUint32(n - 4, l * 8); dv.setUint32(n - 8, Math.floor(l / 0x20000000));
    const w = new Uint32Array(64), r = (x, k) => (x >>> k) | (x << (32 - k));
    for (let o = 0; o < n; o += 64) {
      for (let i = 0; i < 16; i++) w[i] = dv.getUint32(o + 4 * i);
      for (let i = 16; i < 64; i++) {
        const s0 = r(w[i - 15], 7) ^ r(w[i - 15], 18) ^ (w[i - 15] >>> 3), s1 = r(w[i - 2], 17) ^ r(w[i - 2], 19) ^ (w[i - 2] >>> 10);
        w[i] = (w[i - 16] + s0 + w[i - 7] + s1) >>> 0;
      }
      let [a, b, c, d, e, f, g, h] = H;
      for (let i = 0; i < 64; i++) {
        const t1 = (h + (r(e, 6) ^ r(e, 11) ^ r(e, 25)) + ((e & f) ^ (~e & g)) + K[i] + w[i]) >>> 0;
        const t2 = ((r(a, 2) ^ r(a, 13) ^ r(a, 22)) + ((a & b) ^ (a & c) ^ (b & c))) >>> 0;
        h = g; g = f; f = e; e = (d + t1) >>> 0; d = c; c = b; b = a; a = (t1 + t2) >>> 0;
      }
      H[0] += a; H[1] += b; H[2] += c; H[3] += d; H[4] += e; H[5] += f; H[6] += g; H[7] += h;
    }
    return [...H].map((x) => x.toString(16).padStart(8, '0')).join('');
  }

  /** Verify a hypgraph/1-bundle string-for-string — the same checks as hypgraph.verify_bundle in Python. */
  async function verifyBundle(b) {
    if (!b || b.format !== 'hypgraph/1-bundle') return { ok: false, problem: 'not a hypgraph/1-bundle' };
    let prev = '0'.repeat(64), checked = 0, red = 0;
    const creates = new Map(), revs = new Map(), reviews = new Map(), links = new Map(), withdraws = new Set(), retracts = new Set();
    for (const ev of [...(b.events || [])].sort((x, y) => x.seq - y.seq)) {
      if (ev.redacted) {
        if (ev.prev !== prev) return { ok: false, broken_at: ev.seq, problem: 'chain broken (redacted event)' };
        prev = ev.hash; red += 1; continue;
      }
      if (await sha256(ev.body) !== ev.hash) return { ok: false, broken_at: ev.seq, problem: 'event body does not match its hash' };
      const body = JSON.parse(ev.body);
      if (body.prev !== prev) return { ok: false, broken_at: ev.seq, problem: 'chain broken (prev does not match)' };
      prev = ev.hash; checked += 1;
      const p = body.payload || {};
      if (body.kind === 'create') { creates.set(body.ref, p); revs.set(`${body.ref}#${p.v || 1}`, p.body_sha); }
      else if (body.kind === 'revise') revs.set(`${body.ref}#${p.v}`, p.body_sha);
      else if (body.kind === 'review') { reviews.set(p.review, p); revs.set(`${p.review}#1`, p.body_sha); }
      else if (body.kind === 'link') links.set(Number(p.edge), p);
      else if (body.kind === 'withdraw') withdraws.add(body.ref);
      else if (body.kind === 'retract') retracts.add(Number(p.edge));
    }
    if (b.head && b.head !== prev) return { ok: false, problem: "the chain does not end at the bundle's head" };
    for (const n of b.nodes || []) {
      const c = creates.get(n.id);
      if (n.type === 'review') { if (!reviews.has(n.id)) return { ok: false, problem: `review ${n.id} has no event` }; }
      else if (!c || c.type !== n.type || c.code !== n.code || c.inv !== n.inv) return { ok: false, problem: `node ${n.id} differs from its create event` };
    }
    for (const v of b.versions || []) {
      const want = revs.get(`${v.node}#${v.v}`);
      if (want === undefined) return { ok: false, problem: `version ${v.node} v${v.v} has no event` };
      if (await sha256(v.body) !== want) return { ok: false, problem: `version ${v.node} v${v.v} differs from its event` };
    }
    for (const e of b.edges || []) {
      const want = links.get(Number(e.id));
      if (!want) return { ok: false, problem: `edge ${e.id} has no event` };
      if (want.rel !== e.rel || want.dst !== e.dst || (want.dst_v ?? null) !== (e.dst_v ?? null) || await sha256(e.data) !== want.data_sha)
        return { ok: false, problem: `edge ${e.id} differs from its event` };
    }
    for (const w of b.withdrawals || []) if (!withdraws.has(w.node)) return { ok: false, problem: `withdrawal of ${w.node} has no event` };
    for (const r of b.retractions || []) if (!retracts.has(Number(r.edge))) return { ok: false, problem: `retraction of edge ${r.edge} has no event` };
    const out = { ok: true, checked, head: prev, complete: red === 0, redacted: red, nodes: (b.nodes || []).length, edges: (b.edges || []).length };
    if (red) out.warning = `${red} event(s) outside this investigation are redacted: their content can't be checked.`;
    return out;
  }

  // ── data sources ──────────────────────────────────────────────────
  const settle = async (p) => { try { return await p; } catch { return null; } };   // a route a host doesn't serve → null

  /** Live: the JSON API of `hypgraph serve`, or any host that serves the same routes under its own prefix. */
  function HttpSource(base = '/api/graph', fetchOpts = {}) {
    const get = async (path) => {
      const r = await fetch(base + path, fetchOpts);
      let body = null;
      try { body = await r.json(); } catch { /* not json */ }
      if (!r.ok) throw new Error((body && (body.detail?.error || body.detail || body.error)) || `HTTP ${r.status}`);
      return body;
    };
    const q = encodeURIComponent;
    const src = {
      kind: 'http', live: true, base,
      investigations: () => get('/investigations'),
      node: (id) => get(`/node/${q(id)}?history=1`),
      why: (id) => get(`/why/${q(id)}`),
      impact: (id) => get(`/impact/${q(id)}`),
      events: (after, inv, limit) => get(`/events?after=${after || 0}&inv=${q(inv || '')}&limit=${limit || 5000}`),
      exportUrl: (inv) => `${base}/export?inv=${q(inv)}`,
      async load(inv) {
        const [subgraph, stages, board, completion, orders, report, profile, events, verify, refusals, node, telemetry] = await Promise.all([
          get(`/subgraph?inv=${q(inv)}`), settle(get(`/stages?inv=${q(inv)}`)), settle(get(`/board?inv=${q(inv)}`)),
          settle(get(`/completion?inv=${q(inv)}`)), settle(get(`/orders?inv=${q(inv)}`)), settle(get(`/report?inv=${q(inv)}`)),
          settle(get(`/profile?inv=${q(inv)}`)), settle(src.events(0, inv, 5000)), settle(get('/verify')),
          settle(get(`/refusals?inv=${q(inv)}`)), settle(src.node(inv)), settle(get(`/telemetry?inv=${q(inv)}&limit=10000`))]);
        return { subgraph, stages: stages && stages.stages, board: board && board.board, completion,
          orders: orders && orders.orders, report, profile, events, verify, refusals, node, telemetry };
      },
      /** Follow the record and the swarm's telemetry: Server-Sent Events from /stream, or polling /events and
       *  /telemetry where a host has no stream. */
      follow(inv, after, onEvent, onState, onTel, telAfter) {
        let es = null, timer = null, closed = false, head = after || 0, toff = telAfter || 0;
        const poll = async () => {
          if (closed) return;
          try {
            const out = await src.events(head, inv, 500);
            (out.events || []).forEach((e) => { head = Math.max(head, e.seq); onEvent(e); });
            if (onTel) {
              const t = await settle(get(`/telemetry?inv=${q(inv)}&after=${toff}`));
              if (t) { (t.events || []).forEach(onTel); toff = t.next || toff; }
            }
            onState('polling');
          } catch { onState('offline'); }
          timer = setTimeout(poll, 5000);
        };
        if (typeof EventSource === 'function') {
          let opened = false;
          es = new EventSource(`${base}/stream?inv=${q(inv)}&after=${head}&after_telemetry=${toff}`);
          es.onopen = () => { opened = true; onState('live'); };
          es.addEventListener('record', (m) => { try { const e = JSON.parse(m.data); head = Math.max(head, e.seq); onEvent(e); } catch { /* skip */ } });
          es.addEventListener('telemetry', (m) => { try { if (onTel) onTel(JSON.parse(m.data)); } catch { /* skip */ } });
          es.onerror = () => {
            if (!opened) { es.close(); es = null; poll(); }       // no stream route here: poll instead
            else onState('reconnecting');                          // EventSource retries by itself (Last-Event-ID)
          };
        } else poll();
        return () => { closed = true; if (es) es.close(); clearTimeout(timer); };
      },
    };
    return src;
  }

  /** Static: a hypgraph/1-bundle (from `hypgraph export`) — no server, no Python. */
  function BundleSource(bundle) {
    const d = bundle.derived || { by_inv: {}, investigations: [], stats: {} };
    const nodes = new Map(), edges = [];
    Object.values(d.by_inv || {}).forEach((v) => {
      ((v.subgraph || {}).nodes || []).forEach((n) => nodes.set(n.id, n));
      ((v.subgraph || {}).edges || []).forEach((e) => edges.push(e));
    });
    const out = new Map(), inn = new Map();
    edges.forEach((e) => { (out.get(e.src) || out.set(e.src, []).get(e.src)).push(e); (inn.get(e.dst) || inn.set(e.dst, []).get(e.dst)).push(e); });
    const versions = new Map();
    (bundle.versions || []).forEach((v) => { (versions.get(v.node) || versions.set(v.node, []).get(v.node)).push({ ...v, body: JSON.parse(v.body) }); });
    versions.forEach((list) => list.sort((a, b) => a.v - b.v));
    const withdrawn = new Map((bundle.withdrawals || []).map((w) => [w.node, w]));
    const evs = (bundle.events || []).filter((e) => !e.redacted).map((e) => { const b = JSON.parse(e.body); return { seq: e.seq, at: b.at, actor: b.actor, kind: b.kind, ref: b.ref, payload: b.payload }; });
    const head = evs.length ? evs[evs.length - 1].seq : 0;
    const why = (id) => {
      const outRels = ['derived_from', 'requires', 'based_on', 'executes', 'uses', 'cites', 'tests'], inRels = ['supports', 'produced'];
      const seen = new Set([id]); let frontier = [id]; const es = [];
      while (frontier.length && seen.size < 300) {
        const nxt = [];
        frontier.forEach((x) => {
          const ups = (out.get(x) || []).filter((e) => outRels.includes(e.rel)).map((e) => [e, e.dst])
            .concat((inn.get(x) || []).filter((e) => inRels.includes(e.rel)).map((e) => [e, e.src]));
          ups.forEach(([e, y]) => { es.push(e); if (!seen.has(y)) { seen.add(y); nxt.push(y); } });
        });
        frontier = nxt;
      }
      return { center: id, nodes: [...seen].map((x) => nodes.get(x)).filter(Boolean), edges: es };
    };
    const impact = (id) => {
      const step = (x) => (inn.get(x) || []).filter((e) => RISKY.includes(e.rel)).map((e) => [e.src, e.rel])
        .concat((out.get(x) || []).filter((e) => e.rel === 'produced').map((e) => [e.dst, 'produced']))
        .concat((out.get(x) || []).filter((e) => e.rel === 'supports').map((e) => [e.dst, 'supports']));
      const seen = new Set([id]), dep = []; let frontier = [[id, 0]];
      while (frontier.length && dep.length < 500) {
        const nxt = [];
        frontier.forEach(([x, k]) => step(x).forEach(([y, rel]) => { if (!seen.has(y)) { seen.add(y); dep.push({ node: nodes.get(y), rel, depth: k + 1 }); nxt.push([y, k + 1]); } }));
        frontier = nxt;
      }
      return { center: id, dependents: dep.filter((x) => x.node) };
    };
    const node = async (id) => {
      const n = nodes.get(id); if (!n) throw new Error(`no node ${id}`);
      const vs = versions.get(id) || [];
      return { ...n, body: vs.length ? vs[vs.length - 1].body : {}, versions: vs, out: out.get(id) || [], in: inn.get(id) || [],
        ...(withdrawn.has(id) ? { withdrawn: withdrawn.get(id) } : {}) };
    };
    let verified = null;
    const evsOf = (inv) => evs.filter((e) => !inv || e.ref === inv || (nodes.get(e.ref) || {}).inv === inv);
    return {
      kind: 'bundle', live: false, bundle,
      investigations: async () => ({ investigations: d.investigations || [], stats: d.stats || {} }),
      node, why: async (id) => why(id), impact: async (id) => impact(id),
      events: async (after, inv) => ({ head, events: evsOf(inv).filter((e) => e.seq > (after || 0)) }),
      async load(inv) {
        const v = d.by_inv[inv] || {};
        verified = verified || await verifyBundle(bundle);
        let invNode = null;
        try { invNode = await node(inv); } catch { invNode = (d.investigations || []).find((x) => x.id === inv) || null; }
        return { subgraph: v.subgraph || { nodes: [], edges: [] }, stages: v.stages || null, board: v.board || null,
          completion: v.completion || null, orders: v.orders || null, report: v.report || null, profile: v.profile || null,
          events: { head, events: evsOf(inv) }, verify: verified, refusals: null, node: invNode,
          telemetry: v.telemetry || (bundle.telemetry ? { events: (bundle.telemetry.events || bundle.telemetry).filter((t) => !t.inv || t.inv === inv) } : null) };
      },
    };
  }

  // ── the model: one investigation, from either source ──────────────
  function makeModel(inv, raw) {
    const nodes = (raw.subgraph && raw.subgraph.nodes) || [], edges = (raw.subgraph && raw.subgraph.edges) || [];
    const byId = new Map(nodes.map((n) => [n.id, n])), byCode = new Map(nodes.filter((n) => n.code).map((n) => [n.code, n]));
    const profile = raw.profile || { id: '', name: '', labels: {}, workflow: null };
    const body = (raw.node && raw.node.body) || {};
    const events = ((raw.events && raw.events.events) || []).slice().sort((a, b) => a.seq - b.seq);
    return {
      inv, nodes, edges, byId, byCode, profile, events, raw,
      head: (raw.events && raw.events.head) || (events.length ? events[events.length - 1].seq : 0),
      code: (raw.node && raw.node.code) || (byId.get(inv) || {}).code || 'INV', title: body.title || (raw.node && raw.node.title) || (byId.get(inv) || {}).title || inv,
      objective: body.objective || '', pid: profile.id || body.profile || '',
      stages: raw.stages, board: raw.board, completion: raw.completion, orders: raw.orders, report: raw.report,
      verify: raw.verify, refusals: raw.refusals,
      tel: ((raw.telemetry && raw.telemetry.events) || []).slice().sort((a, b) => a.ts - b.ts),
      telNext: (raw.telemetry && raw.telemetry.next) || 0, telSource: raw.telemetry ? (raw.telemetry.exists !== false) : false,
      L: (t) => (profile.labels && profile.labels[t]) || cap(t),
      codeOf: (id) => ((byId.get(id) || {}).code) || id,
    };
  }
  const st = (n) => (n && n.state) || {};
  const reviewOf = (n) => ((st(n).review || {}).state) || '';
  const staleOf = (n) => { const s = st(n).stale; return Array.isArray(s) ? s : (s ? [String(s)] : []); };
  const TYPE_COLOR = { investigation: '#f79009', question: '#0b6bcb', hypothesis: '#7a5af8', claim: '#12b76a', experiment: '#ee46bc',
    run: '#2e90fa', result: '#06aed4', artifact: '#98a2b3', source: '#eaaa08', review: '#cbd5e1', decision: '#f97066', task: '#667085' };
  const PROFILE_COLOR = { scientific: '#0b6bcb', software: '#5925dc', trading: '#b54708', knowledge: '#067647', optimization: '#c11574' };
  const VIEWS = [['overview', '▦', 'Overview'], ['live', '◉', 'Live'], ['pipeline', '⇶', 'Pipeline'], ['graph', '⬡', 'Graph'],
    ['evidence', '☰', 'Evidence'], ['orders', '▤', 'Work orders'], ['audit', '⛓', 'Audit log'], ['report', '❐', 'Report']];
  const LOGO = '<svg viewBox="0 0 64 64" aria-hidden="true"><rect width="64" height="64" rx="14" fill="#0a0d14"/><g fill="none" stroke-linecap="round" stroke-width="3"><path d="M18 44 L32 20 L46 44" stroke="#7cf3ff"/><path d="M18 44 L46 44" stroke="#b18cff" stroke-dasharray="3 5"/></g><circle cx="32" cy="20" r="6" fill="#4ee08a"/><circle cx="18" cy="44" r="5" fill="#7cf3ff"/><circle cx="46" cy="44" r="5" fill="none" stroke="#ff4d5e" stroke-width="3"/></svg>';

  function standingPill(n) {
    if (!n) return '';
    const s = st(n), rv = reviewOf(n), stale = staleOf(n);
    if (s.lifecycle === 'withdrawn') return '<span class="pill bad"><span class="d"></span>withdrawn</span>';
    if (s.lifecycle === 'superseded') return '<span class="pill neutral">superseded</span>';
    if (stale.length) return `<span class="pill warn" title="${esc(stale[0])}"><span class="d"></span>stale</span>`;
    if (s.at_risk) return '<span class="pill warn"><span class="d"></span>at risk</span>';
    if (rv === 'contested') return '<span class="pill bad"><span class="d"></span>contested</span>';
    if (rv === 'checked') return '<span class="pill ok"><span class="d"></span>checked</span>';
    if (rv === 'unchecked') return '<span class="pill neutral">unchecked</span>';
    if (rv === 'needs_revalidation') return '<span class="pill warn">re-check</span>';
    return `<span class="pill neutral">${esc(s.lifecycle || 'active')}</span>`;
  }
  const standingKey = (n) => { const s = st(n), rv = reviewOf(n); return s.lifecycle === 'withdrawn' ? 'withdrawn' : s.lifecycle === 'superseded' ? 'superseded'
    : staleOf(n).length ? 'stale' : s.at_risk ? 'at risk' : rv || s.lifecycle || 'active'; };

  function csv(rows) { return rows.map((r) => r.map((c) => { const s = String(c ?? ''); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; }).join(',')).join('\n'); }
  function download(name, text, type = 'text/plain') {
    const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([text], { type })); a.download = name;
    document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500);
  }
  function md(src) {                                     // the report's markdown: headings, tables, lists, emphasis
    const lines = String(src || '').split('\n'); let out = '', i = 0;
    const inline = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/(^|[\s(])_(.+?)_(?=[\s).,;:]|$)/g, '$1<i>$2</i>').replace(/`(.+?)`/g, '<code>$1</code>');
    while (i < lines.length) {
      const l = lines[i];
      if (/^#{1,6} /.test(l)) { const h = Math.min(l.match(/^#+/)[0].length + 1, 4); out += `<h${h}>${inline(l.replace(/^#+ /, ''))}</h${h}>`; i++; continue; }
      if (l.startsWith('|')) {
        const rows = []; while (i < lines.length && lines[i].startsWith('|')) rows.push(lines[i++]);
        const cells = (r) => r.replace(/^\||\|$/g, '').split('|').map((c) => c.trim());
        out += '<table><thead><tr>' + cells(rows[0]).map((c) => `<th scope="col">${inline(c)}</th>`).join('') + '</tr></thead><tbody>' +
          rows.slice(2).map((r) => '<tr>' + cells(r).map((c) => `<td>${inline(c)}</td>`).join('') + '</tr>').join('') + '</tbody></table>';
        continue;
      }
      if (/^[-*] /.test(l)) { out += '<ul>'; while (i < lines.length && /^[-*] /.test(lines[i])) out += `<li>${inline(lines[i++].slice(2))}</li>`; out += '</ul>'; continue; }
      if (l.trim()) out += `<p>${inline(l)}</p>`;
      i++;
    }
    return out;
  }

  // ── the app ───────────────────────────────────────────────────────
  function mount(root, opts) {
    opts = opts || {};
    const src = opts.source || HttpSource();
    root.classList.add('hg');
    if (!root.dataset.theme) root.dataset.theme = opts.theme || 'light';
    const brand = opts.title && !/^atlas$/i.test(opts.title) ? esc(opts.title) : 'Hyp<b>Graph</b>';
    root.innerHTML = `<div class="hg-app">
      <header class="hg-top"><div class="hg-brand">${LOGO}<span>${brand}</span></div>
        <div class="hg-crumb" id="hg-crumb"></div><div class="sp"></div><span id="hg-status"></span><span id="hg-chain"></span>
        <button class="hg-search" id="hg-search" type="button" aria-label="Search the record (Ctrl+K)">⌕ <span>Search the record</span><kbd>⌘K</kbd></button>
        <button class="btn" id="hg-theme" type="button" aria-label="Switch theme" title="Theme (t)">◐</button></header>
      <nav class="hg-nav" id="hg-nav" aria-label="HypGraph"></nav>
      <main class="hg-main" id="hg-main" tabindex="-1"><div class="empty">Loading the record…</div></main></div>
      <aside class="hg-drawer" id="hg-drawer" aria-label="Details" aria-hidden="true"></aside>
      <div class="hg-pal" id="hg-pal" role="dialog" aria-label="Search"><div class="box"><input id="hg-pal-q" placeholder="Jump to a view, investigation, node or question…" aria-label="Search">
        <ul id="hg-pal-list" role="listbox"></ul></div></div>`;
    const $ = (s) => root.querySelector(s);
    const live = opts.live ?? src.live;
    const S = { invs: [], inv: '', m: null, view: 'overview', cursor: null, playing: false, speed: 4, timer: null, stream: 'off',
      lastEventAt: 0, follow: null, cy: null, drawer: null, ev: { q: '', types: new Set(['claim', 'result', 'hypothesis', 'source', 'decision']), standing: '' },
      sort: { k: 'code', asc: true }, audit: { actor: '', kind: '' }, graphTypes: null, palIdx: 0, profiles: new Map() };
    const fail = (e) => { root.dataset.hgError = String((e && e.message) || e); };

    // ── loading ──
    async function loadInvestigations() {
      const out = await src.investigations();
      S.invs = (out.investigations || []).filter((i) => i && i.id);
      await Promise.all(S.invs.slice(0, 40).map(async (i) => {
        try { const n = await src.node(i.id); S.profiles.set(i.id, String(((n && n.body) || {}).profile || '')); } catch { S.profiles.set(i.id, ''); }
      }));
    }
    async function openInv(inv, keep) {
      S.inv = inv; S.telSeen = null;
      const raw = await src.load(inv);
      S.m = makeModel(inv, raw);
      if (!keep) { S.cursor = null; stopPlay(); }
      if (S.follow) S.follow();
      S.follow = null;
      if (live && src.follow) S.follow = src.follow(inv, S.m.head, onLiveEvent, (s) => { S.stream = s; status(); }, onTel, S.m.telNext);
      render();
    }
    let refreshTimer = null;
    function onLiveEvent(e) {
      if (!S.m || S.m.events.some((x) => x.seq === e.seq)) return;
      S.m.events.push(e); S.m.head = Math.max(S.m.head, e.seq); S.lastEventAt = Date.now();
      if (S.view === 'live') renderSoon();
      clearTimeout(refreshTimer);                          // the derived views (stages, standing) follow a moment later
      refreshTimer = setTimeout(async () => {
        try {
          const raw = await src.load(S.inv);
          const evs = S.m.events, tel = S.m.tel; S.m = makeModel(S.inv, raw);
          if (evs.length > S.m.events.length) S.m.events = evs;
          if (tel.length > S.m.tel.length) S.m.tel = tel;
          render();
        } catch { /* keep what we have */ }
      }, 1200);
    }
    const telKey = (t) => `${t.kind}|${t.span || ''}|${t.ts}|${t.event || ''}`;
    function onTel(t) {
      if (!S.m) return;
      if (!S.telSeen) S.telSeen = new Set(S.m.tel.map(telKey));
      const k = telKey(t);
      if (S.telSeen.has(k)) return;
      S.telSeen.add(k); S.m.tel.push(t); S.m.telSource = true; S.lastEventAt = Date.now();
      if (S.view === 'live' || S.view === 'overview') renderSoon();
    }
    let soon = null;
    const renderSoon = () => { if (!soon) soon = setTimeout(() => { soon = null; render(); }, 250); };

    // ── chrome ──
    function nav() {
      const m = S.m;
      const n = { evidence: m.nodes.filter((x) => S.ev.types.has(x.type) && !(x.type === 'decision' && x.by === 'harness')).length,
        orders: (m.orders || []).length, audit: m.events.length, pipeline: (m.stages || []).length };
      const open = (m.orders || []).filter((o) => ['open', 'overdue'].includes(o.status)).length;
      let h = '<h2>Investigation</h2>' + VIEWS.map(([k, ico, name]) =>
        `<button type="button" data-v="${k}" ${S.view === k ? 'aria-current="page"' : ''}><span class="ico" aria-hidden="true">${ico}</span>${name}` +
        (k === 'live' ? (open ? `<span class="n">${open} open</span>` : '') : n[k] != null ? `<span class="n">${n[k]}</span>` : '') + '</button>').join('');
      if (S.invs.length > 1) {
        h += '<h2>Investigations</h2>' + S.invs.map((i) => {
          const pid = S.profiles.get(i.id) || '', fam = pid.split('@')[0];
          return `<button type="button" data-inv="${esc(i.id)}" ${i.id === S.inv ? 'aria-current="true"' : ''}><div class="inv">
            <span class="dot" style="background:${PROFILE_COLOR[fam] || 'var(--ink3)'}"></span><div><div class="t">${esc(i.title || i.code)}</div>
            <div class="s">${esc(pid || 'no profile')} · ${esc(i.code)}</div></div></div></button>`;
        }).join('');
      }
      $('#hg-nav').innerHTML = h;
    }
    function status() {
      const m = S.m;
      if (!m) return;
      $('#hg-crumb').innerHTML = `<span class="t">${esc(m.code)} · ${esc(m.title)}</span>` +
        (m.pid ? `<span class="pill accent" title="${esc(m.profile.about || '')}">${esc(m.pid)}</span>` : '<span class="pill neutral">no profile</span>');
      const v = m.verify;
      $('#hg-chain').innerHTML = !v ? '' : v.ok ? `<span class="pill ok" title="hash chain re-verified: ${v.checked} events, head ${esc(String(v.head || '').slice(0, 12))}…">⛓ chain verified · ${v.checked}</span>`
        : `<span class="pill bad" title="${esc(v.problem || '')}">⛓ chain broken${v.broken_at ? ' at #' + v.broken_at : ''}</span>`;
      const s = !live ? '' : S.stream === 'live' ? '<span class="pill ok"><span class="d"></span>live</span>'
        : S.stream === 'polling' ? '<span class="pill neutral" title="this host has no event stream; checking every 5 s">polling</span>'
        : S.stream === 'reconnecting' ? '<span class="pill warn">reconnecting</span>' : S.stream === 'offline' ? '<span class="pill bad">offline</span>' : '';
      $('#hg-status').innerHTML = s;
    }
    const head = (h, p, acts = '') => `<div class="head"><div><h1>${h}</h1>${p ? `<p>${p}</p>` : ''}</div>${acts ? `<div class="acts">${acts}</div>` : ''}</div>`;

    // ── stage helpers ──
    function stageBar(sq) {
      const stages = (S.m.profile.workflow && S.m.profile.workflow.stages) || [];
      if (!stages.length || !sq) return '';
      return '<div class="bar" role="img" aria-label="stage ' + sq.index + ' of ' + sq.of + '">' + stages.map((s, i) => {
        const g = (sq.gates || []).find((x) => x.stage === s.name);
        const c = g && g.met ? 'met' : i === sq.index - 1 ? 'cur' : s.optional ? 'opt' : '';
        return `<span class="${c}" title="${esc(s.name)}${g ? ' — ' + (g.met ? 'met' : esc(g.why || 'not met')) : ''}"></span>`;
      }).join('') + '</div>';
    }
    const isBookkeeping = (n) => n.type === 'decision' && n.by === 'harness';

    function alerts() {
      const m = S.m, out = [];
      const claims = m.nodes.filter((n) => n.type === 'claim');
      const stale = m.nodes.filter((n) => ['claim', 'result', 'source', 'decision'].includes(n.type) && staleOf(n).length && st(n).lifecycle === 'active');
      if (m.verify && !m.verify.ok) out.push(['bad', `The hash chain does not verify${m.verify.broken_at ? ' at event #' + m.verify.broken_at : ''}: ${m.verify.problem || ''}`]);
      if (stale.length) out.push(['warn', `${stale.length} node(s) rest on evidence that changed: ${stale.slice(0, 6).map((n) => n.code).join(', ')}`, stale[0].code]);
      const contested = claims.filter((c) => reviewOf(c) === 'contested');
      if (contested.length) out.push(['bad', `${contested.length} ${m.L('claim').toLowerCase()}(s) contested: ${contested.map((n) => n.code).join(', ')}`, contested[0].code]);
      const risk = m.nodes.filter((n) => st(n).at_risk && st(n).lifecycle === 'active');
      if (risk.length) out.push(['warn', `${risk.length} node(s) at risk — a premise fell: ${risk.slice(0, 6).map((n) => n.code).join(', ')}`, risk[0].code]);
      const now = Date.now(), held = new Map();
      m.events.forEach((e) => { const p = e.payload || {};
        if (e.kind === 'lease_take') held.set(p.task, { who: p.for, until: Date.parse(p.expires || '') });
        if (e.kind === 'lease_release') held.delete(p.task); });
      held.forEach((h, task) => { if (h.until && h.until < now) out.push(['warn', `${m.codeOf(task)} held by ${h.who} past its lease`]); });
      const returned = (m.orders || []).filter((o) => o.status === 'returned');
      if (returned.length) out.push(['info', `${returned.length} work order(s) returned, waiting on the record: ${returned.map((o) => o.code).join(', ')}`]);
      const r = m.refusals && (m.refusals.refused ?? m.refusals.total);
      if (r) out.push(['info', `${r} overclaim(s) refused by the record`]);
      if (m.tel.length) out.push(...telAlerts(m.tel));
      return out;
    }
    const alertList = (items) => items.length ? `<ul class="alerts">${items.map(([lvl, txt, code]) =>
      `<li><span class="pill ${lvl}">${lvl === 'bad' ? 'action' : lvl === 'warn' ? 'check' : 'note'}</span><span>${esc(txt)}${code ? ` <button class="btn" type="button" data-n="${esc(code)}" style="padding:1px 8px">open</button>` : ''}</span></li>`).join('')}</ul>`
      : '<div class="dim">Nothing needs attention.</div>';

    // ── telemetry (what the swarm did that the record can't see) ──
    function telUpTo() {                                   // the telemetry the current replay position has reached
      const m = S.m;
      if (S.cursor == null) return m.tel;
      const ev = m.events[Math.max(0, Math.min(S.cursor, m.events.length) - 1)];
      if (!ev || S.cursor === 0) return [];
      const cut = Date.parse(ev.at) / 1000 + 0.999;
      return m.tel.filter((t) => t.ts <= cut);
    }
    // a tool call the record refused (an overclaim, a missing gate) is the record doing its job, not a failure
    const refusedCall = (t) => t.kind === 'tool_end' && t.ok === false && /^refused|\brefused:/.test(String(t.error || ''));
    const failed = (t) => t.ok === false && !refusedCall(t);
    function telStats(tel) {
      const ends = tel.filter((t) => t.kind === 'model_end'), tools = tel.filter((t) => t.kind === 'tool_end');
      const sum = (xs, k) => xs.reduce((a, t) => a + (Number(t[k]) || 0), 0);
      const run = tel.find((t) => t.kind === 'run_start'), b = (run && run.budget) || {};
      const usd = sum(ends, 'usd'), calls = ends.reduce((a, t) => a + (Number(t.calls) || 1), 0);
      const used = b.max_usd ? usd / b.max_usd : b.max_calls ? calls / b.max_calls : null;
      return { calls, tin: sum(ends, 'in'), tout: sum(ends, 'out'), cached: sum(ends, 'cached'), usd, tools: tools.length,
        errors: ends.filter(failed).length + tools.filter(failed).length, refused: tools.filter(refusedCall).length, budget: b, used,
        run, ended: tel.find((t) => t.kind === 'run_end') };
    }
    function openSpans(tel) {                               // spans started and not ended: what is in flight
      const open = new Map();
      tel.forEach((t) => { if (t.kind.endsWith('_start')) open.set(t.span, t); else if (t.kind.endsWith('_end')) open.delete(t.span); });
      return [...open.values()];
    }
    const fmtUsd = (x) => !x ? '$0' : x >= 0.01 ? '$' + x.toFixed(2) : x >= 0.0001 ? '$' + x.toFixed(4) : '<$0.0001';
    const fmtN = (x) => x >= 10000 ? (x / 1000).toFixed(1) + 'k' : String(x);
    function telAlerts(tel) {
      const out = [], last = new Map(), runs = new Map();
      tel.forEach((t) => {
        if (t.kind !== 'tool_end' && t.kind !== 'tool_start') return;
        const key = `${t.seat}|${t.tool}`;
        if (t.kind === 'tool_end') {
          const n = t.ok === false ? (last.get(key) || 0) + 1 : 0;
          last.set(key, n);
          if (n === 3) out.push(['warn', `${t.seat}'s ${t.tool} was ${refusedCall(t) ? 'refused' : 'failed'} 3 times in a row: ${String(t.error || '').slice(0, 90)}`]);
        } else {
          const sig = `${t.seat}|${t.tool}|${JSON.stringify(t.args || {})}`, r = runs.get(t.seat) || { sig: '', n: 0 };
          r.n = r.sig === sig ? r.n + 1 : 1; r.sig = sig; runs.set(t.seat, r);
          if (r.n === 3) out.push(['warn', `${t.seat} called ${t.tool} with the same arguments 3 times in a row — a loop?`]);
        }
      });
      const errs = tel.filter((t) => t.kind === 'model_end' && t.ok === false);
      if (errs.length) out.push(['bad', `${errs.length} model call(s) failed: ${String(errs[errs.length - 1].error || '').slice(0, 100)}`]);
      const st = telStats(tel);
      if (st.used != null && st.used >= 0.8 && !st.ended) out.push(['warn', `the run has used ${Math.round(st.used * 100)} % of its budget`]);
      return out;
    }
    function telRow(t) {
      const c = (x) => `<span class="code">${esc(x)}</span>`, d = (x) => `<span class="dim">${esc(x)}</span>`;
      const tm = String(t.at || '').slice(11, 19);
      let what;
      switch (t.kind) {
        case 'model_end': what = t.ok === false ? `<span class="tel-bad">model call failed</span> ${d(String(t.error || '').slice(0, 120))}`
          : `model ${d(t.model || '')} · ${fmtN(t.in || 0)}→${fmtN(t.out || 0)} tokens${t.usd ? ' · ' + fmtUsd(t.usd) : ''} · ${t.s}s${(t.tool_calls || []).length ? ' → ' + t.tool_calls.map(esc).join(', ') : ''}`; break;
        case 'tool_end': what = refusedCall(t) ? `<span class="tel-warn">${esc(t.tool)} refused by the record</span> ${d(String(t.error || '').replace(/^refused:?\s*/, '').slice(0, 140))}`
          : t.ok === false ? `<span class="tel-bad">tool ${esc(t.tool)} failed</span> ${d(String(t.error || '').slice(0, 120))}` : `tool ${c(t.tool)} · ${t.s}s`; break;
        case 'order_start': what = `took ${c(t.order)} ${d('· ' + (t.model || ''))}`; break;
        case 'order_end': what = `finished ${c(t.order)} · ${t.calls || 0} call(s)${t.stopped ? ' ' + d('· ' + t.stopped) : ''}`; break;
        case 'decision': what = `scheduler: ${esc(t.event)}${t.order ? ' ' + c(t.order) : ''}${t.why || t.missing ? ' ' + d('— ' + String(t.why || t.missing).slice(0, 100)) : ''}`; break;
        case 'run_start': what = `run started · ${esc(t.title || '')}`; break;
        case 'run_end': what = `run ended · ${esc(t.stopped || '')} · ${t.calls || 0} calls${t.usd ? ' · ' + fmtUsd(t.usd) : ''}`; break;
        default: return '';
      }
      return `<div class="ev tel"><span class="seq">${esc(tm)}</span><span class="who">${esc(t.seat || (t.kind.startsWith('run') ? 'run' : 'scheduler'))}</span><span>${what}</span></div>`;
    }
    function trace(tel) {
      const orders = tel.filter((t) => t.kind === 'order_start');
      if (!orders.length) return '<div class="empty">No work orders in the telemetry yet.</div>';
      const pick = orders.find((o) => o.order === S.traceOrder) || orders[orders.length - 1];
      const kids = tel.filter((t) => t.parent === pick.span && (t.kind === 'model_end' || t.kind === 'tool_end' || t.kind === 'model_start' || t.kind === 'tool_start'));
      const ended = new Map(kids.filter((t) => t.kind.endsWith('_end')).map((t) => [t.span, t]));
      const startOf = new Map(kids.filter((t) => t.kind.endsWith('_start')).map((t) => [t.span, t]));
      const oend = tel.find((t) => t.kind === 'order_end' && t.span === pick.span);
      // "now" is the wall clock while following live, and the replay position while replaying
      const now = S.cursor == null ? Date.now() / 1000 : (tel.length ? tel[tel.length - 1].ts : pick.ts);
      const t0 = pick.ts, t1 = oend ? oend.ts : Math.max(t0 + 0.001, now);
      const span = Math.max(t1 - t0, 0.001);
      const rows = [...startOf.values()].map((s) => {
        const e = ended.get(s.span), dur = e ? Math.max(e.s || (e.ts - s.ts), 0) : Math.max(now - s.ts, 0);
        const left = ((s.ts - t0) / span) * 100, width = Math.max((dur / span) * 100, 0.6);
        const kind = s.kind.split('_')[0], bad = e && e.ok === false ? (refusedCall(e) ? ' refused' : ' bad') : '';
        const label = kind === 'model' ? `model ${s.model || ''}${e ? ` · ${fmtN(e.in || 0)}→${fmtN(e.out || 0)}${e.usd ? ' · ' + fmtUsd(e.usd) : ''}` : ' · in flight'}`
          : `${s.tool}${e ? '' : ' · running'}`;
        return `<div class="tr"><span class="tl">${esc(label)}</span><span class="tb"><i class="${kind}${bad}${e ? '' : ' open'}" style="left:${left.toFixed(2)}%;width:${Math.min(width, 100 - left).toFixed(2)}%"></i></span><span class="ts">${dur.toFixed(2)}s</span></div>`;
      }).join('');
      return `<div class="toolbar" style="margin:0 0 8px"><label class="dim" for="hg-trace-order">Work order</label>
        <select class="select" id="hg-trace-order">${orders.map((o) => `<option value="${esc(o.order)}" ${o === pick ? 'selected' : ''}>${esc(o.order)} · ${esc(o.seat)}</option>`).join('')}</select>
        <span class="dim">${esc(pick.model || '')} · ${(t1 - t0).toFixed(1)}s${oend ? ` · ${oend.calls || 0} call(s)${oend.stopped ? ' · ' + esc(oend.stopped) : ''}` : ' · running'}</span></div>
        <div class="trace">${rows || '<div class="dim">No calls yet.</div>'}</div>`;
    }

    // ── views ──
    function vOverview() {
      const m = S.m, qs = m.board || [], claims = m.nodes.filter((n) => n.type === 'claim');
      const settled = qs.filter((q) => q.status === 'settled').length, checked = claims.filter((c) => reviewOf(c) === 'checked').length;
      const stale = m.nodes.filter((n) => staleOf(n).length && st(n).lifecycle === 'active').length;
      const contested = claims.filter((c) => reviewOf(c) === 'contested').length;
      const orders = m.orders || [], done = orders.filter((o) => o.status === 'accepted').length;
      const sp = (m.report && m.report.spend) || {};
      const comp = m.completion;
      const kp = [[m.L('question') + 's settled', `${settled}/${qs.length}`, comp ? (comp.complete ? 'investigation complete' : 'in progress') : '', ''],
        [m.L('claim') + 's checked', `${checked}/${claims.length}`, 'by an independent reviewer', ''],
        ['Stale evidence', stale, stale ? 'rests on changed files or pages' : 'nothing rests on changed inputs', stale ? 'warn' : ''],
        ['Contested', contested, contested ? 'open objections' : 'no open objections', contested ? 'bad' : ''],
        ['Work orders', `${done}/${orders.length}`, 'accepted by the record', ''],
        sp.metered ? ['Spend', '$' + Number(sp.usd || 0).toFixed(3), `${sp.calls} model calls`, '']
          : m.tel.length ? (() => { const t = telStats(m.tel); return ['Spend', fmtUsd(t.usd), `${t.calls} model calls · from telemetry`, '']; })()
          : ['Spend', '—', 'not metered', '']];
      const stagesBy = new Map((m.stages || []).map((x) => [x.code, x]));
      const wf = m.profile.workflow;
      return head(esc(m.title), esc(m.objective), comp ? `<span class="pill ${comp.complete ? 'ok' : 'warn'}"><span class="d"></span>${comp.complete ? 'Complete' : 'In progress'}</span>` : '') +
        `<div class="grid kpis">${kp.map(([k, v, s, c]) => `<div class="card kpi ${c}"><div class="k">${k}</div><div class="v">${v}</div><div class="s">${s}</div></div>`).join('')}</div>
        <div class="grid two" style="margin-top:14px">
          <div class="card"><h3>${esc(m.L('question'))}s ${wf ? `<span class="sub">through the ${esc(m.profile.name)} workflow · ${wf.stages.map((s) => esc(s.name)).join(' → ')}</span>` : ''}</h3>
            ${qs.length ? `<table><thead><tr><th scope="col" style="width:56px"></th><th scope="col">${esc(m.L('question'))}</th>${wf ? '<th scope="col" style="width:210px">Stage</th>' : ''}<th scope="col" style="width:110px">Status</th></tr></thead><tbody>
            ${qs.map((q) => { const sq = stagesBy.get(q.code);
              return `<tr class="click" data-q="${esc(q.code)}" tabindex="0"><td class="code">${esc(q.code)}</td><td>${esc(q.text)}</td>
                ${wf ? `<td>${stageBar(sq)}<div class="dim" style="margin-top:4px">${sq ? `${esc(sq.stage)} · stage ${sq.index} of ${sq.of}` : ''}</div></td>` : ''}
                <td>${q.status === 'settled' ? '<span class="pill ok"><span class="d"></span>settled</span>' : q.status === 'contested' ? '<span class="pill bad">contested</span>' : `<span class="pill neutral">${esc(q.status)}</span>`}</td></tr>`; }).join('')}
            </tbody></table>` : '<div class="empty">No questions in this investigation yet.</div>'}</div>
          <div class="grid" style="align-content:start">
            <div class="card"><h3>Needs attention</h3><div class="body">${alertList(alerts())}</div></div>
            ${comp ? `<div class="card"><h3>Completion <span class="sub">${esc(comp.profile || m.pid || 'kernel')}</span></h3><div class="body">
              ${(comp.criteria || []).map((c) => `<div class="gate" style="margin-bottom:8px"><span class="m ${c.met ? 'met' : 'no'}" aria-hidden="true">${c.met ? '✓' : '·'}</span>
              <div><b>${esc(String(c.name).replace(/_/g, ' '))}</b> <span class="sr">${c.met ? 'met' : 'not met'}</span><div class="dim">${esc(c.why)}</div></div></div>`).join('')}</div></div>` : ''}
            <div class="card"><h3>Recent activity <span class="r"><button class="btn" type="button" data-v="audit">Audit log</button></span></h3><div>${m.events.slice(-6).reverse().map((e) => evRow(e)).join('') || '<div class="empty">No events.</div>'}</div></div>
          </div></div>`;
    }

    function vPipeline() {
      const m = S.m, wf = m.profile.workflow;
      if (!wf) return head('Pipeline', '') + '<div class="note">This investigation has no workflow profile, so its questions have no stages. Start an investigation with a <code>@2</code> profile (scientific, software, trading, knowledge, optimization) to see them move through its workflow.</div>';
      if (!m.stages) return head('Pipeline', '') + '<div class="note warn">This host doesn\'t serve the workflow stages (<code>/api/graph/stages</code>, hypgraph ≥ 0.5).</div>';
      const stages = wf.stages, cols = `56px repeat(${stages.length}, minmax(120px, 1fr))`;
      const qs = new Map((m.board || []).map((q) => [q.code, q]));
      return head('Pipeline', `Each ${esc(m.L('question').toLowerCase())} moves through the ${esc(m.profile.name)} workflow. The stage is derived from the record, never set by hand, and each gate says what would meet it.`) +
        `<div class="card" style="overflow:auto"><div class="lane" style="grid-template-columns:${cols};border-bottom:1px solid var(--line);background:var(--surface2)">
          <div style="min-height:auto"></div>${stages.map((s, i) => `<div style="min-height:auto"><b>${i + 1}. ${esc(s.name)}</b>${s.optional ? ' <span class="pill neutral">optional</span>' : ''}<div class="dim" style="margin-top:2px">${esc(s.holds)}</div></div>`).join('')}</div>
          ${m.stages.map((sq) => `<div class="lane click" data-q="${esc(sq.code)}" tabindex="0" role="button" aria-label="${esc(sq.code)} ${esc((qs.get(sq.code) || {}).text || '')}" style="grid-template-columns:${cols};border-bottom:1px solid var(--line);cursor:pointer">
            <div class="code">${esc(sq.code)}</div>${stages.map((s, i) => { const g = (sq.gates || []).find((x) => x.stage === s.name);
              const c = g && g.met ? 'met' : i === sq.index - 1 ? 'cur' : 'no';
              return `<div><div class="gate"><span class="m ${c}" aria-hidden="true">${c === 'met' ? '✓' : c === 'cur' ? '●' : ''}</span>
                <div><span class="mono">${esc(g ? g.gate : s.gate)}</span><span class="sr">${c === 'met' ? 'met' : c === 'cur' ? 'current' : 'not met'}</span>
                ${g && g.evidence && g.evidence.length ? `<div class="dim">${g.evidence.slice(0, 3).map(esc).join(', ')}</div>` : ''}
                ${g && !g.met && i === sq.index - 1 ? `<div class="why">${esc(g.why)}</div>` : ''}</div></div></div>`; }).join('')}</div>`).join('')}
        </div>`;
    }

    function evidenceRows() {
      const m = S.m, q = S.ev.q.toLowerCase();
      let rows = m.nodes.filter((n) => S.ev.types.has(n.type) && !isBookkeeping(n));
      if (S.ev.standing) rows = rows.filter((n) => standingKey(n) === S.ev.standing);
      if (q) rows = rows.filter((n) => `${n.code} ${n.title} ${n.by}`.toLowerCase().includes(q));
      const k = S.sort.k, dir = S.sort.asc ? 1 : -1;
      const key = (n) => k === 'type' ? m.L(n.type) : k === 'statement' ? n.title : k === 'author' ? n.by : k === 'standing' ? standingKey(n)
        : (n.code || '').replace(/\d+/, (d) => d.padStart(6, '0'));
      return rows.sort((a, b) => String(key(a)).localeCompare(String(key(b))) * dir);
    }
    function vEvidence() {
      const m = S.m, rows = evidenceRows();
      const types = ['claim', 'result', 'hypothesis', 'source', 'decision', 'experiment', 'run', 'artifact'].filter((t) => m.nodes.some((n) => n.type === t));
      const th = (k, label, w) => `<th scope="col" ${w ? `style="width:${w}"` : ''} aria-sort="${S.sort.k === k ? (S.sort.asc ? 'ascending' : 'descending') : 'none'}"><button type="button" data-sort="${k}">${label}${S.sort.k === k ? (S.sort.asc ? ' ↑' : ' ↓') : ''}</button></th>`;
      return head('Evidence', `Every ${esc(m.L('claim').toLowerCase())}, ${esc(m.L('result').toLowerCase())} and source with its derived standing: checked, stale, contested, at risk.`, '<button class="btn" type="button" data-act="csv-evidence">Export CSV</button>') +
        `<div class="toolbar"><input class="input" id="hg-ev-q" placeholder="Filter by code, text or author" value="${esc(S.ev.q)}" aria-label="Filter evidence">
          ${types.map((t) => `<button type="button" class="chip" data-evtype="${t}" aria-pressed="${S.ev.types.has(t)}">${esc(m.L(t))}</button>`).join('')}
          <select class="select" id="hg-ev-st" aria-label="Standing"><option value="">any standing</option>${['checked', 'unchecked', 'contested', 'stale', 'at risk', 'superseded', 'withdrawn'].map((s) => `<option ${S.ev.standing === s ? 'selected' : ''}>${s}</option>`).join('')}</select>
          <span class="dim">${rows.length} shown</span></div>
        <div class="card"><table><thead><tr>${th('code', 'Code', '70px')}${th('type', 'Type', '140px')}${th('statement', 'Statement')}${th('author', 'Author', '120px')}${th('standing', 'Standing', '120px')}</tr></thead><tbody>
        ${rows.map((n) => `<tr class="click" data-n="${esc(n.id)}" tabindex="0"><td class="code">${esc(n.code)}</td><td>${esc(m.L(n.type))}</td><td>${esc(n.title)}</td>
          <td class="dim">${esc(n.by)}${n.by === 'instrument' || n.by === 'lab' ? ' <span class="pill info">re-run</span>' : ''}</td><td>${standingPill(n)}</td></tr>`).join('') || '<tr><td colspan="5" class="empty">Nothing matches.</td></tr>'}
        </tbody></table></div>`;
    }

    function vOrders() {
      const m = S.m, os = m.orders;
      if (!os) return head('Work orders', '') + '<div class="note warn">This host doesn\'t serve work orders (<code>/api/graph/orders</code>).</div>';
      const col = (name, list) => `<div class="col"><h3>${name}<b>${list.length}</b></h3>${list.map(orderCard).join('') || '<div class="dim" style="padding:6px">none</div>'}</div>`;
      return head('Work orders', 'What the harness asked each seat to do, the record\'s predicates for done, and how each order ended.', '<button class="btn" type="button" data-act="csv-orders">Export CSV</button>') +
        `<div class="kanban">${col('Open', os.filter((o) => ['open', 'overdue'].includes(o.status)))}${col('Returned', os.filter((o) => o.status === 'returned'))}
        ${col('Accepted', os.filter((o) => o.status === 'accepted'))}${col('Cancelled · reworked', os.filter((o) => ['cancelled', 'reworked'].includes(o.status)))}</div>`;
    }
    function orderCard(o) {
      const what = String(o.objective || '').split(': ').slice(-1)[0];
      return `<div class="order"><div class="r"><span class="code">${esc(o.code)}</span><span class="pill neutral">${esc(o.assignee)}</span>
        ${o.status === 'overdue' ? '<span class="pill warn">overdue</span>' : ''}<button type="button" class="btn" data-q="${esc(o.target)}" style="margin-left:auto;padding:0 7px">${esc(o.target)}</button></div>
        <div>${esc(what.slice(0, 160))}</div>${o.done_when ? `<div class="dim mono" style="margin-top:4px">done when ${o.done_when.map((p) => esc(p.p)).join(' · ')}</div>` : ''}
        ${o.returned_note ? `<div class="dim" style="margin-top:3px">“${esc(String(o.returned_note).slice(0, 140))}”</div>` : ''}</div>`;
    }

    function auditRows() { return S.m.events.filter((e) => (!S.audit.actor || e.actor === S.audit.actor) && (!S.audit.kind || e.kind === S.audit.kind)); }
    function vAudit() {
      const m = S.m, rows = auditRows(), v = m.verify;
      const actors = [...new Set(m.events.map((e) => e.actor))].sort(), kinds = [...new Set(m.events.map((e) => e.kind))].sort();
      return head('Audit log', 'The record\'s append-only event log. Every write is hash-chained, and the chain is re-verified when the record is read.', '<button class="btn" type="button" data-act="csv-audit">Export CSV</button>') +
        (v ? `<div class="note ${v.ok ? '' : 'warn'}">${v.ok ? `⛓ Chain verified: ${v.checked} events, head <code>${esc(String(v.head || '').slice(0, 16))}…</code>${v.warning ? ' · ' + esc(v.warning) : ''}` : `⛓ The chain does not verify: ${esc(v.problem || '')}`}</div>` : '') +
        `<div class="toolbar"><select class="select" id="hg-au-actor" aria-label="Actor"><option value="">every actor</option>${actors.map((a) => `<option ${S.audit.actor === a ? 'selected' : ''}>${esc(a)}</option>`).join('')}</select>
          <select class="select" id="hg-au-kind" aria-label="Event"><option value="">every event</option>${kinds.map((k) => `<option ${S.audit.kind === k ? 'selected' : ''}>${esc(k)}</option>`).join('')}</select><span class="dim">${rows.length} events</span></div>
        <div class="card"><table><thead><tr><th scope="col" style="width:60px">Seq</th><th scope="col" style="width:170px">Time (UTC)</th><th scope="col" style="width:120px">Actor</th><th scope="col" style="width:120px">Event</th><th scope="col">What happened</th></tr></thead><tbody>
        ${rows.slice().reverse().slice(0, 2000).map((e) => `<tr><td class="mono dim">${e.seq}</td><td class="mono dim">${esc(String(e.at || '').replace('T', ' ').slice(0, 19))}</td>
          <td>${esc(e.actor)}</td><td><span class="pill neutral">${esc(e.kind)}</span></td><td>${say(e)}</td></tr>`).join('')}</tbody></table></div>`;
    }

    function vReport() {
      const m = S.m, name = (m.profile.workflow && m.profile.workflow.report) || 'Facts from the record';
      const acts = '<button class="btn" type="button" data-act="print">Print · PDF</button><button class="btn" type="button" data-act="md">Download Markdown</button>' +
        (src.exportUrl ? `<a class="btn" href="${esc(src.exportUrl(S.inv))}" download>Export bundle</a>` : src.bundle ? '<button class="btn" type="button" data-act="bundle">Export bundle</button>' : '');
      return head(esc(name), 'Generated from the record. Interpretation is written below it and checked against the record before it is accepted.', acts) +
        `<div class="card"><div class="body md">${m.report ? md(m.report.markdown) : '<div class="empty">This host doesn\'t serve the report.</div>'}</div></div>`;
    }

    function vGraph() {
      const m = S.m, types = [...new Set(m.nodes.map((n) => n.type))].filter((t) => t !== 'review');
      if (!S.graphTypes) S.graphTypes = new Set(types.filter((t) => t !== 'task'));
      return head('Graph', `The ${esc(m.profile.name || 'record')} record as a graph: what rests on what. Select a node for its standing, history and provenance.`,
        '<button class="btn" type="button" data-act="png">Export PNG</button><button class="btn" type="button" data-act="json">Export JSON</button>') +
        `<div class="toolbar">${types.map((t) => `<button type="button" class="chip" data-gtype="${t}" aria-pressed="${S.graphTypes.has(t)}"><i style="display:inline-block;width:8px;height:8px;border-radius:2px;background:${TYPE_COLOR[t] || '#98a2b3'};margin-right:5px"></i>${esc(m.L(t))}</button>`).join('')}</div>
        <div class="card"><div class="graph big" id="hg-graph" role="img" aria-label="Graph of ${m.nodes.length} nodes"></div><div class="legend">
          <span><i style="border:2px solid var(--ok)"></i>checked</span><span><i style="border:2px dashed var(--warn)"></i>stale</span><span><i style="border:2px solid var(--bad)"></i>at risk · contested</span><span><i style="background:var(--line2)"></i>superseded · withdrawn</span></div></div>`;
    }

    // ── live ──
    function vLive() {
      const m = S.m, n = m.events.length, cur = S.cursor == null ? n : Math.min(S.cursor, n), seen = m.events.slice(0, cur);
      const following = S.cursor == null, last = seen[seen.length - 1];
      const ranTo = telUpTo(), runEnd = ranTo.filter((t) => t.kind === 'run_end').pop(), runStart = ranTo.filter((t) => t.kind === 'run_start').pop();
      const runOpen = runStart && (!runEnd || runEnd.ts < runStart.ts);   // telemetry says whether a run is under way
      const running = S.playing || (following && live && (runOpen || (!runStart && S.stream === 'live' && Date.now() - S.lastEventAt < 30000)));
      const state = S.playing ? 'Replaying' : running ? 'Running' : !following ? 'Paused'
        : runEnd && runEnd === ranTo.filter((t) => t.kind.startsWith('run_')).pop() ? `Run ended · ${runEnd.stopped || (runEnd.ok === false ? 'failed' : 'done')}`
        : m.completion && m.completion.complete ? 'Complete' : live ? 'Watching' : 'Recorded';
      const c = (f) => seen.filter(f).length;
      const kp = [['Work orders issued', c((e) => e.kind === 'create' && (e.payload || {}).type === 'task')], ['Picked up', c((e) => e.kind === 'lease_take')],
        ['Returned', c((e) => e.kind === 'lease_release')], [m.L('result') + 's', c((e) => e.kind === 'create' && (e.payload || {}).type === 'result')],
        [m.L('claim') + 's', c((e) => e.kind === 'create' && (e.payload || {}).type === 'claim')], ['Reviews', c((e) => e.kind === 'review')]];
      const tel = telUpTo(), ts = telStats(tel);
      const carried = src.kind === 'bundle';                // telemetry handed over in a bundle sits outside its hash chain
      const telPill = m.tel.length ? `<span class="pill ok" title="the swarm's telemetry: model and tool calls, work orders, decisions${carried ? ' — carried in the bundle as observation; the hash chain does not cover it and nothing derived rests on it' : ''}">telemetry · ${m.tel.length} events${carried ? ' · not hash-chained' : ''}</span>`
        : '<span class="pill neutral" title="Run the swarm with hypswarm ≥ 0.1.0a7 (telemetry on by default for a record file): model and tool calls, tokens and cost per seat appear here.">telemetry: not connected</span>';
      const tk = m.tel.length ? [['Model calls', ts.calls, ''], ['Tokens', `${fmtN(ts.tin)} → ${fmtN(ts.tout)}`, ts.cached ? `${fmtN(ts.cached)} cached` : ''],
        ['Spend', fmtUsd(ts.usd), ''], ['Tool calls', ts.tools, ts.refused ? `${ts.refused} refused by the record` : ''],
        ['Errors', ts.errors, '', ts.errors ? 'bad' : ''],
        ['Budget', ts.used == null ? '—' : `${Math.round(ts.used * 100)} %`, ts.budget.max_usd ? `of ${fmtUsd(ts.budget.max_usd)}` : ts.budget.max_calls ? `of ${ts.budget.max_calls} calls` : 'no cap', ts.used >= 0.8 ? 'warn' : '']] : [];
      return head('Live', `Everything the swarm does, as it happens: every model and tool call, who holds which work order, what each seat writes, every review, the record growing.${live ? '' : ' This is the run\'s recorded log; play it back.'}`, telPill) +
        `<div class="card" style="margin-bottom:14px"><div class="live-head">
          <span class="pulse ${running ? '' : 'off'}" aria-hidden="true"></span><b>${state}</b>
          <span class="dim">event ${cur} of ${n}${last ? ' · ' + esc(String(last.at || '').slice(11, 19)) + ' UTC' : ''}</span>
          <button class="btn" type="button" data-act="lv-start" aria-label="Back to the start">⏮</button>
          <button class="btn" type="button" data-act="lv-play">${S.playing ? '❚❚ Pause' : '▶ Play'}</button>
          <select class="select" id="hg-lv-speed" aria-label="Speed">${[1, 4, 12, 40].map((x) => `<option value="${x}" ${S.speed === x ? 'selected' : ''}>${x}×</option>`).join('')}</select>
          <input class="scrub" type="range" id="hg-lv-scrub" min="0" max="${n}" value="${cur}" aria-label="Point in the run">
          <button class="btn" type="button" data-act="lv-live" ${following ? 'disabled' : ''}>${live ? 'Follow live' : 'Jump to end'}</button></div></div>
        ${tk.length ? `<div class="grid kpis" style="margin-bottom:10px">${tk.map(([k, v, s, c]) => `<div class="card kpi ${c || ''}"><div class="k">${esc(k)}</div><div class="v">${v}</div>${s ? `<div class="s">${esc(s)}</div>` : ''}</div>`).join('')}</div>` : ''}
        <div class="grid kpis" style="margin-bottom:14px">${kp.map(([k, v]) => `<div class="card kpi"><div class="k">${esc(k)}</div><div class="v">${v}</div></div>`).join('')}</div>
        ${m.tel.length ? (() => { const a = telAlerts(tel); return a.length ? `<div class="card" style="margin-bottom:14px"><h3>Alerts</h3><div class="body">${alertList(a)}</div></div>` : ''; })() : ''}
        <div class="grid live">
          <div class="card"><h3>Seats <span class="sub">who is working on what</span></h3>${seats(seen, tel)}</div>
          <div class="card"><h3>The record, growing</h3><div class="graph" id="hg-live-graph" role="img" aria-label="The record as of event ${cur}"></div></div>
          <div class="card"><h3>Event stream <span class="sub">newest first</span>
            ${m.tel.length ? `<span class="r"><select class="select" id="hg-lv-feed" aria-label="Show">${[['all', 'record + telemetry'], ['record', 'record'], ['telemetry', 'telemetry']].map(([v, l]) => `<option value="${v}" ${S.feed === v ? 'selected' : ''}>${l}</option>`).join('')}</select></span>` : ''}</h3>
            <div class="feed" aria-live="polite">${feed(seen, tel, running)}</div></div>
        </div>
        ${m.tel.length ? `<div class="card" style="margin-top:14px"><h3>Trace <span class="sub">where a work order's time went: each model and tool call</span></h3><div class="body">${trace(tel)}</div></div>` : ''}`;
    }
    function feed(seen, tel, running) {
      const mode = S.feed || 'all';
      const rec = mode === 'telemetry' ? [] : seen.slice(-300).map((e) => ({ ts: Date.parse(e.at) / 1000, e }));
      const tl = mode === 'record' ? [] : tel.filter((t) => !t.kind.endsWith('_start') || t.kind === 'order_start' || t.kind === 'run_start').slice(-400).map((t) => ({ ts: t.ts, t }));
      const all = rec.concat(tl).sort((a, b) => b.ts - a.ts || ((b.e ? b.e.seq : 0) - (a.e ? a.e.seq : 0))).slice(0, 400);
      return all.map((x, i) => x.e ? evRow(x.e, i === 0 && (S.playing || running)) : telRow(x.t)).join('') || '<div class="empty">Nothing yet.</div>';
    }
    function seats(seen, tel) {
      const m = S.m, by = {};
      seen.forEach((e) => {
        const p = e.payload || {}, who = e.kind === 'lease_take' ? p.for : e.actor;
        if (!who) return;
        const s = by[who] || (by[who] = { writes: 0, holding: null, last: '' });
        if (e.kind === 'lease_take') s.holding = m.codeOf(p.task);
        if (e.kind === 'lease_release') s.holding = null;
        if (['create', 'revise', 'link', 'review', 'withdraw'].includes(e.kind)) s.writes++;
        s.last = say(e, true);
      });
      const ends = (tel || []).filter((t) => t.kind === 'model_end' || t.kind === 'tool_end');
      ends.forEach((t) => { if (t.seat && !by[t.seat]) by[t.seat] = { writes: 0, holding: null, last: '' }; });
      const open = openSpans(tel || []), now = Date.now() / 1000, following = S.cursor == null;
      const names = Object.keys(by).sort((a, b) => (a === 'harness') - (b === 'harness') || a.localeCompare(b));
      return names.map((w) => { const s = by[w];
        const mine = ends.filter((t) => t.seat === w), calls = mine.filter((t) => t.kind === 'model_end');
        const usd = calls.reduce((a, t) => a + (Number(t.usd) || 0), 0), tok = calls.reduce((a, t) => a + (Number(t.in) || 0) + (Number(t.out) || 0), 0);
        const errs = mine.filter(failed).length, refs = mine.filter(refusedCall).length;
        const fly = open.filter((t) => t.seat === w && (t.kind === 'model_start' || t.kind === 'tool_start')).pop();
        const flying = fly ? `<span class="fly"></span>${fly.kind === 'model_start' ? `calling ${esc(fly.model || 'the model')}` : `running ${esc(fly.tool)}`}${following ? ` · ${Math.max(0, now - fly.ts).toFixed(1)}s` : ''}${fly.order ? ` on <span class="code">${esc(fly.order)}</span>` : ''}` : '';
        return `<div class="seat ${s.holding || fly ? 'busy' : ''}"><div class="av" aria-hidden="true">${esc(w.slice(0, 2).toUpperCase())}</div>
          <div><div class="nm">${esc(w)}${w === 'harness' ? ' <span class="pill neutral">scheduler</span>' : (w === 'instrument' || w === 'lab') ? ' <span class="pill info">instrument</span>' : ''}${refs ? ` <span class="pill warn" title="writes the record refused; each refusal says what to fix">${refs} refused</span>` : ''}${errs ? ` <span class="pill bad">${errs} error${errs > 1 ? 's' : ''}</span>` : ''}</div>
          <div class="doing">${flying || (s.holding ? `working <span class="code">${esc(s.holding)}</span>` : esc(s.last))}</div>
          ${calls.length ? `<div class="dim" style="font-size:11.5px">${calls.length} call(s) · ${fmtN(tok)} tokens${usd ? ' · ' + fmtUsd(usd) : ''}</div>` : ''}</div>
          <span class="mono dim" title="record writes">${s.writes}</span></div>`; }).join('')
        || '<div class="empty">Nobody has started yet.</div>';
    }
    function say(e, plain) {
      const m = S.m, p = e.payload || {}, c = (x) => plain ? x : `<span class="code">${esc(x)}</span>`, d = (x) => plain ? x : `<span class="dim">${esc(x)}</span>`;
      const ref = m.codeOf(e.ref);
      switch (e.kind) {
        case 'create': return p.type === 'task' ? `issued work order ${c(p.code || ref)}` : `${p.type === 'investigation' ? 'opened' : 'wrote'} ${esc(m.L(p.type).toLowerCase())} ${c(p.code || ref)}`;
        case 'link': return `linked ${c(ref)} ${d(p.rel || '')} ${c(m.codeOf(p.dst))}`;
        case 'review': return `reviewed ${c(ref)} — ${plain ? p.verdict : '<b>' + esc(p.verdict) + '</b>'}`;
        case 'revise': return `revised ${c(ref)}${p.reason ? ' ' + d('(' + p.reason + ')') : ''}`;
        case 'lease_take': return `${esc(p.for || e.actor)} picked up ${c(m.codeOf(p.task))}`;
        case 'lease_release': return `returned ${c(m.codeOf(p.task))}${p.note ? ' ' + d('— ' + String(p.note).slice(0, 100)) : ''}`;
        case 'withdraw': return `withdrew ${c(ref)}${p.why ? ' ' + d('— ' + p.why) : ''}`;
        case 'retract': return `retracted a link ${d('#' + (p.edge || ''))}`;
        default: return `${esc(e.kind)} ${c(ref)}`;
      }
    }
    function evRow(e, fresh) {
      const p = e.payload || {};
      return `<div class="ev ${fresh ? 'fresh' : ''}"><span class="seq">#${e.seq}</span><span class="who">${esc(e.kind === 'lease_take' ? (p.for || e.actor) : e.actor)}</span><span>${say(e)}</span></div>`;
    }
    function stopPlay() { S.playing = false; clearInterval(S.timer); S.timer = null; }
    function replayFromStart() {                          // open on the Live view, playing the run from its first event
      if (S.view !== 'live') setView('live');
      const still = global.matchMedia && global.matchMedia('(prefers-reduced-motion: reduce)').matches;
      if (!S.m.events.length || still) return;            // reduced motion: the finished run, with Play one click away
      S.cursor = 0; play();
    }
    function play() {
      const n = S.m.events.length;
      if (S.cursor == null || S.cursor >= n) S.cursor = 0;
      S.playing = true; clearInterval(S.timer);
      S.timer = setInterval(() => { if (S.cursor >= S.m.events.length) { stopPlay(); render(); return; } S.cursor++; render(); }, 1000 / S.speed);
      render();
    }

    // ── graph ──
    function graphInto(el, nodes, edges, fit) {
      if (!el || !global.cytoscape) { if (el) el.innerHTML = '<div class="empty">The graph needs vendor/cytoscape.min.js.</div>'; return null; }
      const css = getComputedStyle(root), tok = (k) => css.getPropertyValue(k).trim();
      const shown = nodes.filter((n) => n.type !== 'review');
      const ids = new Set(shown.map((n) => n.id));
      const ring = (n) => staleOf(n).length ? 'stale' : (st(n).at_risk || reviewOf(n) === 'contested') ? 'bad' : reviewOf(n) === 'checked' ? 'ok' : '';
      const cy = global.cytoscape({ container: el, wheelSensitivity: 0.25, boxSelectionEnabled: false,
        elements: [...shown.map((n) => ({ data: { id: n.id, label: n.code || '', type: n.type, color: TYPE_COLOR[n.type] || '#98a2b3', ring: ring(n),
          gone: ['superseded', 'withdrawn'].includes(st(n).lifecycle) ? 'y' : '' } })),
          ...edges.filter((e) => ids.has(e.src) && ids.has(e.dst)).map((e, i) => ({ data: { id: `e${i}-${e.src}-${e.dst}`, source: e.src, target: e.dst, rel: e.rel } }))],
        style: [
          { selector: 'node', style: { 'background-color': 'data(color)', label: 'data(label)', 'font-size': 9, color: tok('--ink2'), 'text-valign': 'bottom',
            'text-margin-y': 3, width: 16, height: 16, 'font-family': 'ui-monospace, monospace' } },
          { selector: 'node[type="investigation"]', style: { width: 26, height: 26, shape: 'star' } },
          { selector: 'node[type="question"]', style: { width: 22, height: 22, shape: 'diamond' } },
          { selector: 'node[type="claim"]', style: { shape: 'round-rectangle', width: 20 } },
          { selector: 'node[type="hypothesis"]', style: { shape: 'hexagon', width: 20, height: 18 } },
          { selector: 'node[type="experiment"]', style: { shape: 'round-triangle' } },
          { selector: 'node[type="artifact"]', style: { shape: 'rectangle', width: 12, height: 12 } },
          { selector: 'node[type="source"]', style: { shape: 'tag' } },
          { selector: 'node[type="decision"]', style: { shape: 'octagon' } },
          { selector: 'node[type="task"]', style: { shape: 'tag', width: 12, height: 12, opacity: 0.65 } },
          { selector: 'node[ring="ok"]', style: { 'border-width': 2, 'border-color': tok('--ok') } },
          { selector: 'node[ring="stale"]', style: { 'border-width': 2, 'border-style': 'dashed', 'border-color': tok('--warn') } },
          { selector: 'node[ring="bad"]', style: { 'border-width': 2, 'border-color': tok('--bad') } },
          { selector: 'node[gone="y"]', style: { opacity: 0.35 } },
          { selector: 'edge', style: { width: 1, 'line-color': tok('--line2'), 'target-arrow-shape': 'triangle', 'target-arrow-color': tok('--line2'), 'curve-style': 'bezier', 'arrow-scale': 0.6 } },
          { selector: 'edge[rel="supersedes"]', style: { 'line-style': 'dashed', 'line-color': tok('--warn'), 'target-arrow-color': tok('--warn') } },
          { selector: 'edge[rel="challenges"]', style: { 'line-color': tok('--bad'), 'target-arrow-color': tok('--bad') } },
          { selector: ':selected', style: { 'overlay-color': tok('--accent'), 'overlay-opacity': 0.22, 'overlay-padding': 5 } },
        ] });
      try { cy.layout({ name: hasFcose() ? 'fcose' : 'cose', animate: false, randomize: true, nodeRepulsion: 6500, idealEdgeLength: 60, fit: fit !== false, padding: 24 }).run(); }
      catch { cy.layout({ name: 'cose', animate: false }).run(); }
      cy.on('tap', 'node', (ev) => openNode(ev.target.id()));
      return cy;
    }
    let fcoseKnown = null;
    function hasFcose() {
      if (fcoseKnown != null) return fcoseKnown;
      try { const t = global.cytoscape({ headless: true }); t.layout({ name: 'fcose' }); fcoseKnown = true; } catch { fcoseKnown = false; }
      return fcoseKnown;
    }

    // ── drawer ──
    function drawer(title, sub, body) {
      const d = $('#hg-drawer');
      d.innerHTML = `<header><div style="flex:1;min-width:0"><h2>${title}</h2><div class="dim" style="margin-top:4px">${sub}</div></div>
        <button class="btn" type="button" data-act="close" aria-label="Close details">✕</button></header>${body}`;
      d.classList.add('open'); d.setAttribute('aria-hidden', 'false');
      const b = d.querySelector('[data-act="close"]'); if (b) b.focus({ preventScroll: true });
    }
    function closeDrawer() { const d = $('#hg-drawer'); d.classList.remove('open'); d.setAttribute('aria-hidden', 'true'); S.drawer = null; syncHash(); }
    const nodeLink = (id, rel) => { const n = S.m.byId.get(id); return `<div class="link"><button type="button" data-n="${esc(id)}"><span class="code">${esc((n && n.code) || id)}</span></button>
      ${rel ? `<span class="dim">${esc(rel)}</span>` : ''}<span class="ink2" style="min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(n ? (S.m.L(n.type) + ' · ' + (n.title || '')) : '')}</span></div>`; };
    async function openNode(idOrCode) {
      const m = S.m, n = m.byId.get(idOrCode) || m.byCode.get(idOrCode);
      if (!n) return;
      if (n.type === 'question') return openQuestion(n.code);
      S.drawer = { node: n.id }; syncHash();
      const s = st(n), rv = s.review || {};
      const skeleton = (det, why, imp) => {
        const body = (det && det.body) || {};
        const fields = Object.entries(body).filter(([k, v]) => v !== '' && v != null && !['title'].includes(k)).slice(0, 14);
        return `
        <section><h4>Standing</h4>${standingPill(n)} <span style="margin-left:6px">${esc(s.sentence || '')}</span>
          ${staleOf(n).length ? `<div class="why">${esc(staleOf(n).join('; '))}</div>` : ''}
          ${rv.positive && rv.positive.length ? `<div class="dim" style="margin-top:6px">checked by ${esc(rv.positive.join(', '))}</div>` : ''}
          ${rv.open_objections && rv.open_objections.length ? `<div class="why">open objections: ${esc(rv.open_objections.join(', '))}</div>` : ''}</section>
        <section><h4>Written</h4><div class="kv"><span class="k">by</span><span>${esc(n.by)}</span><span class="k">at</span><span class="mono">${esc(String(n.at || '').replace('T', ' ').slice(0, 19))}</span>
          ${det && det.versions && det.versions.length > 1 ? `<span class="k">versions</span><span>${det.versions.map((v) => `v${v.v}${v.reason ? ' (' + esc(v.reason) + ')' : ''}`).join(' · ')}</span>` : ''}</div></section>
        ${fields.length ? `<section><h4>Fields</h4><div class="kv">${fields.map(([k, v]) => `<span class="k">${esc(k)}</span><span style="overflow-wrap:anywhere">${esc(typeof v === 'object' ? JSON.stringify(v) : v).slice(0, 600)}</span>`).join('')}</div></section>` : ''}
        <section><h4>Rests on</h4>${det ? (det.out || []).map((e) => nodeLink(e.dst, e.rel)).join('') || '<div class="dim">nothing</div>' : '<div class="dim">…</div>'}</section>
        <section><h4>What rests on it</h4>${det ? (det.in || []).map((e) => nodeLink(e.src, e.rel)).join('') || '<div class="dim">nothing</div>' : '<div class="dim">…</div>'}</section>
        ${why && why.nodes && why.nodes.length > 1 ? `<section><h4>Provenance <span class="dim">· everything it rests on, to the files</span></h4>${why.nodes.filter((x) => x.id !== n.id).slice(0, 40).map((x) => nodeLink(x.id)).join('')}</section>` : ''}
        ${imp && imp.dependents && imp.dependents.length ? `<section><h4>If it fell <span class="dim">· what would be at risk</span></h4>${imp.dependents.slice(0, 40).map((x) => nodeLink(x.node.id, x.rel)).join('')}</section>` : ''}`;
      };
      const title = `<span class="code">${esc(n.code)}</span><span class="pill neutral">${esc(m.L(n.type))}</span>`;
      drawer(title, esc(n.title), skeleton(null));
      const [det, why, imp] = await Promise.all([settle(src.node(n.id)), settle(src.why(n.id)), settle(src.impact(n.id))]);
      if (S.drawer && S.drawer.node === n.id) drawer(title, esc(n.title), skeleton(det, why, imp));
    }
    function openQuestion(code) {
      const m = S.m, sq = (m.stages || []).find((x) => x.code === code), q = (m.board || []).find((x) => x.code === code) || {};
      const qn = m.byCode.get(code);
      S.drawer = { q: code }; syncHash();
      const orders = (m.orders || []).filter((o) => o.target === code);
      drawer(`<span class="code">${esc(code)}</span><span class="pill neutral">${esc(m.L('question'))}</span>`, esc(q.text || (qn && qn.title) || ''), `
        ${sq && sq.workflow !== false ? `<section><h4>Stage</h4>${stageBar(sq)}<div style="margin-top:6px"><b>${esc(sq.stage)}</b> · stage ${sq.index} of ${sq.of}
          ${sq.complete ? ' <span class="pill ok">complete</span>' : ''}${sq.settled_by ? ` <span class="pill info">settled by ${esc(sq.settled_by)}</span>` : ''}${sq.next ? `<div class="dim">next: ${esc(sq.next)}</div>` : ''}</div></section>
        <section><h4>Gates</h4>${(sq.gates || []).map((g) => `<div class="gate" style="margin-bottom:9px"><span class="m ${g.met ? 'met' : 'no'}" aria-hidden="true">${g.met ? '✓' : ''}</span>
          <div><b>${esc(g.stage)}</b> <span class="mono dim">${esc(g.gate)}</span>${g.optional ? ' <span class="pill neutral">optional</span>' : ''} <span class="sr">${g.met ? 'met' : 'not met'}</span>
          <div class="dim">${g.met ? 'met by ' + (g.evidence || []).map(esc).join(', ') : esc(g.why)}${g.who ? ' · ' + esc(g.who) : ''}</div></div></div>`).join('')}</section>` : ''}
        <section><h4>Answered by</h4>${(q.answers || []).map((c) => { const n = m.byCode.get(c);
          return `<div style="margin-bottom:8px"><button type="button" class="btn" data-n="${esc(n ? n.id : c)}" style="padding:1px 8px">${esc(c)}</button> ${standingPill(n)}<div style="margin-top:3px">${esc((n || {}).title || '')}</div></div>`; }).join('') || '<div class="dim">No claim answers it yet.</div>'}</section>
        ${orders.length ? `<section><h4>Work orders</h4>${orders.map((o) => `<div class="link"><span class="code">${esc(o.code)}</span><span class="pill neutral">${esc(o.status)}</span><span class="dim">${esc(o.assignee)}</span></div>`).join('')}</section>` : ''}`);
    }

    // ── palette ──
    function palItems(q) {
      const m = S.m, x = q.trim().toLowerCase(), items = [];
      VIEWS.forEach(([k, , name], i) => items.push({ label: name, kind: `view · ${i + 1}`, run: () => setView(k) }));
      S.invs.forEach((i) => items.push({ label: `${i.code} · ${i.title}`, kind: S.profiles.get(i.id) || 'investigation', run: () => select(i.id) }));
      if (m) m.nodes.filter((n) => n.type !== 'review').forEach((n) => items.push({ label: `${n.code} · ${n.title || ''}`, kind: m.L(n.type), run: () => openNode(n.id) }));
      return (x ? items.filter((it) => it.label.toLowerCase().includes(x) || it.kind.toLowerCase().includes(x)) : items).slice(0, 60);
    }
    function palOpen() { $('#hg-pal').classList.add('open'); const i = $('#hg-pal-q'); i.value = ''; S.palIdx = 0; palDraw(); i.focus(); }
    function palClose() { $('#hg-pal').classList.remove('open'); }
    function palDraw() {
      const its = palItems($('#hg-pal-q').value);
      S.palIdx = Math.max(0, Math.min(S.palIdx, its.length - 1));
      $('#hg-pal-list').innerHTML = its.map((it, i) => `<li role="option" data-pi="${i}" aria-selected="${i === S.palIdx}"><span>${esc(it.label)}</span><span class="k">${esc(it.kind)}</span></li>`).join('') || '<li class="dim">No match.</li>';
      S.palCurrent = its;
    }

    // ── render ──
    const V = { overview: vOverview, live: vLive, pipeline: vPipeline, graph: vGraph, evidence: vEvidence, orders: vOrders, audit: vAudit, report: vReport };
    function render() {
      if (!S.m) return;
      try {
        status(); nav();
        const main = $('#hg-main'), y = main.scrollTop;
        main.innerHTML = V[S.view]();
        if (S.view === 'live') main.scrollTop = y;
        root.dataset.hgView = S.view; root.dataset.hgReady = '1';
        if (S.cy) { try { S.cy.destroy(); } catch { /* gone */ } S.cy = null; }
        // the scheduler's own decisions (accepting work orders) are work-order bookkeeping: shown with the work orders
        if (S.view === 'graph') S.cy = graphInto($('#hg-graph'), S.m.nodes.filter((n) => S.graphTypes.has(n.type) && (S.graphTypes.has('task') || !isBookkeeping(n))), S.m.edges);
        if (S.view === 'live') {
          const made = new Set(S.m.events.slice(0, S.cursor == null ? S.m.events.length : S.cursor).filter((e) => e.kind === 'create').map((e) => e.ref));
          S.cy = graphInto($('#hg-live-graph'), S.m.nodes.filter((n) => made.has(n.id) && n.type !== 'task' && !isBookkeeping(n)).slice(0, 400), S.m.edges);
        }
        syncHash();
      } catch (e) { fail(e); throw e; }
    }
    function setView(v) { if (!V[v]) return; if (v !== 'live') stopPlay(); S.view = v; render(); $('#hg-main').focus({ preventScroll: true }); }
    async function select(inv) { if (inv === S.inv) return; closeDrawer(); await openInv(inv); }
    function syncHash() {
      if (!opts.hash || !S.m) return;
      const p = new URLSearchParams({ view: S.view, inv: S.m.code !== 'INV' && S.invs.length > 1 ? S.inv : '' });
      if (!p.get('inv')) p.delete('inv');
      if (S.drawer && S.drawer.q) p.set('q', S.drawer.q);
      if (S.drawer && S.drawer.node) p.set('node', S.m.codeOf(S.drawer.node));
      if (S.view === 'live' && S.cursor != null) p.set('at', S.cursor);
      const h = '#' + p.toString();
      if (location.hash !== h) history.replaceState(null, '', h);
    }
    function setTheme(t) { root.dataset.theme = t; if (S.m) render(); }

    // ── events (delegated) ──
    root.addEventListener('click', (ev) => {
      const t = ev.target.closest('[data-v],[data-inv],[data-q],[data-n],[data-act],[data-sort],[data-evtype],[data-gtype],[data-pi]');
      if (!t || !root.contains(t)) { if (ev.target.id === 'hg-pal') palClose(); return; }
      if (t.dataset.v) return setView(t.dataset.v);
      if (t.dataset.inv) return select(t.dataset.inv);
      if (t.dataset.q) return openQuestion(t.dataset.q);
      if (t.dataset.n) return openNode(t.dataset.n);
      if (t.dataset.pi != null) { const it = S.palCurrent[+t.dataset.pi]; palClose(); if (it) it.run(); return; }
      if (t.dataset.sort) { S.sort = { k: t.dataset.sort, asc: S.sort.k === t.dataset.sort ? !S.sort.asc : true }; return render(); }
      if (t.dataset.evtype) { const x = t.dataset.evtype; S.ev.types.has(x) ? S.ev.types.delete(x) : S.ev.types.add(x); return render(); }
      if (t.dataset.gtype) { const x = t.dataset.gtype; S.graphTypes.has(x) ? S.graphTypes.delete(x) : S.graphTypes.add(x); return render(); }
      const a = t.dataset.act, m = S.m, slug = (m.code || 'inv').toLowerCase();
      if (a === 'close') return closeDrawer();
      if (a === 'lv-play') return S.playing ? (stopPlay(), render()) : play();
      if (a === 'lv-start') { stopPlay(); S.cursor = 0; return render(); }
      if (a === 'lv-live') { stopPlay(); S.cursor = null; return render(); }
      if (a === 'print') return global.print();
      if (a === 'md') return download(`${slug}-report.md`, (m.report && m.report.markdown) || '', 'text/markdown');
      if (a === 'bundle') return download(`${slug}.bundle.json`, JSON.stringify(src.bundle), 'application/json');
      if (a === 'json') return download(`${slug}-graph.json`, JSON.stringify({ nodes: m.nodes, edges: m.edges }, null, 1), 'application/json');
      if (a === 'png' && S.cy) { const u = S.cy.png({ full: true, scale: 2, bg: getComputedStyle(root).getPropertyValue('--surface') }); const l = document.createElement('a'); l.href = u; l.download = `${slug}-graph.png`; l.click(); return; }
      if (a === 'csv-evidence') return download(`${slug}-evidence.csv`, csv([['code', 'type', 'statement', 'author', 'standing'], ...evidenceRows().map((n) => [n.code, m.L(n.type), n.title, n.by, standingKey(n)])]), 'text/csv');
      if (a === 'csv-orders') return download(`${slug}-work-orders.csv`, csv([['code', 'status', 'assignee', 'target', 'issued', 'objective'], ...(m.orders || []).map((o) => [o.code, o.status, o.assignee, o.target, o.issued, o.objective])]), 'text/csv');
      if (a === 'csv-audit') return download(`${slug}-audit.csv`, csv([['seq', 'at', 'actor', 'kind', 'ref', 'what'], ...auditRows().map((e) => [e.seq, e.at, e.actor, e.kind, m.codeOf(e.ref), say(e, true)])]), 'text/csv');
    });
    root.addEventListener('input', (ev) => {
      const id = ev.target.id;
      if (id === 'hg-ev-q') { S.ev.q = ev.target.value; const pos = ev.target.selectionStart; render(); const i = $('#hg-ev-q'); if (i) { i.focus(); i.setSelectionRange(pos, pos); } }
      if (id === 'hg-lv-scrub') { stopPlay(); const v = +ev.target.value; S.cursor = v >= S.m.events.length ? null : v; render(); }
      if (id === 'hg-pal-q') { S.palIdx = 0; palDraw(); }
    });
    root.addEventListener('change', (ev) => {
      const id = ev.target.id;
      if (id === 'hg-ev-st') { S.ev.standing = ev.target.value; render(); }
      if (id === 'hg-au-actor') { S.audit.actor = ev.target.value; render(); }
      if (id === 'hg-au-kind') { S.audit.kind = ev.target.value; render(); }
      if (id === 'hg-lv-speed') { S.speed = +ev.target.value; if (S.playing) play(); }
      if (id === 'hg-lv-feed') { S.feed = ev.target.value; render(); }
      if (id === 'hg-trace-order') { S.traceOrder = ev.target.value; render(); }
    });
    const typing = (el) => el && (el.tagName === 'INPUT' || el.tagName === 'SELECT' || el.tagName === 'TEXTAREA' || el.isContentEditable);
    root.addEventListener('keydown', (ev) => {
      const palOpenNow = $('#hg-pal').classList.contains('open');
      if (palOpenNow) {
        if (ev.key === 'Escape') { ev.preventDefault(); return palClose(); }
        if (ev.key === 'ArrowDown') { ev.preventDefault(); S.palIdx++; return palDraw(); }
        if (ev.key === 'ArrowUp') { ev.preventDefault(); S.palIdx = Math.max(0, S.palIdx - 1); return palDraw(); }
        if (ev.key === 'Enter') { ev.preventDefault(); const it = (S.palCurrent || [])[S.palIdx]; palClose(); if (it) it.run(); return; }
        return;
      }
      if ((ev.key === 'k' || ev.key === 'K') && (ev.metaKey || ev.ctrlKey)) { ev.preventDefault(); return palOpen(); }
      if (ev.key === 'Escape') return closeDrawer();
      if ((ev.key === 'Enter' || ev.key === ' ') && ev.target.matches && ev.target.matches('tr.click, .lane.click')) { ev.preventDefault(); return ev.target.click(); }
      if (typing(ev.target) || ev.metaKey || ev.ctrlKey || ev.altKey) return;
      if (ev.key === '/') { ev.preventDefault(); return palOpen(); }
      if (/^[1-8]$/.test(ev.key)) return setView(VIEWS[+ev.key - 1][0]);
      if (ev.key === 't') { const t = root.dataset.theme === 'dark' ? 'light' : 'dark'; setTheme(t); if (opts.onTheme) opts.onTheme(t); }
    });
    $('#hg-search').addEventListener('click', palOpen);
    $('#hg-theme').addEventListener('click', () => { const t = root.dataset.theme === 'dark' ? 'light' : 'dark'; setTheme(t); if (opts.onTheme) opts.onTheme(t); });
    if (!root.hasAttribute('tabindex')) root.tabIndex = -1;

    if (live) setInterval(async () => {                    // investigations a swarm starts later appear in the nav
      if (!S.m || document.hidden) return;
      const before = S.invs.length;
      try { await loadInvestigations(); } catch { return; }
      if (S.invs.length !== before) nav();
    }, 10000);
    setInterval(() => {                                    // in-flight calls show their elapsed time while live
      if (S.view === 'live' && S.cursor == null && S.m && S.m.tel.length && openSpans(S.m.tel).length && !document.hidden) render();
    }, 1000);

    // ── start ──
    const fromHash = () => (opts.hash ? new URLSearchParams(location.hash.slice(1)) : new URLSearchParams());
    const ready = (async () => {
      try {
        await loadInvestigations();
        if (!S.invs.length) {
          $('#hg-main').innerHTML = `<div class="empty">This record has no investigations yet.${live ? ' Start a swarm against it and it appears here as soon as it begins.' : ' <code>hypgraph demo</code> builds one to explore.'}</div>`;
          root.dataset.hgReady = '1';
          if (!live) return;
          await new Promise((resolve) => {                 // a swarm started after the page: open it when it begins
            const t = setInterval(async () => {
              try { await loadInvestigations(); } catch { return; }
              if (S.invs.length) { clearInterval(t); resolve(); }
            }, 3000);
          });
        }
        const h = fromHash();
        const want = h.get('inv'), pick = S.invs.find((i) => i.id === want || i.code === want || S.profiles.get(i.id) === want) || S.invs[0];
        if (h.get('view') && V[h.get('view')]) S.view = h.get('view');
        await openInv(pick.id);
        if (h.get('at') && S.view === 'live') { S.cursor = Math.min(+h.get('at'), S.m.events.length); render(); }
        else if (opts.play || h.get('play')) replayFromStart();
        if (h.get('q')) openQuestion(h.get('q'));
        else if (h.get('node')) openNode(h.get('node'));
      } catch (e) {
        fail(e);
        $('#hg-main').innerHTML = `<div class="empty">Couldn't read the record: ${esc(e.message)}</div>`;
      }
    })();
    if (opts.hash && global.addEventListener) {          // a link, Back or Forward changes the fragment: follow it
      global.addEventListener('hashchange', async () => {
        if (!S.m) return;
        const h = fromHash(), want = h.get('inv');
        const pick = want && S.invs.find((i) => i.id === want || i.code === want || S.profiles.get(i.id) === want);
        if (pick && pick.id !== S.inv) await openInv(pick.id);
        if (h.get('view') && V[h.get('view')] && h.get('view') !== S.view) setView(h.get('view'));
        if (h.get('at') && S.view === 'live') { stopPlay(); S.cursor = Math.min(+h.get('at'), S.m.events.length); render(); }
        else if (h.get('play')) replayFromStart();
        if (h.get('q')) openQuestion(h.get('q'));
        else if (h.get('node')) openNode(h.get('node'));
      });
    }
    global.addEventListener && global.addEventListener('error', (e) => { if (e && e.filename && /hypgraph\.js/.test(e.filename)) fail(e.message); });
    return { ready, state: S, setView, setTheme, select, show: openNode, focus: openNode, question: openQuestion, source: src,
      destroy: () => { if (S.follow) S.follow(); stopPlay(); if (S.cy) S.cy.destroy(); root.innerHTML = ''; } };
  }

  const API = { mount, HttpSource, BundleSource, verifyBundle, sha256, version: VERSION, TYPE_COLOR };
  global.HypGraph = API;
  global.HypAtlas = global.HypAtlas || API;        // the Atlas's name, kept for one release
})(typeof window !== 'undefined' ? window : globalThis);
