'use client'

import { useEffect, useRef } from 'react'

export default function BrandWave3DSphere() {
  const mountRef = useRef(null)

  useEffect(() => {
    const container = mountRef.current
    if (!container) return

    // Load Three.js dynamically
    const script = document.createElement('script')
    script.src = 'https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js'
    script.onload = () => initScene()
    document.head.appendChild(script)

    function initScene() {
      const THREE = window.THREE
      const container = mountRef.current
      if (!container) return

      const width = container.clientWidth
      const height = container.clientHeight

      // Renderer
      const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
      renderer.setSize(width, height)
      renderer.setClearColor(0x000000, 0)
      container.appendChild(renderer.domElement)

      const scene = new THREE.Scene()
      const camera = new THREE.PerspectiveCamera(48, width / height, 0.1, 100)
      camera.position.set(0, 0, 5.5)

      // ── CORE SPHERE ──────────────────────────────────────────
      const sphereGeo = new THREE.SphereGeometry(1.3, 80, 80)
      const sphereMat = new THREE.MeshStandardMaterial({
        color: 0x080808,
        metalness: 0.95,
        roughness: 0.08,
      })
      const sphere = new THREE.Mesh(sphereGeo, sphereMat)
      scene.add(sphere)

      // Wireframe overlay
      const wireGeo = new THREE.SphereGeometry(1.315, 26, 26)
      const wireMat = new THREE.MeshBasicMaterial({
        color: 0x3b82f6,
        wireframe: true,
        transparent: true,
        opacity: 0.07,
      })
      scene.add(new THREE.Mesh(wireGeo, wireMat))

      // ── RINGS ──────────────────────────────────────────────────
      const makeRing = (radius, tube, color, opacity, rx, ry = 0) => {
        const geo = new THREE.TorusGeometry(radius, tube, 16, 240)
        const mat = new THREE.MeshBasicMaterial({ color, transparent: true, opacity })
        const mesh = new THREE.Mesh(geo, mat)
        mesh.rotation.x = rx
        mesh.rotation.y = ry
        return mesh
      }
      const ring1 = makeRing(1.75, 0.013, 0x3b82f6, 0.7, Math.PI / 2.4)
      const ring2 = makeRing(2.1,  0.008, 0x818cf8, 0.35, Math.PI / 3.2, Math.PI / 6)
      const ring3 = makeRing(2.4,  0.005, 0x60a5fa, 0.18, Math.PI / 1.8, Math.PI / 4)
      scene.add(ring1, ring2, ring3)

      // ── PARTICLE FIELD ─────────────────────────────────────────
      const pCount = 900
      const pPos = new Float32Array(pCount * 3)
      for (let i = 0; i < pCount; i++) {
        const r = 2.6 + Math.random() * 3.2
        const theta = Math.random() * Math.PI * 2
        const phi = Math.acos(2 * Math.random() - 1)
        pPos[i * 3]     = r * Math.sin(phi) * Math.cos(theta)
        pPos[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta)
        pPos[i * 3 + 2] = r * Math.cos(phi)
      }
      const pGeo = new THREE.BufferGeometry()
      pGeo.setAttribute('position', new THREE.BufferAttribute(pPos, 3))
      const pMat = new THREE.PointsMaterial({
        color: 0x93c5fd, size: 0.022, transparent: true, opacity: 0.6,
      })
      const particles = new THREE.Points(pGeo, pMat)
      scene.add(particles)

      // ── ORBITING NODES ─────────────────────────────────────────
      // Each node represents a BrandWave feature
      const nodeData = [
        { color: 0x22d3ee, orbit: 2.25, speed: 0.38, offset: 0,   yAmp: 0.5,  size: 0.1  }, // Data Scraping
        { color: 0x818cf8, orbit: 2.65, speed: 0.27, offset: 2.1, yAmp: 0.3,  size: 0.08 }, // AI Ads
        { color: 0x34d399, orbit: 2.05, speed: 0.52, offset: 4.2, yAmp: 0.55, size: 0.09 }, // SEO
        { color: 0xfbbf24, orbit: 2.45, speed: 0.33, offset: 1.1, yAmp: 0.4,  size: 0.07 }, // Sentiment
        { color: 0xf472b6, orbit: 1.95, speed: 0.44, offset: 3.3, yAmp: 0.35, size: 0.08 }, // Automation
      ]

      const nodes = nodeData.map(({ color, orbit, speed, offset, yAmp, size }) => {
        const geo = new THREE.SphereGeometry(size, 16, 16)
        const mat = new THREE.MeshBasicMaterial({ color })
        const mesh = new THREE.Mesh(geo, mat)

        // Glow halo
        const glowGeo = new THREE.SphereGeometry(size * 2.2, 16, 16)
        const glowMat = new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.12 })
        mesh.add(new THREE.Mesh(glowGeo, glowMat))

        scene.add(mesh)
        return { mesh, orbit, speed, offset, yAmp }
      })

      // ── CONNECTION LINES between nodes (dynamic) ───────────────
      const lineMat = new THREE.LineBasicMaterial({
        color: 0x3b82f6, transparent: true, opacity: 0.12,
      })
      const lineGeo = new THREE.BufferGeometry()
      const linePositions = new Float32Array(nodeData.length * 2 * 3)
      lineGeo.setAttribute('position', new THREE.BufferAttribute(linePositions, 3))
      const connectionLine = new THREE.LineSegments(lineGeo, lineMat)
      scene.add(connectionLine)

      // ── LIGHTS ─────────────────────────────────────────────────
      scene.add(new THREE.AmbientLight(0xffffff, 0.2))

      const blueLight = new THREE.PointLight(0x3b82f6, 5, 14)
      blueLight.position.set(4, 2, 3)
      scene.add(blueLight)

      const purpleLight = new THREE.PointLight(0x8b5cf6, 3, 12)
      purpleLight.position.set(-3, -2, 2)
      scene.add(purpleLight)

      const cyanLight = new THREE.PointLight(0x22d3ee, 2, 10)
      cyanLight.position.set(0, 3, -2)
      scene.add(cyanLight)

      // ── MOUSE PARALLAX ─────────────────────────────────────────
      let mx = 0, my = 0
      const onMouseMove = (e) => {
        const rect = container.getBoundingClientRect()
        mx = ((e.clientX - rect.left) / rect.width  - 0.5) * 2
        my = -((e.clientY - rect.top)  / rect.height - 0.5) * 2
      }
      window.addEventListener('mousemove', onMouseMove)

      // ── RESIZE ─────────────────────────────────────────────────
      const onResize = () => {
        const w = container.clientWidth
        const h = container.clientHeight
        camera.aspect = w / h
        camera.updateProjectionMatrix()
        renderer.setSize(w, h)
      }
      window.addEventListener('resize', onResize)

      // ── ANIMATION LOOP ─────────────────────────────────────────
      let raf
      const clock = new THREE.Clock()

      const animate = () => {
        raf = requestAnimationFrame(animate)
        const t = clock.getElapsedTime()

        // Sphere slow rotation
        sphere.rotation.y = t * 0.07
        sphere.rotation.x = t * 0.022

        // Rings
        ring1.rotation.z = t * 0.18
        ring2.rotation.z = -t * 0.11
        ring3.rotation.z = t * 0.07

        // Particle drift
        particles.rotation.y = t * 0.035
        particles.rotation.x = t * 0.012

        // Orbiting nodes
        nodes.forEach((n) => {
          const a = t * n.speed + n.offset
          n.mesh.position.x = Math.cos(a) * n.orbit
          n.mesh.position.z = Math.sin(a) * n.orbit
          n.mesh.position.y = Math.sin(a * 0.55) * n.yAmp
        })

        // Update connection lines (connect each node to sphere center)
        const pos = connectionLine.geometry.attributes.position.array
        nodes.forEach((n, i) => {
          const base = i * 6
          pos[base]     = 0; pos[base + 1] = 0; pos[base + 2] = 0
          pos[base + 3] = n.mesh.position.x
          pos[base + 4] = n.mesh.position.y
          pos[base + 5] = n.mesh.position.z
        })
        connectionLine.geometry.attributes.position.needsUpdate = true

        // Camera parallax
        camera.position.x += (mx * 0.45 - camera.position.x) * 0.04
        camera.position.y += (my * 0.32 - camera.position.y) * 0.04
        camera.lookAt(scene.position)

        renderer.render(scene, camera)
      }
      animate()

      // Cleanup
      container._cleanup = () => {
        cancelAnimationFrame(raf)
        window.removeEventListener('mousemove', onMouseMove)
        window.removeEventListener('resize', onResize)
        renderer.dispose()
        if (container.contains(renderer.domElement)) {
          container.removeChild(renderer.domElement)
        }
      }
    }

    return () => {
      mountRef.current?._cleanup?.()
    }
  }, [])

  return (
    <div
      ref={mountRef}
      style={{ width: '100%', height: '100%', minHeight: '500px' }}
    />
  )
}