// SafeSight AI — WebSocket live updates with automatic reconnect
// Connects directly to backend WebSocket to avoid Vite proxy issues.
// Falls back to polling (handled in App.jsx) if the socket temporarily fails.
const BACKEND_HOST = '127.0.0.1:8000'
const WS_URL = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${BACKEND_HOST}/ws/alerts`

// Unique ID generator for socket instances
let socketInstanceId = 0

export function connectAlertsWS({ onMessage, onStatus }) {
  let ws = null
  let closedByUser = false
  let retry = 0
  let reconnectTimer = null
  const instanceId = ++socketInstanceId

  function connect() {
    try {
      console.log(`[WS CREATE] id=${instanceId} url=${WS_URL}`)
      ws = new WebSocket(WS_URL)
    } catch (err) {
      console.log(`[WS ERROR] id=${instanceId} create failed:`, err)
      onStatus && onStatus('OFFLINE')
      scheduleReconnect()
      return
    }

    ws.onopen = () => {
      console.log(`[WS OPEN] id=${instanceId}`)
      retry = 0
      onStatus && onStatus('CONNECTED')
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        console.log(`[WS MESSAGE] id=${instanceId} type=${data.type}`)
        onMessage && onMessage(data)
      } catch {
        console.log(`[WS MESSAGE] id=${instanceId} parse error`)
        /* ignore malformed frames */
      }
    }

    ws.onclose = (event) => {
      console.log(`[WS CLOSE] id=${instanceId} code=${event.code} reason=${event.reason || 'none'}`)
      onStatus && onStatus('OFFLINE')
      if (!closedByUser) scheduleReconnect()
    }

    ws.onerror = (event) => {
      console.log(`[WS ERROR] id=${instanceId} event=`, event)
    }
  }

  function scheduleReconnect() {
    if (closedByUser) return
    retry = Math.min(retry + 1, 6)
    console.log(`[WS RECONNECT] id=${instanceId} attempt=${retry} delay=${1000 * retry}ms`)
    reconnectTimer = setTimeout(connect, 1000 * retry)
  }

  connect()

  return function close() {
    console.log(`[WS CLEANUP] id=${instanceId}`)
    closedByUser = true
    clearTimeout(reconnectTimer)
    if (ws) { try { ws.close() } catch { /* noop */ } }
  }
}
