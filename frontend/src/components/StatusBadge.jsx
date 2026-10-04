// Shared severity helpers
export const SEV_COLOR = {
  SAFE: '#22c55e', WARNING: '#f59e0b', HIGH: '#f97316', CRITICAL: '#ef4444',
}

export function SevBadge({ severity }) {
  const map = {
    SAFE: 'bg-safe-dim text-safe border border-safe-b',
    WARNING: 'bg-warn-dim text-warn border border-warn-b',
    HIGH: 'bg-danger-dim text-danger border border-danger-b',
    CRITICAL: 'bg-critical-dim text-critical border border-critical-b',
  }
  return <span className={`badge ${map[severity] || map.SAFE}`}>{severity}</span>
}

export function StatusBadge({ status }) {
  const map = {
    OPEN: 'bg-critical-dim text-critical border border-critical-b',
    ACKNOWLEDGED: 'bg-warn-dim text-warn border border-warn-b',
    RESOLVED: 'bg-safe-dim text-safe border border-safe-b',
    AUTO_RESOLVED: 'bg-blue-600/10 text-blue-400 border border-blue-500/40',
  }
  return <span className={`badge ${map[status] || map.OPEN}`}>{String(status).replace('_', ' ')}</span>
}
