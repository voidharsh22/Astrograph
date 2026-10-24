import { useEffect, useRef } from 'react';

export default function GalaxyBackground() {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let animationFrameId;

    let w = (canvas.width = window.innerWidth);
    let h = (canvas.height = window.innerHeight);

    const handleResize = () => {
      if (!canvas) return;
      w = canvas.width = window.innerWidth;
      h = canvas.height = window.innerHeight;
    };

    window.addEventListener('resize', handleResize);

    // Generate 280 twinkling cosmic stars with natural depth
    const stars = [];
    const STAR_COUNT = 280;
    const colors = ['#FFF7ED', '#FB923C', '#FDBA74', '#93C5FD', '#FFFFFF'];

    for (let i = 0; i < STAR_COUNT; i++) {
      stars.push({
        x: Math.random() * w,
        y: Math.random() * h,
        radius: Math.random() * 1.4 + 0.3,
        color: colors[Math.floor(Math.random() * colors.length)],
        baseAlpha: Math.random() * 0.7 + 0.2,
        alpha: Math.random() * 0.7 + 0.2,
        twinkleSpeed: Math.random() * 0.02 + 0.005,
        phase: Math.random() * Math.PI * 2
      });
    }

    let time = 0;

    const render = () => {
      ctx.clearRect(0, 0, w, h);
      time += 0.015;

      // Draw all twinkling stars
      for (let i = 0; i < stars.length; i++) {
        const star = stars[i];
        const currentAlpha = star.baseAlpha + Math.sin(time + star.phase) * 0.35;
        const clampedAlpha = Math.max(0.08, Math.min(1, currentAlpha));

        ctx.beginPath();
        ctx.arc(star.x, star.y, star.radius, 0, Math.PI * 2);
        ctx.fillStyle = star.color;
        ctx.globalAlpha = clampedAlpha;
        ctx.fill();

        // Soft subtle glow for brighter stars
        if (star.radius > 1.2) {
          ctx.beginPath();
          ctx.arc(star.x, star.y, star.radius * 2.5, 0, Math.PI * 2);
          ctx.fillStyle = star.color;
          ctx.globalAlpha = clampedAlpha * 0.25;
          ctx.fill();
        }
      }

      ctx.globalAlpha = 1;
      animationFrameId = requestAnimationFrame(render);
    };

    render();

    return () => {
      window.removeEventListener('resize', handleResize);
      cancelAnimationFrame(animationFrameId);
    };
  }, []);

  return (
    <div className="galaxy-cosmos-wrapper">
      {/* 1. Deep Space Cosmic Background Gradients */}
      <div className="galaxy-deep-space" />

      {/* 2. Procedural Twinkling Starfield Canvas */}
      <canvas ref={canvasRef} className="galaxy-stars-canvas" />

      {/* 3. Volumetric Warm Nebula Clouds */}
      <div className="galaxy-nebula-amber" />
      <div className="galaxy-nebula-center" />
      <div className="galaxy-nebula-bottom" />

      {/* 4. Massive Luminous Celestial Ringed Planet (Bottom-Left - Exact match to Image 2) */}
      <div className="galaxy-bottom-planet-wrap">
        <svg
          viewBox="0 0 650 650"
          className="w-full h-full"
          preserveAspectRatio="xMidYMid meet"
        >
          <defs>
            {/* Dark celestial sphere with amber rim illumination */}
            <radialGradient id="dashPlanetSphere" cx="72%" cy="28%" r="72%">
              <stop offset="0%" stopColor="#253556" />
              <stop offset="35%" stopColor="#111a2f" />
              <stop offset="70%" stopColor="#080e1c" />
              <stop offset="100%" stopColor="#020409" />
            </radialGradient>

            {/* Glowing rim-light along the planet horizon */}
            <radialGradient id="dashPlanetRimGlow" cx="68%" cy="32%" r="65%">
              <stop offset="0%" stopColor="#FB923C" stopOpacity="0.85" />
              <stop offset="40%" stopColor="#F59E0B" stopOpacity="0.4" />
              <stop offset="75%" stopColor="#FB923C" stopOpacity="0" />
            </radialGradient>

            {/* Luminous orbital ring specular gradient */}
            <linearGradient id="dashRingGrad" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#FDBA74" stopOpacity="0.95" />
              <stop offset="45%" stopColor="#FB923C" stopOpacity="0.8" />
              <stop offset="75%" stopColor="#D97706" stopOpacity="0.4" />
              <stop offset="100%" stopColor="#FB923C" stopOpacity="0.05" />
            </linearGradient>

            <linearGradient id="dashRingFaint" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#FFFFFF" stopOpacity="0.4" />
              <stop offset="50%" stopColor="#FB923C" stopOpacity="0.25" />
              <stop offset="100%" stopColor="#FB923C" stopOpacity="0.02" />
            </linearGradient>

            {/* Glow filter */}
            <filter id="amberGlow" x="-20%" y="-20%" width="140%" height="140%">
              <feGaussianBlur stdDeviation="8" result="blur" />
              <feComposite in="SourceGraphic" in2="blur" operator="over" />
            </filter>
          </defs>

          {/* BACK HALF OF ORBITAL RINGS (behind planet) */}
          <g transform="rotate(-34 300 350)">
            {/* Outer faint ring */}
            <ellipse cx="300" cy="350" rx="310" ry="92" fill="none" stroke="url(#dashRingFaint)" strokeWidth="1.2" />
            
            {/* Wide soft glow track */}
            <ellipse cx="300" cy="350" rx="275" ry="80" fill="none" stroke="#FB923C" strokeWidth="8" strokeOpacity="0.12" filter="url(#amberGlow)" />
            
            {/* Main sharp illuminated orbital rings */}
            <ellipse cx="300" cy="350" rx="270" ry="78" fill="none" stroke="url(#dashRingGrad)" strokeWidth="3" />
            <ellipse cx="300" cy="350" rx="264" ry="75" fill="none" stroke="#FFF7ED" strokeWidth="1" strokeOpacity="0.75" />
            <ellipse cx="300" cy="350" rx="252" ry="70" fill="none" stroke="url(#dashRingGrad)" strokeWidth="2" strokeOpacity="0.6" />
            <ellipse cx="300" cy="350" rx="235" ry="64" fill="none" stroke="#FDBA74" strokeWidth="1" strokeOpacity="0.35" />
          </g>

          {/* PLANET SPHERE */}
          {/* Planet outer atmosphere rim aura */}
          <circle cx="300" cy="350" r="142" fill="none" stroke="#FB923C" strokeWidth="2" strokeOpacity="0.6" filter="url(#amberGlow)" />
          
          {/* Planet Body */}
          <circle cx="300" cy="350" r="140" fill="url(#dashPlanetSphere)" />
          
          {/* Planet Crescent Rim Highlight */}
          <circle cx="300" cy="350" r="140" fill="url(#dashPlanetRimGlow)" />

          {/* FRONT HALF OF ORBITAL RINGS (in front of planet) */}
          <g transform="rotate(-34 300 350)">
            {/* Clipped front arc cutting over the planet */}
            <path
              d="M 25,350 A 275 80 0 0 0 575,350"
              fill="none"
              stroke="#FB923C"
              strokeWidth="9"
              strokeOpacity="0.18"
              filter="url(#amberGlow)"
            />
            <path
              d="M 30,350 A 270 78 0 0 0 570,350"
              fill="none"
              stroke="url(#dashRingGrad)"
              strokeWidth="3.2"
            />
            <path
              d="M 36,350 A 264 75 0 0 0 564,350"
              fill="none"
              stroke="#FFF7ED"
              strokeWidth="1.2"
              strokeOpacity="0.9"
            />
            <path
              d="M 48,350 A 252 70 0 0 0 552,350"
              fill="none"
              stroke="url(#dashRingGrad)"
              strokeWidth="2.2"
              strokeOpacity="0.75"
            />
            <path
              d="M 65,350 A 235 64 0 0 0 535,350"
              fill="none"
              stroke="#FDBA74"
              strokeWidth="1.2"
              strokeOpacity="0.45"
            />
          </g>
        </svg>
      </div>

      {/* 5. Glowing Celestial Constellation Network Sphere (Center-Top - Exact match to Image 2) */}
      <div className="galaxy-center-constellation-wrap">
        <svg
          viewBox="0 0 500 500"
          className="w-full h-full"
          preserveAspectRatio="xMidYMid meet"
        >
          <defs>
            <radialGradient id="sphereCoreGlow" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#FB923C" stopOpacity="0.55" />
              <stop offset="45%" stopColor="#F59E0B" stopOpacity="0.2" />
              <stop offset="85%" stopColor="#0B0F19" stopOpacity="0" />
            </radialGradient>
          </defs>

          {/* Central Amber Core Glow */}
          <circle cx="250" cy="250" r="160" fill="url(#sphereCoreGlow)" />

          {/* 3D Wireframe Longitudinal / Latitudinal Ellipses */}
          <g stroke="#FB923C" strokeOpacity="0.22" fill="none" strokeWidth="0.8">
            <circle cx="250" cy="250" r="125" strokeDasharray="3 3" />
            <ellipse cx="250" cy="250" rx="125" ry="42" strokeOpacity="0.45" strokeWidth="1" />
            <ellipse cx="250" cy="250" rx="125" ry="85" strokeOpacity="0.28" />
            <ellipse cx="250" cy="250" rx="42" ry="125" strokeOpacity="0.35" />
            <ellipse cx="250" cy="250" rx="85" ry="125" strokeOpacity="0.25" />
            <line x1="125" y1="250" x2="375" y2="250" strokeOpacity="0.3" />
            <line x1="250" y1="125" x2="250" y2="375" strokeOpacity="0.3" />
          </g>

          {/* Intricate Constellation Lines */}
          <g stroke="#FB923C" strokeOpacity="0.48" strokeWidth="1">
            <line x1="190" y1="210" x2="250" y2="180" />
            <line x1="250" y1="180" x2="310" y2="200" />
            <line x1="310" y1="200" x2="340" y2="260" />
            <line x1="340" y1="260" x2="290" y2="300" />
            <line x1="290" y1="300" x2="220" y2="295" />
            <line x1="220" y1="295" x2="190" y2="210" />
            <line x1="250" y1="180" x2="220" y2="295" strokeOpacity="0.3" />
            <line x1="190" y1="210" x2="290" y2="300" strokeOpacity="0.3" />
            <line x1="250" y1="180" x2="290" y2="300" strokeOpacity="0.35" />

            {/* External Satellite Rays */}
            <line x1="250" y1="180" x2="265" y2="135" stroke="#FDBA74" strokeOpacity="0.6" strokeDasharray="2 2" />
            <line x1="310" y1="200" x2="375" y2="175" stroke="#FDBA74" strokeOpacity="0.6" strokeDasharray="2 2" />
            <line x1="340" y1="260" x2="410" y2="280" stroke="#FDBA74" strokeOpacity="0.6" strokeDasharray="2 2" />
            <line x1="290" y1="300" x2="325" y2="355" stroke="#FDBA74" strokeOpacity="0.6" strokeDasharray="2 2" />
            <line x1="220" y1="295" x2="160" y2="340" stroke="#FDBA74" strokeOpacity="0.6" strokeDasharray="2 2" />
            <line x1="190" y1="210" x2="135" y2="190" stroke="#FDBA74" strokeOpacity="0.6" strokeDasharray="2 2" />
          </g>

          {/* Radiant Constellation Star Nodes */}
          {/* Main Core Vertex Nodes */}
          <circle cx="250" cy="180" r="5" fill="#FFF7ED" filter="url(#amberGlow)" />
          <circle cx="250" cy="180" r="3" fill="#FB923C" />

          <circle cx="190" cy="210" r="4.5" fill="#FB923C" />
          <circle cx="310" cy="200" r="5" fill="#F59E0B" />
          <circle cx="340" cy="260" r="4.5" fill="#FB923C" />
          <circle cx="290" cy="300" r="5.5" fill="#FFF7ED" filter="url(#amberGlow)" />
          <circle cx="290" cy="300" r="3.5" fill="#FB923C" />
          <circle cx="220" cy="295" r="4" fill="#FDBA74" />

          {/* External Satellite Nodes */}
          <circle cx="265" cy="135" r="3.5" fill="#FFF" />
          <circle cx="375" cy="175" r="4" fill="#F59E0B" />
          <circle cx="410" cy="280" r="3.5" fill="#FB923C" />
          <circle cx="325" cy="355" r="4" fill="#FDBA74" />
          <circle cx="160" cy="340" r="3.5" fill="#FB923C" />
          <circle cx="135" cy="190" r="4" fill="#FFF7ED" />

          {/* Additional Floating Golden Stardust Nodes */}
          <circle cx="230" cy="240" r="2.5" fill="#FDBA74" opacity="0.8" />
          <circle cx="270" cy="235" r="2.5" fill="#FB923C" opacity="0.8" />
          <circle cx="245" cy="265" r="2" fill="#FFF" opacity="0.9" />
          <circle cx="280" cy="270" r="2.5" fill="#F59E0B" opacity="0.8" />
        </svg>
      </div>

      {/* 6. Diagonal Ambient Orbital Ring Streaks sweeping across the background */}
      <div className="galaxy-sweeping-arc" />
      <div className="galaxy-sweeping-arc-faint" />
    </div>
  );
}

