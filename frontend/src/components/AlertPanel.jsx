import { AlertTriangle, Check, Eye, ShieldAlert } from 'lucide-react'

const SEV_STYLE = {
  SAFE: { cls: 'bg-safe-dim text-safe border-safe-b', label: 'SAFE' },
  WARNING: { cls: 'bg-warn-dim text-warn border-warn-b', label: 'WARNING' },
  HIGH: { cls: 'bg-danger-dim text-danger border-danger-b', label: 'HIGH' },
  CRITICAL: { cls: 'bg-critical-dim text-critical border-critical-b', label: 'CRITICAL' },
}

export default function AlertPanel({ alerts, onAcknowledge, onResolve }) {
  return (
    <div className="card flex flex-col h-full">
      <div className="card-header">
        <span className="card-title flex items-center gap-2">
          <ShieldAlert className="w-3.5 h-3.5 text-red-400" /> LIVE ALERTS
        </span>
        <span className="text-[10px] font-mono text-slate-500">{alerts.length} ACTIVE</span>
      </div>
      <div className="flex-1 overflow-y-auto p-2.5 space-y-2 max-h-[560px]">
        {alerts.length === 0 && (
          <div className="text-center py-10 text-slate-600 text-xs">
            <AlertTriangle className="w-6 h-6 mx-auto mb-2 opacity-40" />
            No active alerts — all workers within safe thresholds.
          </div>
        )}
        {alerts.map((a) => {
          const st = SEV_STYLE[a.severity] || SEV_STYLE.SAFE
          const crit = a.severity === 'CRITICAL'
          const causes = String(a.root_cause || '').split(' + ')
          return (
            <div key={a.incident_id || a.time}
                 className={`rounded-md border bg-navy-900/70 p-2.5 animate-fade-in ${crit ? 'animate-critical' : ''}`}
                 style={{ borderColor: crit ? undefined : undefined }}>
              <div className="flex items-center justify-between mb-1.5">
                <span className={`badge ${st.cls}`}>{st.label}</span>
                <span className="text-[10px] font-mono text-slate-500">{a.time}</span>
              </div>
              <div className="text-xs font-semibold text-white">{a.worker_id}{a.worker_name ? ` — ${a.worker_name}` : ''}</div>
              <div className="text-[10px] text-slate-400 mb-1.5">{a.zone}</div>
              <div className="flex items-center justify-between text-[10px] font-mono">
                <span className="text-slate-500">RISK SCORE:</span>
                <span className={`font-bold ${a.severity === 'CRITICAL' ? 'text-critical' : a.severity === 'HIGH' ? 'text-danger' : 'text-warn'}`}>
                  {Math.round(a.risk_score || 0)}
                </span>
              </div>
              <div className="mt-1.5 flex flex-wrap gap-1">
                {causes.map((c, i) => (
                  <span key={i} className="text-[9px] font-mono text-slate-400 bg-navy-800 border border-navy-600 rounded px-1 py-0.5">
                    {c}{i < causes.length - 1 ? ' +' : ''}
                  </span>
                ))}
              </div>
              <div className="mt-2 flex gap-1.5">
                <button onClick={() => onAcknowledge && onAcknowledge(a.incident_id)}
                        className="btn-ghost flex-1 justify-center py-1">
                  <Check className="w-3 h-3" /> ACKNOWLEDGE
                </button>
                <button onClick={() => onResolve && onResolve(a.incident_id)}
                        className="btn-success flex-1 justify-center py-1">
                  <Eye className="w-3 h-3" /> RESOLVE
                </button>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
