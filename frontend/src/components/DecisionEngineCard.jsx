import { ArrowDown, Brain, Radar, ScanFace, ShieldCheck, Users, Wind } from 'lucide-react'

// UNIFIED SAFETY DECISION ENGINE — the core innovation visual
// PPE + PROXIMITY + FACING ANGLE + CLOSING SPEED + POSTURE -> RISK FUSION
//   -> ROOT-CAUSE TAG -> EXPLAINABLE ALERT
export default function DecisionEngineCard() {
  const inputs = [
    { icon: ShieldCheck, label: 'PPE', tint: 'text-blue-400 border-blue-500/40 bg-blue-600/10' },
    { icon: Radar, label: 'PROXIMITY', tint: 'text-cyan-400 border-cyan-500/40 bg-cyan-600/10' },
    { icon: ScanFace, label: 'FACING ANGLE', tint: 'text-violet-400 border-violet-500/40 bg-violet-600/10' },
    { icon: Wind, label: 'CLOSING SPEED', tint: 'text-amber-400 border-amber-500/40 bg-amber-600/10' },
    { icon: Users, label: 'POSTURE', tint: 'text-pink-400 border-pink-500/40 bg-pink-600/10' },
  ]
  return (
    <div className="card p-4">
      <div className="card-title mb-3 flex items-center gap-2">
        <Brain className="w-3.5 h-3.5 text-blue-400" /> UNIFIED SAFETY DECISION ENGINE
      </div>
      <div className="flex flex-wrap gap-2 justify-center">
        {inputs.map(({ icon: Icon, label, tint }, i) => (
          <div key={label} className="flex items-center gap-2">
            <div className={`flex items-center gap-1.5 px-2.5 py-2 rounded-md border text-[10px] font-bold tracking-wider ${tint}`}>
              <Icon className="w-3.5 h-3.5" />{label}
            </div>
            {i < inputs.length - 1 && <span className="text-slate-600 font-bold">+</span>}
          </div>
        ))}
      </div>
      <div className="flex justify-center my-2"><ArrowDown className="w-4 h-4 text-slate-500" /></div>
      <div className="grid grid-cols-3 gap-2 text-center">
        <div className="bg-navy-900 border border-navy-600 rounded-md py-2">
          <div className="text-[9px] font-mono text-slate-500 tracking-widest">RISK FUSION</div>
          <div className="text-[10px] text-slate-300 mt-0.5">0–100 SCORE</div>
        </div>
        <div className="bg-navy-900 border border-navy-600 rounded-md py-2">
          <div className="text-[9px] font-mono text-slate-500 tracking-widest">ROOT-CAUSE TAG</div>
          <div className="text-[10px] text-slate-300 mt-0.5">EXPLAINABLE</div>
        </div>
        <div className="bg-navy-900 border border-navy-600 rounded-md py-2">
          <div className="text-[9px] font-mono text-slate-500 tracking-widest">SAFETY DECISION</div>
          <div className="text-[10px] text-slate-300 mt-0.5">ALERT + LOG</div>
        </div>
      </div>
    </div>
  )
}
