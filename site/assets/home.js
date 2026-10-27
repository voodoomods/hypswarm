/* hypswarm.com homepage: fills every figure from site-data.js (the page's own HypGraph record, built by
   dev/site_record.py) and runs the HypGraph app on a HypSwarm run, replayed, or on that record. */
'use strict';
(() => {
  const P = window.SITE_DATA || { facts: {}, standing: {}, overclaims: [], lint: { findings: [] }, data_ok: [] };
  const $ = (s) => document.querySelector(s), $$ = (s) => [...document.querySelectorAll(s)];
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const root = document.documentElement;
  const theme = () => (window.HG ? window.HG.theme() : root.dataset.theme || 'light');

  // ── figures, from the record ──
  $$('[data-fact]').forEach((el) => { const v = P.facts[el.dataset.fact]; if (v != null) el.textContent = v; });
  const REVIEW = { replicated: ['ok', 'replicated'], checked: ['ok', 'checked'], contested: ['bad', 'contested'],
    objection: ['bad', 'objection'], unchecked: ['', 'unchecked'] };
  const badge = (k) => {
    const st = P.standing[k]; if (!st) return '';
    const [cls, word] = REVIEW[st.review] || ['', st.review || 'unchecked'];
    return `<button type="button" class="pill ${cls}" data-open-claim="${esc(k)}" title="${esc(st.summary)}">${esc(st.code)} · ${esc(word)} ↗</button>`;
  };
  $$('[data-claim]').forEach((el) => { el.innerHTML = badge(el.dataset.claim); });

  // ── the stage: the app on one bundle at a time ──
  const EXAMPLES = ['scientific', 'software', 'trading', 'knowledge', 'optimization'];
  const SOURCES = EXAMPLES.map((k) => [k, k[0].toUpperCase() + k.slice(1), `data/examples/${k}.bundle.json`])
    .concat([['page', 'This page’s record', 'data/site-record.bundle.json']]);
  const FOOT = {
    page: 'The record behind the figures on this page: each claim bound to the lab’s measurement and re-measured another way by a reviewer.',
    _: 'A HypSwarm run on this repository’s scripted models (answers computed by the example, each reply paced 0.35–1.4 s), replayed from its record and telemetry. The telemetry rides along outside the hash chain.',
  };
  const tabs = $('#stage-tabs'), app = $('#app');
  let view = null, current = null;
  tabs.innerHTML = SOURCES.map(([k, label]) => `<button type="button" data-src="${k}" aria-pressed="false">${esc(label)}</button>`).join('');
  async function show(key, then) {
    const src = SOURCES.find((s) => s[0] === key); if (!src || !window.HypGraph) return;
    tabs.querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.src === key)));
    $('#stage-foot').textContent = FOOT[key] || FOOT._;
    if (key !== current) {
      $('#stage-chain').textContent = 'verifying…'; $('#stage-chain').className = 'pill';
      if (view) view.destroy();
      current = key;
      const bundle = await (await fetch(src[2])).json();
      view = HypGraph.mount(app, { source: HypGraph.BundleSource(bundle), theme: theme(), play: EXAMPLES.includes(key),
        onTheme: (t) => { root.dataset.theme = t; try { localStorage.setItem('hg-theme', t); } catch { /* private */ } (window.HG ? window.HG.onTheme : []).forEach((f) => f(t)); } });
      await view.ready;
      const v = await HypGraph.verifyBundle(bundle);
      $('#stage-chain').textContent = v.ok ? `⛓ chain verified · ${v.checked} events` : `✗ chain broken at #${v.broken_at}`;
      $('#stage-chain').className = 'pill ' + (v.ok ? 'ok' : 'bad');
    }
    if (then) then(view);
  }
  if (window.HG) window.HG.onTheme.push((t) => { if (view) view.setTheme(t); });
  tabs.addEventListener('click', (e) => { const b = e.target.closest('[data-src]'); if (b) show(b.dataset.src); });
  document.addEventListener('click', (e) => {
    const w = e.target.closest('[data-show]');
    if (w) { e.preventDefault(); $('#product').scrollIntoView({ block: 'start' }); show(w.dataset.show); return; }
    const c = e.target.closest('[data-open-claim]');
    if (c) {
      const st = P.standing[c.dataset.openClaim];
      $('#product').scrollIntoView({ block: 'start' });
      show('page', (v) => { v.setView('evidence'); if (st) v.show(st.id);
        setTimeout(() => $('#product').scrollIntoView({ block: 'start', behavior: 'instant' }), 400); });   // after the drawer takes focus
    }
  });
  show('software');

  // ── the page's own record ──
  const rows = Object.entries(P.standing).map(([k, st]) => {
    const [cls, word] = REVIEW[st.review] || ['', st.review || 'unchecked'];
    return `<tr><td>${badge(k)}</td><td>${esc(st.statement)}<div style="font-size:12.5px;color:var(--ink2);margin-top:2px">${esc(st.summary)}</div></td><td><span class="pill ${cls}">${esc(word)}</span><div style="font-size:12px;color:var(--ink2);margin-top:4px">${esc((st.verdicts || []).join(', '))}</div></td></tr>`;
  }).join('');
  const L = P.lint || { findings: [] };
  const lintRows = (L.findings || []).map((f) => `<li><code>${esc(f.code)}</code> ${esc(f.level)} · ${esc(f.excerpt)} — ${esc(f.message)}</li>`).join('');
  const okRows = (P.data_ok || []).map((d) => `<li>“${esc(d.text)}” — ${esc(d.why)}</li>`).join('');
  $('#record-claims').innerHTML = `<div class="tbl-wrap"><table class="tbl"><thead><tr><th>claim</th><th>the claim, and what the record derives about it</th><th>review</th></tr></thead><tbody>${rows}</tbody></table></div>
    <div class="grid2" style="margin-top:16px">
      <div class="card"><h3>The text of this page, checked against the record</h3>
        <p><code>hypgraph check</code> on <a href="data/homepage-checked.md">the page as read</a>: ${L.errors ?? '—'} errors, ${L.warnings ?? '—'} warnings.</p>
        ${lintRows ? `<ul style="margin:8px 0 0;padding-left:18px;color:var(--ink2);font-size:14px">${lintRows}</ul>` : ''}</div>
      <div class="card"><h3>Phrases true by design</h3>
        <ul style="margin:0;padding-left:18px;color:var(--ink2);font-size:14px">${okRows || '<li>None.</li>'}</ul></div></div>
    <p class="note">Built ${esc(String(P.built || '').replace('T', ' ').replace('Z', ' UTC'))} · chain head <code>${esc(String(P.head || '').slice(0, 16))}…</code></p>`;
})();
