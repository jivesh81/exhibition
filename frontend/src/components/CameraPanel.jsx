import { useEffect, useRef, useState } from 'react'
import { Camera, MonitorPlay, Play, RotateCcw, Square, Upload, Video } from 'lucide-react'
import api from '../services/api'

const SEV_COLOR = {
  SAFE: '#22c55e', WARNING: '#f59e0b', HIGH: '#f97316', CRITICAL: '#ef4444',
}
const ZONE_FILL = {
  safe: 'rgba(34,197,94,0.10)', warning: 'rgba(245,158,11,0.14)',
  danger: 'rgba(249,115,22,0.16)', critical: 'rgba(239,68,68,0.18)',
}
const ZONE_STROKE = {
  safe: 'rgba(34,197,94,0.55)', warning: 'rgba(245,158,11,0.7)',
  danger: 'rgba(249,115,22,0.75)', critical: 'rgba(239,68,68,0.8)',
}

const W = 960
const H = 540

// interpolate positions between previous and current snapshot for smooth motion
function lerp(a, b, t) { return a + (b - a) * t }

export default function CameraPanel({ snapshot, demoStart, demoReset, alerts }) {
  const canvasRef = useRef(null)
  const videoRef = useRef(null)
  const fileRef = useRef(null)
  const [mode, setMode] = useState('demo') // demo | webcam | video
  const [camError, setCamError] = useState(null)
  const [aiDetections, setAiDetections] = useState(null)
  const [clock, setClock] = useState('')
  const prevSnapRef = useRef(null)
  const curSnapRef = useRef(null)
  const snapTimeRef = useRef(0)

  // track snapshots for interpolation
  useEffect(() => {
    if (!snapshot) return
    prevSnapRef.current = curSnapRef.current
    curSnapRef.current = snapshot
    snapTimeRef.current = performance.now()
  }, [snapshot])

  // clock display
  useEffect(() => {
    const t = setInterval(() => setClock(new Date().toLocaleTimeString('en-GB')), 1000)
    setClock(new Date().toLocaleTimeString('en-GB'))
    return () => clearInterval(t)
  }, [])

  // ---------------- webcam / video handling ----------------
  async function startWebcam() {
    setCamError(null)
    setAiDetections(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 1280, height: 720 } })
      if (videoRef.current) {
        videoRef.current.srcObject = stream
        await videoRef.current.play()
      }
      setMode('webcam')
    } catch (err) {
      setCamError('Webcam unavailable — using Demo Mode instead.')
      setMode('demo')
    }
  }

  function startVideoFile(ev) {
    const file = ev.target.files && ev.target.files[0]
    if (!file) return
    setCamError(null)
    setAiDetections(null)
    if (videoRef.current) {
      videoRef.current.srcObject = null
      videoRef.current.src = URL.createObjectURL(file)
      videoRef.current.loop = true
      videoRef.current.play().catch(() => {})
    }
    setMode('video')
  }

  function stopFeed() {
    if (videoRef.current && videoRef.current.srcObject) {
      videoRef.current.srcObject.getTracks().forEach((t) => t.stop())
      videoRef.current.srcObject = null
    }
    if (videoRef.current) videoRef.current.src = null
    setAiDetections(null)
    setMode('demo')
  }

  // optional real-AI inference on the active feed (throttled)
  useEffect(() => {
    if (mode === 'demo') return
    let stop = false
    async function loop() {
      const v = videoRef.current
      if (!v || stop || v.readyState < 2) return
      try {
        const c = document.createElement('canvas')
        c.width = 640
        c.height = Math.round((640 * v.videoHeight) / Math.max(1, v.videoWidth)) || 360
        c.getContext('2d').drawImage(v, 0, 0, c.width, c.height)
        const blob = await new Promise((r) => c.toBlob(r, 'image/jpeg', 0.7))
        if (blob && !stop) {
          const res = await api.detectFrame(blob)
          if (!stop && res) setAiDetections(res)
        }
      } catch { /* inference failure — overlay simply not shown */ }
    }
    const t = setInterval(loop, 1500)
    return () => { stop = true; clearInterval(t) }
  }, [mode])

  // ---------------- canvas scene rendering ----------------
  function drawScene(ctx, snap, t01) {
    // sky + ground
    const sky = ctx.createLinearGradient(0, 0, 0, H * 0.45)
    sky.addColorStop(0, '#0c1626')
    sky.addColorStop(1, '#14243c')
    ctx.fillStyle = sky
    ctx.fillRect(0, 0, W, H * 0.45)
    const ground = ctx.createLinearGradient(0, H * 0.45, 0, H)
    ground.addColorStop(0, '#1d2a17')
    ground.addColorStop(1, '#141c11')
    ctx.fillStyle = ground
    ctx.fillRect(0, H * 0.45, W, H * 0.55)

    // horizon glow
    ctx.fillStyle = 'rgba(90,140,190,0.08)'
    ctx.fillRect(0, H * 0.44, W, 2)

    // perspective grid
    ctx.strokeStyle = 'rgba(120,160,210,0.07)'
    ctx.lineWidth = 1
    for (let i = 0; i <= 10; i++) {
      const x = (W * i) / 10
      ctx.beginPath()
      ctx.moveTo(W / 2 + (x - W / 2) * 0.25, H * 0.45)
      ctx.lineTo(x, H)
      ctx.stroke()
    }
    for (let i = 1; i <= 4; i++) {
      const y = H * 0.45 + (H * 0.55 * i * i) / 16
      ctx.beginPath()
      ctx.moveTo(0, y)
      ctx.lineTo(W, y)
      ctx.stroke()
    }

    // background silhouettes
    ctx.fillStyle = '#101a2a'
    ctx.fillRect(W * 0.02, H * 0.18, W * 0.16, H * 0.27) // building
    ctx.fillRect(W * 0.20, H * 0.26, W * 0.10, H * 0.19)
    ctx.fillStyle = '#0d1524'
    for (let i = 0; i < 5; i++) ctx.fillRect(W * (0.035 + i * 0.028), H * 0.2 + 10, 8, 6)
    ctx.fillRect(W * 0.215, H * 0.28, 6, 6)
    ctx.fillRect(W * 0.245, H * 0.30, 6, 6)

    // crane silhouette (mast + jib + cable + hook + counterweight)
    const craneX = W * 0.78
    ctx.strokeStyle = 'rgba(200,180,90,0.55)'
    ctx.fillStyle = 'rgba(200,180,90,0.5)'
    ctx.lineWidth = 3
    ctx.beginPath(); ctx.moveTo(craneX, H * 0.45); ctx.lineTo(craneX, H * 0.04); ctx.stroke()
    ctx.lineWidth = 2
    ctx.beginPath(); ctx.moveTo(craneX - W * 0.16, H * 0.07); ctx.lineTo(craneX + W * 0.14, H * 0.07); ctx.stroke()
    for (let i = 0; i <= 6; i++) {
      const xx = craneX - W * 0.16 + (W * 0.3 * i) / 6
      ctx.beginPath(); ctx.moveTo(xx, H * 0.07)
      ctx.lineTo(craneX - W * 0.16 + (W * 0.3 * (i + 0.5)) / 6, H * 0.04); ctx.stroke()
    }
    ctx.lineWidth = 1
    const hookX = craneX + W * 0.06
    ctx.beginPath(); ctx.moveTo(hookX, H * 0.07); ctx.lineTo(hookX, H * 0.3); ctx.stroke()
    ctx.fillRect(hookX - 4, H * 0.3, 8, 8)
    ctx.fillRect(craneX + W * 0.14, H * 0.07, 10, 12)

    // safety fence
    ctx.strokeStyle = 'rgba(200,210,220,0.15)'
    ctx.lineWidth = 1
    for (const [x1, y1] of [[W * 0.02, H * 0.9], [W * 0.42, H * 0.9]]) {
      ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x1, y1 - 26); ctx.stroke()
    }
    for (let i = 0; i < 6; i++) {
      ctx.beginPath(); ctx.moveTo(W * 0.02 + i * W * 0.08, H * 0.9 - 20); ctx.lineTo(W * 0.02 + (i + 1) * W * 0.08, H * 0.9 - 20); ctx.stroke()
      ctx.beginPath(); ctx.moveTo(W * 0.02 + i * W * 0.08, H * 0.9 - 10); ctx.lineTo(W * 0.02 + (i + 1) * W * 0.08, H * 0.9 - 10); ctx.stroke()
    }

    // hazard zone polygons
    for (const z of snap?.zones || []) {
      const poly = z.polygon || []
      if (poly.length < 3) continue
      ctx.beginPath()
      poly.forEach(([px, py], i) => (i ? ctx.lineTo(px * W, py * H) : ctx.moveTo(px * W, py * H)))
      ctx.closePath()
      ctx.fillStyle = ZONE_FILL[z.severity] || ZONE_FILL.danger
      ctx.fill()
      ctx.setLineDash([7, 5])
      ctx.strokeStyle = ZONE_STROKE[z.severity] || ZONE_STROKE.danger
      ctx.lineWidth = 1.5
      ctx.stroke()
      ctx.setLineDash([])
      // label plate
      const lx = poly[0][0] * W + 6
      const ly = poly[0][1] * H + 6
      ctx.fillStyle = ZONE_STROKE[z.severity] || ZONE_STROKE.danger
      ctx.fillRect(lx, ly, 130, 26)
      ctx.fillStyle = '#0a101d'
      ctx.font = 'bold 10px Consolas, monospace'
      ctx.fillText(`${z.label || 'ZONE'}`, lx + 6, ly + 11)
      ctx.font = '9px Consolas, monospace'
      ctx.fillText((z.name || '').toUpperCase().slice(0, 20), lx + 6, ly + 21)
    }

    // workers (interpolated positions)
    const prev = prevSnapRef.current
    const list = snap?.workers || []
    for (const wk of list) {
      let x = wk.x, y = wk.y
      if (prev) {
        const pw = (prev.workers || []).find((p) => p.id === wk.id)
        if (pw && typeof pw.x === 'number') { x = lerp(pw.x, wk.x, t01); y = lerp(pw.y, wk.y, t01) }
      }
      drawWorker(ctx, wk, x * W, y * H, snap)
    }

    // real-AI overlay boxes (webcam/video mode)
    if (aiDetections && aiDetections.persons && (mode === 'webcam' || mode === 'video')) {
      for (const p of aiDetections.persons) {
        const [x1, y1, x2, y2] = p.box
        const sx = W / aiDetections.frame_w, sy = H / aiDetections.frame_h
        ctx.strokeStyle = SEV_COLOR[p.risk?.severity] || '#38bdf8'
        ctx.lineWidth = 2
        ctx.strokeRect(x1 * sx, y1 * sy, (x2 - x1) * sx, (y2 - y1) * sy)
        ctx.fillStyle = SEV_COLOR[p.risk?.severity] || '#38bdf8'
        ctx.font = 'bold 10px Consolas, monospace'
        const lbl = `PERSON ${(p.risk?.risk_score ?? 0)} ${p.risk?.severity || ''} ${p.proximity?.distance != null ? p.proximity.distance + 'm' : ''}`
        ctx.fillText(lbl, x1 * sx, Math.max(10, y1 * sy - 4))
      }
    }
  }

  function drawWorker(ctx, wk, px, py, snap) {
    const sev = wk.severity || 'SAFE'
    const color = SEV_COLOR[sev]
    const isCrit = sev === 'CRITICAL'
    const s = 1 + Math.max(0, (0.9 - Math.min(0.9, py / H)) * 0.5) // perspective scale

    // shadow
    ctx.fillStyle = 'rgba(0,0,0,0.35)'
    ctx.beginPath()
    ctx.ellipse(px, py, 16 * s, 5 * s, 0, 0, Math.PI * 2)
    ctx.fill()

    // bounding box with corner brackets
    const bw = 46 * s, bh = 84 * s
    const bx = px - bw / 2, by = py - bh - 8 * s
    ctx.strokeStyle = color
    ctx.lineWidth = isCrit ? 2.5 : 1.5
    if (isCrit) {
      ctx.save()
      ctx.globalAlpha = 0.35 + 0.3 * Math.sin(performance.now() / 200)
      ctx.strokeRect(bx, by, bw, bh)
      ctx.restore()
    }
    const cl = 10
    ctx.beginPath()
    ctx.moveTo(bx, by + cl); ctx.lineTo(bx, by); ctx.lineTo(bx + cl, by)
    ctx.moveTo(bx + bw - cl, by); ctx.lineTo(bx + bw, by); ctx.lineTo(bx + bw, by + cl)
    ctx.moveTo(bx + bw, by + bh - cl); ctx.lineTo(bx + bw, by + bh); ctx.lineTo(bx + bw - cl, by + bh)
    ctx.moveTo(bx + cl, by + bh); ctx.lineTo(bx, by + bh); ctx.lineTo(bx, by + bh - cl)
    ctx.stroke()

    // human figure
    const headR = 6 * s
    const headY = by + 14 * s
    ctx.fillStyle = color
    ctx.beginPath(); ctx.arc(px, headY, headR, 0, Math.PI * 2); ctx.fill()
    // helmet arc
    if (wk.ppe?.helmet) {
      ctx.strokeStyle = '#fbbf24'
      ctx.lineWidth = 3 * s
      ctx.beginPath(); ctx.arc(px, headY, headR + 1.5, Math.PI, 0); ctx.stroke()
    }
    // vest stripe on torso
    ctx.strokeStyle = color
    ctx.lineWidth = 5 * s
    const lean = wk.posture === 'Unsafe' ? 4 * s : wk.posture === 'Severe' ? 14 * s : 0
    const torsoTop = headY + headR + 2
    const torsoBot = torsoTop + 26 * s
    ctx.beginPath(); ctx.moveTo(px, torsoTop); ctx.lineTo(px + lean, torsoBot); ctx.stroke()
    if (wk.ppe?.vest) {
      ctx.strokeStyle = 'rgba(250,250,250,0.9)'
      ctx.lineWidth = 1.6 * s
      ctx.beginPath(); ctx.moveTo(px - 4 * s, torsoTop + 5); ctx.lineTo(px + lean - 4 * s, torsoBot - 6); ctx.stroke()
      ctx.beginPath(); ctx.moveTo(px + 4 * s, torsoTop + 5); ctx.lineTo(px + lean + 4 * s, torsoBot - 6); ctx.stroke()
    }
    // legs
    ctx.lineWidth = 3.5 * s
    ctx.beginPath(); ctx.moveTo(px + lean, torsoBot); ctx.lineTo(px + lean - 5 * s, py); ctx.stroke()
    ctx.beginPath(); ctx.moveTo(px + lean, torsoBot); ctx.lineTo(px + lean + 5 * s, py); ctx.stroke()

    // facing arrow
    if (wk.facing_vector) {
      const [fx, fy] = wk.facing_vector
      const ax = px + fx * 22 * s, ay = torsoTop + 10 + fy * 18 * s
      ctx.strokeStyle = 'rgba(140,180,240,0.8)'
      ctx.lineWidth = 1.5
      ctx.beginPath(); ctx.moveTo(px + fx * 10 * s, torsoTop + 10); ctx.lineTo(ax, ay); ctx.stroke()
      ctx.fillStyle = 'rgba(140,180,240,0.9)'
      ctx.beginPath(); ctx.arc(ax, ay, 2.2, 0, Math.PI * 2); ctx.fill()
    }

    // label plate
    const lw = 168, lh = 54
    const lx = Math.min(W - lw - 4, Math.max(4, px - lw / 2))
    const ly = Math.max(4, by - lh - 6)
    ctx.fillStyle = 'rgba(7,11,20,0.88)'
    ctx.strokeStyle = color
    ctx.lineWidth = 1
    ctx.fillRect(lx, ly, lw, lh)
    ctx.strokeRect(lx, ly, lw, lh)
    ctx.font = 'bold 10px Consolas, monospace'
    ctx.fillStyle = '#ffffff'
    ctx.fillText(`WORKER #${wk.id}`, lx + 6, ly + 12)
    ctx.font = '9px Consolas, monospace'
    const ppe = wk.ppe || {}
    ctx.fillStyle = ppe.helmet ? '#22c55e' : '#ef4444'
    ctx.fillText(`Helmet ${ppe.helmet ? 'OK' : 'X MISSING'}`, lx + 6, ly + 24)
    ctx.fillStyle = ppe.vest ? '#22c55e' : '#ef4444'
    ctx.fillText(`Vest ${ppe.vest ? 'OK' : 'X MISSING'}   ${ppe.gloves ? 'Gloves OK' : 'Gloves X'}`, lx + 6, ly + 34)
    ctx.fillStyle = '#cbd5e1'
    ctx.fillText(`${wk.distance != null ? wk.distance.toFixed(1) + 'm' : '--'}  ${wk.closing_speed != null ? wk.closing_speed.toFixed(1) + 'm/s' : ''}  ${wk.posture || ''}`, lx + 6, ly + 45)
    // risk chip
    ctx.fillStyle = color
    ctx.fillRect(lx + lw - 58, ly + 4, 52, 12)
    ctx.fillStyle = '#0a101d'
    ctx.font = 'bold 9px Consolas, monospace'
    ctx.fillText(`${Math.round(wk.risk_score || 0)} ${sev}`, lx + lw - 55, ly + 13)
  }

  // render loop with smooth interpolation
  useEffect(() => {
    let raf
    const render = () => {
      const cv = canvasRef.current
      if (cv) {
        const ctx = cv.getContext('2d')
        const t01 = Math.min(1, (performance.now() - snapTimeRef.current) / 1200)
        if (mode === 'demo' && curSnapRef.current) {
          drawScene(ctx, curSnapRef.current, t01)
        } else if (mode !== 'demo' && videoRef.current && videoRef.current.readyState >= 2) {
          ctx.drawImage(videoRef.current, 0, 0, W, H)
          if (aiDetections && aiDetections.persons) {
            // reuse overlay drawing
            drawSceneOverlaysOnly(ctx)
          }
        } else if (mode === 'demo') {
          drawScene(ctx, { zones: [], workers: [] }, 1)
        }
      }
      raf = requestAnimationFrame(render)
    }
    raf = requestAnimationFrame(render)
    return () => cancelAnimationFrame(raf)
  }, [mode, aiDetections])

  function drawSceneOverlaysOnly(ctx) {
    if (aiDetections && aiDetections.persons) {
      for (const p of aiDetections.persons) {
        const [x1, y1, x2, y2] = p.box
        const fw = aiDetections.frame_w || 640, fh = aiDetections.frame_h || 360
        const sx = W / fw, sy = H / fh
        ctx.strokeStyle = SEV_COLOR[p.risk?.severity] || '#38bdf8'
        ctx.lineWidth = 2
        ctx.strokeRect(x1 * sx, y1 * sy, (x2 - x1) * sx, (y2 - y1) * sy)
        ctx.fillStyle = SEV_COLOR[p.risk?.severity] || '#38bdf8'
        ctx.font = 'bold 10px Consolas, monospace'
        const lbl = `PERSON ${p.risk?.risk_score ?? 0} ${p.risk?.severity || ''} ${p.proximity?.distance != null ? p.proximity.distance + 'm' : ''}`
        ctx.fillText(lbl, x1 * sx, Math.max(10, y1 * sy - 4))
      }
    }
  }

  const prov = snapshot?.providers || {}
  const aiLabel = (k) => {
    const p = prov[k]
    if (!p) return '…'
    return `${k.toUpperCase()} ${p.available ? '✓' : 'MOCK'}`
  }

  return (
    <div className="card overflow-hidden">
      {/* header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-navy-700 bg-navy-900/60">
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-2">
            <span className="status-dot bg-safe animate-blink" />
            <span className="text-xs font-bold tracking-[0.2em] text-white">LIVE SAFETY MONITOR</span>
          </span>
          <span className="badge bg-safe-dim text-safe border border-safe-b">● SYSTEM ACTIVE</span>
        </div>
        <div className="flex items-center gap-4 text-[10px] font-mono text-slate-400">
          <span>CAM-01 | Main Construction Zone</span>
          <span className="text-slate-500">|</span>
          <span>24 FPS</span>
          <span className="text-slate-500">|</span>
          <span className="text-safe">{aiLabel('ppe')}</span>
          <span className="text-safe">{aiLabel('pose')}</span>
          <span className="text-safe">{aiLabel('proximity')}</span>
        </div>
      </div>

      {/* canvas + side info */}
      <div className="flex">
        <div className="relative flex-1 bg-black">
          <canvas ref={canvasRef} width={W} height={H} className="w-full h-auto block" />
          <video ref={videoRef} className="hidden" playsInline muted />
          {/* HUD */}
          <div className="absolute top-2 left-2 flex items-center gap-2 text-[10px] font-mono">
            <span className="bg-red-600/90 text-white px-1.5 py-0.5 rounded font-bold">● REC</span>
            <span className="bg-navy-950/80 text-slate-300 px-1.5 py-0.5 rounded">{clock}</span>
            <span className="bg-navy-950/80 text-slate-300 px-1.5 py-0.5 rounded uppercase">
              {mode === 'demo' ? 'DEMO FEED' : mode === 'webcam' ? 'WEBCAM' : 'UPLOADED VIDEO'}
            </span>
            {snapshot?.scenario?.running && (
              <span className="bg-blue-600/80 text-white px-1.5 py-0.5 rounded">
                SCENARIO: {snapshot.scenario.stage} ({snapshot.scenario.stage_index}/{snapshot.scenario.total_stages})
              </span>
            )}
          </div>
          {mode !== 'demo' && aiDetections && (
            <div className="absolute top-2 right-2 text-[10px] font-mono bg-navy-950/80 text-slate-300 px-1.5 py-0.5 rounded">
              AI: {aiDetections.persons?.length || 0} persons | {aiDetections.mode || 'OPENCV'}
            </div>
          )}
          {camError && (
            <div className="absolute bottom-2 left-2 right-2 bg-warn-dim border border-warn-b text-warn text-[11px] px-3 py-2 rounded">
              {camError}
            </div>
          )}
        </div>

        {/* right side: demo controls + legend */}
        <div className="w-64 shrink-0 border-l border-navy-700 p-3 space-y-4 bg-navy-900/40">
          <div>
            <div className="card-title mb-2">DEMO CONTROL</div>
            <div className="space-y-2">
              <button onClick={() => demoStart('crane_approach')}
                      className="btn-primary w-full justify-center py-2">
                <Play className="w-3.5 h-3.5" /> START LIVE DEMO
              </button>
              <button onClick={demoReset} className="btn-ghost w-full justify-center py-2">
                <RotateCcw className="w-3.5 h-3.5" /> RESET DEMO
              </button>
              <div className="pt-1 border-t border-navy-800" />
              <button onClick={startWebcam} className="btn-ghost w-full justify-center py-2">
                <Camera className="w-3.5 h-3.5" /> START WEBCAM
              </button>
              <button onClick={() => fileRef.current && fileRef.current.click()}
                      className="btn-ghost w-full justify-center py-2">
                <Upload className="w-3.5 h-3.5" /> UPLOAD VIDEO
              </button>
              <input ref={fileRef} type="file" accept="video/*" className="hidden" onChange={startVideoFile} />
              {mode !== 'demo' && (
                <button onClick={stopFeed} className="btn-danger w-full justify-center py-2">
                  <Square className="w-3.5 h-3.5" /> STOP FEED
                </button>
              )}
            </div>
            <p className="mt-2 text-[10px] text-slate-500 leading-relaxed">
              Scenario: worker approaches crane hazard without helmet. Risk escalates → alert → incident logged.
            </p>
          </div>
          <div>
            <div className="card-title mb-2">RISK LEGEND</div>
            <div className="grid grid-cols-2 gap-1.5 text-[10px] font-mono">
              <span className="bg-safe-dim text-safe border border-safe-b rounded px-2 py-1">SAFE 0-24</span>
              <span className="bg-warn-dim text-warn border border-warn-b rounded px-2 py-1">WARNING 25-49</span>
              <span className="bg-danger-dim text-danger border border-danger-b rounded px-2 py-1">HIGH 50-74</span>
              <span className="bg-critical-dim text-critical border border-critical-b rounded px-2 py-1">CRITICAL 75+</span>
            </div>
          </div>
          <div className="text-[10px] text-slate-500 leading-relaxed">
            <MonitorPlay className="w-3 h-3 inline mr-1" />
            Video stays on-device — edge inference only, no cloud upload.
          </div>
        </div>
      </div>
    </div>
  )
}
