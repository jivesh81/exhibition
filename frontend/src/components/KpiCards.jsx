// KPI cards used on the dashboard — values come from real database data
export default function KpiCards({ dashboard }) {
  const d = dashboard || {}
  const cards = [
    { label: 'TOTAL WORKERS', value: d.total_workers ?? '—', tint: 'text-blue-400' },
    { label: 'ACTIVE CAMERAS', value: d.active_cameras ?? '—', tint: 'text-cyan-400' },
    { label: 'OPEN ALERTS', value: d.open_alerts ?? '—', tint: d.open_alerts > 0 ? 'text-critical' : 'text-safe' },
    { label: "TODAY'S INCIDENTS", value: d.today_incidents ?? '—', tint: 'text-white' },
    { label: 'CRITICAL', value: d.critical ?? '—', tint: 'text-critical' },
    { label: 'HIGH', value: d.high ?? '—', tint: 'text-danger' },
    { label: 'WARNING', value: d.warning ?? '—', tint: 'text-warn' },
    { label: 'SAFE EVENTS', value: d.safe_events ?? '—', tint: 'text-safe' },
    { label: 'PPE COMPLIANCE', value: d.ppe_compliance != null ? `${Math.round(d.ppe_compliance)}%` : '—', tint: 'text-emerald-400' },
    { label: 'AVG RISK SCORE', value: d.avg_risk_score ?? '—', tint: d.avg_risk_score >= 50 ? 'text-critical' : d.avg_risk_score >= 25 ? 'text-warn' : 'text-safe' },
    { label: 'NEAR MISSES', value: d.near_misses ?? '—', tint: 'text-violet-400' },
  ]
  return (
    <div className="grid grid-cols-4 xl:grid-cols-6 gap-2.5">
      {cards.map((c) => (
        <div key={c.label} className="card px-3 py-2.5">
          <div className="text-[9px] font-semibold tracking-[0.14em] text-slate-500 uppercase truncate">{c.label}</div>
          <div className={`kpi-value mt-1 ${c.tint}`}>{c.value}</div>
        </div>
      ))}
    </div>
  )
}
