// HypSwarm site: the hero's living record — the same drifting graph as hypgraph.com. Nodes drift; now and then a
// claim is checked (green ring), or a premise falls (red) and what rests on it dims. Here the nodes are seats and
// what they wrote; the look is kept identical so the two sites read as one family.
(function () {
  const root = document.documentElement;
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const cv = document.getElementById('hero-graph');
  if (!cv) return;
  const ctx = cv.getContext('2d');
  let W = 0, H = 0, dpr = 1, nodes = [], edges = [];
  const css = (n) => getComputedStyle(root).getPropertyValue(n).trim();
  const palette = () => ({ c: css('--accent'), v: css('--violet'), g: css('--green'), r: css('--red'), a: css('--amber'), l: css('--line2'), i: css('--ink3') });
  let P = palette();
  new MutationObserver(() => { P = palette(); }).observe(root, { attributes: true, attributeFilter: ['data-theme'] });
  function size() {
    dpr = Math.min(2, window.devicePixelRatio || 1);
    W = cv.clientWidth; H = cv.clientHeight; cv.width = W * dpr; cv.height = H * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  function seed() {
    const n = Math.round(Math.min(70, Math.max(26, W * H / 16000)));
    nodes = Array.from({ length: n }, (_, i) => ({ x: Math.random() * W, y: Math.random() * H, vx: (Math.random() - .5) * .18,
      vy: (Math.random() - .5) * .18, r: 2 + Math.random() * 3.2, k: ['c', 'v', 'g', 'a'][i % 4], ring: 0, fall: 0, glow: 0 }));
    edges = [];
    nodes.forEach((a, i) => {
      const near = nodes.map((b, j) => [j, Math.hypot(a.x - b.x, a.y - b.y)]).filter(([j]) => j !== i).sort((p, q) => p[1] - q[1]).slice(0, 2);
      near.forEach(([j]) => { if (!edges.some((e) => (e[0] === j && e[1] === i))) edges.push([i, j]); });
    });
  }
  function event() {
    const a = nodes[Math.floor(Math.random() * nodes.length)];
    if (Math.random() < .7) { a.ring = 1; a.glow = 1; }                    // a claim checked
    else {                                                               // a premise falls: what rests on it dims
      a.fall = 1;
      edges.filter((e) => e[0] === nodes.indexOf(a)).forEach((e) => { nodes[e[1]].fall = Math.max(nodes[e[1]].fall, .6); });
    }
  }
  let last = 0, acc = 0;
  function frame(t) {
    const dt = Math.min(50, t - last || 16); last = t; acc += dt;
    if (acc > 1400) { acc = 0; event(); }
    ctx.clearRect(0, 0, W, H);
    for (const n of nodes) {
      n.x += n.vx * dt * .06; n.y += n.vy * dt * .06;
      if (n.x < -10) n.x = W + 10; if (n.x > W + 10) n.x = -10; if (n.y < -10) n.y = H + 10; if (n.y > H + 10) n.y = -10;
      n.glow *= .985; n.fall *= .992; if (n.ring) n.ring *= .996;
    }
    ctx.lineWidth = 1;
    for (const [i, j] of edges) {
      const a = nodes[i], b = nodes[j], d = Math.hypot(a.x - b.x, a.y - b.y);
      if (d > 220) continue;
      ctx.globalAlpha = (1 - d / 220) * .55 * (1 - Math.max(a.fall, b.fall) * .8);
      ctx.strokeStyle = a.glow > .2 ? P.g : P.l;
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
    }
    for (const n of nodes) {
      ctx.globalAlpha = .85 * (1 - n.fall * .85);
      ctx.fillStyle = n.fall > .5 ? P.r : P[n.k];
      ctx.beginPath(); ctx.arc(n.x, n.y, n.r, 0, 6.283); ctx.fill();
      if (n.ring > .05) {
        ctx.globalAlpha = n.ring; ctx.strokeStyle = P.g; ctx.lineWidth = 1.5;
        ctx.beginPath(); ctx.arc(n.x, n.y, n.r + 4 + (1 - n.ring) * 6, 0, 6.283); ctx.stroke(); ctx.lineWidth = 1;
      }
    }
    ctx.globalAlpha = 1;
    if (!reduce && !document.hidden) requestAnimationFrame(frame);
  }
  size(); seed();
  addEventListener('resize', () => { size(); seed(); if (reduce) frame(0); });
  document.addEventListener('visibilitychange', () => { if (!document.hidden && !reduce) requestAnimationFrame(frame); });
  if (reduce) frame(0); else requestAnimationFrame(frame);
})();
