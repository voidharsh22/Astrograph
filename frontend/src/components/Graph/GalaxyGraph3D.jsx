import { useEffect, useRef, useState, useCallback } from 'react';
import * as THREE from 'three';

// Node styling based on AstralGraph NodeType enum
const TYPE_COLORS = {
  directory: '#00e5ff', // cyan
  file: '#38bdf8',      // starlight blue
  class: '#b388ff',     // violet
  function: '#ffd54f',  // amber gold
};

const CLUSTER_COLORS = {
  0: '#f43f5e', // src/ - Rose / Pink neon
  1: '#00e5ff', // services/ - Electric Cyan
  2: '#fb923c', // SolarFluxEngine/ - Sunset Amber
  3: '#10b981', // models/ - Emerald Green
  4: '#a855f7', // api/ - Violet Purple
  5: '#38bdf8', // utils/ - Sky Blue
};

// Create a crisp, large canvas-based text sprite for prominent node labels
function makeTextSprite(message, opts = {}) {
  const fontface = opts.fontface || 'Inter, system-ui, -apple-system, sans-serif';
  const fontsize = 52;
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

  context.shadowBlur = 0;
  context.fillStyle = '#ffffff';
  context.textAlign = 'center';
  context.textBaseline = 'middle';
  context.fillText(message, canvas.width / 2, canvas.height / 2);

  const texture = new THREE.CanvasTexture(canvas);
  texture.minFilter = THREE.LinearFilter;
  const spriteMaterial = new THREE.SpriteMaterial({
    map: texture,
    transparent: true,
    depthTest: false,
    depthWrite: false,
  });
  const sprite = new THREE.Sprite(spriteMaterial);
  sprite.scale.set(30, 7.5, 1);
  sprite.raycast = () => {};
  return sprite;
}

// Create billboard banner sprite for 3D folder region headers
function makeFolderLabelSprite(message, opts = {}) {
  const fontface = 'Inter, system-ui, -apple-system, sans-serif';
  const fontsize = 44;
  const canvas = document.createElement('canvas');
  const context = canvas.getContext('2d');
  
  canvas.width = 1024;
  canvas.height = 256;

  context.font = `bold ${fontsize}px ${fontface}`;
  const textWidth = context.measureText(message).width;
  const padX = 32;
  const padY = 18;
  const boxW = Math.min(canvas.width - 40, textWidth + padX * 2);
  const boxH = fontsize + padY * 2;
  const startX = (canvas.width - boxW) / 2;
  const startY = (canvas.height - boxH) / 2;

  // Folder header banner pill
  context.fillStyle = 'rgba(8, 14, 28, 0.90)';
  context.strokeStyle = opts.color || '#38bdf8';
  context.lineWidth = 3.5;

  const r = 14;
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

  // Text
  context.fillStyle = opts.color || '#38bdf8';
  context.textAlign = 'center';
  context.textBaseline = 'middle';
  context.fillText(message, canvas.width / 2, canvas.height / 2);

  const texture = new THREE.CanvasTexture(canvas);
  texture.minFilter = THREE.LinearFilter;
  const spriteMaterial = new THREE.SpriteMaterial({
    map: texture,
    transparent: true,
    depthTest: false,
    depthWrite: false,
    opacity: 0.9,
  });
  const sprite = new THREE.Sprite(spriteMaterial);
  sprite.scale.set(38, 9.5, 1);
  sprite.raycast = () => {};
  return sprite;
}

export default function GalaxyGraph3D({
  graphData,
  selectedNodeId,
  highlightedNodeIds = [],
  onSelectNode,
  copilotFx = null,
  selectedEdgeId = null,
  onSelectEdge,
  showEdgeLabels = false,
  resetToken = 0,
  className = ''
}) {
  const mountRef = useRef(null);
  const sceneRef = useRef(null);
  const rendererRef = useRef(null);
  const cameraRef = useRef(null);

  const nodeMeshesRef = useRef(new Map());
  const labelSpritesRef = useRef(new Map());
  const edgeObjectsRef = useRef(new Map());
  const folderRegionsRef = useRef(new Map());
  const pulsesRef = useRef([]);

  const flightTargetRef = useRef(null);
  const lookTargetRef = useRef(new THREE.Vector3(0, 0, 0));
  const reqIdRef = useRef(null);

  const selectedNodeIdRef = useRef(selectedNodeId);
  const showEdgeLabelsRef = useRef(showEdgeLabels);
  showEdgeLabelsRef.current = showEdgeLabels;
  const hoverTargetRef = useRef(null);

  const [hoveredNode, setHoveredNode] = useState(null);
  // Cursor-following hover info for the dependency beam under the pointer
  const [edgeHover, setEdgeHover] = useState(null);

  // Astral AI Copilot overlay state (workflow pulses, blast radius, cluster spotlight)
  const copilotFxRef = useRef(copilotFx);
  const copilotOverlayRef = useRef(null);
  const copilotAnimRef = useRef([]);
  // Edge interaction: hover/click focus, high-velocity packets, gradient beam, endpoint rings
  const onSelectEdgeRef = useRef(onSelectEdge);
  const selectedEdgeIdRef = useRef(selectedEdgeId);
  const focusEdgeIdRef = useRef(null);
  const edgeBeamRef = useRef(null);
  const packetPoolRef = useRef([]);
  const edgeRingsRef = useRef([]);
  // Keep the latest selection callback in a ref so parent re-renders never rebuild the WebGL scene
  const onSelectNodeRef = useRef(onSelectNode);

  useEffect(() => {
    selectedNodeIdRef.current = selectedNodeId;
  }, [selectedNodeId]);

  useEffect(() => {
    onSelectNodeRef.current = onSelectNode;
    copilotFxRef.current = copilotFx;
    onSelectEdgeRef.current = onSelectEdge;
  }, [onSelectNode, copilotFx, onSelectEdge]);

  // Edge focus (hover preview or selected beam): dims other beams to 20%, lights the focus beam,
  // and sizes the gradient beam. Runs at the end of every highlight pass.
  const applyEdgeFocus = useCallback(() => {
    const hoverId = hoverTargetRef.current?.edgeId || null;
    const focusId = hoverId || selectedEdgeIdRef.current || null;
    focusEdgeIdRef.current = focusId;
    const edges = edgeObjectsRef.current;
    const beam = edgeBeamRef.current;
    const f = focusId ? edges.get(focusId) : null;
    if (!f) {
      if (beam) beam.visible = false;
      return;
    }
    edges.forEach((e, id) => {
      if (id === focusId) return;
      e.lineMesh.material.color.set(e.defaultColor);
      e.lineMesh.material.opacity = 0.2;
      e.pulseMesh.material.opacity = 0.2;
    });
    f.lineMesh.material.color.set(0xfdba74);
    f.lineMesh.material.opacity = 1;
    f.pulseMesh.material.opacity = 1;
    if (beam) {
      const radius = hoverId ? 0.42 : 0.6; // hover: ~2.5x the base beam; selected: thicker still
      const key = `${focusId}|${radius}`;
      if (beam.userData.key !== key) {
        const a = f.start;
        const b = f.end;
        const dir = new THREE.Vector3().subVectors(b, a);
        const len = Math.max(0.01, dir.length());
        const geo = new THREE.CylinderGeometry(radius, radius, len, 10, 1, true);
        const c1 = new THREE.Color(0xfb923c);
        const c2 = new THREE.Color(0xfdba74);
        const pos = geo.attributes.position;
        const colors = [];
        for (let i = 0; i < pos.count; i++) {
          const t = (pos.getY(i) + len / 2) / len;
          const c = c1.clone().lerp(c2, t);
          colors.push(c.r, c.g, c.b);
        }
        geo.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
        beam.geometry.dispose();
        beam.geometry = geo;
        beam.position.copy(a).add(b).multiplyScalar(0.5);
        beam.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir.normalize());
        beam.userData.key = key;
      }
      beam.visible = true;
    }
  }, []);

  // Centralized visual state manager for 3D selection, relationship highlighting, and folder grouping
  const updateVisualHighlights = useCallback((hoverNodeId, hoverEdgeId, selNodeId) => {
    const activeHoverNode = hoverNodeId;
    const activeHoverEdge = hoverEdgeId;
    const activeSelected = selNodeId;

    const activeNodeId = activeHoverNode || activeSelected;

    // Fast lookup sets
    const incomingEdgeIds = new Set();
    const outgoingEdgeIds = new Set();
    const neighborNodeIds = new Set();
    let activeNodeFolder = null;

    if (activeHoverEdge) {
      const edgeObj = edgeObjectsRef.current.get(activeHoverEdge);
      if (edgeObj) {
        neighborNodeIds.add(edgeObj.source);
        neighborNodeIds.add(edgeObj.target);
      }
    } else if (activeNodeId) {
      edgeObjectsRef.current.forEach((edgeObj) => {
        if (edgeObj.target === activeNodeId) {
          incomingEdgeIds.add(edgeObj.id);
          neighborNodeIds.add(edgeObj.source);
        } else if (edgeObj.source === activeNodeId) {
          outgoingEdgeIds.add(edgeObj.id);
          neighborNodeIds.add(edgeObj.target);
        }
      });

      const nodeMesh = nodeMeshesRef.current.get(activeNodeId);
      if (nodeMesh?.userData?.nodeData) {
        const nd = nodeMesh.userData.nodeData;
        activeNodeFolder = nd.cluster || (nd.path ? nd.path.split('/')[0] : 'root');
      }
    }

    const isHighlightActive = Boolean(activeHoverEdge || activeNodeId);

    // 1. Update Nodes & Labels
    nodeMeshesRef.current.forEach((mesh, nodeId) => {
      const isSelected = nodeId === activeSelected;
      const isHovered = nodeId === activeHoverNode;
      const isNeighbor = neighborNodeIds.has(nodeId);
      const sprite = labelSpritesRef.current.get(nodeId);

      if (!isHighlightActive) {
        // Normal default state
        mesh.scale.set(1, 1, 1);
        mesh.material.opacity = 1.0;
        mesh.material.transparent = false;
        mesh.material.emissiveIntensity = 0.65;
        mesh.material.color.set(mesh.userData.defaultColor);
        mesh.material.emissive.set(mesh.userData.defaultColor);
        if (sprite) {
          sprite.material.opacity = 0.95;
        }
      } else if (isSelected || isHovered) {
        // Strongest visual emphasis (rose for selected, cyan for hovered preview)
        mesh.scale.set(1.35, 1.35, 1.35);
        mesh.material.transparent = false;
        mesh.material.opacity = 1.0;
        mesh.material.emissiveIntensity = 1.25;
        mesh.material.color.set(isSelected ? 0xf43f5e : 0x38bdf8);
        mesh.material.emissive.set(isSelected ? 0xf43f5e : 0x38bdf8);
        if (sprite) {
          sprite.material.opacity = 1.0;
        }
      } else if (isNeighbor) {
        // Connected neighbor node
        mesh.scale.set(1.18, 1.18, 1.18);
        mesh.material.transparent = false;
        mesh.material.opacity = 1.0;
        mesh.material.emissiveIntensity = 0.95;
        mesh.material.color.set(mesh.userData.defaultColor);
        mesh.material.emissive.set(mesh.userData.defaultColor);
        if (sprite) {
          sprite.material.opacity = 1.0;
        }
      } else {
        // Unrelated node: subtly dimmed, NOT removed
        mesh.scale.set(1, 1, 1);
        mesh.material.transparent = true;
        mesh.material.opacity = 0.16;
        mesh.material.emissiveIntensity = 0.15;
        mesh.material.color.set(mesh.userData.defaultColor);
        mesh.material.emissive.set(mesh.userData.defaultColor);
        if (sprite) {
          sprite.material.opacity = 0.16;
        }
      }
    });

    // 2. Update Edges & Pulses
    edgeObjectsRef.current.forEach((edgeObj, edgeId) => {
      const isHoveredEdge = edgeId === activeHoverEdge;
      const isIncoming = incomingEdgeIds.has(edgeId);
      const isOutgoing = outgoingEdgeIds.has(edgeId);

      if (!isHighlightActive) {
        // Normal default
        edgeObj.lineMesh.material.color.set(edgeObj.defaultColor);
        edgeObj.lineMesh.material.opacity = edgeObj.defaultOpacity;
        edgeObj.pulseMesh.material.opacity = 0.85;
      } else if (isHoveredEdge) {
        // Hovered edge: prominent glow & full opacity
        edgeObj.lineMesh.material.color.set(0x38bdf8);
        edgeObj.lineMesh.material.opacity = 1.0;
        edgeObj.pulseMesh.material.opacity = 1.0;
      } else if (isIncoming) {
        // Incoming edge: Glowing cyan directed toward active node
        edgeObj.lineMesh.material.color.set(0x38bdf8);
        edgeObj.lineMesh.material.opacity = 0.95;
        edgeObj.pulseMesh.material.opacity = 1.0;
      } else if (isOutgoing) {
        // Outgoing edge: Glowing amber/orange directed away from active node
        edgeObj.lineMesh.material.color.set(0xfb923c);
        edgeObj.lineMesh.material.opacity = 0.95;
        edgeObj.pulseMesh.material.opacity = 1.0;
      } else {
        // Unrelated edge: subtly dimmed
        edgeObj.lineMesh.material.color.set(edgeObj.defaultColor);
        edgeObj.lineMesh.material.opacity = 0.05;
        edgeObj.pulseMesh.material.opacity = 0.05;
      }
    });

    // 3. Update Folder Regions (Part 4)
    folderRegionsRef.current.forEach((folder) => {
      if (!isHighlightActive) {
        // Normal default
        folder.fillMesh.material.opacity = folder.baseFillOpacity;
        folder.outlineMesh.material.opacity = folder.baseOutlineOpacity;
        folder.labelSprite.material.opacity = folder.baseLabelOpacity;
      } else if (activeNodeFolder && folder.cPath === activeNodeFolder) {
        // Active node folder: emphasized boundary & clear fill
        folder.fillMesh.material.opacity = 0.10;
        folder.outlineMesh.material.opacity = 0.50;
        folder.labelSprite.material.opacity = 1.0;
      } else {
        // Unrelated folder: subtly dimmed
        folder.fillMesh.material.opacity = 0.015;
        folder.outlineMesh.material.opacity = 0.08;
        folder.labelSprite.material.opacity = 0.25;
      }
    });

    // 4. Astral AI overlay (workflow / blast radius / cluster) is drawn on top of the base state
    copilotOverlayRef.current?.();
    applyEdgeFocus();
  }, [applyEdgeFocus]);

  // Initialize Three.js scene once
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

    if (typeof window !== 'undefined') {
      window.__astro3D = {
        scene,
        camera,
        nodeMeshesRef,
        edgeObjectsRef,
        folderRegionsRef,
      };
    }

    // Renderer
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setClearColor(0x020308, 1);
    rendererRef.current = renderer;

    mount.appendChild(renderer.domElement);

    // ─── DEEP SPACE BACKGROUND ───────────────────────────
    const bgStarCount = 4500;
    const bgStarGeo = new THREE.BufferGeometry();
    const bgStarPos = new Float32Array(bgStarCount * 3);
    const bgStarColors = new Float32Array(bgStarCount * 3);
    for (let i = 0; i < bgStarCount; i++) {
      const i3 = i * 3;
      bgStarPos[i3] = (Math.random() - 0.5) * 1200;
      bgStarPos[i3 + 1] = (Math.random() - 0.5) * 1200;
      bgStarPos[i3 + 2] = (Math.random() - 0.5) * 1200;
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

    // Mid stars
    const midStarCount = 1800;
    const midStarGeo = new THREE.BufferGeometry();
    const midStarPos = new Float32Array(midStarCount * 3);
    const midStarColors = new Float32Array(midStarCount * 3);
    for (let i = 0; i < midStarCount; i++) {
      const i3 = i * 3;
      midStarPos[i3] = (Math.random() - 0.5) * 1000;
      midStarPos[i3 + 1] = (Math.random() - 0.5) * 1000;
      midStarPos[i3 + 2] = (Math.random() - 0.5) * 1000;
      const temp = Math.random();
      midStarColors[i3] = 0.8 + temp * 0.2;
      midStarColors[i3 + 1] = 0.82 + temp * 0.18;
      midStarColors[i3 + 2] = 0.9 + temp * 0.1;
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

    // Bright stars
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

    // Nebula band
    const nebulaCount = 600;
    const nebulaGeo = new THREE.BufferGeometry();
    const nebulaPos = new Float32Array(nebulaCount * 3);
    const nebulaColors = new Float32Array(nebulaCount * 3);
    for (let i = 0; i < nebulaCount; i++) {
      const i3 = i * 3;
      const t = (Math.random() - 0.5) * 2;
      const spread = 80 + Math.random() * 120;
      nebulaPos[i3] = t * 350 + (Math.random() - 0.5) * spread;
      nebulaPos[i3 + 1] = t * 280 + (Math.random() - 0.5) * spread;
      nebulaPos[i3 + 2] = -200 - Math.random() * 400;
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

    // Lights
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.9);
    scene.add(ambientLight);

    const pointLight = new THREE.PointLight(0x00e5ff, 2.5, 350);
    pointLight.position.set(0, 60, 0);
    scene.add(pointLight);

    // Continuous rotation group
    const galaxyGroup = new THREE.Group();
    galaxyGroup.name = 'GALAXY_ROTATION_GROUP';
    scene.add(galaxyGroup);

    // Edge focus packets (pool reused across edges) and the gradient beam
    const packetGeo = new THREE.SphereGeometry(0.9, 12, 12);
    for (let k = 0; k < 8; k++) {
      const pk = new THREE.Mesh(
        packetGeo,
        new THREE.MeshBasicMaterial({
          color: k % 2 ? 0xfdba74 : 0xfb923c,
          transparent: true,
          opacity: 1,
          blending: THREE.AdditiveBlending,
          depthWrite: false,
        }),
      );
      pk.raycast = () => {};
      pk.visible = false;
      pk.userData.persistentOverlay = true;
      galaxyGroup.add(pk);
      packetPoolRef.current.push(pk);
    }
    const beam = new THREE.Mesh(
      new THREE.BufferGeometry(),
      new THREE.MeshBasicMaterial({
        vertexColors: true,
        transparent: true,
        opacity: 0.9,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      }),
    );
    beam.raycast = () => {};
    beam.visible = false;
    beam.userData.persistentOverlay = true;
    galaxyGroup.add(beam);
    edgeBeamRef.current = beam;

    // Orbit controls / Mouse interaction
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

    window.__astroSyncOrbit = (newCenter, newCamPos) => {
      focusCenter.copy(newCenter);
      const diff = new THREE.Vector3().subVectors(newCamPos, focusCenter);
      spherical.radius = diff.length();
      spherical.phi = Math.acos(Math.max(-1, Math.min(1, diff.y / (spherical.radius || 1))));
      spherical.theta = Math.atan2(diff.x, diff.z);
    };

    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();

    const onMouseDown = (e) => {
      flightTargetRef.current = null;
      isDragging = true;
      prevMousePos = { x: e.clientX, y: e.clientY };
    };

    const onMouseMove = (e) => {
      if (!isDragging) {
        const rect = renderer.domElement.getBoundingClientRect();
        mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
        mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
        raycaster.setFromCamera(mouse, camera);

        // 1. Raycast nodes first
        const meshes = Array.from(nodeMeshesRef.current.values());
        const intersects = raycaster.intersectObjects(meshes);

        if (intersects.length > 0) {
          const hoveredObj = intersects[0].object;
          const nodeData = hoveredObj.userData?.nodeData;
          const nId = hoveredObj.userData?.nodeId;
          hoverTargetRef.current = { nodeId: nId, edgeId: null };
          setHoveredNode(nodeData || null);
          setEdgeHover(null);
          updateVisualHighlights(nId, null, selectedNodeIdRef.current);
          mount.style.cursor = 'pointer';
          return;
        }

        // 2. Raycast edges if no node hovered
        raycaster.params.Line = { threshold: Math.max(2.5, camera.position.length() * 0.025) };
        const edgeLines = Array.from(edgeObjectsRef.current.values()).map((o) => o.lineMesh);
        const edgeIntersects = raycaster.intersectObjects(edgeLines);

        if (edgeIntersects.length > 0) {
          const hoveredLine = edgeIntersects[0].object;
          const edgeData = hoveredLine.userData?.edgeData;
          const eId = hoveredLine.userData?.edgeId;
          hoverTargetRef.current = { nodeId: null, edgeId: eId };
          setHoveredNode(null);
          {
            const mr = mount.getBoundingClientRect();
            const lab = (id) => nodeMeshesRef.current.get(id)?.userData?.nodeData?.label || String(id).replace(/^file::/, '').split('/').pop();
            setEdgeHover({
              rel: edgeData?.relation || 'imports',
              src: lab(edgeData?.source),
              tgt: lab(edgeData?.target),
              x: e.clientX - mr.left,
              y: e.clientY - mr.top,
            });
          }
          updateVisualHighlights(null, eId, selectedNodeIdRef.current);
          mount.style.cursor = 'pointer';
          return;
        }

        // 3. Pointer in empty space: clear hovers and restore active selection
        if (hoverTargetRef.current?.nodeId || hoverTargetRef.current?.edgeId) {
          hoverTargetRef.current = null;
          setHoveredNode(null);
          setEdgeHover(null);
          updateVisualHighlights(null, null, selectedNodeIdRef.current);
        }
        mount.style.cursor = 'grab';
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
          onSelectNodeRef.current?.(clickedMesh.userData.nodeId);
        }
      } else {
        // No star under the pointer: a beam click selects that edge; empty space clears both
        raycaster.params.Line = { threshold: Math.max(2.5, camera.position.length() * 0.025) };
        const edgeLines = Array.from(edgeObjectsRef.current.values()).map((o) => o.lineMesh);
        const hitEdge = raycaster.intersectObjects(edgeLines)[0];
        if (hitEdge) {
          setEdgeHover(null); // camera reframes; tooltip returns on the next pointer move
          onSelectEdgeRef.current?.(hitEdge.object.userData?.edgeId ?? null);
        } else {
          onSelectNodeRef.current?.(null);
          onSelectEdgeRef.current?.(null);
        }
      }
    };
    canvas.addEventListener('click', onClick);

    // Animation loop
    const animate = () => {
      reqIdRef.current = requestAnimationFrame(animate);
      bgStarField.rotation.y += 0.00008;
      midStarField.rotation.y += 0.00012;
      brightStarField.rotation.y += 0.00015;
      nebulaField.rotation.y += 0.00005;
      galaxyGroup.rotation.y += 0.0006;

      // Smooth camera interpolation
      if (flightTargetRef.current) {
        camera.position.lerp(flightTargetRef.current, 0.05);
        if (window.__astroSyncOrbit && lookTargetRef.current) {
          window.__astroSyncOrbit(lookTargetRef.current, camera.position);
        }
        if (camera.position.distanceTo(flightTargetRef.current) < 0.8) {
          flightTargetRef.current = null;
        }
      }

      if (lookTargetRef.current) {
        camera.lookAt(lookTargetRef.current);
      }

      // Advance pulse particles
      if (pulsesRef.current && pulsesRef.current.length > 0) {
        pulsesRef.current.forEach((pulse) => {
          const fid = focusEdgeIdRef.current;
          const mult = fid && pulse.edgeId === fid ? 6 : selectedEdgeIdRef.current && pulse.edgeId === selectedEdgeIdRef.current ? 2.2 : 1;
          pulse.progress += pulse.speed * mult;
          if (pulse.progress > 1) {
            pulse.progress = 0;
          }
          pulse.mesh.position.lerpVectors(pulse.start, pulse.end, pulse.progress);
        });
      }

      // Arrowheads follow each line's highlight color/opacity and scale with camera distance
      {
        const zoomScale = Math.min(3.2, Math.max(0.9, camera.position.length() / 130));
        edgeObjectsRef.current.forEach((eo) => {
          const am = eo.arrowMesh;
          if (!am) return;
          am.material.color.copy(eo.lineMesh.material.color);
          am.material.opacity = Math.min(1, eo.lineMesh.material.opacity + 0.35);
          am.scale.setScalar(zoomScale);
        });
      }

      // Astral AI overlay animations (data pulses, shockwave rings)
      if (copilotAnimRef.current.length > 0) {
        const tNow = performance.now() / 1000;
        copilotAnimRef.current.forEach((fn) => fn(tNow));
      }

      // Edge focus packets: high-velocity energy along Source → Target
      const tEdge = performance.now() / 1000;
      const pool = packetPoolRef.current;
      const fe = focusEdgeIdRef.current ? edgeObjectsRef.current.get(focusEdgeIdRef.current) : null;
      if (fe && pool.length) {
        pool.forEach((pk, k) => {
          const u = (tEdge * 0.55 + k / pool.length) % 1;
          pk.position.lerpVectors(fe.start, fe.end, u);
          pk.scale.setScalar(0.9 + 0.35 * Math.sin(tEdge * 10 + k));
          pk.visible = true;
        });
      } else {
        pool.forEach((pk) => (pk.visible = false));
      }
      // Selected-edge endpoint rings: billboard towards camera and breathe
      if (edgeRingsRef.current.length) {
        const qInv = galaxyGroup.getWorldQuaternion(new THREE.Quaternion()).invert();
        const qFace = qInv.multiply(camera.quaternion);
        edgeRingsRef.current.forEach((r) => {
          const sc = 6.4 + 1.1 * Math.sin(tEdge * 3 + r.phase);
          r.mesh.scale.setScalar(sc);
          r.mesh.quaternion.copy(qFace);
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
  }, [updateVisualHighlights]);

  // Populate 3D graph elements ONLY when graphData changes (Preserves scene across selections)
  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene || !graphData || !graphData.nodes) return;

    const galaxyGroup = scene.getObjectByName('GALAXY_ROTATION_GROUP');
    if (!galaxyGroup) return;

    // Clear previous children (edge-focus beam and packet pool persist across rebuilds)
    [...galaxyGroup.children].forEach((obj) => {
      if (!obj.userData?.persistentOverlay) galaxyGroup.remove(obj);
    });

    nodeMeshesRef.current.clear();
    labelSpritesRef.current.clear();
    edgeObjectsRef.current.clear();
    folderRegionsRef.current.clear();
    pulsesRef.current = [];

    const nodes = graphData.nodes;
    const nodeCoords = new Map();

    // Map clusters for palettes and names
    const clusterMap = new Map();
    if (Array.isArray(graphData.clusters)) {
      graphData.clusters.forEach((c) => clusterMap.set(c.path, c));
    }

    // Step 1: Bucket nodes by cluster_id
    const clusterBuckets = new Map();
    nodes.forEach((node) => {
      const cid = node.position_hint?.cluster_id ?? 0;
      if (!clusterBuckets.has(cid)) clusterBuckets.set(cid, []);
      clusterBuckets.get(cid).push(node);
    });

    const uniqueClusters = Array.from(clusterBuckets.keys()).sort((a, b) => a - b);
    const numClusters = Math.max(uniqueClusters.length, 1);

    // Step 2: Position cluster constellation centers
    const clusterCenters = new Map();
    uniqueClusters.forEach((cid, cIdx) => {
      const cAngle = (cIdx / numClusters) * Math.PI * 2;
      const cRadius = numClusters === 1 ? 0 : 74;
      const cElevation = (cIdx % 2 === 0 ? 1 : -1) * 12;
      clusterCenters.set(cid, new THREE.Vector3(
        Math.cos(cAngle) * cRadius,
        cElevation,
        Math.sin(cAngle) * cRadius
      ));
    });

    // Step 3: Position individual nodes in planetary orbits around their cluster center
    uniqueClusters.forEach((cid) => {
      const cCenter = clusterCenters.get(cid);
      const cNodes = clusterBuckets.get(cid) || [];
      const cTotal = Math.max(cNodes.length, 1);

      cNodes.forEach((node, j) => {
        const nAngle = (j / cTotal) * Math.PI * 2;
        const nRadius = cTotal === 1 ? 0 : (20 + (j % 2) * 8);
        const nHeight = (j % 2 === 0 ? 1 : -1) * (6 + (j % 3) * 4);

        const pos = new THREE.Vector3(
          cCenter.x + Math.cos(nAngle) * nRadius,
          cCenter.y + nHeight,
          cCenter.z + Math.sin(nAngle) * nRadius
        );
        nodeCoords.set(node.id, pos);
      });
    });

    // Step 4: Relaxation pass ensuring no two spheres collide
    const minDistance = 22;
    for (let pass = 0; pass < 12; pass++) {
      nodes.forEach((n1) => {
        const p1 = nodeCoords.get(n1.id);
        if (!p1) return;
        nodes.forEach((n2) => {
          if (n1.id === n2.id) return;
          const p2 = nodeCoords.get(n2.id);
          if (!p2) return;
          const dist = p1.distanceTo(p2);
          if (dist < minDistance && dist > 0.001) {
            const diff = new THREE.Vector3().subVectors(p1, p2).normalize();
            const push = (minDistance - dist) * 0.5;
            p1.addScaledVector(diff, push);
            p2.addScaledVector(diff, -push);
          }
        });
      });
    }

    // Step 5: Construct 3D Folder Grouping Regions (Part 3)
    const clusterPoints = new Map();
    nodes.forEach((node) => {
      const pos = nodeCoords.get(node.id);
      if (!pos) return;
      const cPath = node.cluster || (node.path ? node.path.split('/')[0] : 'root');
      if (!clusterPoints.has(cPath)) {
        clusterPoints.set(cPath, []);
      }
      clusterPoints.get(cPath).push({ pos, node });
    });

    clusterPoints.forEach((items, cPath) => {
      let minX = Infinity, maxX = -Infinity;
      let minY = Infinity, maxY = -Infinity;
      let minZ = Infinity, maxZ = -Infinity;

      items.forEach(({ pos }) => {
        minX = Math.min(minX, pos.x);
        maxX = Math.max(maxX, pos.x);
        minY = Math.min(minY, pos.y);
        maxY = Math.max(maxY, pos.y);
        minZ = Math.min(minZ, pos.z);
        maxZ = Math.max(maxZ, pos.z);
      });

      const clusterInfo = clusterMap.get(cPath);
      const folderColor = clusterInfo?.color || CLUSTER_COLORS[items[0]?.node?.position_hint?.cluster_id ?? 0] || '#38bdf8';
      const folderName = clusterInfo?.name || (cPath === 'root' ? 'root/' : `${cPath}/`);

      const pad = 24;
      const sizeX = Math.max(maxX - minX + pad * 2, 42);
      const sizeY = Math.max(maxY - minY + pad * 2, 30);
      const sizeZ = Math.max(maxZ - minZ + pad * 2, 42);

      const centerX = (minX + maxX) / 2;
      const centerY = (minY + maxY) / 2;
      const centerZ = (minZ + maxZ) / 2;

      // Subtle translucent box fill
      const boxGeo = new THREE.BoxGeometry(sizeX, sizeY, sizeZ);
      const fillMat = new THREE.MeshBasicMaterial({
        color: folderColor,
        transparent: true,
        opacity: 0.04,
        depthWrite: false,
        side: THREE.BackSide,
      });
      const fillMesh = new THREE.Mesh(boxGeo, fillMat);
      fillMesh.position.set(centerX, centerY, centerZ);
      fillMesh.raycast = () => {};
      galaxyGroup.add(fillMesh);

      // Thin boundary wireframe shell
      const edgesGeo = new THREE.EdgesGeometry(boxGeo);
      const edgeMat = new THREE.LineBasicMaterial({
        color: folderColor,
        transparent: true,
        opacity: 0.22,
        depthWrite: false,
      });
      const outlineMesh = new THREE.LineSegments(edgesGeo, edgeMat);
      outlineMesh.position.set(centerX, centerY, centerZ);
      outlineMesh.raycast = () => {};
      galaxyGroup.add(outlineMesh);

      // Crisp billboard label positioned above region
      const labelText = `${folderName} (${items.length} ${items.length === 1 ? 'file' : 'files'})`;
      const labelSprite = makeFolderLabelSprite(labelText, { color: folderColor });
      labelSprite.position.set(centerX, centerY + sizeY / 2 + 10, centerZ);
      galaxyGroup.add(labelSprite);

      folderRegionsRef.current.set(cPath, {
        cPath,
        folderName,
        color: folderColor,
        fillMesh,
        outlineMesh,
        labelSprite,
        baseFillOpacity: 0.04,
        baseOutlineOpacity: 0.22,
        baseLabelOpacity: 0.90,
      });
    });

    // Step 6: Render Code Nodes (Spheres + Crisp elevated labels)
    nodes.forEach((node, i) => {
      const pos = nodeCoords.get(node.id);
      const cluster = node.position_hint?.cluster_id ?? 0;
      const size = Math.max(2.0, Math.min(4.0, 2.2 + (node.metrics?.centrality || 0) * 2.5));
      const geom = new THREE.SphereGeometry(size, 24, 24);

      const baseColor =
        (node.type === 'class' || node.type === 'function' || node.type === 'directory')
          ? (TYPE_COLORS[node.type] || '#00e5ff')
          : (CLUSTER_COLORS[cluster] || '#38bdf8');
      const colorHex = node.color || baseColor;

      const mat = new THREE.MeshStandardMaterial({
        color: colorHex,
        emissive: colorHex,
        emissiveIntensity: 0.65,
        roughness: 0.2,
        metalness: 0.7,
      });

      const mesh = new THREE.Mesh(geom, mat);
      mesh.position.copy(pos);
      mesh.userData = { nodeId: node.id, nodeData: node, defaultColor: colorHex };

      galaxyGroup.add(mesh);
      nodeMeshesRef.current.set(node.id, mesh);

      // Node label
      const sprite = makeTextSprite(node.label, { color: colorHex });
      const labelElev = size + 5.0 + (i % 2) * 4.0;
      sprite.position.set(pos.x, pos.y + labelElev, pos.z);
      galaxyGroup.add(sprite);
      labelSpritesRef.current.set(node.id, sprite);
    });

    // Step 7: Render Directed Edges & Flowing Data Pulses
    if (Array.isArray(graphData.edges)) {
      const pulseGeom = new THREE.SphereGeometry(0.75, 12, 12);
      const arrowGeo = new THREE.ConeGeometry(1.15, 3.6, 14);

      graphData.edges.forEach((edge, eIdx) => {
        const p1 = nodeCoords.get(edge.source);
        const p2 = nodeCoords.get(edge.target);
        if (p1 && p2) {
          // Consistent encoding (also in the legend): color + line style + arrowhead + optional label.
          //   imports = orange solid, calls = sky dashed, structural = purple/green (hidden by default)
          let defaultColor = 0xf97316;
          if (edge.relation === 'calls') defaultColor = 0x38bdf8;
          else if (edge.relation === 'defines') defaultColor = 0xa855f7;
          else if (edge.relation === 'contains') defaultColor = 0x10b981;
          else if (edge.relation === 'extends') defaultColor = 0xe879f9;
          else if (edge.relation === 'implements') defaultColor = 0xa3e635;
          else if (edge.relation === 'renders') defaultColor = 0xfacc15;
          const dashed = ['calls', 'implements', 'renders'].includes(edge.relation);

          const edgeGeo = new THREE.BufferGeometry().setFromPoints([p1, p2]);
          const edgeMat = dashed
            ? new THREE.LineDashedMaterial({ color: defaultColor, transparent: true, opacity: 0.62, depthWrite: false, dashSize: 3, gapSize: 2 })
            : new THREE.LineBasicMaterial({ color: defaultColor, transparent: true, opacity: 0.62, depthWrite: false });
          const line = new THREE.Line(edgeGeo, edgeMat);
          if (dashed) line.computeLineDistances();
          line.renderOrder = 2;
          line.userData = { edgeId: edge.id, edgeData: edge };
          galaxyGroup.add(line);

          // Directional arrowhead at the TARGET (importer -> imported, caller -> callee)
          const dirN = new THREE.Vector3().subVectors(p2, p1);
          const edgeLen = dirN.length();
          let arrow = null;
          if (edgeLen > 1) {
            dirN.normalize();
            arrow = new THREE.Mesh(
              arrowGeo,
              new THREE.MeshBasicMaterial({ color: defaultColor, transparent: true, opacity: 0.95, depthTest: false, depthWrite: false }),
            );
            arrow.position.copy(p2).addScaledVector(dirN, -Math.min(6.4, edgeLen * 0.4));
            arrow.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dirN); // cone tip (+Y) -> target
            arrow.renderOrder = 4;
            arrow.raycast = () => {};
            galaxyGroup.add(arrow);
          }

          if (showEdgeLabelsRef.current) {
            const lbl = makeTextSprite(edge.relation || 'imports', { color: '#' + defaultColor.toString(16).padStart(6, '0') });
            lbl.position.copy(p1).add(p2).multiplyScalar(0.5);
            lbl.raycast = () => {};
            galaxyGroup.add(lbl);
          }

          // Flowing pulse particle
          const pulseMat = new THREE.MeshBasicMaterial({
            color: defaultColor,
            transparent: true,
            opacity: 0.90,
          });
          const pulseMesh = new THREE.Mesh(pulseGeom, pulseMat);
          pulseMesh.position.copy(p1);
          pulseMesh.raycast = () => {};
          galaxyGroup.add(pulseMesh);

          pulsesRef.current.push({
            edgeId: edge.id,
            mesh: pulseMesh,
            start: p1,
            end: p2,
            progress: (eIdx * 0.22) % 1,
            speed: 0.005 + (eIdx % 3) * 0.002,
          });

          edgeObjectsRef.current.set(edge.id, {
            id: edge.id,
            start: p1.clone(),
            end: p2.clone(),
            source: edge.source,
            target: edge.target,
            relation: edge.relation || 'imports',
            lineMesh: line,
            pulseMesh,
            arrowMesh: arrow,
            defaultColor,
            defaultOpacity: 0.62,
          });
        }
      });
    }

    // Apply active selection / highlights
    updateVisualHighlights(null, null, selectedNodeIdRef.current);
  }, [graphData, showEdgeLabels, updateVisualHighlights]);

  // Reset camera + selection overlay (driven by the Graph Tools panel)
  useEffect(() => {
    if (!resetToken || !cameraRef.current) return;
    flightTargetRef.current = new THREE.Vector3(0, 45, 140);
    lookTargetRef.current = new THREE.Vector3(0, 0, 0);
  }, [resetToken]);

  // Synchronize selection changes with visual highlights and smooth camera navigation
  useEffect(() => {
    updateVisualHighlights(hoverTargetRef.current?.nodeId, hoverTargetRef.current?.edgeId, selectedNodeId);

    if (selectedNodeId) {
      const mesh = nodeMeshesRef.current.get(selectedNodeId);
      if (mesh && cameraRef.current) {
        const targetWorldPos = new THREE.Vector3();
        mesh.getWorldPosition(targetWorldPos);

        const offsetDir = targetWorldPos.clone().normalize();
        if (offsetDir.lengthSq() < 0.001) offsetDir.set(0, 0, 1);

        const zoom = Math.max(0.5, Math.min(4, copilotFxRef.current?.zoom || 1));
        const cameraDest = targetWorldPos
          .clone()
          .add(offsetDir.multiplyScalar(68 / zoom))
          .add(new THREE.Vector3(0, 22 / zoom, 34 / zoom));
        flightTargetRef.current = cameraDest;
        lookTargetRef.current = targetWorldPos.clone();
      }
    } else {
      // Clear flight target when deselected
      flightTargetRef.current = null;
      lookTargetRef.current = new THREE.Vector3(0, 0, 0);
    }
  }, [selectedNodeId, updateVisualHighlights]);

  // Fly to a node on demand (also when it is already selected), used by Astral AI `focusCameraOnNode`
  useEffect(() => {
    const id = copilotFx?.focusNodeId;
    if (!copilotFx?.focusToken || !id) return;
    const mesh = nodeMeshesRef.current.get(id);
    if (!mesh || !cameraRef.current) return;
    const targetWorldPos = new THREE.Vector3();
    mesh.getWorldPosition(targetWorldPos);
    const offsetDir = targetWorldPos.clone().normalize();
    if (offsetDir.lengthSq() < 0.001) offsetDir.set(0, 0, 1);
    const zoom = Math.max(0.5, Math.min(4, copilotFx.zoom || 1));
    flightTargetRef.current = targetWorldPos
      .clone()
      .add(offsetDir.multiplyScalar(68 / zoom))
      .add(new THREE.Vector3(0, 22 / zoom, 34 / zoom));
    lookTargetRef.current = targetWorldPos.clone();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [copilotFx?.focusToken]);

  // Frame a set of nodes (workflow path, blast radius, cluster) in the viewport
  const fitCameraToNodes = useCallback((ids) => {
    const cam = cameraRef.current;
    if (!cam) return;
    const pts = [];
    ids.forEach((id) => {
      const mesh = nodeMeshesRef.current.get(id);
      if (mesh) {
        const v = new THREE.Vector3();
        mesh.getWorldPosition(v);
        pts.push(v);
      }
    });
    if (!pts.length) return;
    const center = pts.reduce((a, p) => a.add(p), new THREE.Vector3()).divideScalar(pts.length);
    const radius = Math.max(18, ...pts.map((p) => p.distanceTo(center)));
    const dir = cam.position.clone().sub(center);
    if (dir.lengthSq() < 1) dir.set(0, 0.35, 1);
    dir.normalize();
    flightTargetRef.current = center.clone().add(dir.multiplyScalar(Math.min(420, radius * 2.1 + 55)));
    lookTargetRef.current = center;
  }, []);

  // Draw the overlay on top of the base highlight state (called at the end of updateVisualHighlights)
  const applyCopilotOverlay = useCallback(() => {
    const fx = copilotFxRef.current;
    if (!fx || (!fx.workflow && !fx.blast && !fx.cluster)) return;

    const meshes = nodeMeshesRef.current;
    const sprites = labelSpritesRef.current;
    const edges = edgeObjectsRef.current;

    const paint = (id, o) => {
      const mesh = meshes.get(id);
      if (!mesh) return;
      mesh.scale.setScalar(o.scale ?? 1);
      mesh.material.transparent = o.opacity < 1;
      mesh.material.opacity = o.opacity;
      mesh.material.emissiveIntensity = o.glow;
      const color = o.color !== undefined ? o.color : mesh.userData.defaultColor;
      mesh.material.color.set(color);
      mesh.material.emissive.set(color);
      const sp = sprites.get(id);
      if (sp) sp.material.opacity = o.labelOpacity ?? o.opacity;
    };
    const paintEdge = (edgeObj, color, lineOpacity, pulseOpacity) => {
      edgeObj.lineMesh.material.color.set(color !== undefined ? color : edgeObj.defaultColor);
      edgeObj.lineMesh.material.opacity = lineOpacity;
      edgeObj.pulseMesh.material.opacity = pulseOpacity;
    };

    const isCluster = Boolean(fx.cluster);
    const dimOpacity = isCluster ? 0.15 : 0.12;

    // Baseline: dim everything
    meshes.forEach((_, id) => paint(id, { opacity: dimOpacity, glow: 0.12 }));
    edges.forEach((e) => paintEdge(e, undefined, 0.04, 0.04));
    folderRegionsRef.current.forEach((folder) => {
      folder.fillMesh.material.opacity = 0.015;
      folder.outlineMesh.material.opacity = 0.08;
      folder.labelSprite.material.opacity = 0.25;
    });

    if (fx.workflow) {
      const ids = fx.workflow.nodeIds;
      ids.forEach((id, i) =>
        paint(id, {
          opacity: 1,
          glow: 1.35,
          scale: i === 0 ? 1.5 : 1.3,
          color: i === 0 ? 0xfdba74 : 0xfb923c,
        }),
      );
      for (let i = 0; i < ids.length - 1; i++) {
        edges.forEach((e) => {
          if ((e.source === ids[i] && e.target === ids[i + 1]) || (e.source === ids[i + 1] && e.target === ids[i])) {
            paintEdge(e, 0xfb923c, 1, 1);
          }
        });
      }
    } else if (fx.blast) {
      const { sourceId, affected } = fx.blast;
      const depthOf = new Map(affected.map((a) => [a.id, a.depth]));
      const depthColor = (d) => (d <= 1 ? 0xef4444 : d === 2 ? 0xf97316 : 0xfbbf24);
      paint(sourceId, { opacity: 1, glow: 1.7, scale: 1.6, color: 0xef4444 });
      affected.forEach((a) => paint(a.id, { opacity: 1, glow: 1.25, scale: 1.25, color: depthColor(a.depth) }));
      edges.forEach((e) => {
        const tgtIn = e.target === sourceId || depthOf.has(e.target);
        const srcIn = e.source === sourceId || depthOf.has(e.source);
        if (tgtIn && srcIn) paintEdge(e, 0xf59e0b, 0.95, 1);
      });
    } else if (fx.cluster) {
      const set = new Set(fx.cluster.nodeIds);
      set.forEach((id) => paint(id, { opacity: 1, glow: 0.95, scale: 1.1 }));
      edges.forEach((e) => {
        const a = set.has(e.source);
        const b = set.has(e.target);
        if (a && b) paintEdge(e, undefined, 0.85, 1);
        else if (a || b) paintEdge(e, undefined, 0.08, 0.08);
      });
      folderRegionsRef.current.forEach((folder) => {
        if (folder.cPath === fx.cluster.key) {
          folder.fillMesh.material.opacity = 0.12;
          folder.outlineMesh.material.opacity = 0.6;
          folder.labelSprite.material.opacity = 1;
        }
      });
    }
  }, []);
  copilotOverlayRef.current = applyCopilotOverlay;

  // Build / tear down the animated overlay objects (path pulses, shockwave rings)
  const fxWorkflow = copilotFx?.workflow || null;
  const fxBlast = copilotFx?.blast || null;
  const fxCluster = copilotFx?.cluster || null;
  useEffect(() => {
    const scene = sceneRef.current;
    const group = scene?.getObjectByName('GALAXY_ROTATION_GROUP');
    const created = [];
    const anim = [];

    if (group) {
      const meshes = nodeMeshesRef.current;

      if (fxWorkflow) {
        const pts = fxWorkflow.nodeIds
          .map((id) => meshes.get(id))
          .filter(Boolean)
          .map((m) => m.position.clone());
        if (pts.length >= 2) {
          const lineGeo = new THREE.BufferGeometry().setFromPoints(pts);
          const lineMat = new THREE.LineBasicMaterial({
            color: 0xfb923c,
            transparent: true,
            opacity: 0.95,
            depthWrite: false,
            blending: THREE.AdditiveBlending,
          });
          const line = new THREE.Line(lineGeo, lineMat);
          line.raycast = () => {};
          group.add(line);
          created.push(line);

          const cum = [0];
          for (let i = 1; i < pts.length; i++) cum.push(cum[i - 1] + pts[i].distanceTo(pts[i - 1]));
          const total = cum[cum.length - 1] || 1;

          const PULSES = 4;
          for (let k = 0; k < PULSES; k++) {
            const core = new THREE.Mesh(
              new THREE.SphereGeometry(0.95, 16, 16),
              new THREE.MeshBasicMaterial({ color: 0xfff1e0 }),
            );
            const halo = new THREE.Mesh(
              new THREE.SphereGeometry(2.4, 16, 16),
              new THREE.MeshBasicMaterial({
                color: 0xfb923c,
                transparent: true,
                opacity: 0.38,
                depthWrite: false,
                blending: THREE.AdditiveBlending,
              }),
            );
            core.add(halo);
            core.raycast = () => {};
            halo.raycast = () => {};
            group.add(core);
            created.push(core);
            anim.push((t) => {
              const u = (t * 0.17 + k / PULSES) % 1;
              const d = u * total;
              let seg = 1;
              while (seg < cum.length - 1 && cum[seg] < d) seg++;
              const span = cum[seg] - cum[seg - 1] || 1;
              core.position.lerpVectors(pts[seg - 1], pts[seg], Math.min(1, Math.max(0, (d - cum[seg - 1]) / span)));
              core.scale.setScalar(1 + 0.25 * Math.sin(t * 8 + k * 1.7));
            });
          }
          fitCameraToNodes(fxWorkflow.nodeIds);
        }
      } else if (fxBlast) {
        const src = meshes.get(fxBlast.sourceId);
        if (src) {
          const origin = src.position.clone();
          let maxR = 24;
          fxBlast.affected.forEach((a) => {
            const m = meshes.get(a.id);
            if (m) maxR = Math.max(maxR, origin.distanceTo(m.position));
          });
          const reach = maxR * 1.12 + 8;
          const qWorld = new THREE.Quaternion();
          const RINGS = 3;
          for (let k = 0; k < RINGS; k++) {
            const ring = new THREE.Mesh(
              new THREE.RingGeometry(0.93, 1, 96),
              new THREE.MeshBasicMaterial({
                color: k % 2 ? 0xf97316 : 0xef4444,
                transparent: true,
                opacity: 0.8,
                side: THREE.DoubleSide,
                depthWrite: false,
                blending: THREE.AdditiveBlending,
              }),
            );
            ring.position.copy(origin);
            ring.raycast = () => {};
            group.add(ring);
            created.push(ring);
            anim.push((t) => {
              const phase = (t * 0.42 + k / RINGS) % 1;
              const s = 2 + phase * reach;
              ring.scale.set(s, s, s);
              ring.material.opacity = Math.pow(1 - phase, 1.6) * 0.85;
              // billboard the ring towards the camera inside the rotating group
              const cam = cameraRef.current;
              if (cam) {
                group.getWorldQuaternion(qWorld).invert();
                ring.quaternion.copy(qWorld.multiply(cam.quaternion));
              }
            });
          }
          fitCameraToNodes([fxBlast.sourceId, ...fxBlast.affected.map((a) => a.id)]);
        }
      } else if (fxCluster) {
        fitCameraToNodes(fxCluster.nodeIds);
      }
    }

    copilotAnimRef.current = anim;
    // Restore the base highlight state and (if active) draw the overlay on top
    updateVisualHighlights(hoverTargetRef.current?.nodeId, hoverTargetRef.current?.edgeId, selectedNodeIdRef.current);

    return () => {
      copilotAnimRef.current = [];
      created.forEach((obj) => {
        obj.parent?.remove(obj);
        obj.traverse((child) => {
          child.geometry?.dispose?.();
          child.material?.dispose?.();
        });
      });
    };
  }, [fxWorkflow, fxBlast, fxCluster, graphData, fitCameraToNodes, updateVisualHighlights]);

  // Selected beam: frame both endpoints, add orbital rings, and repaint the highlight pass
  useEffect(() => {
    selectedEdgeIdRef.current = selectedEdgeId || null;
    const group = sceneRef.current?.getObjectByName('GALAXY_ROTATION_GROUP');
    edgeRingsRef.current.forEach((r) => {
      r.mesh.parent?.remove(r.mesh);
      r.mesh.geometry.dispose();
      r.mesh.material.dispose();
    });
    edgeRingsRef.current = [];

    const f = selectedEdgeId ? edgeObjectsRef.current.get(selectedEdgeId) : null;
    if (f && group) {
      [f.start, f.end].forEach((p, i) => {
        const mesh = new THREE.Mesh(
          new THREE.RingGeometry(0.9, 1, 64),
          new THREE.MeshBasicMaterial({
            color: i ? 0xfdba74 : 0xfb923c,
            transparent: true,
            opacity: 0.9,
            side: THREE.DoubleSide,
            depthWrite: false,
            blending: THREE.AdditiveBlending,
          }),
        );
        mesh.position.copy(p);
        mesh.raycast = () => {};
        group.add(mesh);
        edgeRingsRef.current.push({ mesh, phase: i * Math.PI });
      });

      const cam = cameraRef.current;
      if (cam) {
        const mid = f.start.clone().add(f.end).multiplyScalar(0.5);
        const span = f.start.distanceTo(f.end);
        const dir = cam.position.clone().sub(mid);
        if (dir.lengthSq() < 1) dir.set(0, 0.35, 1);
        dir.normalize();
        flightTargetRef.current = mid.clone().add(dir.multiplyScalar(Math.max(70, span * 1.6 + 60)));
        lookTargetRef.current = mid;
      }
    }

    updateVisualHighlights(hoverTargetRef.current?.nodeId, hoverTargetRef.current?.edgeId, selectedNodeIdRef.current);
  }, [selectedEdgeId, graphData, updateVisualHighlights]);

  return (
    <div className={`relative w-full h-full overflow-hidden ${className}`}>
      <div ref={mountRef} className="w-full h-full" style={{ cursor: 'grab' }} />

      {/* Floating Node Tooltip HUD on Hover */}
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

      {/* Floating micro-tooltip that follows the cursor over a dependency beam */}
      {edgeHover && (
        <div className="astral-edge-tip" style={{ left: edgeHover.x + 16, top: edgeHover.y + 16 }}>
          <div className="astral-edge-tip__row">
            <span className="astral-edge-tip__node">[ {edgeHover.src} ]</span>
            <span className="astral-edge-tip__beam">━━( {edgeHover.rel} )━━▶</span>
            <span className="astral-edge-tip__node">[ {edgeHover.tgt} ]</span>
          </div>
          <div className="astral-edge-tip__sub">Click to inspect live data flow &amp; payload →</div>
        </div>
      )}

      {/* Legend: relationship encoding (color + line style + arrowhead), not color alone */}
      <div className="absolute top-4 right-4 pointer-events-none bg-black/70 border border-white/10 p-2.5 rounded text-xs font-mono space-y-1.5 backdrop-blur-sm z-20" aria-label="Graph legend">
        <div className="text-gray-400 text-[10px] uppercase font-bold tracking-wider">Edges (arrow = direction)</div>
        <div className="flex items-center gap-2"><span style={{ color: '#f97316' }}>━━▶</span> imports (solid): A imports B</div>
        <div className="flex items-center gap-2"><span style={{ color: '#38bdf8' }}>╌╌▶</span> calls (dashed): A calls B</div>
        <div className="flex items-center gap-2"><span style={{ color: '#e879f9' }}>━━▶</span> extends (solid): A inherits B</div>
        <div className="flex items-center gap-2"><span style={{ color: '#a3e635' }}>╌╌▶</span> implements (dashed): A implements B</div>
        <div className="flex items-center gap-2"><span style={{ color: '#facc15' }}>╌╌▶</span> renders (dashed): component A renders B</div>
        <div className="text-gray-500 text-[10px]">Folders are visual groups, never endpoints. Unresolved imports are listed in the panel, not drawn.</div>
      </div>
    </div>
  );
}
