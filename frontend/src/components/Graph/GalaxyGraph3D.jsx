import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';

// Node styling based on AstralGraph NodeType enum
const TYPE_COLORS = {
  directory: '#00e5ff', // cyan
  file: '#e2e8f0',      // starlight white
  class: '#b388ff',     // violet
  function: '#ffd54f',  // amber gold
};

// Create a crisp, large canvas-based text sprite for prominent labels
function makeTextSprite(message, opts = {}) {
  const fontface = opts.fontface || 'Inter, system-ui, -apple-system, sans-serif';
  const fontsize = 52; // High-resolution font size for crisp rendering
  const borderThickness = 4;
  const canvas = document.createElement('canvas');
  const context = canvas.getContext('2d');
  
  canvas.width = 1024;
  canvas.height = 256;

  context.font = `bold ${fontsize}px ${fontface}`;
  
  const textWidth = context.measureText(message).width;
  const padX = 36;
  const padY = 20;
  const boxW = Math.min(canvas.width - 40, textWidth + padX * 2);
  const boxH = fontsize + padY * 2;
  const startX = (canvas.width - boxW) / 2;
  const startY = (canvas.height - boxH) / 2;

  // Background pill with dark glow
  context.shadowColor = opts.color || 'rgba(0, 229, 255, 0.8)';
  context.shadowBlur = 16;
  context.fillStyle = 'rgba(8, 12, 24, 0.9)';
  context.strokeStyle = opts.color || '#00e5ff';
  context.lineWidth = borderThickness;

  // Rounded rectangle
  const r = 18;
  context.beginPath();
  context.moveTo(startX + r, startY);
  context.lineTo(startX + boxW - r, startY);
  context.quadraticCurveTo(startX + boxW, startY, startX + boxW, startY + r);
  context.lineTo(startX + boxW, startY + boxH - r);
  context.quadraticCurveTo(startX + boxW, startY + boxH, startX + boxW - r, startY + boxH);
  context.lineTo(startX + r, startY + boxH);
  context.quadraticCurveTo(startX, startY + boxH, startX, startY + boxH - r);
  context.lineTo(startX, startY + r);
  context.quadraticCurveTo(startX, startY, startX + r, startY);
  context.closePath();
  context.fill();
  context.stroke();

  // Reset shadow for text sharpness
  context.shadowBlur = 0;

  // Bold high-contrast text
  context.fillStyle = '#ffffff';
  context.textAlign = 'center';
  context.textBaseline = 'middle';
  context.fillText(message, canvas.width / 2, canvas.height / 2);

  const texture = new THREE.CanvasTexture(canvas);
  texture.minFilter = THREE.LinearFilter;
  const spriteMaterial = new THREE.SpriteMaterial({
    map: texture,
    transparent: true,
    depthTest: false, // Ensures labels are never occluded behind edges or nodes
    depthWrite: false
  });
  const sprite = new THREE.Sprite(spriteMaterial);
  // Prominently sized & easily readable across the galaxy
  sprite.scale.set(30, 7.5, 1);
  return sprite;
}

export default function GalaxyGraph3D({
  graphData,
  selectedNodeId,
  highlightedNodeIds = [],
  onSelectNode,
  className = ''
}) {
  const mountRef = useRef(null);
  const sceneRef = useRef(null);
  const rendererRef = useRef(null);
  const cameraRef = useRef(null);
  const nodeMeshesRef = useRef(new Map());
  const labelSpritesRef = useRef(new Map());
  const pulsesRef = useRef([]);
  const flightTargetRef = useRef(null);
  const lookTargetRef = useRef(new THREE.Vector3(0, 0, 0));
  const reqIdRef = useRef(null);

  const [hoveredNode, setHoveredNode] = useState(null);

  // Initialize Three.js scene
  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    const width = mount.clientWidth || 800;
    const height = mount.clientHeight || 600;

    // Scene
    const scene = new THREE.Scene();
    scene.fog = new THREE.FogExp2(0x020308, 0.002);
    sceneRef.current = scene;

    // Camera
    const camera = new THREE.PerspectiveCamera(50, width / height, 0.1, 2000);
    camera.position.set(0, 45, 140);
    camera.lookAt(0, 0, 0);
    cameraRef.current = camera;

    // Renderer
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setClearColor(0x020308, 1);
    rendererRef.current = renderer;

    mount.appendChild(renderer.domElement);

    // ─── REALISTIC DEEP SPACE BACKGROUND ───────────────────────────
    // Layer 1: Dense dim background stars (thousands of tiny pinpoints)
    const bgStarCount = 4500;
    const bgStarGeo = new THREE.BufferGeometry();
    const bgStarPos = new Float32Array(bgStarCount * 3);
    const bgStarColors = new Float32Array(bgStarCount * 3);
    for (let i = 0; i < bgStarCount; i++) {
      const i3 = i * 3;
      bgStarPos[i3] = (Math.random() - 0.5) * 1200;
      bgStarPos[i3 + 1] = (Math.random() - 0.5) * 1200;
      bgStarPos[i3 + 2] = (Math.random() - 0.5) * 1200;
      // Slightly warm/cool tint variation for realism
      const warmth = 0.85 + Math.random() * 0.15;
      bgStarColors[i3] = warmth;
      bgStarColors[i3 + 1] = warmth - Math.random() * 0.06;
      bgStarColors[i3 + 2] = warmth + Math.random() * 0.08;
    }
    bgStarGeo.setAttribute('position', new THREE.BufferAttribute(bgStarPos, 3));
    bgStarGeo.setAttribute('color', new THREE.BufferAttribute(bgStarColors, 3));
    const bgStarMat = new THREE.PointsMaterial({
      size: 0.6,
      transparent: true,
      opacity: 0.5,
      vertexColors: true,
      sizeAttenuation: true
    });
    const bgStarField = new THREE.Points(bgStarGeo, bgStarMat);
    scene.add(bgStarField);

    // Layer 2: Medium brightness stars (scattered, varied sizes)
    const midStarCount = 1800;
    const midStarGeo = new THREE.BufferGeometry();
    const midStarPos = new Float32Array(midStarCount * 3);
    const midStarColors = new Float32Array(midStarCount * 3);
    const midStarSizes = new Float32Array(midStarCount);
    for (let i = 0; i < midStarCount; i++) {
      const i3 = i * 3;
      midStarPos[i3] = (Math.random() - 0.5) * 1000;
      midStarPos[i3 + 1] = (Math.random() - 0.5) * 1000;
      midStarPos[i3 + 2] = (Math.random() - 0.5) * 1000;
      const temp = Math.random();
      // Color temperature: blue-white to warm white
      midStarColors[i3] = 0.8 + temp * 0.2;
      midStarColors[i3 + 1] = 0.82 + temp * 0.18;
      midStarColors[i3 + 2] = 0.9 + temp * 0.1;
      midStarSizes[i] = 0.8 + Math.random() * 1.4;
    }
    midStarGeo.setAttribute('position', new THREE.BufferAttribute(midStarPos, 3));
    midStarGeo.setAttribute('color', new THREE.BufferAttribute(midStarColors, 3));
    const midStarMat = new THREE.PointsMaterial({
      size: 1.2,
      transparent: true,
      opacity: 0.65,
      vertexColors: true,
      sizeAttenuation: true
    });
    const midStarField = new THREE.Points(midStarGeo, midStarMat);
    scene.add(midStarField);

    // Layer 3: Bright prominent stars (sparse, large glow)
    const brightStarCount = 120;
    const brightStarGeo = new THREE.BufferGeometry();
    const brightStarPos = new Float32Array(brightStarCount * 3);
    const brightStarColors = new Float32Array(brightStarCount * 3);
    for (let i = 0; i < brightStarCount; i++) {
      const i3 = i * 3;
      brightStarPos[i3] = (Math.random() - 0.5) * 900;
      brightStarPos[i3 + 1] = (Math.random() - 0.5) * 900;
      brightStarPos[i3 + 2] = (Math.random() - 0.5) * 900;
      brightStarColors[i3] = 0.95 + Math.random() * 0.05;
      brightStarColors[i3 + 1] = 0.93 + Math.random() * 0.07;
      brightStarColors[i3 + 2] = 1.0;
    }
    brightStarGeo.setAttribute('position', new THREE.BufferAttribute(brightStarPos, 3));
    brightStarGeo.setAttribute('color', new THREE.BufferAttribute(brightStarColors, 3));
    const brightStarMat = new THREE.PointsMaterial({
      size: 2.8,
      transparent: true,
      opacity: 0.85,
      vertexColors: true,
      sizeAttenuation: true
    });
    const brightStarField = new THREE.Points(brightStarGeo, brightStarMat);
    scene.add(brightStarField);

    // Layer 4: Milky Way nebula band — soft glowing cloud particles
    // Creates a diagonal band of faint volumetric haze like the reference photo
    const nebulaCount = 600;
    const nebulaGeo = new THREE.BufferGeometry();
    const nebulaPos = new Float32Array(nebulaCount * 3);
    const nebulaColors = new Float32Array(nebulaCount * 3);
    for (let i = 0; i < nebulaCount; i++) {
      const i3 = i * 3;
      // Distribute along a diagonal band (top-right to bottom-left)
      const t = (Math.random() - 0.5) * 2;
      const spread = 80 + Math.random() * 120;
      nebulaPos[i3] = t * 350 + (Math.random() - 0.5) * spread;
      nebulaPos[i3 + 1] = t * 280 + (Math.random() - 0.5) * spread;
      nebulaPos[i3 + 2] = -200 - Math.random() * 400;
      // Faint blue-white-gray cloud color
      const brightness = 0.25 + Math.random() * 0.35;
      nebulaColors[i3] = brightness * 0.7;
      nebulaColors[i3 + 1] = brightness * 0.78;
      nebulaColors[i3 + 2] = brightness * 1.0;
    }
    nebulaGeo.setAttribute('position', new THREE.BufferAttribute(nebulaPos, 3));
    nebulaGeo.setAttribute('color', new THREE.BufferAttribute(nebulaColors, 3));
    const nebulaMat = new THREE.PointsMaterial({
      size: 28,
      transparent: true,
      opacity: 0.06,
      vertexColors: true,
      sizeAttenuation: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending
    });
    const nebulaField = new THREE.Points(nebulaGeo, nebulaMat);
    scene.add(nebulaField);

    // Layer 5: Dense milky way core — concentrated bright cluster along the band
    const coreCount = 2200;
    const coreGeo = new THREE.BufferGeometry();
    const corePos = new Float32Array(coreCount * 3);
    const coreColors = new Float32Array(coreCount * 3);
    for (let i = 0; i < coreCount; i++) {
      const i3 = i * 3;
      const t = (Math.random() - 0.5) * 2;
      const bandSpread = 30 + Math.random() * 60;
      corePos[i3] = t * 380 + (Math.random() - 0.5) * bandSpread;
      corePos[i3 + 1] = t * 300 + (Math.random() - 0.5) * bandSpread;
      corePos[i3 + 2] = -250 - Math.random() * 350;
      const b = 0.6 + Math.random() * 0.4;
      coreColors[i3] = b * 0.85;
      coreColors[i3 + 1] = b * 0.88;
      coreColors[i3 + 2] = b;
    }
    coreGeo.setAttribute('position', new THREE.BufferAttribute(corePos, 3));
    coreGeo.setAttribute('color', new THREE.BufferAttribute(coreColors, 3));
    const coreMat = new THREE.PointsMaterial({
      size: 0.9,
      transparent: true,
      opacity: 0.45,
      vertexColors: true,
      sizeAttenuation: true
    });
    const coreField = new THREE.Points(coreGeo, coreMat);
    scene.add(coreField);

    // Ambient & Point lights
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.9);
    scene.add(ambientLight);

    const pointLight = new THREE.PointLight(0x00e5ff, 2.5, 350);
    pointLight.position.set(0, 60, 0);
    scene.add(pointLight);

    // Continuous rotation group
    const galaxyGroup = new THREE.Group();
    galaxyGroup.name = 'GALAXY_ROTATION_GROUP';
    scene.add(galaxyGroup);

    // Orbit controls / Mouse interaction centered on dynamic focus point
    let isDragging = false;
    let prevMousePos = { x: 0, y: 0 };
    const focusCenter = new THREE.Vector3(0, 0, 0);
    lookTargetRef.current = focusCenter;
    let spherical = { radius: 140, theta: 0, phi: Math.PI / 3 };

    const updateCamera = () => {
      camera.position.x = focusCenter.x + spherical.radius * Math.sin(spherical.phi) * Math.sin(spherical.theta);
      camera.position.y = focusCenter.y + spherical.radius * Math.cos(spherical.phi);
      camera.position.z = focusCenter.z + spherical.radius * Math.sin(spherical.phi) * Math.cos(spherical.theta);
      camera.lookAt(focusCenter);
    };
    updateCamera();

    // Store sync helper to update spherical coordinates whenever camera finishes warping
    window.__astroSyncOrbit = (newCenter, newCamPos) => {
      focusCenter.copy(newCenter);
      const diff = new THREE.Vector3().subVectors(newCamPos, focusCenter);
      spherical.radius = diff.length();
      spherical.phi = Math.acos(Math.max(-1, Math.min(1, diff.y / (spherical.radius || 1))));
      spherical.theta = Math.atan2(diff.x, diff.z);
    };

    const onMouseDown = (e) => {
      // User started manual interaction: cancel any active auto-flight
      flightTargetRef.current = null;
      isDragging = true;
      prevMousePos = { x: e.clientX, y: e.clientY };
    };

    const onMouseMove = (e) => {
      if (!isDragging) {
        // Handle hovering
        const rect = renderer.domElement.getBoundingClientRect();
        mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
        mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
        raycaster.setFromCamera(mouse, camera);
        const meshes = Array.from(nodeMeshesRef.current.values());
        const intersects = raycaster.intersectObjects(meshes);
        if (intersects.length > 0) {
          const hovered = intersects[0].object.userData?.nodeData;
          setHoveredNode(hovered || null);
          mount.style.cursor = 'pointer';
        } else {
          setHoveredNode(null);
          mount.style.cursor = 'grab';
        }
        return;
      }

      const dx = e.clientX - prevMousePos.x;
      const dy = e.clientY - prevMousePos.y;
      spherical.theta -= dx * 0.006;
      spherical.phi = Math.max(0.1, Math.min(Math.PI - 0.1, spherical.phi - dy * 0.006));
      prevMousePos = { x: e.clientX, y: e.clientY };
      updateCamera();
    };

    const onMouseUp = () => {
      isDragging = false;
    };

    const onWheel = (e) => {
      flightTargetRef.current = null;
      spherical.radius = Math.max(20, Math.min(450, spherical.radius + e.deltaY * 0.12));
      updateCamera();
    };

    const canvas = renderer.domElement;
    canvas.addEventListener('mousedown', onMouseDown);
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
    canvas.addEventListener('wheel', onWheel);

    // Raycasting for node selection
    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();

    const onClick = (e) => {
      const rect = canvas.getBoundingClientRect();
      mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

      raycaster.setFromCamera(mouse, camera);
      const meshes = Array.from(nodeMeshesRef.current.values());
      const intersects = raycaster.intersectObjects(meshes);

      if (intersects.length > 0) {
        const clickedMesh = intersects[0].object;
        if (clickedMesh.userData && clickedMesh.userData.nodeId) {
          onSelectNode?.(clickedMesh.userData.nodeId);
        }
      }
    };
    canvas.addEventListener('click', onClick);

    // Animation loop
    const animate = () => {
      reqIdRef.current = requestAnimationFrame(animate);
      // Very slow rotation for a living, breathing deep space feel
      bgStarField.rotation.y += 0.00008;
      midStarField.rotation.y += 0.00012;
      brightStarField.rotation.y += 0.00015;
      nebulaField.rotation.y += 0.00005;
      coreField.rotation.y += 0.0001;
      galaxyGroup.rotation.y += 0.0006;

      // Camera Warp / Flight Animation to target node
      if (flightTargetRef.current) {
        camera.position.lerp(flightTargetRef.current, 0.05);
        
        // Sync the orbit control pivot & spherical radius so subsequent zooming/dragging starts from here!
        if (window.__astroSyncOrbit && lookTargetRef.current) {
          window.__astroSyncOrbit(lookTargetRef.current, camera.position);
        }

        // Check if camera has arrived close to the target
        if (camera.position.distanceTo(flightTargetRef.current) < 0.6) {
          flightTargetRef.current = null;
        }
      }

      // Smooth camera orientation towards current focal point
      if (lookTargetRef.current) {
        camera.lookAt(lookTargetRef.current);
      }

      // Animate flowing data pulses along dependency edges
      if (pulsesRef.current && pulsesRef.current.length > 0) {
        pulsesRef.current.forEach((pulse) => {
          pulse.progress += pulse.speed;
          if (pulse.progress > 1) {
            pulse.progress = 0;
          }
          pulse.mesh.position.lerpVectors(pulse.start, pulse.end, pulse.progress);
        });
      }

      renderer.render(scene, camera);
    };
    animate();

    const handleResize = () => {
      if (!mount) return;
      const w = mount.clientWidth;
      const h = mount.clientHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    };
    window.addEventListener('resize', handleResize);

    return () => {
      cancelAnimationFrame(reqIdRef.current);
      canvas.removeEventListener('mousedown', onMouseDown);
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
      canvas.removeEventListener('wheel', onWheel);
      canvas.removeEventListener('click', onClick);
      window.removeEventListener('resize', handleResize);
      if (mount && renderer.domElement) {
        mount.removeChild(renderer.domElement);
      }
      renderer.dispose();
    };
  }, []);

  // Populate graph nodes, edges & labels
  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene || !graphData || !graphData.nodes) return;

    const galaxyGroup = scene.getObjectByName('GALAXY_ROTATION_GROUP');
    if (!galaxyGroup) return;

    // Clear previous children
    while (galaxyGroup.children.length > 0) {
      const obj = galaxyGroup.children[0];
      galaxyGroup.remove(obj);
    }

    nodeMeshesRef.current.clear();
    labelSpritesRef.current.clear();

    // Compact single-view galaxy: fits completely inside the screen on page load
    const nodeCoords = new Map();
    const nodes = graphData.nodes;
    const total = Math.max(nodes.length, 1);

    // Perfectly balanced galaxy radius: fits comfortably in the viewport while giving each node its own bubble
    nodes.forEach((node, i) => {
      const cluster = node.position_hint?.cluster_id ?? 0;
      const depth = node.position_hint?.depth ?? 0;

      // Distribute evenly along the circumference with cluster sectoring
      const angle = (i / total) * Math.PI * 2 + cluster * 0.55;
      
      // Radius scaled around 44-58 for optimal spacing on 1080p/laptop screens
      const radius = 44 + depth * 7 + ((i % 3) - 1) * 6;
      
      // Alternating vertical separation (+/- 9) so neighboring nodes and labels never collide
      const height = (i % 2 === 0 ? 1 : -1) * (7 + (i % 3) * 3);

      const pos = new THREE.Vector3(
        Math.cos(angle) * radius,
        height,
        Math.sin(angle) * radius
      );
      nodeCoords.set(node.id, pos);

      // Node sphere geometry
      const size = Math.max(1.8, Math.min(3.8, 2.0 + (node.metrics?.centrality || 0) * 2.4));
      const geom = new THREE.SphereGeometry(size, 20, 20);

      const colorHex = TYPE_COLORS[node.type] || '#ffffff';
      const isSelected = selectedNodeId === node.id;
      const isHighlighted = highlightedNodeIds.includes(node.id);

      const mat = new THREE.MeshStandardMaterial({
        color: isSelected ? 0xff0055 : (isHighlighted ? 0x00ff88 : colorHex),
        emissive: isSelected ? 0xff0055 : (isHighlighted ? 0x00ff88 : colorHex),
        emissiveIntensity: isSelected || isHighlighted ? 1.0 : 0.45,
        roughness: 0.25,
        metalness: 0.8
      });

      const mesh = new THREE.Mesh(geom, mat);
      mesh.position.copy(pos);
      mesh.userData = { nodeId: node.id, nodeData: node };

      galaxyGroup.add(mesh);
      nodeMeshesRef.current.set(node.id, mesh);

      // Label elevated above the node with alternating heights (+/- 3.5)
      const sprite = makeTextSprite(node.label, {
        color: isSelected ? '#ff0055' : (isHighlighted ? '#00ff88' : colorHex)
      });
      const labelElev = size + 5.0 + (i % 2) * 4.0;
      sprite.position.set(pos.x, pos.y + labelElev, pos.z);
      galaxyGroup.add(sprite);
      labelSpritesRef.current.set(node.id, sprite);
    });

    // Edges & Glowing Data Pulses
    pulsesRef.current = [];
    if (graphData.edges) {
      const edgeMat = new THREE.LineBasicMaterial({
        color: 0xfdba74,
        transparent: true,
        opacity: 0.35
      });

      // Pulse particle geometry & material matching Sunset Orange palette
      const pulseGeom = new THREE.SphereGeometry(0.75, 12, 12);
      const pulseMat = new THREE.MeshBasicMaterial({
        color: 0xfb923c,
        transparent: true,
        opacity: 0.95
      });

      graphData.edges.forEach((edge, eIdx) => {
        const p1 = nodeCoords.get(edge.source);
        const p2 = nodeCoords.get(edge.target);
        if (p1 && p2) {
          // Static base edge
          const points = [p1, p2];
          const edgeGeo = new THREE.BufferGeometry().setFromPoints(points);
          const line = new THREE.Line(edgeGeo, edgeMat);
          galaxyGroup.add(line);

          // Flowing glowing pulse particle along the edge
          const pulseMesh = new THREE.Mesh(pulseGeom, pulseMat);
          pulseMesh.position.copy(p1);
          galaxyGroup.add(pulseMesh);

          pulsesRef.current.push({
            mesh: pulseMesh,
            start: p1,
            end: p2,
            progress: (eIdx * 0.22) % 1, // stagger starting offsets
            speed: 0.005 + (eIdx % 3) * 0.002 // varied natural speeds
          });
        }
      });
    }
  }, [graphData, selectedNodeId, highlightedNodeIds]);

  // Trigger smooth 3D camera warp flight whenever selectedNodeId changes
  useEffect(() => {
    if (!selectedNodeId) return;
    const mesh = nodeMeshesRef.current.get(selectedNodeId);
    if (!mesh || !cameraRef.current) return;

    // Get the world position of the target node
    const targetWorldPos = new THREE.Vector3();
    mesh.getWorldPosition(targetWorldPos);

    // Compute cinematic camera arrival coordinates: slightly above and pulled back
    const offsetDir = targetWorldPos.clone().normalize();
    if (offsetDir.lengthSq() < 0.001) offsetDir.set(0, 0, 1);
    
    // Position camera comfortably pulled back (~68 units) so the surrounding constellation remains in view
    const cameraDest = targetWorldPos.clone().add(offsetDir.multiplyScalar(68)).add(new THREE.Vector3(0, 22, 34));

    flightTargetRef.current = cameraDest;
    lookTargetRef.current = targetWorldPos.clone();
  }, [selectedNodeId]);

  return (
    <div className={`relative w-full h-full overflow-hidden ${className}`}>
      <div ref={mountRef} className="w-full h-full" style={{ cursor: 'grab' }} />

      {/* Floating Tooltip HUD on Hover */}
      {hoveredNode && (
        <div
          className="absolute bottom-6 left-6 pointer-events-none p-3 rounded bg-slate-900/90 border border-cyan-400/40 text-xs font-mono text-white shadow-xl backdrop-blur-md flex flex-col gap-1 z-30"
          style={{ maxWidth: '320px' }}
        >
          <div className="flex items-center justify-between text-cyan-300 font-bold border-b border-white/10 pb-1">
            <span>{hoveredNode.label}</span>
            <span className="uppercase text-[10px] px-1.5 py-0.5 rounded bg-white/10">{hoveredNode.type}</span>
          </div>
          <div className="text-gray-400 text-[11px] truncate">{hoveredNode.path}</div>
          {hoveredNode.ai_summary && (
            <div className="text-gray-300 text-[11px] italic mt-1 line-clamp-2">
              {hoveredNode.ai_summary}
            </div>
          )}
        </div>
      )}

      {/* Legend / Overlay */}
      <div className="absolute top-4 right-4 pointer-events-none bg-black/60 border border-white/10 p-2.5 rounded text-xs font-mono space-y-1.5 backdrop-blur-sm">
        <div className="text-gray-400 text-[10px] uppercase font-bold tracking-wider">Node Types</div>
        <div className="flex items-center gap-2"><span className="w-2.5 h-2.5 rounded-full bg-[#00e5ff]" /> directory</div>
        <div className="flex items-center gap-2"><span className="w-2.5 h-2.5 rounded-full bg-[#e2e8f0]" /> file</div>
        <div className="flex items-center gap-2"><span className="w-2.5 h-2.5 rounded-full bg-[#b388ff]" /> class</div>
        <div className="flex items-center gap-2"><span className="w-2.5 h-2.5 rounded-full bg-[#ffd54f]" /> function</div>
      </div>
    </div>
  );
}
