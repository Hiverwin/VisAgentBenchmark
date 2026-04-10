import { create } from 'zustand'

const normalizeSession = (session, fallbackTime) => ({
  session_id: session.session_id,
  chart_type: session.chart_type || '',
  created_at: session.created_at || fallbackTime,
  last_activity: session.last_activity || fallbackTime,
})

const stableSpecKey = (spec) => {
  try {
    return JSON.stringify(spec || {})
  } catch {
    return String(Date.now())
  }
}

const toSpecObject = (entry) => {
  if (entry && typeof entry === 'object' && !Array.isArray(entry) && entry.spec && typeof entry.spec === 'object') {
    return entry.spec
  }
  return entry && typeof entry === 'object' && !Array.isArray(entry) ? entry : null
}

const buildRestoredSpecHistory = (statePayload) => {
  const rawHistory = Array.isArray(statePayload?.spec_history) ? statePayload.spec_history : []
  const currentSpec = statePayload?.current_spec || null
  const items = []
  const seen = new Set()
  const now = Date.now()

  rawHistory.forEach((entry, idx) => {
    const spec = toSpecObject(entry)
    if (!spec) return
    const key = stableSpecKey(spec)
    if (seen.has(key)) return
    seen.add(key)
    const hasMeta = entry && typeof entry === 'object' && !Array.isArray(entry) && entry.spec
    items.push({
      spec_id: hasMeta && entry.spec_id ? entry.spec_id : `restored_${idx + 1}`,
      spec,
      iteration: hasMeta && Number.isFinite(entry.iteration) ? entry.iteration : idx,
      tool_name: hasMeta && entry.tool_name ? entry.tool_name : (idx === 0 ? 'baseline' : 'restored'),
      timestamp: hasMeta && Number.isFinite(entry.timestamp) ? entry.timestamp : now + idx,
      source: hasMeta && entry.source ? entry.source : 'session_restore',
      version_index: idx,
    })
  })

  if (currentSpec && typeof currentSpec === 'object' && !Array.isArray(currentSpec)) {
    const curKey = stableSpecKey(currentSpec)
    if (!seen.has(curKey)) {
      items.push({
        spec_id: `restored_${items.length + 1}`,
        spec: currentSpec,
        iteration: items.length + 1,
        tool_name: 'restored_current',
        timestamp: now + items.length,
        source: 'session_restore_current',
        version_index: items.length,
      })
    }
  }

  return items
}

export const useAppStore = create((set) => ({
  modelAvailable: null,
  sessions: [],
  currentSessionId: null,
  currentSpec: null,
  specHistory: [],
  isRunning: false,
  runMode: 'goal_oriented',
  scrollToIteration: null,
  currentSelection: null,
  samplingInfo: null,
  presetQueryDraft: '',
  specVersionCounter: 0,
  provenanceRevision: 0,

  setModelAvailable: (modelAvailable) => set({ modelAvailable }),
  setSessions: (sessions) => set({ sessions: Array.isArray(sessions) ? sessions : [] }),
  setCurrentSessionId: (currentSessionId) => set({ currentSessionId }),
  setCurrentSpec: (currentSpec) => set({ currentSpec }),
  setSpecHistory: (specHistory) => set({ specHistory: Array.isArray(specHistory) ? specHistory : [] }),
  setIsRunning: (isRunning) => set({ isRunning: !!isRunning }),
  setRunMode: (runMode) => set({ runMode }),
  setScrollToIteration: (scrollToIteration) => set({ scrollToIteration }),
  setCurrentSelection: (currentSelection) => set({ currentSelection }),
  setSamplingInfo: (samplingInfo) => set({ samplingInfo }),
  setPresetQueryDraft: (presetQueryDraft) => set({ presetQueryDraft: presetQueryDraft || '' }),
  clearPresetQueryDraft: () => set({ presetQueryDraft: '' }),
  bumpProvenanceRevision: () => set((state) => ({ provenanceRevision: (state.provenanceRevision || 0) + 1 })),

  hydrateSessions: (sessions) =>
    set(() => ({
      sessions: (sessions || []).map((s) => normalizeSession(s, Date.now())),
    })),

  applySessionCreated: (res) =>
    set((state) => {
      const now = Date.now()
      const sessionId = res.session_id
      const baselineSpec = res.baseline_spec
      const already = state.sessions.some((s) => s.session_id === sessionId)
      return {
        currentSessionId: sessionId,
        currentSpec: baselineSpec,
        samplingInfo: res.sampling_info ?? null,
        currentSelection: null,
        provenanceRevision: 0,
        specVersionCounter: baselineSpec ? 1 : 0,
        specHistory: baselineSpec
          ? [{
              spec_id: 'baseline',
              spec: baselineSpec,
              iteration: 0,
              tool_name: 'baseline',
              timestamp: now,
              source: 'session_created',
              version_index: 0,
            }]
          : [],
        sessions: already
          ? state.sessions
          : [
              {
                session_id: sessionId,
                chart_type: res.chart_type || '',
                created_at: now,
                last_activity: now,
              },
              ...state.sessions,
            ],
      }
    }),

  applySessionSwitched: (sessionId, statePayload) =>
    set(() => {
      const restoredHistory = buildRestoredSpecHistory(statePayload)
      return {
        currentSessionId: sessionId,
        currentSpec: statePayload?.current_spec || null,
        samplingInfo: statePayload?.sampling_info ?? null,
        currentSelection: null,
        scrollToIteration: null,
        provenanceRevision: 0,
        specHistory: restoredHistory,
        specVersionCounter: restoredHistory.length,
      }
    }),

  appendSpecHistoryItem: (item) =>
    set((state) => {
      if (!item || !item.spec || typeof item.spec !== 'object' || Array.isArray(item.spec)) {
        return { specHistory: state.specHistory || [], specVersionCounter: state.specVersionCounter || 0 }
      }
      const prev = state.specHistory || []
      const prevBySpec = new Set(prev.map((p) => stableSpecKey(p.spec)))
      const nextVersion = (state.specVersionCounter || prev.length) + 1
      const normalized = {
        ...item,
        spec_id: item.spec_id || `spec_v${nextVersion}`,
        iteration: Number.isFinite(item.iteration) ? item.iteration : (prev.length > 0 ? prev.length : 0),
        tool_name: item.tool_name || 'tool_update',
        timestamp: Number.isFinite(item.timestamp) ? item.timestamp : Date.now(),
        source: item.source || 'stream_event',
        version_index: Number.isFinite(item.version_index) ? item.version_index : prev.length,
      }
      const normalizedSpecKey = stableSpecKey(normalized.spec)
      if (prev.some((p) => p.spec_id === normalized.spec_id) || prevBySpec.has(normalizedSpecKey)) {
        return { specHistory: prev, specVersionCounter: state.specVersionCounter || prev.length }
      }
      if (normalized.tool_name === 'final' && prev.length > 0) {
        const last = prev[prev.length - 1]
        if (last.tool_name === 'final' && last.iteration === normalized.iteration) {
          return {
            specHistory: [...prev.slice(0, -1), { ...normalized, spec_id: last.spec_id }],
            specVersionCounter: state.specVersionCounter || prev.length,
          }
        }
      }
      return {
        specHistory: [...prev, normalized],
        specVersionCounter: nextVersion,
      }
    }),
}))
