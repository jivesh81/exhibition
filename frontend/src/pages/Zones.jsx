import { useCallback, useEffect, useState } from 'react'
import { Plus, Save, Trash2 } from 'lucide-react'
import api from '../services/api'

const SEVERITIES = ['safe', 'warning', 'danger', 'critical']

const EMPTY_FORM = { name: '', label: 'ZONE', severity: 'danger', x: 0.05, y: 0.1, w: 0.3, h: 0.3, active: true }

export default function Zones({ snapshot, refreshKey }) {
  const [data, setData] = useState({ cameras: [], zones: [] })
  const [form, setForm] = useState(EMPTY_FORM)
  const [editingId, setEditingId] = useState(null)
  const [msg, setMsg] = useState(null)

  const load = useCallback(() => {
    api.zones().then(setData).catch(() => setData({ cameras: [], zones: [] }))
  }, [])

  useEffect(() => { load() }, [load, refreshKey])

  function setField(key, val) { setForm((f) => ({ ...f, [key]: val })) }

  async function save() {
    if (!form.name.trim()) { setMsg('Zone name is required.'); return }
    const polygon = [[form.x, form.y], [form.x + form.w, form.y], [form.x + form.w, form.y + form.h], [form.x, form.y + form.h]]
    const payload = { name: form.name, label: form.label, severity: form.severity, polygon, active: form.active }
    try {
      if (editingId) await api.updateZone(editingId, payload)
      else await api.createZone(payload)
      setMsg(editingId ? 'Zone updated.' : 'Zone created.')
      setEditingId(null)
      setForm(EMPTY_FORM)
      load()
    } catch (e) {
      setMsg(`Failed: ${e.message}`)
    }
  }

  async function remove(id) {
    try { await api.deleteZone(id) } catch { /* noop */ }
    if (editingId === id) { setEditingId(null); setForm(EMPTY_FORM) }
    load()
  }

  function editZone(z) {
    const poly = z.polygon && z.polygon[0] ? z.polygon : [[0.05, 0.1], [0.35, 0.1], [0.35, 0.4], [0.05, 0.4]]
    setEditingId(z.id)
    setForm({
      name: z.name, label: z.label, severity: z.severity,
      x: poly[0][0], y: poly[0][1], w: +(poly[1][0] - poly[0][0]).toFixed(3), h: +(poly[2][1] - poly[1][1]).toFixed(3),
      active: z.active,
    })
  }

  return (
    <div className="p-4 space-y-3.5">
      <div>
        <h1 className="text-lg font-bold text-white tracking-wide">ZONES & CAMERAS</h1>
        <p className="text-[11px] text-slate-500">Hazard zones are stored in SQLite — workers entering them influence the risk score.</p>
      </div>

      {/* cameras */}
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-2.5">
        {(data.cameras || []).map((c) => (
          <div key={c.id} className="card p-3">
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-xs font-bold text-white font-mono">{c.id}</span>
              <span className="badge bg-safe-dim text-safe border border-safe-b">● {c.status}</span>
            </div>
            <div className="text-[10px] text-slate-400">{c.name}</div>
            <div className="text-[9px] text-slate-600 mt-1 font-mono">
              {c.location} | {c.resolution} | {c.fps} FPS | Input: {c.input_mode}
            </div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-3.5">
        {/* zone editor */}
        <div className="card p-3">
          <div className="card-title mb-2">{editingId ? `EDIT ZONE #${editingId}` : 'ADD ZONE'}</div>
          <div className="space-y-2">
            <div>
              <label className="text-[9px] tracking-widest text-slate-500 uppercase">Zone Name</label>
              <input className="input mt-1" placeholder="e.g. Crane Swing Area" value={form.name} onChange={(e) => setField('name', e.target.value)} />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-[9px] tracking-widest text-slate-500 uppercase">Label</label>
                <input className="input mt-1" value={form.label} onChange={(e) => setField('label', e.target.value)} />
              </div>
              <div>
                <label className="text-[9px] tracking-widest text-slate-500 uppercase">Severity</label>
                <select className="input mt-1" value={form.severity} onChange={(e) => setField('severity', e.target.value)}>
                  {SEVERITIES.map((s) => <option key={s} value={s}>{s.toUpperCase()}</option>)}
                </select>
              </div>
            </div>
            <div className="grid grid-cols-4 gap-1.5">
              {['x', 'y', 'w', 'h'].map((k) => (
                <div key={k}>
                  <label className="text-[9px] tracking-widest text-slate-500 uppercase">{k}</label>
                  <input type="number" step="0.01" min="0" max="1" className="input mt-1"
                         value={form[k]} onChange={(e) => setField(k, +e.target.value)} />
                </div>
              ))}
            </div>
            <p className="text-[9px] text-slate-600">Rectangle in normalized camera coordinates (0–1).</p>
            <div className="flex gap-2 pt-1">
              <button onClick={save} className="btn-primary flex-1 justify-center"><Save className="w-3 h-3" /> {editingId ? 'UPDATE' : 'ADD ZONE'}</button>
              {editingId && <button onClick={() => { setEditingId(null); setForm(EMPTY_FORM) }} className="btn-ghost">CANCEL</button>}
            </div>
            {msg && <div className="text-[10px] text-blue-400">{msg}</div>}
          </div>
        </div>

        {/* zones table */}
        <div className="card overflow-hidden xl:col-span-2">
          <div className="card-header">
            <span className="card-title">{(data.zones || []).length} HAZARD ZONES</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr>
                  <th className="table-th">Label</th>
                  <th className="table-th">Zone Name</th>
                  <th className="table-th">Severity</th>
                  <th className="table-th">Polygon (normalized)</th>
                  <th className="table-th">Active</th>
                  <th className="table-th">Actions</th>
                </tr>
              </thead>
              <tbody>
                {(data.zones || []).length === 0 && (
                  <tr><td colSpan="6" className="table-td text-center py-8 text-slate-600">No zones configured.</td></tr>
                )}
                {(data.zones || []).map((z) => (
                  <tr key={z.id} className="hover:bg-navy-800/50">
                    <td className="table-td font-mono font-semibold text-white">{z.label}</td>
                    <td className="table-td">{z.name}</td>
                    <td className="table-td">
                      <span className={`badge ${z.severity === 'critical' ? 'bg-critical-dim text-critical' : z.severity === 'danger' ? 'bg-danger-dim text-danger' : z.severity === 'warning' ? 'bg-warn-dim text-warn' : 'bg-safe-dim text-safe'}`}>
                        {String(z.severity).toUpperCase()}
                      </span>
                    </td>
                    <td className="table-td font-mono text-[9px] text-slate-500">
                      [{(z.polygon || []).map((p) => `(${p[0]},${p[1]})`).join(' ')}]
                    </td>
                    <td className="table-td">{z.active ? <span className="text-safe">●</span> : <span className="text-slate-600">○</span>}</td>
                    <td className="table-td">
                      <div className="flex gap-1">
                        <button onClick={() => editZone(z)} className="btn-ghost px-1.5 py-0.5 text-[9px]">EDIT</button>
                        <button onClick={() => remove(z.id)} className="btn-ghost px-1.5 py-0.5 text-[9px] hover:!text-red-400" title="Delete">
                          <Trash2 className="w-3 h-3" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* live zone preview from the current camera view */}
      {snapshot && (snapshot.zones || []).length > 0 && (
        <div className="card p-3">
          <div className="card-title mb-2">CAMERA VIEW — ZONE OVERLAYS (LIVE)</div>
          <div className="relative bg-black rounded" style={{ aspectRatio: '16/9' }}>
            {snapshot.zones.map((z) => {
              const poly = z.polygon || []
              if (poly.length < 3) return null
              const xs = poly.map((p) => p[0] * 100), ys = poly.map((p) => p[1] * 100)
              const color = z.severity === 'critical' ? '#ef4444' : z.severity === 'danger' ? '#f97316' : z.severity === 'warning' ? '#f59e0b' : '#22c55e'
              return (
                <div key={z.id} className="absolute border-2 rounded-sm flex items-start justify-center"
                     style={{
                       left: `${Math.min(...xs)}%`, top: `${Math.min(...ys)}%`,
                       width: `${Math.max(...xs) - Math.min(...xs)}%`, height: `${Math.max(...ys) - Math.min(...ys)}%`,
                       borderColor: color, background: color + '22',
                     }}>
                  <span className="text-[9px] font-mono font-bold mt-1" style={{ color }}>{z.label}</span>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
