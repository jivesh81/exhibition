import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Activity, AlertTriangle, BarChart3, LayoutDashboard, MapPin, ShieldCheck,
  Users, Video, Wifi, WifiOff, Cpu, Volume2, VolumeX, Mic, MicOff, Terminal,
} from 'lucide-react'
import api from './services/api'
import { connectAlertsWS } from './services/websocket'
import { voiceService } from './services/voice'
import Dashboard from './pages/Dashboard'
import Incidents from './pages/Incidents'
import Analytics from './pages/Analytics'
import Workers from './pages/Workers'
import Zones from './pages/Zones'
import SystemStatus from './pages/SystemStatus'
import VoiceDebugPanel from './components/VoiceDebugPanel'

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
  const [refreshKey, setRefreshKey] = useState(0)
  const [voiceStatus, setVoiceStatus] = useState({ enabled: false, queueLength: 0, isPlaying: false })
  const pageRef = useRef(page)
  pageRef.current = page

  // ---- initial load -------------------------------------------------
  useEffect(() => {
    api.snapshot().then(setSnapshot).catch(() => {})
    api.workers().then(setWorkers).catch(() => {})
    api.dashboard().then(setDashboard).catch(() => {})
    api.incidents({ status: 'OPEN' }).then(setAlerts).catch(() => {})
    // Initialize voice service state
    setVoiceStatus(voiceService.getStatus())
  }, [])

  // ---- Voice service callbacks ---------------------------------------
  useEffect(() => {
    voiceService.setCallbacks({
      onStateChange: (status) => setVoiceStatus(status),
      onPlaybackStart: (alert) => {
        console.log('[Voice] Playing:', alert.worker_id, alert.severity);
      },
      onPlaybackEnd: (alert) => {
        console.log('[Voice] Finished:', alert.worker_id);
      },
      onError: (alert, error) => {
        console.error('[Voice] Error:', error);
      },
    })
  }, [])

  // Simple browser TTS fallback for alert messages
const spokenAlertIds = new Set()

function speakBrowserAlert(text) {
  if (!('speechSynthesis' in window)) {
    console.warn('[BROWSER TTS] speechSynthesis not supported')
    return
  }

  window.speechSynthesis.cancel()

  const utterance = new SpeechSynthesisUtterance(text)
  utterance.rate = 0.95
  utterance.pitch = 1.0
  utterance.volume = 1.0

  utterance.onstart = () =>
    console.log('[BROWSER TTS] START', text)

  utterance.onend = () =>
    console.log('[BROWSER TTS] END')

  utterance.onerror = (e) =>
    console.error('[BROWSER TTS] ERROR', e)

  window.speechSynthesis.speak(utterance)
}

  // ---- WebSocket live updates ---------------------------------------
  useEffect(() => {
    const close = connectAlertsWS({
      onStatus: setWsStatus,
      onMessage: (msg) => {
        if (msg.type === 'snapshot') {
          setSnapshot(msg)
          setWorkers(msg.workers)
        } else if (msg.type === 'alert' && msg.alert) {
          const alert = msg.alert

          console.log('[AUTO BROWSER TTS] ALERT RECEIVED', {
            worker_id: alert.worker_id,
            worker_name: alert.worker_name,
            severity: alert.severity,
            message: alert.message,
            alert_id: alert.alert_id
          })

          if (alert.alert_id && spokenAlertIds.has(alert.alert_id)) {
            console.log('[AUTO BROWSER TTS] DUPLICATE SKIPPED', alert.alert_id)
          } else {
            if (alert.alert_id) {
              spokenAlertIds.add(alert.alert_id)
            }

            const worker = alert.worker_name || alert.worker_id || 'Worker'
            const severity = alert.severity || 'WARNING'
            const message =
              alert.message ||
              'Safety warning. Please move to a safe area.'

            console.log('[AUTO BROWSER TTS] SPEAKING', {
              worker,
              severity,
              message
            })

            speakBrowserAlert(
              `${worker}. ${severity} alert. ${message}`
            )
          }

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
        } else if (msg.type === 'voice_alert') {
          // DIAGNOSTIC: Log the complete received autonomous voice_alert
          console.log("[AUTO VOICE RECEIVED]", JSON.stringify(msg, null, 2));
          // Handle voice alert from backend - play audio in browser
          if (msg.alert && msg.alert.audio_url) {
            voiceService.addAlert({
              alert_id: msg.alert.alert_id,
              worker_id: msg.alert.worker_id,
              worker_name: msg.alert.worker_name,
              severity: msg.alert.severity,
              message: msg.alert.message,
              root_cause: msg.alert.root_cause,
              zone: msg.alert.zone,
              audio_url: msg.alert.audio_url,
            });
          }
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

  const demoStart = useCallback(async (scenario) => {
    // Unlock audio context on demo start (user gesture) to allow autonomous alerts
    if (voiceService.enabled) {
      await voiceService.unlock();
    }
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

  // ---- Voice control callbacks ---------------------------------------
  const toggleVoice = useCallback(async () => {
    const newEnabled = !voiceStatus.enabled;
    await voiceService.setEnabled(newEnabled);
    if (newEnabled) {
      // Test the voice system
      try {
        const res = await api.voiceTest();
        if (res.audio_url) {
          voiceService.testVoice(res.audio_url);
        }
      } catch (e) {
        console.warn('Voice test failed:', e);
      }
    }
    setVoiceStatus(voiceService.getStatus());
  }, [voiceStatus.enabled])

  const testVoice = useCallback(async () => {
    try {
      // Use the static test speech endpoint which serves a pre-generated valid WAV
      const staticAudioUrl = '/api/voice/audio/test-speech-static';
      voiceService.testVoice(staticAudioUrl);
    } catch (e) {
      console.error('Voice test failed:', e);
    }
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
          
          {/* Voice Status Panel */}
          <div className="rounded bg-navy-800 border border-navy-600 p-2 space-y-1.5">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-mono text-slate-400">VOICE ALERTS</span>
              <span className={`flex items-center gap-1 font-mono font-bold text-[10px] ${voiceStatus.enabled ? 'text-safe' : 'text-warn'}`}>
                {voiceStatus.enabled ? <Volume2 className="w-3 h-3" /> : <VolumeX className="w-3 h-3" />}
                {voiceStatus.enabled ? 'ENABLED' : 'DISABLED'}
              </span>
            </div>
            <div className="flex items-center justify-between text-[9px]">
              <span className="text-slate-500">Queue</span>
              <span className="font-mono text-slate-300">{voiceStatus.queueLength}</span>
            </div>
            <div className="flex items-center justify-between text-[9px]">
              <span className="text-slate-500">Status</span>
              <span className={`font-mono ${voiceStatus.isPlaying ? 'text-warn' : 'text-slate-400'}`}>
                {voiceStatus.isPlaying ? '🔊 PLAYING' : 'IDLE'}
              </span>
            </div>
            <div className="flex gap-1 pt-1">
              <button
                onClick={toggleVoice}
                className={`flex-1 px-2 py-1.5 rounded text-[9px] font-mono transition-colors ${
                  voiceStatus.enabled
                    ? 'bg-emerald-600/20 border border-emerald-500/30 text-emerald-400 hover:bg-emerald-600/30'
                    : 'bg-amber-600/20 border border-amber-500/30 text-amber-400 hover:bg-amber-600/30'
                }`}
              >
                {voiceStatus.enabled ? (
                  <>
                    <Mic className="w-3 h-3 mr-1" /> DISABLE
                  </>
                ) : (
                  <>
                    <MicOff className="w-3 h-3 mr-1" /> ENABLE
                  </>
                )}
              </button>
              <button
                onClick={testVoice}
                className="flex-1 px-2 py-1.5 rounded text-[9px] font-mono bg-blue-600/20 border border-blue-500/30 text-blue-400 hover:bg-blue-600/30 transition-colors"
                title="Test voice alert system"
              >
                <Volume2 className="w-3 h-3 mr-1" /> TEST
              </button>
            </div>
          </div>

          <div className="inline-flex items-center px-1.5 py-0.5 rounded bg-navy-800 border border-emerald-600/40 text-[9px] font-mono text-emerald-400 tracking-widest">
            EDGE-FIRST • NO CLOUD VIDEO
          </div>

          {/* Voice Debug Panel (collapsible) */}
          <div className="px-4 pb-4">
            <VoiceDebugPanel
              voiceStatus={voiceStatus}
              wsStatus={wsStatus}
              onTestVoice={testVoice}
              onToggleVoice={toggleVoice}
            />
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