import { useEffect, useRef } from 'react';

// Animated "iris" of repository nodes: glowing fibres radiate from a ring,
// each ending in a node. Hub nodes are linked by thin edges with data pulses.
// Pure canvas, no dependencies. Reacts to the cursor.

const TAU = Math.PI * 2;
const FIBRES = 260;
const HUB_EVERY = 13;

function rand(seed) {
  // small deterministic PRNG so the layout is stable between renders
  let s = seed;
  return () => {
    s = (s * 1664525 + 1013904223) % 4294967296;
    return s / 4294967296;
  };
}

function buildScene() {
  const r = rand(7);
  const fibres = [];
  for (let i = 0; i < FIBRES; i += 1) {
    fibres.push({
      a: (i / FIBRES) * TAU + (r() - 0.5) * 0.012,
      len: 0.16 + Math.pow(r(), 1.6) * 0.42,
      phase: r() * TAU,
      speed: 0.5 + r() * 0.9,
      width: 0.6 + r() * 1.1,
      hub: i % HUB_EVERY === 0,
      tone: r(),
    });
  }
  const hubs = fibres.filter((f) => f.hub);
  const edges = [];
  hubs.forEach((h, i) => {
    edges.push([i, (i + 1) % hubs.length]);
    edges.push([i, (i + 4) % hubs.length]);
    if (i % 3 === 0) edges.push([i, (i + Math.floor(hubs.length / 2)) % hubs.length]);
  });
  const pulses = edges.map((e, i) => ({ e, t: (i * 0.137) % 1, v: 0.08 + (i % 5) * 0.02 }));
  return { fibres, hubs, edges, pulses };
}

export default function HeroGraph({ className = '' }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    const scene = buildScene();
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    let w = 0;
    let h = 0;
    let dpr = 1;
    let raf = 0;
    const mouse = { x: 0, y: 0, tx: 0, ty: 0, on: 0, ton: 0 };
    const start = performance.now();

    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = rect.width;
      h = rect.height;
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    const onMove = (e) => {
      const rect = canvas.getBoundingClientRect();
      mouse.tx = e.clientX - rect.left - w / 2;
      mouse.ty = e.clientY - rect.top - h / 2;
      mouse.ton = 1;
    };
    const onLeave = () => {
      mouse.ton = 0;
    };

    const draw = (now) => {
      const t = reduce ? 6 : (now - start) / 1000;
      const intro = Math.min(1, t / 2.4);
      const ease = 1 - Math.pow(1 - intro, 4);

      mouse.x += (mouse.tx - mouse.x) * 0.08;
      mouse.y += (mouse.ty - mouse.y) * 0.08;
      mouse.on += (mouse.ton - mouse.on) * 0.06;

      ctx.clearRect(0, 0, w, h);
      const cx = w / 2 + mouse.x * -0.02;
      const cy = h / 2 + mouse.y * -0.02;
      const R = Math.min(w * 0.5, h * 0.5) * 0.96;
      const inner = R * 0.42 * (0.55 + 0.45 * ease);
      const spin = t * 0.045;
      const mouseAngle = Math.atan2(mouse.y, mouse.x);

      // soft amber glow under the ring
      const glow = ctx.createRadialGradient(cx, cy, inner * 0.6, cx, cy, R * 1.05);
      glow.addColorStop(0, 'rgba(255,196,80,0)');
      glow.addColorStop(0.55, `rgba(255,176,48,${0.2 * ease})`);
      glow.addColorStop(1, 'rgba(255,176,48,0)');
      ctx.fillStyle = glow;
      ctx.fillRect(0, 0, w, h);

      // faint orbit guides + tick marks (like the thin outer ring in the reference)
      ctx.strokeStyle = 'rgba(255,255,255,0.55)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.arc(cx, cy, R * 1.04, 0, TAU);
      ctx.stroke();
      ctx.strokeStyle = 'rgba(40,40,40,0.12)';
      ctx.beginPath();
      ctx.arc(cx, cy, inner * 0.9, 0, TAU);
      ctx.stroke();
      for (let i = 0; i < 72; i += 1) {
        const a = (i / 72) * TAU + spin * 0.4;
        const long = i % 6 === 0;
        const r1 = R * 1.04;
        const r2 = r1 + (long ? 14 : 6) * ease;
        ctx.strokeStyle = long ? 'rgba(255,255,255,0.9)' : 'rgba(255,255,255,0.55)';
        ctx.beginPath();
        ctx.moveTo(cx + Math.cos(a) * r1, cy + Math.sin(a) * r1);
        ctx.lineTo(cx + Math.cos(a) * r2, cy + Math.sin(a) * r2);
        ctx.stroke();
      }

      // fibres
      const tips = [];
      ctx.lineCap = 'round';
      for (let i = 0; i < scene.fibres.length; i += 1) {
        const f = scene.fibres[i];
        const a = f.a + spin;
        let d = Math.abs(((a - mouseAngle + Math.PI * 3) % TAU) - Math.PI);
        d = Math.min(d, TAU - d);
        const near = Math.exp(-(d * d) / 0.06) * mouse.on;
        const breathe = 1 + 0.14 * Math.sin(t * f.speed + f.phase);
        const len = R * f.len * breathe * ease * (1 + near * 0.55);
        const r1 = inner;
        const r2 = inner + len;
        const x1 = cx + Math.cos(a) * r1;
        const y1 = cy + Math.sin(a) * r1;
        const x2 = cx + Math.cos(a) * r2;
        const y2 = cy + Math.sin(a) * r2;

        const g = ctx.createLinearGradient(x1, y1, x2, y2);
        g.addColorStop(0, 'rgba(70,40,24,0.85)');
        g.addColorStop(0.45, `rgba(214,120,40,${0.7 + near * 0.3})`);
        g.addColorStop(1, `rgba(255,${200 + Math.floor(f.tone * 40)},70,1)`);
        ctx.strokeStyle = g;
        ctx.lineWidth = f.width * (f.hub ? 1.5 : 1);
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();

        // node at the tip
        const rad = f.hub ? 3.4 + near * 2 : 1.3 + f.tone * 0.9 + near * 1.2;
        ctx.fillStyle = f.hub ? '#ffd24a' : '#ffc23a';
        ctx.beginPath();
        ctx.arc(x2, y2, rad, 0, TAU);
        ctx.fill();
        if (f.hub) {
          ctx.strokeStyle = `rgba(255,255,255,${0.9 * ease})`;
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.arc(x2, y2, rad + 4 + 1.5 * Math.sin(t * 1.6 + f.phase), 0, TAU);
          ctx.stroke();
          tips.push([x2, y2]);
        } else if (f.tone > 0.97) {
          tips.push(null);
        }
        if (f.hub) f.cache = [x2, y2];
      }

      // hub-to-hub edges and travelling pulses
      ctx.lineWidth = 0.8;
      ctx.strokeStyle = 'rgba(60,45,30,0.22)';
      scene.edges.forEach(([i, j]) => {
        const A = scene.hubs[i].cache;
        const B = scene.hubs[j].cache;
        if (!A || !B) return;
        ctx.beginPath();
        ctx.moveTo(A[0], A[1]);
        ctx.lineTo(B[0], B[1]);
        ctx.stroke();
      });
      if (!reduce) {
        scene.pulses.forEach((p) => {
          p.t = (p.t + p.v * 0.016) % 1;
          const A = scene.hubs[p.e[0]].cache;
          const B = scene.hubs[p.e[1]].cache;
          if (!A || !B) return;
          const x = A[0] + (B[0] - A[0]) * p.t;
          const y = A[1] + (B[1] - A[1]) * p.t;
          ctx.fillStyle = 'rgba(255,170,30,0.95)';
          ctx.beginPath();
          ctx.arc(x, y, 2, 0, TAU);
          ctx.fill();
        });
      }

      // bright core ring (the "pupil")
      ctx.strokeStyle = `rgba(255,255,255,${0.95 * ease})`;
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.arc(cx, cy, inner - 4, 0, TAU);
      ctx.stroke();
      const core = ctx.createRadialGradient(cx, cy, 0, cx, cy, inner - 4);
      core.addColorStop(0, 'rgba(255,255,255,0.0)');
      core.addColorStop(1, 'rgba(255,255,255,0.55)');
      ctx.fillStyle = core;
      ctx.beginPath();
      ctx.arc(cx, cy, inner - 4, 0, TAU);
      ctx.fill();

      if (!reduce) raf = requestAnimationFrame(draw);
    };

    resize();
    const ro = new ResizeObserver(() => {
      resize();
      if (reduce) draw(performance.now());
    });
    ro.observe(canvas);
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerleave', onLeave);
    raf = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerleave', onLeave);
    };
  }, []);

  return <canvas ref={canvasRef} className={className} aria-hidden="true" />;
}
