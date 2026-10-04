import { useEffect, useState } from 'react'
import { X } from 'lucide-react'
import api from '../services/api'

const SEV_COLOR = {
  SAFE: '#22c55e', WARNING: '#f59e0b', HIGH: '#f97316', CRITICAL: '#ef4444',
}

// Incident detail modal — explainable breakdown + timeline + recommendation
export default function IncidentModal({ incidentId, onClose }) {
  const [inc, setInc] = useState(null)
  useEffect(() => {
    if (incidentId) api.incidentDetail(incidentId).then(setInc).catch(() => setInc(null))
  }, [incidentId])

  if (!incidentId) return null
  const color = SEV_COLOR[inc?.severity] || '#38bdf8'
  const ppe = inc?.ppe_status || {}
  const breakdown = inc?.breakdown || []

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-6">
      <div className="absolute inset-0 bg-black/70" onClick={onClose} />
      <div className="card relative w-full max-w-2xl max-h-[88vh] overflow-y-auto animate-fade-in">
        <div className="card-header sticky top-0 bg-navy-850 z-10">
          <span className="card-title">INCIDENT #{incidentId} — DETAILS</span>
          <button onClick={onClose} className="text-slate-500 hover:text-white"><X className="w-4 h-4" /></button>
        </div>
        {!inc ? (
          <div className="p-8 text-center text-slate-500 text-xs">Loading incident…</div>
        ) : (
          <div className="p-4 space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-navy-900 border border-navy-700 rounded-md p-3 space-y-1.5 text-[11px]">
                <div className="flex justify-between"><span className="text-slate-500">Time</span><span className="font-mono text-slate-200">{(inc.timestamp || '').replace('T', ' ')}</span></div>
                <div className="flex justify-between"><span className="text-slate-500">Worker</span><span className="font-mono text-slate-200">{inc.worker_id}</span></div>
                <div className="flex justify-between"><span className="text-slate-500">Camera</span><span className="font-mono text-slate-200">{inc.camera_id || 'CAM-01'}</span></div>
                <div className="flex justify-between"><span className="text-slate-500">Zone</span><span className="text-slate-200">{inc.zone_name || '—'}</span></div>
                <div className="flex justify-between"><span className="text-slate-500">Event Type</span><span className="text-slate-200">{inc.event_type}</span></div>
                <div className="flex justify-between"><span className="text-slate-500">Status</span><span className="font-mono text-slate-200">{inc.status}</span></div>
              </div>
              <div className="bg-navy-900 border rounded-md p-3 space-y-1.5 text-[11px]" style={{ borderColor: color + '55' }}>
                <div className="flex justify-between items-center">
                  <span className="text-slate-500">RISK SCORE</span>
                  <span className="font-mono font-bold text-lg" style={{ color: color }}>
                    {Math.round(inc.risk_score)} — {inc.severity}
                  </span>
                </div>
                <div className="flex justify-between"><span className="text-slate-500">PPE</span>
                  <span className="font-mono">
                    <span style={{ color: ppe.helmet ? '#22c55e' : '#ef4444' }}>Helmet {ppe.helmet ? '✓' : '✕'}</span>{' '}
                    <span style={{ color: ppe.vest ? '#22c55e' : '#ef4444' }}>Vest {ppe.vest ? '✓' : '✕'}</span>{' '}
                    <span style={{ color: ppe.gloves ? '#22c55e' : '#ef4444' }}>Gloves {ppe.gloves ? '✓' : '✕'}</span>
                  </span>
                </div>
                <div className="flex justify-between"><span className="text-slate-500">Distance</span><span className="font-mono text-slate-200">{inc.distance != null ? inc.distance + ' m' : '—'}</span></div>
                <div className="flex justify-between"><span className="text-slate-500">Facing Angle</span><span className="font-mono text-slate-200">{inc.facing_angle != null ? inc.facing_angle + '°' : '—'}</span></div>
                <div className="flex justify-between"><span className="text-slate-500">Closing Speed</span><span className="font-mono text-slate-200">{inc.closing_speed != null ? inc.closing_speed + ' m/s' : '—'}</span></div>
                <div className="flex justify-between"><span className="text-slate-500">Posture</span><span className="text-slate-200">{inc.posture_status || '—'}</span></div>
              </div>
            </div>

            <div className="bg-navy-900 border border-navy-700 rounded-md p-3">
              <div className="card-title mb-2">WHY? — EXPLAINABLE RISK BREAKDOWN</div>
              {breakdown.length === 0 ? (
                <div className="text-[11px] text-slate-500">No contributing risk factors recorded.</div>
              ) : (
                <div className="space-y-1.5">
                  {breakdown.map((f, i) => (
                    <div key={i} className="flex items-center gap-2">
                      <span className="text-[11px] text-slate-300 flex-1">{f.factor}</span>
                      <div className="w-40 h-1.5 bg-navy-800 rounded overflow-hidden">
                        <div className="h-full bg-blue-500" style={{ width: `${Math.min(100, (f.points || 0) * 2.5)}%` }} />
                      </div>
                      <span className="text-[11px] font-mono font-bold text-blue-400 w-9 text-right">+{f.points}</span>
                    </div>
                  ))}
                  <div className="flex items-center gap-2 pt-1.5 border-t border-navy-700">
                    <span className="text-[11px] font-bold text-white flex-1">TOTAL (clamped 0–100)</span>
                    <span className="text-[11px] font-mono font-bold" style={{ color: color }}>{Math.round(inc.risk_score)}</span>
                  </div>
                </div>
              )}
            </div>

            <div className="bg-critical-dim border border-critical-b rounded-md p-3">
              <div className="card-title mb-1 text-critical">ROOT CAUSE</div>
              <div className="text-xs font-bold text-white">{inc.root_cause}</div>
              <div className="text-[11px] text-slate-300 mt-1">{inc.description}</div>
            </div>

            <div className="bg-blue-600/10 border border-blue-500/40 rounded-md p-3">
              <div className="card-title mb-1 text-blue-300">SYSTEM RECOMMENDATION</div>
              <div className="text-[11px] text-slate-200">{inc.recommendation}</div>
            </div>

            <div className="bg-navy-900 border border-navy-700 rounded-md p-3">
              <div className="card-title mb-2">EVENT TIMELINE</div>
              <div className="space-y-1">
                {(inc.timeline || []).map((t, i) => (
                  <div key={i} className="flex gap-2 text-[11px]">
                    <span className="font-mono text-slate-500 w-20">{t.time}</span>
                    <span className="text-slate-300">{t.event}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
