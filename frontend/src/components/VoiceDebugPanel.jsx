import { useState, useEffect, useRef } from 'react'
import { Mic, MicOff, Volume2, VolumeX, Wifi, WifiOff, Database, Cpu, AlertTriangle, Check, X, RefreshCw, Terminal, Play, Pause, Volume2 as VolumeIcon } from 'lucide-react'
import api from '../services/api'
import { voiceService } from '../services/voice'

export default function VoiceDebugPanel({ voiceStatus, wsStatus, onTestVoice, onToggleVoice }) {
  const [lastAlert, setLastAlert] = useState(null)
  const [lastPlayback, setLastPlayback] = useState(null)
  const [audioUrl, setAudioUrl] = useState(null)
  const [ttsStatus, setTtsStatus] = useState('UNKNOWN')
  const [backendVoiceStatus, setBackendVoiceStatus] = useState(null)
  const [hardwareTestLog, setHardwareTestLog] = useState([])
  const [nativeAudioState, setNativeAudioState] = useState({})
  const nativeAudioRef = useRef(null)
  const speechAudioRef = useRef(null)

  const addLog = (msg) => {
    const entry = `[${new Date().toLocaleTimeString()}] ${msg}`
    console.log('[HW TEST]', entry)
    setHardwareTestLog(prev => [...prev.slice(-49), entry])
  }

  // Subscribe to voice service events
  useEffect(() => {
    let unsubscribe = () => {};

    try {
      unsubscribe = voiceService.setCallbacks({
        onStateChange: (status) => {
          // This will be handled by parent via voiceStatus prop
        },
        onPlaybackStart: (alert) => {
          setLastPlayback({ status: 'PLAYING', worker: alert.worker_id, severity: alert.severity, time: new Date().toLocaleTimeString() })
          setLastAlert(alert)
        },
        onPlaybackEnd: (alert) => {
          setLastPlayback({ status: 'SUCCESS', worker: alert.worker_id, severity: alert.severity, time: new Date().toLocaleTimeString() })
        },
        onError: (alert, error) => {
          setLastPlayback({ status: 'FAILED', worker: alert.worker_id, error: error.message, time: new Date().toLocaleTimeString() })
        },
      }) || (() => {});
    } catch (e) {
      console.warn('[VoiceDebugPanel] Failed to set voice callbacks:', e);
      unsubscribe = () => {};
    }

    // Fetch backend voice status
    api.voiceStatus().then(setBackendVoiceStatus).catch(() => setTtsStatus('ERROR'))
    setTtsStatus('READY')

    return () => {
      try {
        if (typeof unsubscribe === 'function') {
          unsubscribe();
        }
      } catch (e) {
        console.warn('[VoiceDebugPanel] Cleanup error:', e);
      }
    };
  }, [])

  // Update TTS status when backend status changes
  useEffect(() => {
    if (backendVoiceStatus) {
      setTtsStatus(backendVoiceStatus.active_provider !== 'NONE' ? 'READY' : 'ERROR')
    }
  }, [backendVoiceStatus])

  // Hardware test functions
  const playHardwareBeep = () => {
    const url = 'http://127.0.0.1:8000/api/voice/audio/hardware-test'
    addLog('[NATIVE AUDIO] creating audio')
    if (nativeAudioRef.current) {
      nativeAudioRef.current.pause()
      nativeAudioRef.current.src = ''
    }
    const audio = new Audio(url)
    audio.volume = 1.0
    audio.muted = false
    nativeAudioRef.current = audio

    addLog('[NATIVE AUDIO] muted = false')
    addLog('[NATIVE AUDIO] volume = 1')
    addLog('[NATIVE AUDIO] src = ' + url)

    audio.oncanplaythrough = () => {
      addLog('[NATIVE AUDIO] canplaythrough')
      updateNativeAudioState(audio, 'canplaythrough')
    }
    audio.onloadeddata = () => {
      addLog('[NATIVE AUDIO] loadeddata')
      updateNativeAudioState(audio, 'loadeddata')
    }
    audio.onerror = (e) => {
      addLog('[NATIVE AUDIO] ERROR: ' + e.message)
      updateNativeAudioState(audio, 'error')
    }
    audio.onended = () => {
      addLog('[NATIVE AUDIO] playback ended')
      updateNativeAudioState(audio, 'ended')
    }
    audio.onpause = () => {
      addLog('[NATIVE AUDIO] paused')
      updateNativeAudioState(audio, 'paused')
    }
    audio.onplay = () => {
      addLog('[NATIVE AUDIO] play started')
      updateNativeAudioState(audio, 'playing')
    }

    addLog('[NATIVE AUDIO] calling play()')
    const playPromise = audio.play()
    if (playPromise !== undefined) {
      playPromise.then(() => {
        addLog('[NATIVE AUDIO] play() resolved')
      }).catch(err => {
        addLog('[NATIVE AUDIO] play() REJECTED: ' + err.name + ' - ' + err.message)
      })
    }

    return false
  }

  const playTestSpeech = () => {
    const url = 'http://127.0.0.1:8000/api/voice/audio/test-speech'
    addLog('[NATIVE SPEECH] creating audio')
    if (speechAudioRef.current) {
      speechAudioRef.current.pause()
      speechAudioRef.current.src = ''
    }
    const audio = new Audio(url)
    audio.volume = 1.0
    audio.muted = false
    speechAudioRef.current = audio

    addLog('[NATIVE SPEECH] muted = false')
    addLog('[NATIVE SPEECH] volume = 1')
    addLog('[NATIVE SPEECH] src = ' + url)

    audio.oncanplaythrough = () => {
      addLog('[NATIVE SPEECH] canplaythrough')
      updateNativeAudioState(audio, 'canplaythrough')
    }
    audio.onloadeddata = () => {
      addLog('[NATIVE SPEECH] loadeddata')
      updateNativeAudioState(audio, 'loadeddata')
    }
    audio.onerror = (e) => {
      addLog('[NATIVE SPEECH] ERROR: ' + e.message)
      updateNativeAudioState(audio, 'error')
    }
    audio.onended = () => {
      addLog('[NATIVE SPEECH] playback ended')
      updateNativeAudioState(audio, 'ended')
    }
    audio.onpause = () => {
      addLog('[NATIVE SPEECH] paused')
      updateNativeAudioState(audio, 'paused')
    }
    audio.onplay = () => {
      addLog('[NATIVE SPEECH] play started')
      updateNativeAudioState(audio, 'playing')
    }

    addLog('[NATIVE SPEECH] calling play()')
    const playPromise = audio.play()
    if (playPromise !== undefined) {
      playPromise.then(() => {
        addLog('[NATIVE SPEECH] play() resolved')
      }).catch(err => {
        addLog('[NATIVE SPEECH] play() REJECTED: ' + err.name + ' - ' + err.message)
      })
    }
  }

  const updateNativeAudioState = (audio, event) => {
    setNativeAudioState({
      src: audio.src,
      readyState: audio.readyState,
      networkState: audio.networkState,
      duration: audio.duration,
      volume: audio.volume,
      muted: audio.muted,
      paused: audio.paused,
      currentTime: audio.currentTime,
      lastEvent: event,
      error: audio.error ? audio.error.message : null,
    })
  }

  const logAudioProperties = (label, audio) => {
    if (!audio) return
    addLog(`[${label}] src=${audio.src} readyState=${audio.readyState} networkState=${audio.networkState} duration=${audio.duration} volume=${audio.volume} muted=${audio.muted} paused=${audio.paused}`)
  }

  const clearLogs = () => {
    setHardwareTestLog([])
    setNativeAudioState({})
  }

  const statusColor = (status) => {
    if (status === 'READY' || status === 'CONNECTED' || status === 'SUCCESS') return 'text-safe'
    if (status === 'PLAYING' || status === 'QUEUED') return 'text-warn'
    if (status === 'ERROR' || status === 'FAILED' || status === 'DISCONNECTED' || status === 'BLOCKED') return 'text-critical'
    return 'text-slate-500'
  }

  const statusBg = (status) => {
    if (status === 'READY' || status === 'CONNECTED' || status === 'SUCCESS') return 'bg-safe-dim border-safe-b'
    if (status === 'PLAYING' || status === 'QUEUED') return 'bg-warn-dim border-warn-b'
    if (status === 'ERROR' || status === 'FAILED' || status === 'DISCONNECTED' || status === 'BLOCKED') return 'bg-critical-dim border-critical-b'
    return 'bg-navy-800 border-navy-600'
  }

  const statusIcon = (status) => {
    if (status === 'READY' || status === 'CONNECTED' || status === 'SUCCESS') return <Check className="w-3 h-3" />
    if (status === 'PLAYING') return <Volume2 className="w-3 h-3 animate-blink" />
    if (status === 'QUEUED') return <AlertTriangle className="w-3 h-3" />
    if (status === 'ERROR' || status === 'FAILED' || status === 'DISCONNECTED' || status === 'BLOCKED') return <X className="w-3 h-3" />
    return <Terminal className="w-3 h-3" />
  }

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title flex items-center gap-2">
          <Terminal className="w-3.5 h-3.5 text-purple-400" /> VOICE SYSTEM DEBUG
        </span>
      </div>
      <div className="p-3 space-y-3">
        {/* Backend Connection */}
        <div className="flex items-center justify-between">
          <span className="text-xs font-mono text-slate-400">BACKEND</span>
          <span className={`badge ${statusBg(ttsStatus)}`}>
            <span className={`status-dot ${statusColor(ttsStatus).replace('text-', 'bg-')}`} />
            {ttsStatus}
          </span>
        </div>

        {/* WebSocket */}
        <div className="flex items-center justify-between">
          <span className="text-xs font-mono text-slate-400">WEBSOCKET</span>
          <span className={`badge ${wsStatus === 'CONNECTED' ? 'bg-safe-dim text-safe border-safe-b' : 'bg-critical-dim text-critical border-critical-b'}`}>
            <span className={`status-dot ${wsStatus === 'CONNECTED' ? 'bg-safe' : 'bg-critical'}`} />
            {wsStatus}
          </span>
        </div>

        {/* TTS Engine */}
        <div className="flex items-center justify-between">
          <span className="text-xs font-mono text-slate-400">TTS ENGINE</span>
          <span className={`badge ${backendVoiceStatus ? (backendVoiceStatus.active_provider !== 'NONE' ? 'bg-safe-dim text-safe border-safe-b' : 'bg-critical-dim text-critical border-critical-b') : 'bg-navy-800 border-navy-600 text-slate-500'}`}>
            {backendVoiceStatus?.active_provider || 'UNKNOWN'}
          </span>
        </div>

        {/* Voice State */}
        <div className="flex items-center justify-between">
          <span className="text-xs font-mono text-slate-400">VOICE STATE</span>
          <span className={`badge ${voiceStatus.enabled ? 'bg-purple-600/20 border-purple-500/30 text-purple-400' : 'bg-slate-600/20 border-slate-500/30 text-slate-500'}`}>
            {voiceStatus.unlocked ? <Mic className="w-3 h-3 mr-1" /> : <MicOff className="w-3 h-3 mr-1" />}
            {voiceStatus.enabled ? (voiceStatus.unlocked ? 'UNLOCKED' : 'ENABLED (BLOCKED)') : 'DISABLED'}
          </span>
        </div>

        {/* Queue */}
        <div className="flex items-center justify-between text-xs">
          <span className="text-slate-400 font-mono">QUEUE LENGTH</span>
          <span className="font-mono text-white">{voiceStatus.queueLength}</span>
        </div>

        {/* Current Playback */}
        <div className="bg-navy-900/50 border border-navy-700 rounded p-2 space-y-1">
          <div className="flex items-center justify-between text-xs">
            <span className="text-slate-400 font-mono">CURRENT</span>
            {voiceStatus.isPlaying && <span className="badge bg-warn-dim text-warn border-warn-b text-[9px]">🔊 PLAYING</span>}
          </div>
          {voiceStatus.currentAlert && (
            <div className="text-[9px] font-mono text-slate-300 space-y-0.5">
              <div>Worker: <span className="text-white">{voiceStatus.currentAlert.worker_id}</span></div>
              <div>Severity: <span className={`font-bold ${voiceStatus.currentAlert.severity === 'CRITICAL' ? 'text-critical' : voiceStatus.currentAlert.severity === 'HIGH' ? 'text-danger' : 'text-warn'}`}>{voiceStatus.currentAlert.severity}</span></div>
              <div className="truncate">Msg: <span className="text-slate-400">{voiceStatus.currentAlert.message}</span></div>
            </div>
          )}
        </div>

        {/* Hardware Audio Test Section */}
        <div className="bg-navy-900/50 border border-purple-500/30 rounded p-3 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono text-purple-400">HARDWARE AUDIO TEST</span>
            <span className="badge bg-purple-600/20 border-purple-500/30 text-purple-400 text-[9px]">
              DIAGNOSTIC
            </span>
          </div>

          <p className="text-[9px] text-slate-500 leading-relaxed">
            Test browser audio output directly. Press buttons in order A → B → C.
          </p>

          {/* A. Hardware Beep (1000Hz tone) */}
          <div className="bg-navy-900/50 border border-navy-700 rounded p-2 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-mono text-slate-400">A. HARDWARE BEEP TEST</span>
              <span className="text-[9px] text-slate-500">1000 Hz, 1s, 48kHz</span>
            </div>
            <div className="flex gap-2">
              <button
                onClick={playHardwareBeep}
                className="flex-1 px-2 py-1.5 rounded text-[9px] font-mono bg-purple-600/20 border border-purple-500/30 text-purple-400 hover:bg-purple-600/30 transition-colors"
              >
                <VolumeIcon className="w-3 h-3 mr-1" /> PLAY BEEP
              </button>
              <button
                onClick={() => nativeAudioRef.current && logAudioProperties('BEEP', nativeAudioRef.current)}
                className="flex-1 px-2 py-1.5 rounded text-[9px] font-mono bg-slate-600/20 border border-slate-500/30 text-slate-400 hover:bg-slate-600/30 transition-colors"
              >
                LOG PROPS
              </button>
            </div>
            {/* Native audio element (visible for manual testing) */}
            <audio
              ref={nativeAudioRef}
              controls
              src="http://127.0.0.1:8000/api/voice/audio/hardware-test"
              className="w-full mt-2"
              style={{ height: '36px' }}
            />
          </div>

          {/* B. Native Speech Test */}
          <div className="bg-navy-900/50 border border-navy-700 rounded p-2 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-mono text-slate-400">B. NATIVE SPEECH TEST</span>
              <span className="text-[9px] text-slate-500">TTS Speech</span>
            </div>
            <div className="flex gap-2">
              <button
                onClick={playTestSpeech}
                className="flex-1 px-2 py-1.5 rounded text-[9px] font-mono bg-blue-600/20 border border-blue-500/30 text-blue-400 hover:bg-blue-600/30 transition-colors"
              >
                <Volume2 className="w-3 h-3 mr-1" /> PLAY SPEECH
              </button>
              <button
                onClick={() => speechAudioRef.current && logAudioProperties('SPEECH', speechAudioRef.current)}
                className="flex-1 px-2 py-1.5 rounded text-[9px] font-mono bg-slate-600/20 border border-slate-500/30 text-slate-400 hover:bg-slate-600/30 transition-colors"
              >
                LOG PROPS
              </button>
            </div>
            <audio
              ref={speechAudioRef}
              controls
              src="http://127.0.0.1:8000/api/voice/audio/test-speech"
              className="w-full mt-2"
              style={{ height: '36px' }}
            />
          </div>

          {/* C. Direct WAV Links */}
          <div className="bg-navy-900/50 border border-navy-700 rounded p-2 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-mono text-slate-400">C. DIRECT WAV URLS</span>
              <span className="text-[9px] text-slate-500">Open in new tab</span>
            </div>
            <div className="space-y-1 text-[9px]">
              <a href="http://127.0.0.1:8000/api/voice/audio/hardware-test" target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:underline block truncate">
                http://127.0.0.1:8000/api/voice/audio/hardware-test (1000Hz beep)
              </a>
              <a href="http://127.0.0.1:8000/api/voice/audio/test-speech" target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:underline block truncate">
                http://127.0.0.1:8000/api/voice/audio/test-speech (TTS speech)
              </a>
            </div>
          </div>

          {/* Native Audio State Display */}
          {Object.keys(nativeAudioState).length > 0 && (
            <div className="bg-navy-900/50 border border-navy-700 rounded p-2">
              <div className="text-xs font-mono text-slate-400 mb-1">NATIVE AUDIO STATE</div>
              <pre className="text-[8px] text-slate-300 overflow-auto max-h-32">{JSON.stringify(nativeAudioState, null, 2)}</pre>
            </div>
          )}

          {/* Test Log */}
          <div className="bg-navy-900/50 border border-navy-700 rounded p-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-mono text-slate-400">TEST LOG</span>
              <button
                onClick={clearLogs}
                className="text-[9px] font-mono text-slate-500 hover:text-slate-300"
              >
                CLEAR
              </button>
            </div>
            <div className="max-h-48 overflow-y-auto text-[8px] font-mono text-slate-300">
              {hardwareTestLog.map((entry, i) => (
                <div key={i} className="border-t border-navy-700 pt-0.5">{entry}</div>
              ))}
            </div>
          </div>
        </div>

        {/* Last Alert Received */}
        {lastAlert && (
          <div className="bg-navy-900/50 border border-navy-700 rounded p-2 space-y-1">
            <div className="text-xs font-mono text-slate-400">LAST ALERT RECEIVED</div>
            <div className="text-[9px] font-mono text-slate-300 space-y-0.5">
              <div>ID: <span className="text-white">{lastAlert.alert_id}</span></div>
              <div>Worker: <span className="text-white">{lastAlert.worker_id}</span></div>
              <div>Severity: <span className={`font-bold ${lastAlert.severity === 'CRITICAL' ? 'text-critical' : lastAlert.severity === 'HIGH' ? 'text-danger' : 'text-warn'}`}>{lastAlert.severity}</span></div>
              <div>Zone: <span className="text-slate-400">{lastAlert.zone}</span></div>
              <div className="truncate">Msg: <span className="text-slate-400">{lastAlert.message}</span></div>
              {lastAlert.audio_url && (
                <div>Audio: <span className="text-blue-400 truncate block">{lastAlert.audio_url}</span></div>
              )}
            </div>
          </div>
        )}

        {/* Last Playback Result */}
        {lastPlayback && (
          <div className={`bg-navy-900/50 border border-navy-700 rounded p-2 space-y-1 ${lastPlayback.status === 'FAILED' ? 'border-critical-b/50' : ''}`}>
            <div className="flex items-center justify-between text-xs">
              <span className="text-slate-400 font-mono">LAST PLAYBACK</span>
              <span className={`badge ${statusBg(lastPlayback.status)} text-[9px]`}>
                {statusIcon(lastPlayback.status)} {lastPlayback.status}
              </span>
            </div>
            <div className="text-[9px] font-mono text-slate-300 space-y-0.5">
              <div>Worker: <span className="text-white">{lastPlayback.worker}</span></div>
              <div>Severity: <span className={`font-bold ${lastPlayback.severity === 'CRITICAL' ? 'text-critical' : lastPlayback.severity === 'HIGH' ? 'text-danger' : 'text-warn'}`}>{lastPlayback.severity}</span></div>
              <div>Time: <span className="text-slate-400">{lastPlayback.time}</span></div>
              {lastPlayback.error && <div className="text-critical">Error: {lastPlayback.error}</div>}
            </div>
          </div>
        )}

        {/* Test Buttons */}
        <div className="flex gap-2 pt-2 border-t border-navy-700">
          <button
            onClick={onTestVoice}
            className="flex-1 px-2 py-1.5 rounded text-[9px] font-mono bg-blue-600/20 border border-blue-500/30 text-blue-400 hover:bg-blue-600/30 transition-colors"
            title="Test voice alert system (uses production pipeline)"
          >
            <Volume2 className="w-3 h-3 mr-1" /> TEST VOICE
          </button>
          <button
            onClick={() => voiceService.clearHistory()}
            className="flex-1 px-2 py-1.5 rounded text-[9px] font-mono bg-slate-600/20 border border-slate-500/30 text-slate-400 hover:bg-slate-600/30 transition-colors"
            title="Clear played alerts history"
          >
            <RefreshCw className="w-3 h-3 mr-1" /> CLEAR HISTORY
          </button>
        </div>

        {/* Backend Voice Status Details */}
        {backendVoiceStatus && (
          <details className="text-[9px] text-slate-500">
            <summary className="cursor-pointer font-mono">Backend Voice Details</summary>
            <pre className="mt-1 p-2 bg-navy-900 rounded text-[8px] overflow-auto">{JSON.stringify(backendVoiceStatus, null, 2)}</pre>
          </details>
        )}
      </div>
    </div>
  )
}