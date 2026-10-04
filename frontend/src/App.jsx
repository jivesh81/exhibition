import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Activity, AlertTriangle, BarChart3, LayoutDashboard, MapPin, ShieldCheck,
  Users, Video, Wifi, WifiOff, Cpu,
} from 'lucide-react'
import api from './services/api'
import { connectAlertsWS } from './services/websocket'
import Dashboard from './pages/Dashboard'
import Incidents from './pages/Incidents'
import Analytics from './pages/Analytics'
import Workers from './pages/Workers'
import Zones from './pages/Zones'
import SystemStatus from './pages/SystemStatus'

const NAV = [
  { id: 'dashboard', label: 'Dashboard', sub: 'Live Monitoring', icon: LayoutDashboard },
  { id: 'incidents', label: 'Incidents', sub: 'Event History', icon: AlertTriangle },
  { id: 'analytics', label: 'Analytics', sub: 'Reports & Trends', icon: BarChart3 },
  { id: 'workers', label: 'Workers', sub: 'Personnel Monitor', icon: Users },
  { id: 'zones', label: 'Zones & Cameras', sub: 'Configuration', icon: MapPin },
  { id: 'system', label: 'System Status', sub: 'Health Panel', icon: Activity },
]

export default function App() {
  const [page, setPage] = useState('dashboard')
  const [snapshot, setSnapshot] = useState(null)
  const [workers, setWorkers] = useState([])
  const [alerts, setAlerts] = useState([])
  const [dashboard, setDashboard] = useState(null)
  const [wsStatus, setWsStatus] = useState('CONNECTING')
  const [refreshKey, setRefreshKey] = useState(0) // pages re-fetch when this changes
  const pageRef = useRef(page)
  pageRef.current = page

  // ---- initial load -------------------------------------------------
  useEffect(() => {
    api.snapshot().then(setSnapshot).catch(() => {})
    api.workers().then(setWorkers).catch(() => {})
    api.dashboard().then(setDashboard).catch(() => {})
    api.incidents({ status: 'OPEN' }).then(setAlerts).catch(() => {})
  }, [])

  // ---- WebSocket live updates ---------------------------------------
  useEffect(() => {
    const close = connectAlertsWS({
      onStatus: setWsStatus,
      onMessage: (msg) => {
        if (msg.type === 'snapshot') {
          setSnapshot(msg)
          setWorkers(msg.workers)
        } else if (msg.type === 'alert') {
          setAlerts((prev) => {
            const rest = prev.filter((a) => a.worker_id !== msg.alert.worker_id)
            return [{ ...msg.alert, status: 'OPEN' }, ...rest].slice(0, 50)
          })
          api.dashboard().then(setDashboard).catch(() => {})
          setRefreshKey((k) => k + 1)
        } else if (msg.type === 'resolved') {
          setAlerts((prev) => prev.filter((a) => a.worker_id !== msg.worker_id))
          api.dashboard().then(setDashboard).catch(() => {})
          setRefreshKey((k) => k + 1)
        }
      },
    })
    return close
  }, [])

  // ---- polling fallback (also keeps other pages fresh) ---------------
  useEffect(() => {
    const t = setInterval(() => {
      api.workers().then(setWorkers).catch(() => {})
      api.dashboard().then(setDashboard).catch(() => {})
      if (pageRef.current === 'incidents') {
        api.incidents({ status: 'OPEN' }).then(setAlerts).catch(() => {})
      }
    }, 4000)
    return () => clearInterval(t)
  }, [])

  // ---- shared callbacks for alert actions ----------------------------
  const acknowledge = useCallback((id) => {
    api.acknowledge(id).then(() => {
      setAlerts((prev) => prev.filter((a) => a.incident_id !== id))
      api.dashboard().then(setDashboard).catch(() => {})
      setRefreshKey((k) => k + 1)
    }).catch(() => {})
  }, [])

  const resolve = useCallback((id) => {
    api.resolve(id).then(() => {
      setAlerts((prev) => prev.filter((a) => a.incident_id !== id))
      api.dashboard().then(setDashboard).catch(() => {})
      setRefreshKey((k) => k + 1)
    }).catch(() => {})
  }, [])

  const demoStart = useCallback((scenario) => {
    api.demoStart(scenario).then(() => setRefreshKey((k) => k + 1)).catch(() => {})
  }, [])

  const demoReset = useCallback(() => {
    api.demoReset().then(() => {
      setAlerts([])
      api.snapshot().then(setSnapshot).catch(() => {})
      api.workers().then(setWorkers).catch(() => {})
      api.dashboard().then(setDashboard).catch(() => {})
      setRefreshKey((k) => k + 1)
    }).catch(() => {})
  }, [])

  const openIncidents = alerts.length
  const aiMode = snapshot?.ai_mode || dashboard?.ai_mode || 'DEMO'

  return (
    <div className="flex h-screen overflow-hidden">
      {/* ---------------- Sidebar ---------------- */}
      <aside className="w-60 shrink-0 bg-navy-900 border-r border-navy-700 flex flex-col">
        <div className="px-4 py-5 border-b border-navy-700">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-md bg-blue-600/20 border border-blue-500/40 flex items-center justify-center">
              <ShieldCheck className="w-5 h-5 text-blue-400" />
            </div>
            <div>
              <div className="text-white font-bold text-[15px] leading-tight tracking-wide">SafeSight AI</div>
              <div className="text-[10px] text-slate-500 leading-tight">AI-Powered Workplace Safety Monitoring</div>
            </div>
          </div>
          <div className="mt-2 inline-flex items-center px-1.5 py-0.5 rounded bg-navy-800 border border-navy-600 text-[9px] font-mono text-slate-400 tracking-widest">
            GROUP 173 PROTOTYPE
          </div>
        </div>

        <nav className="flex-1 py-3 px-2 space-y-0.5">
          {NAV.map(({ id, label, sub, icon: Icon }) => {
            const active = page === id
            return (
              <button
                key={id}
                onClick={() => setPage(id)}
                className={`w-full flex items-center gap-3 px-3 py-2 rounded-md text-left transition-colors duration-150 ${
                  active ? 'bg-blue-600/15 border border-blue-500/30' : 'border border-transparent hover:bg-navy-800'
                }`}
              >
                <Icon className={`w-4 h-4 ${active ? 'text-blue-400' : 'text-slate-500'}`} />
                <span className="flex-1">
                  <span className={`block text-xs font-semibold ${active ? 'text-white' : 'text-slate-300'}`}>{label}</span>
                  <span className="block text-[9px] text-slate-600">{sub}</span>
                </span>
                {id === 'incidents' && openIncidents > 0 && (
                  <span className="bg-red-600 text-white text-[9px] font-bold px-1.5 py-0.5 rounded-full">{openIncidents}</span>
                )}
              </button>
            )
          })}
        </nav>

        <div className="px-4 py-3 border-t border-navy-700 space-y-2">
          <div className="flex items-center justify-between text-[10px]">
            <span className="text-slate-500 tracking-wider">AI MODE</span>
            <span className="flex items-center gap-1 font-mono font-bold text-blue-400">
              <Cpu className="w-3 h-3" />{aiMode.toUpperCase()}
            </span>
          </div>
          <div className="flex items-center justify-between text-[10px]">
            <span className="text-slate-500 tracking-wider">WEBSOCKET</span>
            <span className={`flex items-center gap-1 font-mono font-bold ${wsStatus === 'CONNECTED' ? 'text-safe' : 'text-warn'}`}>
              {wsStatus === 'CONNECTED' ? <Wifi className="w-3 h-3" /> : <WifiOff className="w-3 h-3" />}{wsStatus}
            </span>
          </div>
          <div className="inline-flex items-center px-1.5 py-0.5 rounded bg-navy-800 border border-emerald-600/40 text-[9px] font-mono text-emerald-400 tracking-widest">
            EDGE-FIRST • NO CLOUD VIDEO
          </div>
        </div>
      </aside>

      {/* ---------------- Main content ---------------- */}
      <main className="flex-1 overflow-y-auto">
        {page === 'dashboard' && (
          <Dashboard snapshot={snapshot} workers={workers} dashboard={dashboard}
                     alerts={alerts} onAcknowledge={acknowledge} onResolve={resolve}
                     demoStart={demoStart} demoReset={demoReset} />
        )}
        {page === 'incidents' && (
          <Incidents refreshKey={refreshKey} onAcknowledge={acknowledge} onResolve={resolve} />
        )}
        {page === 'analytics' && <Analytics refreshKey={refreshKey} />}
        {page === 'workers' && <Workers workers={workers} refreshKey={refreshKey} />}
        {page === 'zones' && <Zones snapshot={snapshot} refreshKey={refreshKey} />}
        {page === 'system' && <SystemStatus snapshot={snapshot} />}
      </main>
    </div>
  )
}
