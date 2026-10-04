import { useEffect, useMemo, useState } from 'react'
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { AlertTriangle, Brain, Target } from 'lucide-react'
import api from '../services/api'

const SEV_COLORS = { CRITICAL: '#ef4444', HIGH: '#f97316', WARNING: '#f59e0b', SAFE: '#22c55e' }
const CAUSE_COLORS = ['#3b82f6', '#f97316', '#ef4444', '#f59e0b', '#8b5cf6', '#14b8a6', '#64748b']

export default function Analytics({ refreshKey }) {
  const [a, setA] = useState(null)
  const [selectedCause, setSelectedCause] = useState(null)
  const [causeIncidents, setCauseIncidents] = useState([])

  useEffect(() => { api.analytics().then(setA).catch(() => setA(null)) }, [refreshKey])

  // clicking a root-cause slice shows its associated incidents
  useEffect(() => {
    if (!selectedCause) { setCauseIncidents([]); return }
    api.incidents({ root_cause: selectedCause.split(' ')[0] })
      .then(setCauseIncidents)
      .catch(() => setCauseIncidents([]))
  }, [selectedCause])

  const kpis = useMemo(() => ([
    { label: 'TOTAL INCIDENTS', value: a ? (a.incidents_over_time || []).reduce((s, d) => s + d.count, 0) : '—', tint: 'text-white' },
    { label: 'CRITICAL', value: a ? (a.incidents_by_severity || []).find((s) => s.severity === 'CRITICAL')?.count ?? 0 : '—', tint: 'text-critical' },
    { label: 'HIGH', value: a ? (a.incidents_by_severity || []).find((s) => s.severity === 'HIGH')?.count ?? 0 : '—', tint: 'text-danger' },
    { label: 'PPE COMPLIANCE', value: a ? `${Math.round(a.ppe_compliance)}%` : '—', tint: 'text-emerald-400' },
    { label: 'AVG RISK SCORE', value: a?.avg_risk_score ?? '—', tint: (a?.avg_risk_score || 0) >= 50 ? 'text-critical' : 'text-warn' },
    { label: 'NEAR MISSES', value: a?.near_misses ?? '—', tint: 'text-violet-400' },
  ]), [a])

  if (!a) {
    return <div className="p-6 text-slate-500 text-xs">Loading analytics from SQLite…</div>
  }

  return (
    <div className="p-4 space-y-3.5">
      <div>
        <h1 className="text-lg font-bold text-white tracking-wide">SAFETY ANALYTICS</h1>
        <p className="text-[11px] text-slate-500">All charts use ACTUAL SQLite event data — they update as demo incidents are generated.</p>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-3 xl:grid-cols-6 gap-2.5">
        {kpis.map((c) => (
          <div key={c.label} className="card px-3 py-2.5">
            <div className="text-[9px] font-semibold tracking-[0.14em] text-slate-500 uppercase truncate">{c.label}</div>
            <div className={`kpi-value mt-1 ${c.tint}`}>{c.value}</div>
          </div>
        ))}
      </div>

      {/* incidents over time + by severity */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-3.5">
        <div className="card p-3 xl:col-span-2">
          <div className="card-title mb-2">1. SAFETY INCIDENTS OVER TIME (7 DAYS)</div>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={a.incidents_over_time}>
              <CartesianGrid stroke="#1a2540" strokeDasharray="3 3" />
              <XAxis dataKey="date" stroke="#64748b" fontSize={10} />
              <YAxis stroke="#64748b" fontSize={10} allowDecimals={false} />
              <Tooltip contentStyle={{ background: '#0d1526', border: '1px solid #243252', fontSize: 11 }} />
              <Line type="monotone" dataKey="count" stroke="#3b82f6" strokeWidth={2} dot={{ fill: '#3b82f6', r: 3 }} name="Incidents" />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <div className="card p-3">
          <div className="card-title mb-2">2. INCIDENTS BY SEVERITY</div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={a.incidents_by_severity}>
              <CartesianGrid stroke="#1a2540" strokeDasharray="3 3" />
              <XAxis dataKey="severity" stroke="#64748b" fontSize={10} />
              <YAxis stroke="#64748b" fontSize={10} allowDecimals={false} />
              <Tooltip contentStyle={{ background: '#0d1526', border: '1px solid #243252', fontSize: 11 }} />
              <Bar dataKey="count" name="Incidents" radius={[3, 3, 0, 0]}>
                {(a.incidents_by_severity || []).map((s) => <Cell key={s.severity} fill={SEV_COLORS[s.severity] || '#3b82f6'} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* WHY ARE INCIDENTS HAPPENING? (interactive) + PPE compliance */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-3.5">
        <div className="card p-3 xl:col-span-2">
          <div className="card-title mb-2 flex items-center gap-2">
            <Brain className="w-3.5 h-3.5 text-blue-400" /> 3. WHY ARE INCIDENTS HAPPENING?
          </div>
          <div className="flex items-center">
            <ResponsiveContainer width="45%" height={220}>
              <PieChart>
                <Pie data={a.incidents_by_root_cause} dataKey="count" nameKey="cause"
                     innerRadius={45} outerRadius={80} paddingAngle={2}
                     onClick={(entry) => setSelectedCause(entry && entry.payload ? entry.cause : entry && entry.cause)}>
                  {(a.incidents_by_root_cause || []).map((r, i) => (
                    <Cell key={i} fill={CAUSE_COLORS[i % CAUSE_COLORS.length]} stroke="#0d1526" cursor="pointer" />
                  ))}
                </Pie>
                <Tooltip contentStyle={{ background: '#0d1526', border: '1px solid #243252', fontSize: 11 }} />
              </PieChart>
            </ResponsiveContainer>
            <div className="flex-1 space-y-1.5 pl-3">
              {(a.incidents_by_root_cause || []).map((r, i) => (
                <button key={i} onClick={() => setSelectedCause(r.cause)}
                        className={`w-full flex items-center gap-2 px-2 py-1 rounded border text-left transition-colors ${
                          selectedCause === r.cause ? 'bg-blue-600/15 border-blue-500/40' : 'border-navy-700 hover:bg-navy-800'}`}>
                  <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ background: CAUSE_COLORS[i % CAUSE_COLORS.length] }} />
                  <span className="text-[10px] text-slate-300 flex-1 truncate">{r.cause}</span>
                  <span className="text-[10px] font-mono font-bold text-white">{r.pct}%</span>
                </button>
              ))}
              {selectedCause && (
                <button onClick={() => setSelectedCause(null)} className="text-[9px] text-slate-500 hover:text-white pt-1">
                  ✕ clear selection
                </button>
              )}
            </div>
          </div>
          {selectedCause && (
            <div className="mt-2 border-t border-navy-700 pt-2">
              <div className="card-title mb-1.5">INCIDENTS FOR “{selectedCause}” — {causeIncidents.length} FOUND</div>
              <div className="max-h-32 overflow-y-auto space-y-1">
                {causeIncidents.slice(0, 10).map((inc) => (
                  <div key={inc.id} className="flex items-center gap-2 text-[10px] bg-navy-900 border border-navy-800 rounded px-2 py-1">
                    <span className="font-mono text-slate-500">#{inc.id}</span>
                    <span className="font-mono font-semibold text-white">{inc.worker_id}</span>
                    <span className="text-slate-500 flex-1 truncate">{(inc.timestamp || '').replace('T', ' ')}</span>
                    <span className="font-mono font-bold">{Math.round(inc.risk_score)}</span>
                    <span className="font-mono" style={{ color: SEV_COLORS[inc.severity] }}>{inc.severity}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
        <div className="card p-3">
          <div className="card-title mb-2">4. PPE COMPLIANCE RATE</div>
          <div className="flex items-center justify-center">
            <div className="relative">
              <ResponsiveContainer width={180} height={180}>
                <PieChart>
                  <Pie data={[{ name: 'Compliant', value: a.ppe_compliance },
                             { name: 'Non-compliant', value: Math.max(0, 100 - a.ppe_compliance) }]}
                       dataKey="value" innerRadius={55} outerRadius={80} startAngle={90} endAngle={-270}>
                    <Cell fill="#22c55e" /><Cell fill="#1a2540" />
                  </Pie>
                  <Tooltip contentStyle={{ background: '#0d1526', border: '1px solid #243252', fontSize: 11 }} />
                </PieChart>
              </ResponsiveContainer>
              <div className="absolute inset-0 flex items-center justify-center">
                <span className="text-2xl font-bold font-mono text-safe">{Math.round(a.ppe_compliance)}%</span>
              </div>
            </div>
          </div>
          <div className="mt-2 space-y-1">
            {(a.ppe_missing || []).map((m) => (
              <div key={m.item} className="flex justify-between text-[10px] bg-navy-900 border border-navy-800 rounded px-2 py-1">
                <span className="text-slate-400">{m.item} missing events</span>
                <span className="font-mono font-bold text-warn">{m.missing}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* zone entries + worker exposure + posture */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-3.5">
        <div className="card p-3">
          <div className="card-title mb-2">6. HAZARD-ZONE ENTRIES</div>
          <ResponsiveContainer width="100%" height={190}>
            <BarChart data={a.zone_entries} layout="vertical">
              <CartesianGrid stroke="#1a2540" strokeDasharray="3 3" />
              <XAxis type="number" stroke="#64748b" fontSize={10} allowDecimals={false} />
              <YAxis type="category" dataKey="zone" stroke="#64748b" fontSize={9} width={150} />
              <Tooltip contentStyle={{ background: '#0d1526', border: '1px solid #243252', fontSize: 11 }} />
              <Bar dataKey="entries" fill="#f97316" radius={[0, 3, 3, 0]} name="Entries" />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="card p-3">
          <div className="card-title mb-2">7. WORKER EXPOSURE TIME (MIN IN ZONES)</div>
          <ResponsiveContainer width="100%" height={190}>
            <BarChart data={a.worker_exposure}>
              <CartesianGrid stroke="#1a2540" strokeDasharray="3 3" />
              <XAxis dataKey="worker" stroke="#64748b" fontSize={10} />
              <YAxis stroke="#64748b" fontSize={10} />
              <Tooltip contentStyle={{ background: '#0d1526', border: '1px solid #243252', fontSize: 11 }} />
              <Bar dataKey="minutes" fill="#8b5cf6" radius={[3, 3, 0, 0]} name="Minutes" />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="card p-3">
          <div className="card-title mb-2">5. POSTURE EVENTS</div>
          <ResponsiveContainer width="100%" height={190}>
            <BarChart data={a.posture_events}>
              <CartesianGrid stroke="#1a2540" strokeDasharray="3 3" />
              <XAxis dataKey="posture" stroke="#64748b" fontSize={10} />
              <YAxis stroke="#64748b" fontSize={10} allowDecimals={false} />
              <Tooltip contentStyle={{ background: '#0d1526', border: '1px solid #243252', fontSize: 11 }} />
              <Bar dataKey="count" fill="#ec4899" radius={[3, 3, 0, 0]} name="Events" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* 8. near-miss intelligence */}
      <div className="card p-4">
        <div className="card-title mb-3 flex items-center gap-2">
          <Target className="w-3.5 h-3.5 text-violet-400" /> 8. NEAR-MISS INTELLIGENCE
        </div>
        <div className="grid grid-cols-3 gap-3">
          <div className="bg-navy-900 border border-navy-700 rounded-md p-3 text-center">
            <div className="text-[9px] tracking-widest text-slate-500 uppercase">Near Misses Today</div>
            <div className="text-3xl font-bold font-mono text-violet-400 mt-1">{a.near_misses_today}</div>
          </div>
          <div className="bg-navy-900 border border-navy-700 rounded-md p-3 text-center">
            <div className="text-[9px] tracking-widest text-slate-500 uppercase">Most Common Cause</div>
            <div className="text-sm font-bold text-white mt-2">{a.near_most_common_cause}</div>
          </div>
          <div className="bg-navy-900 border border-navy-700 rounded-md p-3 text-center">
            <div className="text-[9px] tracking-widest text-slate-500 uppercase">Highest Risk Zone</div>
            <div className="text-sm font-bold text-white mt-2">{a.near_highest_risk_zone}</div>
          </div>
        </div>
        <p className="mt-3 text-[10px] text-slate-500 flex items-start gap-1.5">
          <AlertTriangle className="w-3 h-3 mt-0.5 shrink-0 text-violet-400" />
          Auto-detected events are logged continuously rather than relying only on manual/self-reported observations.
          Near-misses are HIGH-severity events that auto-resolved without escalating to CRITICAL.
        </p>
      </div>
    </div>
  )
}
