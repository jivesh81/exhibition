import { useCallback, useEffect, useState } from 'react'
import { Trash2 } from 'lucide-react'
import api from '../services/api'
import IncidentModal from '../components/IncidentModal'
import { SevBadge, StatusBadge } from '../components/StatusBadge'

const SEVERITIES = ['', 'CRITICAL', 'HIGH', 'WARNING', 'SAFE']
const STATUSES = ['', 'OPEN', 'ACKNOWLEDGED', 'RESOLVED', 'AUTO_RESOLVED']
const ZONES = ['', 'ZONE A', 'ZONE B', 'ZONE C']
const ROOT_CAUSES = ['', 'PPE NON-COMPLIANCE', 'UNSAFE PROXIMITY', 'UNSAFE POSTURE', 'INATTENTIVENESS']

export default function Incidents({ refreshKey, onAcknowledge, onResolve }) {
  const [rows, setRows] = useState([])
  const [filters, setFilters] = useState({ severity: '', date: '', worker: '', zone: '', root_cause: '', status: '' })
  const [selected, setSelected] = useState(null)

  const load = useCallback(() => {
    api.incidents(filters).then(setRows).catch(() => setRows([]))
  }, [filters])

  useEffect(() => { load() }, [load, refreshKey])

  function setFilter(key, val) {
    setFilters((f) => ({ ...f, [key]: val }))
  }

  async function remove(id) {
    try { await api.deleteIncident(id) } catch { /* noop */ }
    load()
  }

  return (
    <div className="p-4 space-y-3.5">
      <div>
        <h1 className="text-lg font-bold text-white tracking-wide">INCIDENT HISTORY</h1>
        <p className="text-[11px] text-slate-500">Every generated alert is automatically logged to SQLite.</p>
      </div>

      {/* filters */}
      <div className="card p-3 grid grid-cols-3 xl:grid-cols-6 gap-2">
        <div>
          <label className="text-[9px] tracking-widest text-slate-500 uppercase">Severity</label>
          <select className="input mt-1" value={filters.severity} onChange={(e) => setFilter('severity', e.target.value)}>
            {SEVERITIES.map((s) => <option key={s} value={s}>{s || 'All'}</option>)}
          </select>
        </div>
        <div>
          <label className="text-[9px] tracking-widest text-slate-500 uppercase">Date</label>
          <input type="date" className="input mt-1" value={filters.date} onChange={(e) => setFilter('date', e.target.value)} />
        </div>
        <div>
          <label className="text-[9px] tracking-widest text-slate-500 uppercase">Worker</label>
          <input className="input mt-1" placeholder="W-002" value={filters.worker} onChange={(e) => setFilter('worker', e.target.value)} />
        </div>
        <div>
          <label className="text-[9px] tracking-widest text-slate-500 uppercase">Zone</label>
          <select className="input mt-1" value={filters.zone} onChange={(e) => setFilter('zone', e.target.value)}>
            {ZONES.map((z) => <option key={z} value={z}>{z || 'All'}</option>)}
          </select>
        </div>
        <div>
          <label className="text-[9px] tracking-widest text-slate-500 uppercase">Root Cause</label>
          <select className="input mt-1" value={filters.root_cause} onChange={(e) => setFilter('root_cause', e.target.value)}>
            {ROOT_CAUSES.map((r) => <option key={r} value={r}>{r || 'All'}</option>)}
          </select>
        </div>
        <div>
          <label className="text-[9px] tracking-widest text-slate-500 uppercase">Status</label>
          <select className="input mt-1" value={filters.status} onChange={(e) => setFilter('status', e.target.value)}>
            {STATUSES.map((s) => <option key={s} value={s}>{s.replace('_', ' ') || 'All'}</option>)}
          </select>
        </div>
      </div>

      {/* table */}
      <div className="card overflow-hidden">
        <div className="card-header">
          <span className="card-title">{rows.length} INCIDENTS</span>
        </div>
        <div className="overflow-x-auto max-h-[62vh] overflow-y-auto">
          <table className="w-full">
            <thead className="sticky top-0 z-10">
              <tr>
                <th className="table-th">ID</th>
                <th className="table-th">Timestamp</th>
                <th className="table-th">Worker</th>
                <th className="table-th">Zone</th>
                <th className="table-th">Event Type</th>
                <th className="table-th">Risk</th>
                <th className="table-th">Severity</th>
                <th className="table-th">Root Cause</th>
                <th className="table-th">Status</th>
                <th className="table-th">Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && (
                <tr><td colSpan="10" className="table-td text-center py-8 text-slate-600">No incidents match the current filters.</td></tr>
              )}
              {rows.map((r) => (
                <tr key={r.id} className="hover:bg-navy-800/50 cursor-pointer" onClick={() => setSelected(r.id)}>
                  <td className="table-td font-mono text-slate-400">#{r.id}</td>
                  <td className="table-td font-mono text-[10px]">{(r.timestamp || '').replace('T', ' ')}</td>
                  <td className="table-td font-mono font-semibold text-white">{r.worker_id}</td>
                  <td className="table-td text-[10px]">{r.zone_id ? `ZONE ${r.zone_id}` : '—'}</td>
                  <td className="table-td text-[10px]">{r.event_type}</td>
                  <td className="table-td font-mono font-bold">{Math.round(r.risk_score || 0)}</td>
                  <td className="table-td"><SevBadge severity={r.severity} /></td>
                  <td className="table-td text-[10px] max-w-[180px] truncate" title={r.root_cause}>{r.root_cause}</td>
                  <td className="table-td"><StatusBadge status={r.status} /></td>
                  <td className="table-td" onClick={(e) => e.stopPropagation()}>
                    <div className="flex gap-1">
                      {r.status !== 'RESOLVED' && r.status !== 'AUTO_RESOLVED' && (
                        <>
                          <button onClick={() => onAcknowledge(r.id)} className="btn-ghost px-1.5 py-0.5 text-[9px]">ACK</button>
                          <button onClick={() => onResolve(r.id)} className="btn-success px-1.5 py-0.5 text-[9px]">RESOLVE</button>
                        </>
                      )}
                      <button onClick={() => remove(r.id)} className="btn-ghost px-1.5 py-0.5 text-[9px] hover:!text-red-400" title="Delete">
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

      <IncidentModal incidentId={selected} onClose={() => setSelected(null)} />
    </div>
  )
}
