import { useEffect, useRef } from 'react'

import styles from './AuthLayout.module.scss'

/**
 * 소개 패널 우하단의 데이터 네트워크. 곡선으로 이어진 노드 사이를 작은 빛이
 * 오가며 기록이 흘러 들어오는 모습을 배경 수준으로만 보여 줍니다.
 *
 * 글자를 방해하면 안 되므로 우하단에서 중앙 쪽으로 갈수록 옅어지고,
 * 마우스에는 가까운 선·노드만 은은하게 반응합니다.
 *
 * 그림일 뿐이라 읽어 줄 것이 없고(aria-hidden) 클릭도 받지 않습니다.
 */

/** 노드 자리. (1,1) 이 우하단 모서리. 우하단에 모여 중앙으로 퍼집니다. */
const NODES: [number, number][] = [
  [1.02, 1.04],
  [0.9, 0.96],
  [0.97, 0.82],
  [0.82, 0.86],
  [0.72, 0.98],
  [0.86, 0.72],
  [0.71, 0.78],
  [0.6, 0.88],
  [0.95, 0.64],
  [0.78, 0.6],
  [0.64, 0.68],
  [0.52, 0.76],
  [0.88, 0.5],
  [0.7, 0.48],
  [0.55, 0.58],
  [0.44, 0.66],
  [0.8, 0.36],
  [0.62, 0.38],
  [0.47, 0.47],
  [0.36, 0.56],
  [0.72, 0.25],
  [0.54, 0.29],
  [0.4, 0.36],
]

/** 이어진 노드 쌍. 가까운 것끼리만 이어 격자가 아니라 흐름으로 보이게 합니다. */
const EDGES: [number, number][] = [
  [0, 1],
  [0, 2],
  [1, 3],
  [1, 4],
  [2, 5],
  [3, 5],
  [3, 6],
  [4, 7],
  [6, 7],
  [5, 8],
  [5, 9],
  [6, 10],
  [7, 11],
  [9, 10],
  [10, 11],
  [8, 12],
  [9, 12],
  [9, 13],
  [10, 14],
  [11, 15],
  [13, 14],
  [14, 15],
  [12, 16],
  [13, 16],
  [13, 17],
  [14, 18],
  [15, 19],
  [17, 18],
  [18, 19],
  [16, 20],
  [17, 20],
  [17, 21],
  [18, 22],
  [21, 22],
]

/** 빛이 오가는 선. 전부 흐르면 산만해서 일부만 씁니다. */
const FLOWS = [1, 4, 8, 11, 15, 19, 23, 27, 31]

/** 네트워크가 차지하는 영역. 소개 패널 우하단 기준입니다. */
const AREA = { w: 0.55, h: 0.58 }

/** 곡선의 휨 정도. 선마다 조금씩 달라야 손으로 그은 듯 보입니다. */
function bend(i: number) {
  return ((i % 5) - 2) * 0.055
}

interface Point {
  x: number
  y: number
}

/** 두 점을 잇는 2차 베지에의 제어점. */
function control(a: Point, b: Point, k: number): Point {
  const mx = (a.x + b.x) / 2
  const my = (a.y + b.y) / 2
  return { x: mx - (b.y - a.y) * k, y: my + (b.x - a.x) * k }
}

function at(a: Point, c: Point, b: Point, t: number): Point {
  const s = 1 - t
  return {
    x: s * s * a.x + 2 * s * t * c.x + t * t * b.x,
    y: s * s * a.y + 2 * s * t * c.y + t * t * b.y,
  }
}

export default function AuthNetwork() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const still = window.matchMedia('(prefers-reduced-motion: reduce)').matches

    let width = 0
    let height = 0
    let points: Point[] = []
    // 마우스는 실제 위치(target)를 향해 조금씩 따라갑니다. 그래야 반응이 덜컹거리지 않습니다.
    const pointer = { x: -9999, y: -9999, tx: -9999, ty: -9999 }

    function layout() {
      const canvasEl = canvas as HTMLCanvasElement
      const context = ctx as CanvasRenderingContext2D
      const rect = canvasEl.getBoundingClientRect()
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      width = rect.width
      height = rect.height
      canvasEl.width = Math.round(width * dpr)
      canvasEl.height = Math.round(height * dpr)
      context.setTransform(dpr, 0, 0, dpr, 0, 0)

      const areaW = width * AREA.w
      const areaH = height * AREA.h
      points = NODES.map(([nx, ny]) => ({
        x: width - areaW + nx * areaW,
        y: height - areaH + ny * areaH,
      }))
    }

    /** 우하단에서 멀어질수록 옅어지는 값. 글자 쪽에서 그림이 사라지게 합니다. */
    function fade(p: Point) {
      const dx = (width - p.x) / (width * AREA.w)
      const dy = (height - p.y) / (height * AREA.h)
      return Math.max(0, 1 - Math.hypot(dx, dy) * 0.95)
    }

    /** 마우스가 가까울수록 커지는 값(0~1). */
    function near(p: Point) {
      const d = Math.hypot(p.x - pointer.x, p.y - pointer.y)
      return Math.max(0, 1 - d / 180)
    }

    function draw(time: number) {
      // 좁은 화면에서는 소개가 통째로 감춰집니다. 그릴 것이 없으면 바로 돌아갑니다.
      if (width === 0 || height === 0) return

      const context = ctx as CanvasRenderingContext2D
      context.clearRect(0, 0, width, height)
      context.globalCompositeOperation = 'lighter'

      pointer.x += (pointer.tx - pointer.x) * 0.12
      pointer.y += (pointer.ty - pointer.y) * 0.12

      EDGES.forEach(([ai, bi], i) => {
        const a = points[ai]
        const b = points[bi]
        const c = control(a, b, bend(i))
        const mid = at(a, c, b, 0.5)
        // 아주 느린 숨쉬기. 선마다 위상을 달리해 한꺼번에 밝아지지 않게 합니다.
        const breath = 0.72 + 0.28 * Math.sin(time / 2600 + i)
        const alpha = fade(mid) * (0.16 + 0.34 * near(mid)) * breath

        if (alpha <= 0.004) return

        context.strokeStyle = `rgba(90, 178, 255, ${alpha})`
        context.lineWidth = 1
        context.beginPath()
        context.moveTo(a.x, a.y)
        context.quadraticCurveTo(c.x, c.y, b.x, b.y)
        context.stroke()
      })

      points.forEach((p) => {
        const glow = near(p)
        const alpha = fade(p) * (0.4 + 0.6 * glow)
        if (alpha <= 0.01) return

        const r = 1.6 + glow * 1.4
        const halo = context.createRadialGradient(p.x, p.y, 0, p.x, p.y, r * 6)
        halo.addColorStop(0, `rgba(120, 200, 255, ${alpha * 0.55})`)
        halo.addColorStop(1, 'rgba(120, 200, 255, 0)')
        context.fillStyle = halo
        context.beginPath()
        context.arc(p.x, p.y, r * 6, 0, Math.PI * 2)
        context.fill()

        context.fillStyle = `rgba(190, 232, 255, ${alpha})`
        context.beginPath()
        context.arc(p.x, p.y, r, 0, Math.PI * 2)
        context.fill()
      })

      if (!still) {
        FLOWS.forEach((edgeIndex, i) => {
          const [ai, bi] = EDGES[edgeIndex]
          const a = points[ai]
          const b = points[bi]
          const c = control(a, b, bend(edgeIndex))
          // 선마다 길이가 달라도 대략 같은 속도로 보이도록 주기만 조금씩 어긋냅니다.
          const t = (((time / (3200 + i * 260) + i * 0.37) % 1) + 1) % 1
          const p = at(a, c, b, t)
          const alpha = fade(p) * (0.5 + 0.5 * Math.sin(Math.PI * t))
          if (alpha <= 0.01) return

          const halo = context.createRadialGradient(p.x, p.y, 0, p.x, p.y, 9)
          halo.addColorStop(0, `rgba(160, 226, 255, ${alpha * 0.8})`)
          halo.addColorStop(1, 'rgba(160, 226, 255, 0)')
          context.fillStyle = halo
          context.beginPath()
          context.arc(p.x, p.y, 9, 0, Math.PI * 2)
          context.fill()

          context.fillStyle = `rgba(225, 245, 255, ${alpha})`
          context.beginPath()
          context.arc(p.x, p.y, 1.6, 0, Math.PI * 2)
          context.fill()
        })
      }

      context.globalCompositeOperation = 'source-over'
    }

    let frame = 0
    function loop(time: number) {
      draw(time)
      frame = requestAnimationFrame(loop)
    }

    function onResize() {
      layout()
      if (still) draw(0)
    }

    function onPointerMove(e: PointerEvent) {
      const rect = (canvas as HTMLCanvasElement).getBoundingClientRect()
      pointer.tx = e.clientX - rect.left
      pointer.ty = e.clientY - rect.top
    }

    function onPointerLeave() {
      pointer.tx = -9999
      pointer.ty = -9999
    }

    layout()
    window.addEventListener('resize', onResize)
    window.addEventListener('pointermove', onPointerMove)
    window.addEventListener('pointerleave', onPointerLeave)

    // 동작 줄이기를 켠 사람에게는 한 장만 그리고 멈춥니다.
    if (still) draw(0)
    else frame = requestAnimationFrame(loop)

    return () => {
      cancelAnimationFrame(frame)
      window.removeEventListener('resize', onResize)
      window.removeEventListener('pointermove', onPointerMove)
      window.removeEventListener('pointerleave', onPointerLeave)
    }
  }, [])

  return <canvas ref={canvasRef} className={styles.network} aria-hidden="true" />
}
