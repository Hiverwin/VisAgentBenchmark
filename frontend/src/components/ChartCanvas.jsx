import { useEffect, useMemo, useRef, useState } from 'react'
import vegaEmbed from 'vega-embed'
import t from '../locale.js'

/** True when array looks like inline tabular rows (objects), not scale domains etc. */
function isTabularValuesArray(arr) {
  if (!Array.isArray(arr) || arr.length === 0) return false
  const first = arr[0]
  return first !== null && typeof first === 'object' && !Array.isArray(first)
}

/**
 * Deep clone spec and omit inline data rows for safe display (no raw data.values in the panel).
 * Keeps structure, encodings, urls, and non-tabular `values` (e.g. categorical domains).
 */
function redactInlineDataForSpecDisplay(node) {
  if (node === null || typeof node !== 'object') return node
  if (Array.isArray(node)) return node.map(redactInlineDataForSpecDisplay)
  const out = {}
  for (const [k, v] of Object.entries(node)) {
    if (k === 'values' && Array.isArray(v) && (v.length === 0 || isTabularValuesArray(v))) {
      out[k] = { _omitted: 'inline data rows', rowCount: v.length }
    } else if (k === 'datasets' && v && typeof v === 'object' && !Array.isArray(v)) {
      const ds = {}
      for (const [name, rows] of Object.entries(v)) {
        if (Array.isArray(rows) && (rows.length === 0 || isTabularValuesArray(rows))) {
          ds[name] = { _omitted: 'dataset rows', rowCount: rows.length }
        } else {
          ds[name] = redactInlineDataForSpecDisplay(rows)
        }
      }
      out[k] = ds
    } else {
      out[k] = redactInlineDataForSpecDisplay(v)
    }
  }
  return out
}

function toPositiveNumber(value) {
  const n = Number(value)
  return Number.isFinite(n) && n > 0 ? n : null
}

function resolveBaseSize(spec) {
  const explicitWidth = toPositiveNumber(spec?.width)
  const explicitHeight = toPositiveNumber(spec?.height)
  const viewWidth = toPositiveNumber(spec?.config?.view?.continuousWidth)
  const viewHeight = toPositiveNumber(spec?.config?.view?.continuousHeight)
  return {
    width: explicitWidth ?? viewWidth ?? 700,
    height: explicitHeight ?? viewHeight ?? 420,
  }
}

export default function ChartCanvas({
  spec,
  selectionEnabled = false,
  onSelectionChange,
}) {
  const containerRef = useRef(null)
  const viewRef = useRef(null)
  const [renderError, setRenderError] = useState('')
  const [showSpecJson, setShowSpecJson] = useState(false)
  const onSelectionChangeRef = useRef(onSelectionChange)
  onSelectionChangeRef.current = onSelectionChange

  useEffect(() => {
    if (!selectionEnabled) onSelectionChange?.(null)
  }, [selectionEnabled, onSelectionChange])

  useEffect(() => {
    if (!spec || !containerRef.current) return
    setRenderError('')

    if (viewRef.current) {
      try { viewRef.current.finalize() } catch {}
      viewRef.current = null
    }

    const baseSize = resolveBaseSize(spec)
    const enc = spec.encoding || {}
    const hasXY = enc.x && enc.y
    const embedSpec = {
      ...spec,
      width: baseSize.width,
      height: baseSize.height,
      // Keep native spec size and rely on panel scrolling for overflow.
      autosize: { type: 'pad', contains: 'padding' },
      config: {
        ...(spec.config || {}),
        background: 'transparent',
      },
      ...(selectionEnabled && hasXY && {
        selection: { brush: { type: 'interval' } },
      }),
    }

    vegaEmbed(containerRef.current, embedSpec, {
      actions: false,
      renderer: 'canvas',
    })
      .then((result) => {
        viewRef.current = result.view
        if (!selectionEnabled || !onSelectionChangeRef.current || !hasXY) return
        const view = result.view
        const xField = enc.x?.field ?? 'x'
        const yField = enc.y?.field ?? 'y'
        const data = Array.isArray(spec.data?.values) ? spec.data.values : []
        function emitSelection() {
          try {
            let xMin, xMax, yMin, yMax
            const brush = view.signal('brush')
            if (brush && (Array.isArray(brush) || (brush.x && brush.y))) {
              const xr = Array.isArray(brush) ? brush : brush.x
              const yr = Array.isArray(brush) ? brush : brush.y
              if (xr && yr && xr.length >= 2 && yr.length >= 2) {
                xMin = Math.min(xr[0], xr[1])
                xMax = Math.max(xr[0], xr[1])
                yMin = Math.min(yr[0], yr[1])
                yMax = Math.max(yr[0], yr[1])
              }
            }
            if (xMin == null) {
              const x1 = view.signal('brush_x_1')
              const x2 = view.signal('brush_x_2')
              const y1 = view.signal('brush_y_1')
              const y2 = view.signal('brush_y_2')
              if (x1 != null && x2 != null && y1 != null && y2 != null) {
                xMin = Math.min(x1, x2)
                xMax = Math.max(x1, x2)
                yMin = Math.min(y1, y2)
                yMax = Math.max(y1, y2)
              }
            }
            // Vega-Lite interval selections are often represented in brush_store.
            if (xMin == null) {
              const tupleStore = view.data?.('brush_store')
              const tuple = Array.isArray(tupleStore) && tupleStore.length > 0 ? tupleStore[0] : null
              const fields = tuple?.fields
              const values = tuple?.values
              if (Array.isArray(fields) && Array.isArray(values) && fields.length >= 2 && values.length >= 2) {
                const xVal = values[0]
                const yVal = values[1]
                if (Array.isArray(xVal) && xVal.length >= 2 && Array.isArray(yVal) && yVal.length >= 2) {
                  xMin = Math.min(xVal[0], xVal[1])
                  xMax = Math.max(xVal[0], xVal[1])
                  yMin = Math.min(yVal[0], yVal[1])
                  yMax = Math.max(yVal[0], yVal[1])
                }
              }
            }
            if (xMin == null || xMax == null || yMin == null || yMax == null) {
              onSelectionChangeRef.current?.(null)
              return
            }
            const filtered = data.filter(d => {
              const x = d[xField]
              const y = d[yField]
              if (x == null || y == null) return false
              return x >= xMin && x <= xMax && y >= yMin && y <= yMax
            })
            onSelectionChangeRef.current?.({
              selection_id: `sel_${Date.now()}`,
              selection_type: 'interval',
              predicates: [
                { field: xField, op: 'between', value: [xMin, xMax] },
                { field: yField, op: 'between', value: [yMin, yMax] },
              ],
              count: filtered.length,
              summary: `${xField} ${xMin.toFixed(1)}–${xMax.toFixed(1)}, ${yField} ${yMin.toFixed(1)}–${yMax.toFixed(1)}`,
            })
          } catch {
            onSelectionChangeRef.current?.(null)
          }
        }
        try {
          view.addSignalListener('brush', emitSelection)
        } catch {}
        try {
          view.addSignalListener('brush_x_1', emitSelection)
          view.addSignalListener('brush_x_2', emitSelection)
          view.addSignalListener('brush_y_1', emitSelection)
          view.addSignalListener('brush_y_2', emitSelection)
        } catch {}
        // Fallback trigger for environments where brush signals are not consistently exposed.
        try {
          view.addEventListener('mouseup', emitSelection)
        } catch {}
      })
      .catch((err) => setRenderError(err.message || String(err)))

    return () => {
      if (viewRef.current) {
        try { viewRef.current.finalize() } catch {}
        viewRef.current = null
      }
    }
    // Re-embed when switching from spec view back to chart view.
  }, [spec, selectionEnabled, showSpecJson])

  const specStr = useMemo(() => {
    if (!spec) return ''
    try {
      const clone = JSON.parse(JSON.stringify(spec))
      const redacted = redactInlineDataForSpecDisplay(clone)
      return JSON.stringify(redacted, null, 2)
    } catch {
      return JSON.stringify(spec, null, 2)
    }
  }, [spec])

  return (
    <div className="flex flex-col overflow-hidden" style={{ height: '100%', background: 'var(--surface)' }}>
      {/* toolbar */}
      <div className="panel-header">
        <div className="header-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" width="16" height="16">
            <rect x="3" y="3" width="18" height="18" rx="2" />
            <polyline points="7 14 11 10 15 13 19 8" />
          </svg>
          <span>{t.visualizationCanvas}</span>
        </div>
        {selectionEnabled && spec && (
          <div style={{ fontSize: 11, color: 'var(--accent)', fontWeight: 500 }}>
            {t.selectionModeHint}
          </div>
        )}
        <div className="flex gap-2">
          {spec && (
            <button className="btn btn-ghost btn-sm" onClick={() => setShowSpecJson(v => !v)}>
              {showSpecJson ? (
                <>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <rect x="3" y="3" width="18" height="18" rx="2" />
                    <polyline points="7 14 11 10 15 13 19 8" />
                  </svg>
                  {t.chart}
                </>
              ) : (
                <>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <polyline points="16 18 22 12 16 6" />
                    <polyline points="8 6 2 12 8 18" />
                  </svg>
                  {t.spec}
                </>
              )}
            </button>
          )}
        </div>
      </div>

      {/* main area */}
      <div className="flex flex-col overflow-hidden" style={{ flex: 1, background: 'var(--surface)' }}>
        {showSpecJson ? (
          <pre className="overflow-auto p-3 font-mono text-xs" style={{
            flex: 1,
            overflowX: 'auto',
            overflowY: 'auto',
            whiteSpace: 'pre',
            color: 'var(--text)',
            background: 'var(--surface2)',
          }}>
            {specStr}
          </pre>
        ) : (
          <div
            style={{
              flex: '1 1 0',
              minHeight: 0,
              overflow: 'auto',
              position: 'relative',
            }}
          >
            {!spec ? (
              <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', color: 'var(--text-dim)' }}>
                <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="var(--border-strong)" strokeWidth="0.8" style={{ marginBottom: 16 }}>
                  <rect x="3" y="3" width="18" height="18" rx="2" />
                  <polyline points="7 14 11 10 15 13 19 8" />
                  <circle cx="17" cy="8" r="1.5" fill="var(--accent)" stroke="none" opacity="0.3" />
                </svg>
                <div style={{ fontFamily: "'Inter', sans-serif", fontSize: 12, fontWeight: 600, letterSpacing: '0.04em', color: 'var(--text-dim)' }}>
                  {t.awaitingDataInput}
                </div>
              </div>
            ) : renderError ? (
              <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <div style={{ padding: 16, maxWidth: 500 }}>
                  <div className="font-semibold mb-2" style={{ color: 'var(--danger)' }}>{t.renderError}</div>
                  <pre className="text-xs font-mono" style={{ color: 'var(--text-muted)', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                    {renderError}
                  </pre>
                  <div className="mt-2 text-dim text-xs">{t.viewSpecViaButton}</div>
                </div>
              </div>
            ) : (
              <div ref={containerRef} id="vega-container" style={{
                minWidth: '100%',
                minHeight: '100%',
                width: 'max-content',
                height: 'max-content',
                display: 'flex',
                alignItems: 'flex-start',
                justifyContent: 'center',
                padding: 16,
                boxSizing: 'border-box',
              }} />
            )}
          </div>
        )}
      </div>
    </div>
  )
}
