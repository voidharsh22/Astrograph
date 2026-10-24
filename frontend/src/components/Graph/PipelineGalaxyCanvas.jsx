import { useEffect, useRef } from 'react';

/**
 * PipelineGalaxyCanvas
 * High-performance, lightweight HTML5 Canvas rendering an evolving celestial
 * graph constellation that mirrors the 9 repository analysis pipeline stages.
 */
export default function PipelineGalaxyCanvas({ stage = 'ingestion', progress = 10, isComplete = false }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationFrameId;
    let width = (canvas.width = canvas.offsetWidth);
    let height = (canvas.height = canvas.offsetHeight);

    const handleResize = () => {
      if (!canvas) return;
      width = canvas.width = canvas.offsetWidth;
      height = canvas.height = canvas.offsetHeight;
    };
    window.addEventListener('resize', handleResize);

    // Check prefers-reduced-motion
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    // Starfield particles
    const starCount = 90;
    const stars = Array.from({ length: starCount }, () => ({
      x: Math.random() * width,
      y: Math.random() * height,
      radius: Math.random() * 1.2 + 0.3,
      alpha: Math.random() * 0.7 + 0.2,
      twinkleSpeed: Math.random() * 0.02 + 0.005,
    }));

    // Constellation graph nodes
    const communityColors = ['#38BDF8', '#C084FC', '#34D399', '#FB923C', '#F472B6'];
    const clusterCenters = [
      { x: -140, y: -60, color: '#38BDF8' },  // Routes / APIs
      { x: 130, y: -70, color: '#C084FC' },   // Services
      { x: -120, y: 80, color: '#34D399' },   // Models
      { x: 140, y: 70, color: '#F59E0B' },    // Utils / DB
    ];

    const nodeCount = 48;
    const nodes = Array.from({ length: nodeCount }, (_, i) => {
      const clusterIdx = i % clusterCenters.length;
      const center = clusterCenters[clusterIdx];
      const spread = 75;
      const angle = Math.random() * Math.PI * 2;
      const dist = Math.random() * spread;
      return {
        id: i,
        relX: center.x + Math.cos(angle) * dist,
        relY: center.y + Math.sin(angle) * dist,
        cluster: clusterIdx,
        color: communityColors[clusterIdx],
        size: i === 0 ? 7 : Math.random() * 3 + 2,
        isCore: i === 0,
        orbitAngle: Math.random() * Math.PI * 2,
        orbitSpeed: (Math.random() * 0.003 + 0.001) * (i % 2 === 0 ? 1 : -1),
      };
    });

    let rotationAngle = 0;

    const render = () => {
      ctx.clearRect(0, 0, width, height);

      // Deep space cosmic gradient
      const bgGrad = ctx.createRadialGradient(width / 2, height / 2, 20, width / 2, height / 2, width * 0.65);
      bgGrad.addColorStop(0, '#0c1428');
      bgGrad.addColorStop(0.5, '#050914');
      bgGrad.addColorStop(1, '#020308');
      ctx.fillStyle = bgGrad;
      ctx.fillRect(0, 0, width, height);

      // 1. Draw Starfield
      for (const star of stars) {
        if (!prefersReducedMotion) {
          star.alpha += Math.sin(Date.now() * star.twinkleSpeed) * 0.008;
        }
        ctx.beginPath();
        ctx.arc(star.x, star.y, star.radius, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(255, 247, 237, ${Math.max(0.1, Math.min(1, star.alpha))})`;
        ctx.fill();
      }

      // 2. Soft Ambient Planet on Bottom-Left Horizon
      const planetX = width * 0.08;
      const planetY = height * 0.95;
      const planetRadius = height * 0.45;

      const planetGlow = ctx.createRadialGradient(planetX, planetY, planetRadius * 0.4, planetX, planetY, planetRadius * 1.2);
      planetGlow.addColorStop(0, 'rgba(251, 146, 60, 0.28)');
      planetGlow.addColorStop(0.6, 'rgba(251, 146, 60, 0.05)');
      planetGlow.addColorStop(1, 'rgba(0, 0, 0, 0)');
      ctx.fillStyle = planetGlow;
      ctx.beginPath();
      ctx.arc(planetX, planetY, planetRadius * 1.2, 0, Math.PI * 2);
      ctx.fill();

      // Planet surface
      ctx.beginPath();
      ctx.arc(planetX, planetY, planetRadius, 0, Math.PI * 2);
      const planetBody = ctx.createLinearGradient(planetX - planetRadius, planetY - planetRadius, planetX + planetRadius, planetY + planetRadius);
      planetBody.addColorStop(0, '#1a243c');
      planetBody.addColorStop(0.5, '#0b1122');
      planetBody.addColorStop(1, '#020308');
      ctx.fillStyle = planetBody;
      ctx.fill();
      ctx.lineWidth = 1;
      ctx.strokeStyle = 'rgba(251, 146, 60, 0.45)';
      ctx.stroke();

      // Planetary ring
      ctx.save();
      ctx.translate(planetX, planetY);
      ctx.rotate(-0.35);
      ctx.scale(1, 0.28);
      ctx.beginPath();
      ctx.arc(0, 0, planetRadius * 1.5, 0, Math.PI * 2);
      ctx.strokeStyle = 'rgba(253, 186, 116, 0.35)';
      ctx.lineWidth = 1.5;
      ctx.stroke();
      ctx.restore();

      // 3. Central Constellation Graph
      const centerX = width / 2;
      const centerY = height / 2;

      if (!prefersReducedMotion) {
        rotationAngle += 0.002;
      }

      // Stage-dependent thresholds
      // 0 - 30%: faint stars, low edges
      // 30 - 60%: edges visible, nodes expanding
      // 60 - 90%: clusters color-coded, active filaments
      // 90 - 100%: full galaxy sweep
      const p = Math.max(10, Math.min(100, progress));
      const visibleNodeCount = Math.floor((p / 100) * nodeCount);
      const edgeOpacity = Math.min(0.5, (p / 100) * 0.55);

      // Pre-compute node screen positions
      const screenPositions = [];
      for (let i = 0; i < visibleNodeCount; i++) {
        const n = nodes[i];
        const rotX = n.relX * Math.cos(rotationAngle) - n.relY * Math.sin(rotationAngle);
        const rotY = n.relX * Math.sin(rotationAngle) + n.relY * Math.cos(rotationAngle);
        screenPositions.push({
          x: centerX + rotX,
          y: centerY + rotY,
          color: p > 55 ? n.color : '#94A3B8',
          size: n.size,
          isCore: n.isCore,
        });
      }

      // Draw Edges
      if (p >= 35 && screenPositions.length > 2) {
        ctx.lineWidth = 0.8;
        for (let i = 0; i < screenPositions.length; i++) {
          for (let j = i + 1; j < screenPositions.length; j++) {
            const dx = screenPositions[i].x - screenPositions[j].x;
            const dy = screenPositions[i].y - screenPositions[j].y;
            const dist = Math.sqrt(dx * dx + dy * dy);

            // Connect nearest neighbor nodes
            if (dist < 85) {
              const alpha = (1 - dist / 85) * edgeOpacity;
              ctx.strokeStyle = `rgba(251, 146, 60, ${alpha})`;
              ctx.beginPath();
              ctx.moveTo(screenPositions[i].x, screenPositions[i].y);
              ctx.lineTo(screenPositions[j].x, screenPositions[j].y);
              ctx.stroke();
            }
          }
        }
      }

      // Central Solar Core Node
      if (p >= 40) {
        const pulse = 1 + Math.sin(Date.now() * 0.004) * 0.2;
        const coreGrad = ctx.createRadialGradient(centerX, centerY, 3, centerX, centerY, 24 * pulse);
        coreGrad.addColorStop(0, '#FB923C');
        coreGrad.addColorStop(0.4, 'rgba(251, 146, 60, 0.4)');
        coreGrad.addColorStop(1, 'rgba(251, 146, 60, 0)');
        ctx.fillStyle = coreGrad;
        ctx.beginPath();
        ctx.arc(centerX, centerY, 24 * pulse, 0, Math.PI * 2);
        ctx.fill();

        ctx.fillStyle = '#FB923C';
        ctx.beginPath();
        ctx.arc(centerX, centerY, 6, 0, Math.PI * 2);
        ctx.fill();

        ctx.fillStyle = '#FFF7ED';
        ctx.beginPath();
        ctx.arc(centerX, centerY, 2.5, 0, Math.PI * 2);
        ctx.fill();
      }

      // Draw Nodes
      for (const n of screenPositions) {
        ctx.beginPath();
        ctx.arc(n.x, n.y, n.size, 0, Math.PI * 2);
        ctx.fillStyle = n.color;
        ctx.shadowColor = n.color;
        ctx.shadowBlur = 8;
        ctx.fill();
        ctx.shadowBlur = 0; // reset
      }

      animationFrameId = requestAnimationFrame(render);
    };

    render();

    return () => {
      cancelAnimationFrame(animationFrameId);
      window.removeEventListener('resize', handleResize);
    };
  }, [stage, progress, isComplete]);

  return <canvas ref={canvasRef} className="analyze-vis-canvas" />;
}

