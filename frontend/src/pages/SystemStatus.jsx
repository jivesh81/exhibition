import { Activity, Camera, Cpu, Database, Radio, ShieldCheck, Siren, Workflow, Mic, Cpu as CpuIcon, Brain, Users, Volume2, AlertTriangle } from 'lucide-react'

const DOT = {
  READY: 'bg-safe', CONNECTED: 'bg-safe', ONLINE: 'bg-safe', ACTIVE: 'bg-safe',
  DISABLED: 'bg-slate-600', DEGRADED: 'bg-warn', OFFLINE: 'bg-critical', RULE_ONLY: 'bg-warn',
}

export default function SystemStatus({ snapshot }) {
  const sys = snapshot || {}
  const mlLoaded = sys.ml_model_loaded || false
  const voiceEnabled = sys.voice_enabled !== false
  const voiceProvider = sys.voice_provider || 'NONE'
  const voiceQueue = sys.voice_queue_size || 0
  const trackingActive = sys.tracking_active || false
  const fusionMode = sys.fusion_mode || (mlLoaded ? 'HYBRID' : 'RULE_ONLY')
  const aiMode = sys.ai_mode || 'DEMO'
  
  const rows = [
    { icon: Camera, label: 'Camera Input', value: sys.camera_input || 'ONLINE', note: 'CAM-01 — Main Construction Zone' },
    { icon: CpuIcon, label: 'PPE Model', value: sys.ppe_model || 'READY (Mock fallback)', note: sys.ppe_available ? 'Real YOLO inference' : 'Mock fallback — see README to enable YOLO' },
    { icon: Workflow, label: 'Pose Model', value: sys.pose_model || 'READY (Mock fallback)', note: sys.pose_available ? 'Real pose estimation' : 'Mock fallback — see README to enable YOLO-pose' },
    { icon: Users, label: 'Person Detector', value: sys.person_detector || 'READY (OpenCV HOG)', note: 'OpenCV HOG + SVM detector' },
    { icon: Brain, label: 'Hybrid Risk Model', value: sys.hybrid_risk_model || (mlLoaded ? 'READY (LightGBM)' : 'RULE_ONLY'), note: mlLoaded ? 'ML + Rules fusion active' : 'Deterministic rules only' },
    { icon: Cpu, label: 'Rule Engine', value: 'ACTIVE', note: 'Deterministic safety rules — risk_config.py' },
    { icon: Brain, label: 'Feature Extractor', value: sys.ml_components?.feature_extractor || 'ACTIVE', note: '17-dimensional worker feature vectors' },
    { icon: Workflow, label: 'Risk Fusion', value: sys.ml_components?.risk_fusion || 'ACTIVE', note: 'ML probability + Rules + Temporal fusion' },
    { icon: Users, label: 'Worker Tracker', value: sys.ml_components?.worker_tracker || (trackingActive ? 'ACTIVE' : 'STANDBY'), note: trackingActive ? 'ByteTrack-inspired multi-worker tracking' : 'Waiting for detections' },
    { icon: Mic, label: 'Voice Engine', value: sys.voice_engine || 'UNAVAILABLE', note: voiceEnabled ? `Provider: ${voiceProvider}` : 'Disabled' },
    { icon: Volume2, label: 'Voice Alerts', value: voiceEnabled ? 'ENABLED' : 'DISABLED', note: `Queue: ${voiceQueue} | Provider: ${voiceProvider}` },
    { icon: Database, label: 'Database', value: 'CONNECTED', note: 'SQLite — safesight.db (WAL mode)' },
    { icon: Siren, label: 'WebSocket', value: 'CONNECTED', note: '/ws/alerts — live alert streaming' },
  ]

  const mlInfo = sys.hybrid_risk_model_info || {}

  return (
    <div className="p-4 space-y-3.5">
      <div>
        <h1 className="text-lg font-bold text-white tracking-wide">SYSTEM STATUS</h1>
        <p className="text-[11px] text-slate-500">Edge-first privacy architecture — video processing stays on-device.</p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3.5">
        <div className="card">
          <div className="card-header">
            <span className="card-title">SYSTEM HEALTH</span>
            <span className={`badge ${mlLoaded ? 'bg-safe-dim text-safe border border-safe-b' : 'bg-blue-600/10 text-blue-400 border border-blue-500/30'}`}>
              {mlLoaded ? 'HYBRID AI OPERATIONAL' : 'RULE-ONLY MODE'}
            </span>
          </div>
          <div className="divide-y divide-navy-800">
            {rows.map((r) => (
              <div key={r.label} className="flex items-center gap-3 px-4 py-2.5">
                <r.icon className="w-4 h-4 text-slate-500" />
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-semibold text-slate-200 truncate">{r.label}</div>
                  <div className="text-[9px] text-slate-600 truncate">{r.note}</div>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <span className={`status-dot ${DOT[(r.value || '').split(' ')[0]] || 'bg-safe'}`} />
                  <span className="text-[11px] font-mono font-bold text-safe truncate">{r.value}</span>
                </div>
              </div>
            ))}
            <div className="flex items-center gap-3 px-4 py-2.5">
              <Activity className="w-4 h-4 text-slate-500" />
              <div className="flex-1">
                <div className="text-xs font-semibold text-slate-200">Inference</div>
                <div className="text-[9px] text-slate-600">Detection tick rate</div>
              </div>
              <span className="text-[11px] font-mono font-bold text-safe">{sys.inference_fps || '0.8'} FPS</span>
            </div>
            <div className="flex items-center gap-3 px-4 py-2.5">
              <Cpu className="w-4 h-4 text-slate-500" />
              <div className="flex-1">
                <div className="text-xs font-semibold text-slate-200">Deployment</div>
                <div className="text-[9px] text-slate-600">Jetson / Raspberry-Pi-class edge concept</div>
              </div>
              <span className="text-[11px] font-mono font-bold text-blue-400">LOCAL / EDGE</span>
            </div>
            <div className="flex items-center gap-3 px-4 py-2.5">
              <Radio className="w-4 h-4 text-slate-500" />
              <div className="flex-1">
                <div className="text-xs font-semibold text-slate-200">Cloud Video Transfer</div>
                <div className="text-[9px] text-slate-600">Not implemented by design</div>
              </div>
              <span className="text-[11px] font-mono font-bold text-slate-500">DISABLED</span>
            </div>
          </div>
        </div>

        <div className="space-y-3.5">
          <div className="card p-4">
            <div className="card-title mb-3">AI PIPELINE STATUS</div>
            <div className="space-y-2">
              <div className="flex items-center gap-3 bg-navy-900 border border-navy-700 rounded-md px-3 py-2">
                <Brain className={`w-4 h-4 ${mlLoaded ? 'text-safe' : 'text-warn'}`} />
                <div className="flex-1">
                  <div className="text-[11px] font-semibold text-slate-200 font-mono">
                    {mlInfo.model_type || (mlLoaded ? 'LightGBM' : 'Rule-Only')}
                  </div>
                  <div className="text-[9px] text-slate-600">v{mlInfo.version || '1.0'} • {fusionMode} mode</div>
                </div>
                <span className={`badge ${mlLoaded ? 'bg-safe-dim text-safe' : 'bg-warn-dim text-warn'}`}>
                  {mlLoaded ? 'LOADED' : 'NOT LOADED'}
                </span>
              </div>
              <div className="flex items-center gap-3 bg-navy-900 border border-navy-700 rounded-md px-3 py-2">
                <Cpu className="w-4 h-4 text-blue-400" />
                <div className="flex-1">
                  <div className="text-[11px] font-semibold text-slate-200 font-mono">Feature Vector</div>
                  <div className="text-[9px] text-slate-600">{mlInfo.n_features || 17} dimensions • v{mlInfo.feature_version || '1'}</div>
                </div>
                <span className="badge bg-blue-600/10 text-blue-400">ACTIVE</span>
              </div>
              <div className="flex items-center gap-3 bg-navy-900 border border-navy-700 rounded-md px-3 py-2">
                <Users className="w-4 h-4 text-emerald-400" />
                <div className="flex-1">
                  <div className="text-[11px] font-semibold text-slate-200 font-mono">Worker Tracker</div>
                  <div className="text-[9px] text-slate-600">ByteTrack-inspired • IoU + Kalman</div>
                </div>
                <span className={`badge ${trackingActive ? 'bg-safe-dim text-safe' : 'bg-blue-600/10 text-blue-400'}`}>
                  {trackingActive ? 'TRACKING' : 'STANDBY'}
                </span>
              </div>
              <div className="flex items-center gap-3 bg-navy-900 border border-navy-700 rounded-md px-3 py-2">
                <Mic className="w-4 h-4 text-purple-400" />
                <div className="flex-1">
                  <div className="text-[11px] font-semibold text-slate-200 font-mono">Voice Alerts</div>
                  <div className="text-[9px] text-slate-600">Provider: {voiceProvider} • Queue: {voiceQueue}</div>
                </div>
                <span className={`badge ${voiceEnabled ? 'bg-purple-600/10 text-purple-400' : 'bg-slate-600/10 text-slate-500'}`}>
                  {voiceEnabled ? 'ENABLED' : 'DISABLED'}
                </span>
              </div>
            </div>
            <p className="mt-3 text-[10px] text-slate-500 leading-relaxed">
              The platform auto-selects HYBRID AI MODE when ML model is loaded, otherwise RULE-ONLY MODE.
              Voice alerts use offline TTS (pyttsx3) by default. Worker tracking provides stable IDs across frames.
            </p>
          </div>

          {mlLoaded && mlInfo.metrics && Object.keys(mlInfo.metrics).length > 0 && (
            <div className="card p-4 border border-emerald-600/30">
              <div className="card-title mb-3 text-emerald-400">ML MODEL METRICS (Test Set)</div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-center">
                <div className="bg-navy-900 border border-navy-700 rounded-md p-3">
                  <div className="text-2xl font-bold font-mono text-safe">{Math.round((mlInfo.metrics.accuracy || 0) * 100)}%</div>
                  <div className="text-[9px] text-slate-500 uppercase">Accuracy</div>
                </div>
                <div className="bg-navy-900 border border-navy-700 rounded-md p-3">
                  <div className="text-2xl font-bold font-mono text-blue-400">{Math.round((mlInfo.metrics.precision || 0) * 100)}%</div>
                  <div className="text-[9px] text-slate-500 uppercase">Precision</div>
                </div>
                <div className="bg-navy-900 border border-navy-700 rounded-md p-3">
                  <div className="text-2xl font-bold font-mono text-emerald-400">{Math.round((mlInfo.metrics.recall || 0) * 100)}%</div>
                  <div className="text-[9px] text-slate-500 uppercase">Recall</div>
                </div>
                <div className="bg-navy-900 border border-navy-700 rounded-md p-3">
                  <div className="text-2xl font-bold font-mono text-purple-400">{Math.round((mlInfo.metrics.f1 || 0) * 100)}%</div>
                  <div className="text-[9px] text-slate-500 uppercase">F1 Score</div>
                </div>
                <div className="bg-navy-900 border border-navy-700 rounded-md p-3 col-span-2 md:col-span-1">
                  <div className="text-2xl font-bold font-mono text-amber-400">{Math.round((mlInfo.metrics.roc_auc || 0) * 100)}%</div>
                  <div className="text-[9px] text-slate-500 uppercase">ROC-AUC</div>
                </div>
                <div className="bg-navy-900 border border-navy-700 rounded-md p-3 col-span-2 md:col-span-1">
                  <div className="text-2xl font-bold font-mono text-slate-400">CV F1: {mlInfo.metrics.cv_f1_mean ? (mlInfo.metrics.cv_f1_mean * 100).toFixed(1) + '%' : 'N/A'}</div>
                  <div className="text-[9px] text-slate-500 uppercase">Cross-Val F1</div>
                </div>
              </div>
              <p className="mt-2 text-[10px] text-slate-500">
                Trained on {mlInfo.training_dataset || 'synthetic'} • {mlInfo.training_date ? new Date(mlInfo.training_date).toLocaleDateString() : 'recent'}
              </p>
            </div>
          )}

          <div className="card p-4 border border-emerald-600/30">
            <div className="card-title mb-2 text-emerald-400">EDGE-FIRST • NO CLOUD VIDEO</div>
            <p className="text-[11px] text-slate-300 leading-relaxed">
              Video processing is designed for local/edge inference. Raw video is not uploaded to the cloud —
              webcam and uploaded video stay on-device; only lightweight detection results are exchanged with the backend.
              Voice synthesis runs locally via pyttsx3 (Windows SAPI) or Piper (Linux). ML inference runs on-device CPU/GPU.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}