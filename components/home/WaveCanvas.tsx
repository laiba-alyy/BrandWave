'use client'

import { useEffect, useRef } from 'react'

interface Layer {
  amp: number
  len: number
  sp: number
  y: number
  col: string
  a: number
  lw: number
}

const layers: Layer[] = [
  { amp: 26, len: 0.0042, sp: 0.00022, y: 0.42, col: '240,166,60', a: 0.3, lw: 1.6 },
  { amp: 38, len: 0.0031, sp: 0.00015, y: 0.55, col: '62,217,164', a: 0.24, lw: 1.4 },
  { amp: 18, len: 0.006, sp: 0.00033, y: 0.66, col: '240,166,60', a: 0.15, lw: 1.1 },
  { amp: 52, len: 0.0022, sp: 0.0001, y: 0.78, col: '190,225,218', a: 0.1, lw: 1.0 },
]

/**
 * Hero ke peeche chalti hui lehrein — brand mark ka bara version.
 *
 * `prefers-reduced-motion` par ek static frame draw hota hai (blank nahi), aur
 * unmount par rAF loop cancel hota hai — warna route change ke baad bhi canvas
 * har frame par draw karta rehta.
 */
export default function WaveCanvas({ className = 'hero__canvas' }: { className?: string }) {
  const ref = useRef<HTMLCanvasElement | null>(null)

  useEffect(() => {
    const cv = ref.current
    if (!cv) return
    const ctx = cv.getContext('2d')
    if (!ctx) return

    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    let w = 0
    let h = 0
    let raf = 0

    const resize = () => {
      const r = cv.getBoundingClientRect()
      w = r.width
      h = r.height
      cv.width = Math.round(w * dpr)
      cv.height = Math.round(h * dpr)
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    }

    const draw = (t: number) => {
      ctx.clearRect(0, 0, w, h)
      for (const L of layers) {
        ctx.beginPath()
        for (let x = 0; x <= w; x += 6) {
          const y =
            L.y * h +
            Math.sin(x * L.len + t * L.sp) * L.amp +
            Math.sin(x * L.len * 2.3 + t * L.sp * 1.7) * (L.amp * 0.35)
          if (x === 0) ctx.moveTo(x, y)
          else ctx.lineTo(x, y)
        }
        const g = ctx.createLinearGradient(0, 0, w, 0)
        g.addColorStop(0, `rgba(${L.col},0)`)
        g.addColorStop(0.35, `rgba(${L.col},${L.a})`)
        g.addColorStop(0.75, `rgba(${L.col},${L.a * 0.65})`)
        g.addColorStop(1, `rgba(${L.col},0)`)
        ctx.strokeStyle = g
        ctx.lineWidth = L.lw
        ctx.stroke()
      }
    }

    const loop = (t: number) => {
      draw(t)
      raf = requestAnimationFrame(loop)
    }

    const onResize = () => {
      resize()
      draw(performance.now())
    }

    resize()
    draw(0)
    window.addEventListener('resize', onResize)
    if (!reduce) raf = requestAnimationFrame(loop)

    return () => {
      window.removeEventListener('resize', onResize)
      if (raf) cancelAnimationFrame(raf)
    }
  }, [])

  return <canvas ref={ref} className={className} aria-hidden="true" />
}
