import { useEffect, useMemo, useState } from 'react'

const PHASE_ORDER = ['observe', 'plan', 'act', 'verify', 'reason']
const PHASE_LABELS = {
  observe: 'Observe',
  plan: 'Plan',
  act: 'Act',
  verify: 'Verify',
  reason: 'Reason',
}
const STATUS_LABEL = {
  running: 'Running',
  completed: 'Completed',
  interrupted: 'Interrupted',
  failed: 'Failed',
}

function ToolExecutionCard({ tool, index }) {
  const [openArgs, setOpenArgs] = useState(false)
  const [openResult, setOpenResult] = useState(false)
  const statusClass = tool.status === 'failed' ? 'failed' : tool.status === 'running' ? 'running' : 'success'
  const isDataSummary = tool.toolName === 'get_data_summary' && tool.result && typeof tool.result === 'object'
  const summary = isDataSummary && tool.result.summary && typeof tool.result.summary === 'object' ? tool.result.summary : null
  const numericKeys = summary?.numeric_fields && typeof summary.numeric_fields === 'object' ? Object.keys(summary.numeric_fields) : []
  const categoricalKeys = summary?.categorical_fields && typeof summary.categorical_fields === 'object' ? Object.keys(summary.categorical_fields) : []
  return (
    <div className="iter-tool-card">
      <div className="iter-tool-header">
        <div className="iter-tool-left">
          <span className={`iter-tool-dot ${statusClass}`} />
          <span className="iter-tool-title">{tool.toolName || `Tool #${index + 1}`}</span>
          <span className={`iter-tool-status ${statusClass}`}>{tool.status}</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <button type="button" className="iter-tool-toggle-btn" onClick={() => setOpenResult((v) => !v)}>
            {openResult ? 'Hide result' : 'Show result'}
          </button>
          <button type="button" className="iter-tool-toggle-btn" onClick={() => setOpenArgs((v) => !v)}>
            {openArgs ? 'Hide args' : 'Show args'}
          </button>
        </div>
      </div>
      {tool.resultPreview ? (
        <div className="iter-tool-result-preview">{tool.resultPreview}</div>
      ) : null}
      {openResult && (
        <div className="iter-tool-args">
          {isDataSummary && summary ? (
            <div className="iter-summary-grid">
              <div className="iter-summary-item">
                <span className="iter-tool-subtitle">Rows</span>
                <span className="iter-summary-value">{Number.isFinite(summary.count) ? summary.count : '--'}</span>
              </div>
              <div className="iter-summary-item">
                <span className="iter-tool-subtitle">Numeric fields</span>
                <span className="iter-summary-value">{numericKeys.length}</span>
              </div>
              <div className="iter-summary-item">
                <span className="iter-tool-subtitle">Categorical fields</span>
                <span className="iter-summary-value">{categoricalKeys.length}</span>
              </div>
              <div className="iter-summary-item">
                <span className="iter-tool-subtitle">Top numeric</span>
                <span className="iter-summary-value">{numericKeys.slice(0, 4).join(', ') || '--'}</span>
              </div>
              <div className="iter-summary-item">
                <span className="iter-tool-subtitle">Top categorical</span>
                <span className="iter-summary-value">{categoricalKeys.slice(0, 4).join(', ') || '--'}</span>
              </div>
            </div>
          ) : null}
          <div className="iter-tool-subtitle">Result</div>
          <pre className="font-mono">{JSON.stringify(tool.result || {}, null, 2)}</pre>
        </div>
      )}
      {openArgs && (
        <div className="iter-tool-args">
          <div className="iter-tool-subtitle">Args</div>
          <pre className="font-mono">{JSON.stringify(tool.args || {}, null, 2)}</pre>
        </div>
      )}
    </div>
  )
}

function PhaseProgress({ phases, activePhase, selectedPhase, onSelectPhase }) {
  return (
    <div className="iter-phase-strip">
      {PHASE_ORDER.map((phase, idx) => {
        const status = phases?.[phase]?.status || 'pending'
        const cls = status === 'completed' ? 'done' : activePhase === phase ? 'active' : 'pending'
        return (
          <div className="iter-phase-item-wrap" key={phase}>
            <button
              type="button"
              className={`iter-phase-item ${phase} ${cls} ${selectedPhase === phase ? 'selected' : ''}`}
              onClick={() => onSelectPhase?.(phase)}
            >
              <span className="iter-phase-dot" />
              <span>{PHASE_LABELS[phase]}</span>
            </button>
            {idx < PHASE_ORDER.length - 1 && <div className="iter-phase-link" />}
          </div>
        )
      })}
    </div>
  )
}

function SummaryList({ title, lines }) {
  if (!lines?.length) return null
  return (
    <div className="iter-block">
      <div className="iter-block-title">{title}</div>
      <ul className="iter-list">
        {lines.map((line, i) => <li key={`${title}-${i}`}>{line}</li>)}
      </ul>
    </div>
  )
}

export default function IterationCard({ iterationData, id }) {
  const {
    iteration,
    status = 'running',
    mode,
    activePhase,
    phases,
    tools = [],
    observationLines = [],
    planLines = [],
    verifyLines = [],
    reasoningLines = [],
    finalResponse = '',
    stopReason,
  } = iterationData || {}

  const statusText = STATUS_LABEL[status] || status
  const reasonLines = useMemo(
    () => reasoningLines.filter(Boolean).slice(-6),
    [reasoningLines],
  )
  const [selectedPhase, setSelectedPhase] = useState(activePhase || 'observe')

  useEffect(() => {
    if (activePhase && PHASE_ORDER.includes(activePhase)) {
      setSelectedPhase(activePhase)
    }
  }, [activePhase, iteration])

  const normalizedSelectedPhase = PHASE_ORDER.includes(selectedPhase) ? selectedPhase : 'observe'

  const hasActContent = tools.length > 0
  const hasObserveContent = observationLines.length > 0
  const hasPlanContent = planLines.length > 0
  const hasVerifyContent = verifyLines.length > 0
  const hasReasonContent = reasonLines.length > 0

  function EmptyPhase({ text }) {
    return (
      <div className="iter-block">
        <div className="iter-block-title">{PHASE_LABELS[normalizedSelectedPhase]} Details</div>
        <div className="iter-empty">{text}</div>
      </div>
    )
  }

  return (
    <section id={id} className="iteration-card">
      <header className="iteration-header">
        <div>
          <div className="iteration-title">Iteration {iteration}</div>
          {mode && <div className="iteration-mode">{mode}</div>}
        </div>
        <span className={`iteration-status ${status}`}>{statusText}</span>
      </header>

      <PhaseProgress
        phases={phases}
        activePhase={activePhase}
        selectedPhase={normalizedSelectedPhase}
        onSelectPhase={setSelectedPhase}
      />

      {normalizedSelectedPhase === 'observe' ? (
        hasObserveContent ? <SummaryList title="Observation Summary" lines={observationLines} /> : <EmptyPhase text="No observation details yet." />
      ) : null}

      {normalizedSelectedPhase === 'plan' ? (
        hasPlanContent ? <SummaryList title="Plan Summary" lines={planLines} /> : <EmptyPhase text="No planning details yet." />
      ) : null}

      {normalizedSelectedPhase === 'act' ? (
        hasActContent ? (
          <div className="iter-block">
            <div className="iter-block-title">Action Trace</div>
            <div className="iter-tool-list">
              {tools.map((tool, idx) => (
                <ToolExecutionCard key={tool.id || `${tool.toolName}-${idx}`} tool={tool} index={idx} />
              ))}
            </div>
          </div>
        ) : <EmptyPhase text="No tool action in this iteration." />
      ) : null}

      {normalizedSelectedPhase === 'verify' ? (
        hasVerifyContent ? <SummaryList title="Verification" lines={verifyLines} /> : <EmptyPhase text="No verification details yet." />
      ) : null}

      {normalizedSelectedPhase === 'reason' ? (
        <>
          {hasReasonContent ? <SummaryList title="Reasoning" lines={reasonLines} /> : <EmptyPhase text="No reasoning details yet." />}
          <div className="iter-block">
            <div className="iter-block-title">Final Response</div>
            <div className="iter-final-response">
              {String(finalResponse || '').trim() || 'No direct final response yet.'}
            </div>
          </div>
        </>
      ) : null}

      {(stopReason || status !== 'running') && (
        <footer className="iter-footer">
          <span>Iteration status: {statusText}</span>
          {stopReason ? <span>Stop reason: {stopReason}</span> : null}
        </footer>
      )}
    </section>
  )
}

