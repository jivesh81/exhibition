import { useState } from 'react'
import { Radio } from 'lucide-react'
import CameraPanel from '../components/CameraPanel'
import AlertPanel from '../components/AlertPanel'
import DecisionEngineCard from '../components/DecisionEngineCard'
import PipelineFlow from '../components/PipelineFlow'
import KpiCards from '../components/KpiCards'
import IncidentModal from '../components/IncidentModal'
import { SevBadge } from '../components/StatusBadge'

export default function Dashboard({ snapshot, workers, dashboard, alerts,
                                    onAcknowledge, onResolve, demoStart, demoReset }) {
  const [selectedIncident, setSelectedIncident] = useState(null)

  return (
    <div className="p-4 space-y-3.5">
      {/* page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-white tracking-wide">SAFETY COMMAND CENTER</h1>
          <p className="text-[11px] text-slate-500">
            PPE compliance · hazard proximity · posture · rule-based risk fusion — one explainable decision layer
          </p>
        </div>
        <div className="flex items-center gap-2 text-[10px] font-mono">
          <span className="flex items-center gap-1.5 text-safe">
            <Radio className="w-3.5 h-3.5 animate-blink" /> EDGE-FIRST • NO CLOUD VIDEO
          </span>
        </div>
      </div>

      <KpiCards dashboard={dashboard} />

      {/* live monitor + alerts */}
      <div className="flex gap-3.5 items-stretch">
        <div className="flex-1 min-w-0">
          <CameraPanel snapshot={snapshot} demoStart={demoStart} demoReset={demoReset} alerts={alerts} />
        </div>
        <div className="w-72 shrink-0">
          <AlertPanel alerts={alerts} onAcknowledge={onAcknowledge} onResolve={onResolve} />
        </div>
      </div>

      {/* decision engine + worker strip */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-3.5">
        <div className="xl:col-span-1">
          <DecisionEngineCard />
        </div>
        <div className="xl:col-span-2">
          <WorkerStrip workers={workers} />
        </div>
      </div>

      <PipelineFlow />

      <IncidentModal incidentId={selectedIncident} onClose={() => setSelectedIncident(null)} />
    </div>
  )
}

// Live worker strip — compact table of monitored personnel
function WorkerStrip({ workers }) {
  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">WORKER STATUS — LIVE</span>
        <span className="text-[10px] font-mono text-slate-500">{workers.length} MONITORED</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr>
              <th className="table-th">Worker</th>
              <th className="table-th">Track ID</th>
              <th className="table-th">Zone</th>
              <th className="table-th">PPE</th>
              <th className="table-th">Distance</th>
              <th className="table-th">Posture</th>
              <th className="table-th">ML Prob</th>
              <th className="table-th">Risk</th>
              <th className="table-th">Voice</th>
            </tr>
          </thead>
          <tbody>
            {(workers || []).slice(0, 8).map((w) => {
              const ppe = w.ppe || {}
              const ok = ppe.helmet && ppe.vest && ppe.gloves
              const trackingId = w.tracking_id != null ? `#${w.tracking_id}` : '—'
              const trackState = w.track_state || '—'
              const mlProb = w.ml_probability != null ? `${Math.round(w.ml_probability * 100)}%` : '—'
              const voiceAlert = w.voice_alert ? '🔊' : '—'
              return (
                <tr key={w.id} className="hover:bg-navy-800/50">
                  <td className="table-td font-mono font-semibold text-white">{w.id}</td>
                  <td className="table-td font-mono text-[10px]">{trackingId} <span className="text-[9px] text-slate-500 ml-1">({trackState})</span></td>
                  <td className="table-td">{w.current_zone || '—'}</td>
                  <td className="table-td">
                    {ok ? <span className="text-safe">✓ PPE</span>
                        : <span className="text-critical">✕ {!(ppe.helmet) ? 'Helmet' : !(ppe.vest) ? 'Vest' : 'Gloves'}</span>}
                  </td>
                  <td className="table-td font-mono">{w.distance != null ? `${w.distance}m` : '—'}</td>
                  <td className="table-td">{w.posture || 'Normal'}</td>
                  <td className="table-td font-mono text-[10px]">{mlProb}</td>
                  <td className="table-td">
                    <div className="flex items-center gap-2">
                      <span className="font-mono font-bold">{Math.round(w.risk_score || 0)}</span>
                      <SevBadge severity={w.severity || 'SAFE'} />
                    </div>
                  </td>
                  <td className="table-td text-center">{voiceAlert}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
