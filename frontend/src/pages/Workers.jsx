import { useEffect, useState } from 'react'
import { X, Mic, VolumeX } from 'lucide-react'
import api from '../services/api'
import { SevBadge } from '../components/StatusBadge'

export default function Workers({ workers, refreshKey }) {
  const [selected, setSelected] = useState(null)
  const [detail, setDetail] = useState(null)

  useEffect(() => {
    if (selected) api.workerDetail(selected).then(setDetail).catch(() => setDetail(null))
    else setDetail(null)
  }, [selected, refreshKey])

  return (
    <div className="p-4 space-y-3.5">
      <div>
        <h1 className="text-lg font-bold text-white tracking-wide">WORKER MONITORING</h1>
        <p className="text-[11px] text-slate-500">Live personnel safety status — click a worker for full history.</p>
      </div>

      <div className="card overflow-hidden">
        <div className="card-header">
          <span className="card-title">{(workers || []).length} WORKERS</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr>
                <th className="table-th">Worker ID</th>
                <th className="table-th">Name</th>
                <th className="table-th">Status</th>
                <th className="table-th">Track ID</th>
                <th className="table-th">Current Zone</th>
                <th className="table-th">PPE</th>
                <th className="table-th">Distance</th>
                <th className="table-th">Risk</th>
                <th className="table-th">ML Prob</th>
                <th className="table-th">Voice</th>
              </tr>
            </thead>
            <tbody>
              {(workers || []).length === 0 && (
                <tr><td colSpan="10" className="table-td text-center py-8 text-slate-600">No worker data — start the demo or check the backend.</td></tr>
              )}
              {(workers || []).map((w) => {
                const ppe = w.ppe || {}
                const trackingId = w.tracking_id != null ? `#${w.tracking_id}` : '—'
                const trackState = w.track_state || '—'
                const mlProb = w.ml_probability != null ? `${Math.round(w.ml_probability * 100)}%` : '—'
                const voiceAlert = w.voice_alert ? '🔊' : '—'
                return (
                  <tr key={w.id} className="hover:bg-navy-800/50 cursor-pointer" onClick={() => setSelected(w.id)}>
                    <td className="table-td font-mono font-semibold text-white">{w.id}</td>
                    <td className="table-td">{w.name}</td>
                    <td className="table-td"><SevBadge severity={w.status || w.severity} /></td>
                    <td className="table-td font-mono text-[10px]">{trackingId} <span className="text-[9px] text-slate-500 ml-1">({trackState})</span></td>
                    <td className="table-td text-[10px]">{w.current_zone || '—'}</td>
                    <td className="table-td">
                      {ppe.helmet && ppe.vest && ppe.gloves
                        ? <span className="text-safe">✓ PPE</span>
                        : <span className="flex gap-1.5 font-mono text-[10px]">
                            <span style={{ color: ppe.helmet ? '#22c55e' : '#ef4444' }}>H{ppe.helmet ? '✓' : '✕'}</span>
                            <span style={{ color: ppe.vest ? '#22c55e' : '#ef4444' }}>V{ppe.vest ? '✓' : '✕'}</span>
                            <span style={{ color: ppe.gloves ? '#22c55e' : '#ef4444' }}>G{ppe.gloves ? '✓' : '✕'}</span>
                          </span>}
                    </td>
                    <td className="table-td font-mono">{w.distance != null ? `${w.distance}m` : '—'}</td>
                    <td className="table-td">
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-bold">{Math.round(w.risk_score || 0)}</span>
                        <SevBadge severity={w.severity || 'SAFE'} />
                      </div>
                    </td>
                    <td className="table-td font-mono text-[10px]">{mlProb}</td>
                    <td className="table-td text-center">{voiceAlert}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* worker detail drawer */}
      {detail && (
        <div className="fixed inset-0 z-50 flex justify-end">
          <div className="absolute inset-0 bg-black/70" onClick={() => setSelected(null)} />
          <div className="relative w-full max-w-md bg-navy-850 border-l border-navy-700 h-full overflow-y-auto animate-fade-in">
            <div className="card-header sticky top-0 bg-navy-850 z-10">
              <span className="card-title">WORKER {detail.id} — {detail.name}</span>
              <button onClick={() => setSelected(null)} className="text-slate-500 hover:text-white"><X className="w-4 h-4" /></button>
            </div>
            <div className="p-4 space-y-3">
              <div className="grid grid-cols-2 gap-2 text-[11px]">
                <div className="bg-navy-900 border border-navy-700 rounded-md p-2.5">
                  <div className="text-slate-500 text-[9px] tracking-widest uppercase mb-1">Current Risk</div>
                  <div className="flex items-center gap-2">
                    <span className="font-mono font-bold text-xl text-white">{Math.round(detail.risk_score || 0)}</span>
                    <SevBadge severity={detail.status} />
                  </div>
                </div>
                <div className="bg-navy-900 border border-navy-700 rounded-md p-2.5">
                  <div className="text-slate-500 text-[9px] tracking-widest uppercase mb-1">Current Zone</div>
                  <div className="text-slate-200">{detail.current_zone || '—'}</div>
                </div>
                <div className="bg-navy-900 border border-navy-700 rounded-md p-2.5">
                  <div className="text-slate-500 text-[9px] tracking-widest uppercase mb-1">PPE Compliance</div>
                  <div className="font-mono">
                    <span style={{ color: (detail.ppe || {}).helmet ? '#22c55e' : '#ef4444' }}>Helmet {(detail.ppe || {}).helmet ? '✓' : '✕'}</span>{' '}
                    <span style={{ color: (detail.ppe || {}).vest ? '#22c55e' : '#ef4444' }}>Vest {(detail.ppe || {}).vest ? '✓' : '✕'}</span>{' '}
                    <span style={{ color: (detail.ppe || {}).gloves ? '#22c55e' : '#ef4444' }}>Gloves {(detail.ppe || {}).gloves ? '✓' : '✕'}</span>
                  </div>
                </div>
                <div className="bg-navy-900 border border-navy-700 rounded-md p-2.5">
                  <div className="text-slate-500 text-[9px] tracking-widest uppercase mb-1">Exposure Time</div>
                  <div className="font-mono text-slate-200">{detail.exposure_time ?? 0} min</div>
                </div>
                <div className="bg-navy-900 border border-navy-700 rounded-md p-2.5">
                  <div className="text-slate-500 text-[9px] tracking-widest uppercase mb-1">Tracking ID</div>
                  <div className="font-mono text-slate-200">#{detail.tracking_id || '—'}</div>
                </div>
                <div className="bg-navy-900 border border-navy-700 rounded-md p-2.5">
                  <div className="text-slate-500 text-[9px] tracking-widest uppercase mb-1">ML Probability</div>
                  <div className="font-mono text-slate-200">{detail.ml_probability != null ? `${Math.round(detail.ml_probability * 100)}%` : '—'}</div>
                </div>
                <div className="bg-navy-900 border border-navy-700 rounded-md p-2.5">
                  <div className="text-slate-500 text-[9px] tracking-widest uppercase mb-1">Voice Cooldown</div>
                  <div className="flex items-center gap-2 font-mono text-[10px]">
                    {detail.voice_cooldown?.cooldown_active ? (
                      <>
                        <VolumeX className="w-3.5 h-3.5 text-warn" />
                        <span className="text-warn">Active</span>
                        {detail.voice_cooldown.critical_remaining != null && <span>CRIT: {detail.voice_cooldown.critical_remaining}s</span>}
                        {detail.voice_cooldown.high_remaining != null && <span>HIGH: {detail.voice_cooldown.high_remaining}s</span>}
                        {detail.voice_cooldown.warning_remaining != null && <span>WARN: {detail.voice_cooldown.warning_remaining}s</span>}
                      </>
                    ) : (
                      <>
                        <Mic className="w-3.5 h-3.5 text-safe" />
                        <span className="text-safe">Ready</span>
                      </>
                    )}
                  </div>
                </div>
                <div className="bg-navy-900 border border-navy-700 rounded-md p-2.5">
                  <div className="text-slate-500 text-[9px] tracking-widest uppercase mb-1">Model Version</div>
                  <div className="font-mono text-slate-200">{detail.model_version || 'rule-only'}</div>
                </div>
              </div>
              <div className="bg-navy-900 border border-navy-700 rounded-md p-3">
                <div className="card-title mb-2">SAFETY HISTORY</div>
                <div className="grid grid-cols-3 gap-2 text-center mb-2">
                  <div><div className="text-lg font-bold font-mono text-white">{detail.total_incidents}</div><div className="text-[9px] text-slate-500 uppercase">Total</div></div>
                  <div><div className="text-lg font-bold font-mono text-critical">{detail.critical_count}</div><div className="text-[9px] text-slate-500 uppercase">Critical</div></div>
                  <div><div className="text-lg font-bold font-mono text-warn">{detail.avg_risk}</div><div className="text-[9px] text-slate-500 uppercase">Avg Risk</div></div>
                </div>
              </div>
              <div className="bg-navy-900 border border-navy-700 rounded-md p-3">
                <div className="card-title mb-2">RECENT ALERTS</div>
                <div className="space-y-1.5">
                  {(detail.recent_alerts || []).length === 0 && (
                    <div className="text-[11px] text-slate-600">No recorded alerts for this worker.</div>
                  )}
                  {(detail.recent_alerts || []).map((r) => (
                    <div key={r.id} className="flex items-center gap-2 text-[10px] bg-navy-950/60 border border-navy-800 rounded px-2 py-1.5">
                      <SevBadge severity={r.severity} />
                      <span className="font-mono text-slate-500">{(r.timestamp || '').replace('T', ' ').slice(5)}</span>
                      <span className="text-slate-400 flex-1 truncate">{r.event_type}</span>
                      <span className="font-mono font-bold text-white">{Math.round(r.risk_score)}</span>
                      {r.ml_probability != null && <span className="font-mono text-[10px] text-blue-400">ML: {Math.round(r.ml_probability * 100)}%</span>}
                      {r.voice_alert && <span className="text-[10px] text-purple-400">🔊</span>}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
