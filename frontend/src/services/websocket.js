// SafeSight AI — WebSocket live updates with automatic reconnect
// Falls back to polling (handled in App.jsx) if the socket temporarily fails.
const WS_URL = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/alerts`

export function connectAlertsWS({ onMessage, onStatus }) {
  let ws = null
  let closedByUser = false
  let retry = 0
  let reconnectTimer = null

  function connect() {
    try {
      ws = new WebSocket(WS_URL)
    } catch (err) {
      onStatus && onStatus('OFFLINE')
      scheduleReconnect()
      return
    }

    ws.onopen = () => {
      retry = 0
      onStatus && onStatus('CONNECTED')
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        onMessage && onMessage(data)
      } catch {
        /* ignore malformed frames */
      }
    }

    ws.onclose = () => {
      onStatus && onStatus('OFFLINE')
      if (!closedByUser) scheduleReconnect()
    }

    ws.onerror = () => { /* onclose follows */ }
  }

  function scheduleReconnect() {
    if (closedByUser) return
    retry = Math.min(retry + 1, 6)
    reconnectTimer = setTimeout(connect, 1000 * retry)
  }

  connect()

  return function close() {
    closedByUser = true
    clearTimeout(reconnectTimer)
    if (ws) { try { ws.close() } catch { /* noop */ } }
  }
}
