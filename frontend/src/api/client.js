const BASE = '/api'

async function req(path, opts = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...opts.headers },
    ...opts,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(body.detail || res.statusText)
  }
  return res.json()
}

// ---------- health ----------
export const health = () => req('/health')

// ---------- files ----------
export function uploadCSV(file, onProgress) {
  const form = new FormData()
  form.append('file', file)
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${BASE}/files/upload`)
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve(JSON.parse(xhr.responseText))
      else reject(new Error(JSON.parse(xhr.responseText)?.detail || xhr.statusText))
    }
    xhr.onerror = () => reject(new Error('Upload failed'))
    if (onProgress) xhr.upload.onprogress = onProgress
    xhr.send(form)
  })
}

// ---------- sessions ----------
export const listSessions = () => req('/sessions')

export const createSession = (body) =>
  req('/sessions', { method: 'POST', body: JSON.stringify(body) })

export const getSession = (id) => req(`/sessions/${id}`)

export const deleteSession = (id) => req(`/sessions/${id}`, { method: 'DELETE' })

// ---------- session actions ----------
export const resetView = (id) => req(`/sessions/${id}/reset`, { method: 'POST' })

// ---------- trajectory fork (human interrupt) ----------
export const interruptSession = (id, reason = 'interrupt', meta = null) =>
  req(`/sessions/${id}/interrupt`, { method: 'POST', body: JSON.stringify({ reason, meta }) })

/** Cooperative: request pause at next safe point; backend will emit run.paused */
export const pauseRun = (sessionId) =>
  req(`/sessions/${sessionId}/pause`, { method: 'POST' })

/** Cooperative: resume from pause; backend will emit run.resumed and continue */
export const resumeRun = (sessionId) =>
  req(`/sessions/${sessionId}/resume`, { method: 'POST' })

export const getSuggestions = (sessionId) =>
  req(`/sessions/${sessionId}/suggestions`)

export const exportSession = (id) => {
  window.open(`${BASE}/sessions/${id}/export`, '_blank')
}

// ---------- SSE query stream ----------
/**
 * Submit a query and stream SSE events.
 * @param {string} sessionId
 * @param {string} query
 * @param {string} runMode  'cooperative' | 'autonomous'
 * @param {(event: {event: string, data: any}) => void} onEvent
 * @param {{ selection_id: string, selection_type: string, predicates: any[], count: number } | null} [selection]  Brush selection when following up after pause
 * @returns {() => void}  cancel function
 */
export function streamQuery(sessionId, query, runMode, onEvent, selection = null) {
  let cancelled = false
  let controller = new AbortController()
  // UI mode names: goal_oriented / copilot; backend expects cooperative / autonomous (compat kept)
  const mappedMode =
    runMode === 'goal_oriented' ? 'cooperative'
    : runMode === 'copilot' ? 'autonomous'
    : runMode
  const body = { query, run_mode: mappedMode }
  if (selection && selection.selection_id) body.selection = selection
  const normalizeEventMessage = (msg) => {
    if (!msg || typeof msg !== 'object') return null
    const eventName = typeof msg.event === 'string' ? msg.event : null
    if (!eventName) return null
    return {
      event: eventName,
      data: msg.data && typeof msg.data === 'object' ? msg.data : {},
      meta: msg.meta && typeof msg.meta === 'object' ? msg.meta : undefined,
    }
  }

  ;(async () => {
    let res
    try {
      res = await fetch(`${BASE}/sessions/${sessionId}/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: controller.signal,
      })
    } catch (err) {
      // User abort: do not report AbortError as a generic failure
      if (!cancelled && err.name !== 'AbortError') onEvent({ event: 'error', data: { message: err.message } })
      return
    }

    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      onEvent({ event: 'error', data: { message: body.detail || res.statusText } })
      return
    }

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    function processLine(line) {
      if (!line.startsWith('data: ')) return
      const raw = line.slice(6).trim()
      if (!raw || raw === '[DONE]') return
      try {
        const msg = normalizeEventMessage(JSON.parse(raw))
        if (!msg) return
        if (msg.event !== 'ping') onEvent(msg)
      } catch {
        // ignore malformed
      }
    }

    while (!cancelled) {
      let chunk
      try {
        chunk = await reader.read()
      } catch {
        break
      }
      buffer += decoder.decode(chunk.value ?? new Uint8Array(0), { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      for (const line of lines) processLine(line)
      if (chunk.done) {
        if (buffer.trim()) processLine(buffer)
        break
      }
    }
    // Stream end (normal or disconnect): stop loading so UI does not spin forever
    if (!cancelled) onEvent({ event: 'stream.end', data: {} })
  })()

  return () => {
    cancelled = true
    controller.abort()
    onEvent({ event: 'stream.end', data: { cancelled: true } })
  }
}
