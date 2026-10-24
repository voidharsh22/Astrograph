/**
 * Astral Cartographer — Three.js 3D Celestial Galaxy Canvas
 * High-performance WebGL visualization rendered in deep obsidian space with amber cosmic glow,
 * Louvain constellation clusters, raycaster picking, and camera fly-to animations.
 */

import React, { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { GraphEdge, GraphNode, NodeType, Workflow } from '../types/galaxy'

interface GalaxyCanvas3DProps {
  nodes: GraphNode[]
  edges: GraphEdge[]
  selectedNodeId: string | null
  focusNodeId: string | null
  activeWorkflow: Workflow | null
  activeTypeFilter: string // 'all' | 'file' | 'class' | 'function' | 'directory'
  onSelectNode: (node: GraphNode | null) => void
}

export const GalaxyCanvas3D: React.FC<GalaxyCanvas3DProps> = ({
  nodes,
  edges,
  selectedNodeId,
  focusNodeId,
  activeWorkflow,
  activeTypeFilter,
  onSelectNode,
}) => {
  const mountRef = useRef<HTMLDivElement>(null)
  const [hoveredNode, setHoveredNode] = useState<{ node: GraphNode; x: number; y: number } | null>(null)

  // Three.js object references across renders
  const sceneRef = useRef<THREE.Scene | null>(null)
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null)
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null)
  const nodeMeshMapRef = useRef<Map<string, THREE.Mesh>>(new Map())
  const nodeDataMapRef = useRef<Map<string, GraphNode>>(new Map())
  const edgeMeshGroupRef = useRef<THREE.Group | null>(null)
  const pulseGroupRef = useRef<THREE.Group | null>(null)

  // Camera animation target
  const cameraTargetRef = useRef<{
    active: boolean
    targetPos: THREE.Vector3
    lookAtPos: THREE.Vector3
    alpha: number
  }>({
    active: false,
    targetPos: new THREE.Vector3(),
    lookAtPos: new THREE.Vector3(),
    alpha: 0,
  })

  // Camera Orbit Controls state
  const orbitRef = useRef({
    isDragging: false,
    isPanning: false,
    prevMouseX: 0,
    prevMouseY: 0,
    spherical: { radius: 360, theta: Math.PI / 4, phi: Math.PI / 3 },
    target: new THREE.Vector3(0, 0, 0),
  })

  // Initialize Three.js Scene
  useEffect(() => {
    const mount = mountRef.current
    if (!mount) return

    const width = mount.clientWidth || window.innerWidth
    const height = mount.clientHeight || window.innerHeight

    // 1. Scene
    const scene = new THREE.Scene()
    scene.background = new THREE.Color('#070a13')
    scene.fog = new THREE.FogExp2('#070a13', 0.0012)
    sceneRef.current = scene

    // 2. Camera
    const camera = new THREE.PerspectiveCamera(45, width / height, 1, 3000)
    camera.position.set(220, 180, 260)
    camera.lookAt(0, 0, 0)
    cameraRef.current = camera

    // 3. Renderer
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: 'high-performance' })
    renderer.setSize(width, height)
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.toneMapping = THREE.ACESFilmicToneMapping
    renderer.toneMappingExposure = 1.2
    mount.appendChild(renderer.domElement)
    rendererRef.current = renderer

    // 4. Lights
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.7)
    scene.add(ambientLight)

    const centralLight = new THREE.PointLight(0xf97316, 2.5, 800, 1)
    centralLight.position.set(0, 0, 0)
    scene.add(centralLight)

    const rimLight = new THREE.DirectionalLight(0x38bdf8, 1.2)
    rimLight.position.set(300, 400, 200)
    scene.add(rimLight)

    // 5. Cosmic Starfield Background Particles
    const starCount = 3200
    const starGeo = new THREE.BufferGeometry()
    const starPositions = new Float32Array(starCount * 3)
    const starColors = new Float32Array(starCount * 3)

    for (let i = 0; i < starCount; i++) {
      const radius = 600 + Math.random() * 1200
      const theta = Math.random() * Math.PI * 2
      const phi = Math.acos(2 * Math.random() - 1)
      starPositions[i * 3] = radius * Math.sin(phi) * Math.cos(theta)
      starPositions[i * 3 + 1] = radius * Math.sin(phi) * Math.sin(theta)
      starPositions[i * 3 + 2] = radius * Math.cos(phi)

      // Mix of warm amber, crisp cyan, and pale white stars
      const rVal = Math.random()
      if (rVal < 0.25) {
        starColors[i * 3] = 0.98; starColors[i * 3 + 1] = 0.65; starColors[i * 3 + 2] = 0.25
      } else if (rVal < 0.5) {
        starColors[i * 3] = 0.25; starColors[i * 3 + 1] = 0.75; starColors[i * 3 + 2] = 0.98
      } else {
        starColors[i * 3] = 0.85; starColors[i * 3 + 1] = 0.9; starColors[i * 3 + 2] = 1.0
      }
    }
    starGeo.setAttribute('position', new THREE.BufferAttribute(starPositions, 3))
    starGeo.setAttribute('color', new THREE.BufferAttribute(starColors, 3))
    const starMat = new THREE.PointsMaterial({ size: 2.2, vertexColors: true, transparent: true, opacity: 0.85 })
    const starField = new THREE.Points(starGeo, starMat)
    scene.add(starField)

    // 6. Groups for Edges and Workflow Pulses
    const edgeGroup = new THREE.Group()
    scene.add(edgeGroup)
    edgeMeshGroupRef.current = edgeGroup

    const pulseGroup = new THREE.Group()
    scene.add(pulseGroup)
    pulseGroupRef.current = pulseGroup

    // 7. Mouse Orbit & Pan Listeners
    const onMouseDown = (e: MouseEvent) => {
      if (e.button === 0) orbitRef.current.isDragging = true
      if (e.button === 2) orbitRef.current.isPanning = true
      orbitRef.current.prevMouseX = e.clientX
      orbitRef.current.prevMouseY = e.clientY
    }

    const onMouseMove = (e: MouseEvent) => {
      const deltaX = e.clientX - orbitRef.current.prevMouseX
      const deltaY = e.clientY - orbitRef.current.prevMouseY
      orbitRef.current.prevMouseX = e.clientX
      orbitRef.current.prevMouseY = e.clientY

      if (orbitRef.current.isDragging) {
        cameraTargetRef.current.active = false
        orbitRef.current.spherical.theta -= deltaX * 0.005
        orbitRef.current.spherical.phi = Math.max(0.1, Math.min(Math.PI - 0.1, orbitRef.current.spherical.phi - deltaY * 0.005))
      } else if (orbitRef.current.isPanning) {
        cameraTargetRef.current.active = false
        const cam = cameraRef.current
        if (!cam) return
        const right = new THREE.Vector3(1, 0, 0).applyQuaternion(cam.quaternion)
        const up = new THREE.Vector3(0, 1, 0).applyQuaternion(cam.quaternion)
        orbitRef.current.target.addScaledVector(right, -deltaX * 0.3)
        orbitRef.current.target.addScaledVector(up, deltaY * 0.3)
      }
    }

    const onMouseUp = () => {
      orbitRef.current.isDragging = false
      orbitRef.current.isPanning = false
    }

    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      cameraTargetRef.current.active = false
      orbitRef.current.spherical.radius = Math.max(
        30,
        Math.min(1200, orbitRef.current.spherical.radius + e.deltaY * 0.4)
      )
    }

    const onContextMenu = (e: MouseEvent) => e.preventDefault()

    const dom = renderer.domElement
    dom.addEventListener('mousedown', onMouseDown)
    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('mouseup', onMouseUp)
    dom.addEventListener('wheel', onWheel, { passive: false })
    dom.addEventListener('contextmenu', onContextMenu)

    // Window Resize Handler
    const handleResize = () => {
      if (!mount || !rendererRef.current || !cameraRef.current) return
      const w = mount.clientWidth
      const h = mount.clientHeight
      cameraRef.current.aspect = w / h
      cameraRef.current.updateProjectionMatrix()
      rendererRef.current.setSize(w, h)
    }
    window.addEventListener('resize', handleResize)

    // Animation Loop
    let animationFrameId: number
    let clock = new THREE.Clock()

    const animate = () => {
      animationFrameId = requestAnimationFrame(animate)
      const elapsedTime = clock.getElapsedTime()

      // Slow background cosmic rotation
      starField.rotation.y = elapsedTime * 0.015

      // Smooth camera interpolation (Fly-to animation)
      if (cameraTargetRef.current.active && cameraRef.current) {
        const { targetPos, lookAtPos } = cameraTargetRef.current
        cameraRef.current.position.lerp(targetPos, 0.06)
        orbitRef.current.target.lerp(lookAtPos, 0.08)
        cameraRef.current.lookAt(orbitRef.current.target)

        if (cameraRef.current.position.distanceTo(targetPos) < 1.0) {
          cameraTargetRef.current.active = false
        }
      } else if (cameraRef.current) {
        // Standard Spherical Orbit Update
        const { radius, theta, phi } = orbitRef.current.spherical
        const target = orbitRef.current.target
        const x = target.x + radius * Math.sin(phi) * Math.sin(theta)
        const y = target.y + radius * Math.cos(phi)
        const z = target.z + radius * Math.sin(phi) * Math.cos(theta)
        cameraRef.current.position.set(x, y, z)
        cameraRef.current.lookAt(target)
      }

      // Animate active workflow energy pulses
      if (pulseGroupRef.current && pulseGroupRef.current.children.length > 0) {
        pulseGroupRef.current.children.forEach((pulseMesh: any) => {
          if (pulseMesh.userData?.curve) {
            pulseMesh.userData.t = (pulseMesh.userData.t + 0.008) % 1
            const pt = pulseMesh.userData.curve.getPointAt(pulseMesh.userData.t)
            pulseMesh.position.copy(pt)
          }
        })
      }

      renderer.render(scene, camera)
    }
    animate()

    // Cleanup on unmount
    return () => {
      cancelAnimationFrame(animationFrameId)
      window.removeEventListener('resize', handleResize)
      dom.removeEventListener('mousedown', onMouseDown)
      window.removeEventListener('mousemove', onMouseMove)
      window.removeEventListener('mouseup', onMouseUp)
      dom.removeEventListener('wheel', onWheel)
      dom.removeEventListener('contextmenu', onContextMenu)
      if (mount && renderer.domElement) {
        mount.removeChild(renderer.domElement)
      }
      renderer.dispose()
    }
  }, [])

  // Build / Update Nodes and Edges when nodes/edges/filters change
  useEffect(() => {
    const scene = sceneRef.current
    if (!scene) return

    // Clear previous node meshes
    nodeMeshMapRef.current.forEach((mesh) => scene.remove(mesh))
    nodeMeshMapRef.current.clear()
    nodeDataMapRef.current.clear()

    // Sphere geometries
    const geoSphere = new THREE.SphereGeometry(1, 20, 20)

    nodes.forEach((node) => {
      // Check filter
      if (activeTypeFilter !== 'all' && node.type !== activeTypeFilter) {
        return
      }

      const size = node.size || 3.0
      const colorHex = node.color || '#38bdf8'
      const isSelected = selectedNodeId === node.id || focusNodeId === node.id

      const mat = new THREE.MeshStandardMaterial({
        color: new THREE.Color(colorHex),
        emissive: new THREE.Color(isSelected ? '#ffffff' : colorHex),
        emissiveIntensity: isSelected ? 0.9 : 0.45,
        roughness: 0.3,
        metalness: 0.6,
      })

      const mesh = new THREE.Mesh(geoSphere, mat)
      mesh.scale.set(size, size, size)
      mesh.position.set(node.x ?? 0, node.y ?? 0, node.z ?? 0)
      mesh.userData = { nodeId: node.id }

      scene.add(mesh)
      nodeMeshMapRef.current.set(node.id, mesh)
      nodeDataMapRef.current.set(node.id, node)
    })

    // Rebuild Edges
    const edgeGroup = edgeMeshGroupRef.current
    if (edgeGroup) {
      while (edgeGroup.children.length > 0) {
        edgeGroup.remove(edgeGroup.children[0])
      }

      // Edge relationship color mapping matching Astrograph snapshot
      const edgeColors: Record<string, string> = {
        calls: '#a855f7',     // Purple
        imports: '#38bdf8',   // Cyan / Blue
        contains: '#f59e0b',  // Amber
        inherits: '#10b981',  // Emerald
      }

      const linePoints: THREE.Vector3[] = []
      const lineColors: THREE.Color[] = []

      edges.forEach((edge) => {
        const srcNode = nodeDataMapRef.current.get(edge.source)
        const tgtNode = nodeDataMapRef.current.get(edge.target)

        if (srcNode && tgtNode) {
          const p1 = new THREE.Vector3(srcNode.x ?? 0, srcNode.y ?? 0, srcNode.z ?? 0)
          const p2 = new THREE.Vector3(tgtNode.x ?? 0, tgtNode.y ?? 0, tgtNode.z ?? 0)

          linePoints.push(p1, p2)
          const c = new THREE.Color(edgeColors[edge.relation] || '#38bdf8')
          lineColors.push(c, c)
        }
      })

      if (linePoints.length > 0) {
        const lineGeo = new THREE.BufferGeometry().setFromPoints(linePoints)
        const colorArray = new Float32Array(lineColors.length * 3)
        lineColors.forEach((c, idx) => {
          colorArray[idx * 3] = c.r
          colorArray[idx * 3 + 1] = c.g
          colorArray[idx * 3 + 2] = c.b
        })
        lineGeo.setAttribute('color', new THREE.BufferAttribute(colorArray, 3))

        const lineMat = new THREE.LineBasicMaterial({
          vertexColors: true,
          transparent: true,
          opacity: 0.35,
          blending: THREE.AdditiveBlending,
        })

        const lineSegments = new THREE.LineSegments(lineGeo, lineMat)
        edgeGroup.add(lineSegments)
      }
    }
  }, [nodes, edges, activeTypeFilter, selectedNodeId, focusNodeId])

  // Setup Workflow Pulse Packets
  useEffect(() => {
    const pulseGroup = pulseGroupRef.current
    if (!pulseGroup) return

    while (pulseGroup.children.length > 0) {
      pulseGroup.remove(pulseGroup.children[0])
    }

    if (!activeWorkflow || activeWorkflow.ordered_node_ids.length < 2) return

    const pulseGeo = new THREE.SphereGeometry(1.6, 12, 12)
    const pulseMat = new THREE.MeshBasicMaterial({ color: 0xffedd5, wireframe: false })

    for (let i = 0; i < activeWorkflow.ordered_node_ids.length - 1; i++) {
      const srcId = activeWorkflow.ordered_node_ids[i]
      const tgtId = activeWorkflow.ordered_node_ids[i + 1]
      const src = nodeDataMapRef.current.get(srcId)
      const tgt = nodeDataMapRef.current.get(tgtId)

      if (src && tgt) {
        const p1 = new THREE.Vector3(src.x ?? 0, src.y ?? 0, src.z ?? 0)
        const p2 = new THREE.Vector3(tgt.x ?? 0, tgt.y ?? 0, tgt.z ?? 0)
        const curve = new THREE.LineCurve3(p1, p2)

        const pulseMesh = new THREE.Mesh(pulseGeo, pulseMat)
        pulseMesh.position.copy(p1)
        pulseMesh.userData = { curve, t: i * 0.25 }
        pulseGroup.add(pulseMesh)
      }
    }
  }, [activeWorkflow])

  // Camera Fly-To when node selected or focused
  useEffect(() => {
    const targetId = focusNodeId || selectedNodeId
    if (!targetId || !cameraRef.current) return

    const targetNode = nodeDataMapRef.current.get(targetId)
    if (!targetNode) return

    const nodePos = new THREE.Vector3(targetNode.x ?? 0, targetNode.y ?? 0, targetNode.z ?? 0)

    // Position camera slightly offset from the target node
    const offset = new THREE.Vector3(35, 25, 45)
    const destination = nodePos.clone().add(offset)

    cameraTargetRef.current = {
      active: true,
      targetPos: destination,
      lookAtPos: nodePos,
      alpha: 0,
    }
  }, [focusNodeId, selectedNodeId])

  // Raycasting Click & Hover Interaction
  const handlePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return // Left click only
    const mount = mountRef.current
    if (!mount || !cameraRef.current || !sceneRef.current) return

    const rect = mount.getBoundingClientRect()
    const mouse = new THREE.Vector2(
      ((e.clientX - rect.left) / rect.width) * 2 - 1,
      -((e.clientY - rect.top) / rect.height) * 2 + 1
    )

    const raycaster = new THREE.Raycaster()
    raycaster.setFromCamera(mouse, cameraRef.current)

    const meshes = Array.from(nodeMeshMapRef.current.values())
    const intersects = raycaster.intersectObjects(meshes, false)

    if (intersects.length > 0) {
      const hitMesh = intersects[0].object as THREE.Mesh
      const nodeId = hitMesh.userData?.nodeId
      const node = nodeDataMapRef.current.get(nodeId)
      if (node) {
        onSelectNode(node)
      }
    }
  }

  const handlePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const mount = mountRef.current
    if (!mount || !cameraRef.current) return

    const rect = mount.getBoundingClientRect()
    const mouse = new THREE.Vector2(
      ((e.clientX - rect.left) / rect.width) * 2 - 1,
      -((e.clientY - rect.top) / rect.height) * 2 + 1
    )

    const raycaster = new THREE.Raycaster()
    raycaster.setFromCamera(mouse, cameraRef.current)

    const meshes = Array.from(nodeMeshMapRef.current.values())
    const intersects = raycaster.intersectObjects(meshes, false)

    if (intersects.length > 0) {
      const hitMesh = intersects[0].object as THREE.Mesh
      const nodeId = hitMesh.userData?.nodeId
      const node = nodeDataMapRef.current.get(nodeId)
      if (node) {
        setHoveredNode({ node, x: e.clientX, y: e.clientY })
        mount.style.cursor = 'pointer'
        return
      }
    }
    setHoveredNode(null)
    mount.style.cursor = 'default'
  }

  return (
    <div
      ref={mountRef}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      style={{
        width: '100%',
        height: '100%',
        position: 'relative',
        overflow: 'hidden',
        background: '#070a13',
      }}
    >
      {/* 3D Cosmic Holographic Tooltip on Hover */}
      {hoveredNode && (
        <div
          style={{
            position: 'fixed',
            left: hoveredNode.x + 14,
            top: hoveredNode.y + 14,
            pointerEvents: 'none',
            zIndex: 100,
            background: 'rgba(11, 15, 25, 0.92)',
            backdropFilter: 'blur(12px)',
            border: `1px solid ${hoveredNode.node.color || '#38bdf8'}`,
            boxShadow: `0 8px 24px rgba(0,0,0,0.6), 0 0 16px ${hoveredNode.node.color}40`,
            borderRadius: '8px',
            padding: '8px 12px',
            color: '#fff',
            fontFamily: 'Outfit, sans-serif',
            fontSize: '12px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
            <span
              style={{
                display: 'inline-block',
                width: '8px',
                height: '8px',
                borderRadius: '50%',
                background: hoveredNode.node.color,
                boxShadow: `0 0 8px ${hoveredNode.node.color}`,
              }}
            />
            <span style={{ fontWeight: 600, fontSize: '13px' }}>{hoveredNode.node.label}</span>
            <span
              style={{
                textTransform: 'uppercase',
                fontSize: '9px',
                padding: '2px 5px',
                borderRadius: '4px',
                background: 'rgba(255,255,255,0.08)',
                color: hoveredNode.node.color,
                fontWeight: 700,
              }}
            >
              {hoveredNode.node.type}
            </span>
          </div>
          <div style={{ color: '#94a3b8', fontSize: '11px', fontFamily: 'JetBrains Mono, monospace' }}>
            {hoveredNode.node.path}
          </div>
          {hoveredNode.node.metrics && (
            <div style={{ display: 'flex', gap: '10px', marginTop: '6px', color: '#cbd5e1', fontSize: '11px' }}>
              <span>LOC: <b>{hoveredNode.node.metrics.loc}</b></span>
              <span>Centrality: <b>{(hoveredNode.node.metrics.centrality * 100).toFixed(1)}%</b></span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
