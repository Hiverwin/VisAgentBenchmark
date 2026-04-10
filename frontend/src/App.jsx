import { useCallback, useEffect } from 'react'
import DataPanel from './components/DataPanel.jsx'
import ChartCanvas from './components/ChartCanvas.jsx'
import AgentPanel from './components/AgentPanel.jsx'
import InteractionTrajectoryPanel from './components/InteractionTrajectoryPanel.jsx'
import { CenterWorkspace, SideRailPanel, WorkspaceContainer } from './components/layout/PanelPrimitives.jsx'
import { health, listSessions, getSession } from './api/client.js'
import t from './locale.js'
import { useAppStore } from './state/appStore.js'

export default function App() {
  const modelAvailable = useAppStore((s) => s.modelAvailable)
  const sessions = useAppStore((s) => s.sessions)
  const currentSessionId = useAppStore((s) => s.currentSessionId)
  const currentSpec = useAppStore((s) => s.currentSpec)
  const specHistory = useAppStore((s) => s.specHistory)
  const isRunning = useAppStore((s) => s.isRunning)
  const runMode = useAppStore((s) => s.runMode)
  const scrollToIteration = useAppStore((s) => s.scrollToIteration)
  const provenanceRevision = useAppStore((s) => s.provenanceRevision)
  const currentSelection = useAppStore((s) => s.currentSelection)
  const samplingInfo = useAppStore((s) => s.samplingInfo)

  const setModelAvailable = useAppStore((s) => s.setModelAvailable)
  const hydrateSessions = useAppStore((s) => s.hydrateSessions)
  const applySessionCreated = useAppStore((s) => s.applySessionCreated)
  const applySessionSwitched = useAppStore((s) => s.applySessionSwitched)
  const setCurrentSpec = useAppStore((s) => s.setCurrentSpec)
  const appendSpecHistoryItem = useAppStore((s) => s.appendSpecHistoryItem)
  const setSamplingInfo = useAppStore((s) => s.setSamplingInfo)
  const setCurrentSelection = useAppStore((s) => s.setCurrentSelection)
  const setIsRunning = useAppStore((s) => s.setIsRunning)
  const setRunMode = useAppStore((s) => s.setRunMode)
  const setScrollToIteration = useAppStore((s) => s.setScrollToIteration)

  useEffect(() => {
    health()
      .then(d => setModelAvailable(d.model_available))
      .catch(() => setModelAvailable(false))
  }, [])

  useEffect(() => {
    listSessions().then((d) => hydrateSessions(d.sessions || [])).catch(() => {})
  }, [])

  const handleSessionCreated = useCallback(async (res) => {
    applySessionCreated(res)
  }, [])

  const handleSwitchSession = useCallback(async (id) => {
    if (id === currentSessionId) return
    try {
      const state = await getSession(id)
      applySessionSwitched(id, state)
    } catch (e) {
      console.error('Switch session failed', e)
    }
  }, [currentSessionId])

  const handleSpecUpdated = useCallback((spec) => {
    setCurrentSpec(spec)
  }, [])

  const handleSpecHistoryItem = useCallback((item) => {
    appendSpecHistoryItem({
      ...item,
      source: item?.source || 'app_append',
    })
  }, [])

  useEffect(() => {
    setCurrentSelection(null)
  }, [currentSessionId])

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100vh',
      overflow: 'hidden',
      background: 'var(--bg)',
    }}>

      {/* ── Status warning ── */}
      {modelAvailable === false && (
        <div style={{
          background: 'var(--danger-dim)',
          color: 'var(--danger)',
          fontSize: 12,
          padding: '8px 24px',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          borderBottom: '1px solid rgba(239, 68, 68, 0.15)',
          flexShrink: 0,
          fontWeight: 500,
        }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
            <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
          </svg>
          {t.modelApiUnavailable}
        </div>
      )}

      {/* ── Main layout: left / center(top+bottom) / right ── */}
      <WorkspaceContainer>
        {/* left: data panel */}
        <SideRailPanel className="panel-shell-left">
          <DataPanel
            onSessionCreated={handleSessionCreated}
            sessions={sessions}
            currentSessionId={currentSessionId}
            onSwitchSession={handleSwitchSession}
          />
        </SideRailPanel>

        {/* center: top visualization + bottom interaction trajectory */}
        <CenterWorkspace
          top={(
            <div className="panel-content-fill">
            {samplingInfo?.active && (
              <div className="sampling-banner" style={{
                padding: '8px 12px',
                background: 'var(--warning-dim)',
                borderLeft: '3px solid var(--warning)',
                fontSize: 12,
                color: 'var(--text)',
                flexShrink: 0,
              }}>
                <strong>{t.samplingActive}:</strong>{' '}
                {samplingInfo.chart_type === 'sankey_diagram' && samplingInfo.sankey_top_per_layer != null
                  ? t.samplingSankeyLine.replace('{n}', String(samplingInfo.sankey_top_per_layer))
                  : samplingInfo.chart_type === 'parallel_coordinates'
                    ? t.samplingParallelLine
                        .replace('{displayed}', String(samplingInfo.displayed ?? 0))
                        .replace('{total}', String(samplingInfo.total ?? 0))
                        .replace('{max}', String(samplingInfo.max_per_view ?? 0))
                    : t.samplingScatterLine
                        .replace('{displayed}', String(samplingInfo.displayed ?? 0))
                        .replace('{total}', String(samplingInfo.total ?? 0))
                        .replace('{max}', String(samplingInfo.max_per_view ?? 0))}
                <div style={{ marginTop: 4, fontSize: 12, color: 'var(--text-dim)' }}>
                  {t.samplingLimitsSummary}
                </div>
                {(samplingInfo.chart_type === 'scatter_plot' || !samplingInfo.chart_type) && (
                  <div style={{ marginTop: 2, fontSize: 12, color: 'var(--text-dim)' }}>
                    {t.samplingHintZoom}
                  </div>
                )}
              </div>
            )}
            <ChartCanvas
              spec={currentSpec}
              selectionEnabled={true}
              onSelectionChange={setCurrentSelection}
            />
            </div>
          )}
          bottom={(
            <div className="panel-content-fill">
            <InteractionTrajectoryPanel
              sessionId={currentSessionId}
              specHistory={specHistory}
              provenanceRevision={provenanceRevision}
              currentSpec={currentSpec}
              onSelectSpec={handleSpecUpdated}
              onSelectIteration={setScrollToIteration}
            />
            </div>
          )}
        />

        {/* right: agent panel */}
        <SideRailPanel className="panel-shell-right">
          <AgentPanel
            sessionId={currentSessionId}
            onSpecUpdated={handleSpecUpdated}
            onSamplingInfoUpdate={setSamplingInfo}
            onSpecHistoryItem={handleSpecHistoryItem}
            isRunning={isRunning}
            setIsRunning={setIsRunning}
            runMode={runMode}
            setRunMode={setRunMode}
            scrollToIteration={scrollToIteration}
            onScrollToIterationDone={() => setScrollToIteration(null)}
            currentSelection={currentSelection}
            onClearSelection={() => setCurrentSelection(null)}
          />
        </SideRailPanel>
      </WorkspaceContainer>
    </div>
  )
}
