// SafeSight AI — REST API client
const BASE = '/api'

async function request(path, options = {}) {
  try {
    const res = await fetch(BASE + path, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    })
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
    return await res.json()
  } catch (err) {
    console.error(`API ${path} failed:`, err.message)
    throw err
  }
}

export const api = {
  health: () => request('/health'),
  dashboard: () => request('/dashboard'),
  systemStatus: () => request('/system-status'),
  workers: () => request('/workers'),
  workerDetail: (id) => request(`/workers/${id}`),
  incidents: (filters = {}) => {
    const q = new URLSearchParams()
    Object.entries(filters).forEach(([k, v]) => { if (v) q.set(k, v) })
    const qs = q.toString()
    return request(`/incidents${qs ? '?' + qs : ''}`)
  },
  incidentDetail: (id) => request(`/incidents/${id}`),
  acknowledge: (id) => request(`/incidents/${id}/acknowledge`, { method: 'POST' }),
  resolve: (id) => request(`/incidents/${id}/resolve`, { method: 'POST' }),
  deleteIncident: (id) => request(`/incidents/${id}`, { method: 'DELETE' }),
  analytics: () => request('/analytics'),
  zones: () => request('/zones'),
  createZone: (zone) => request('/zones', { method: 'POST', body: JSON.stringify(zone) }),
  updateZone: (id, zone) => request(`/zones/${id}`, { method: 'PUT', body: JSON.stringify(zone) }),
  deleteZone: (id) => request(`/zones/${id}`, { method: 'DELETE' }),
  demoStart: (scenario = 'crane_approach') =>
    request('/demo/start', { method: 'POST', body: JSON.stringify({ scenario }) }),
  demoReset: () => request('/demo/reset', { method: 'POST' }),
  snapshot: () => request('/snapshot'),
  scenarios: () => request('/demo/scenarios'),
  // real-AI frame inference (optional; graceful fallback)
  detectFrame: async (blob) => {
    const form = new FormData()
    form.append('file', blob, 'frame.jpg')
    const res = await fetch(BASE + '/detect/frame', { method: 'POST', body: form })
    return await res.json()
  },
}

export default api
