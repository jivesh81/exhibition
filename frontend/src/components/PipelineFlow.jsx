import { ArrowDown } from 'lucide-react'

const STEPS = [
  'CAMERA', 'PPE DETECTION', 'PROXIMITY', 'POSE', 'RISK FUSION',
  'DECISION ENGINE', 'ALERT', 'INCIDENT LOGGED',
]

// Processing pipeline — mirrors the real backend data flow
export default function PipelineFlow() {
  return (
    <div className="card p-4">
      <div className="card-title mb-3">PROCESSING PIPELINE</div>
      <div className="flex items-stretch gap-1 overflow-x-auto">
        {STEPS.map((s, i) => (
          <div key={s} className="flex items-center gap-1">
            <div className={`px-2.5 py-1.5 rounded text-[9px] font-bold tracking-wider whitespace-nowrap border ${
              i >= 4 ? 'bg-blue-600/10 border-blue-500/40 text-blue-300'
                     : 'bg-navy-900 border-navy-600 text-slate-400'}`}>
              {s}
            </div>
            {i < STEPS.length - 1 && <span className="text-slate-600 text-[9px]">→</span>}
          </div>
        ))}
      </div>
    </div>
  )
}
