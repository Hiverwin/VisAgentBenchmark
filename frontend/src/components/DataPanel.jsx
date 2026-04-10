import { useRef, useState } from 'react'
import { uploadCSV, createSession } from '../api/client.js'
import t from '../locale.js'
import { DEMO_CASES } from '../presets/demoCases.js'
import { useAppStore } from '../state/appStore.js'

const CHART_TYPES = [
  { value: 'scatter',  label: t.scatterPlot },
  { value: 'bar',      label: t.barChart },
  { value: 'line',     label: t.lineChart },
  { value: 'parallel', label: t.parallelCoordinates },
  { value: 'heatmap',  label: t.heatmap },
  { value: 'sankey',   label: t.sankeyDiagram },
]

const ENCODING_FIELDS = {
  scatter:  ['x', 'y', 'color', 'size'],
  bar:      ['x', 'y', 'color'],
  line:     ['x', 'y', 'color'],
  parallel: ['columns', 'color'],
  heatmap:  ['x', 'y', 'color'],
  sankey:   ['source', 'target', 'value'],
}

function ColumnTag({ type, name }) {
  const cls = type === 'numeric' ? 'tag tag-numeric'
    : type === 'datetime' ? 'tag tag-datetime'
    : 'tag tag-categorical'
  return <span className={cls} title={type}>{name}</span>
}

export default function DataPanel({ onSessionCreated }) {
  const fileRef = useRef(null)
  const [dragOver, setDragOver] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [dataset, setDataset] = useState(null)
  const [chartType, setChartType] = useState('scatter')
  const [encoding, setEncoding] = useState({})
  const [width, setWidth] = useState(600)
  const [height, setHeight] = useState(400)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState('')
  const [specJson, setSpecJson] = useState('')
  const [useDirectSpec, setUseDirectSpec] = useState(false)
  const setRunMode = useAppStore((s) => s.setRunMode)
  const setPresetQueryDraft = useAppStore((s) => s.setPresetQueryDraft)

  const colInfo = dataset?.column_info || {}
  const allCols = colInfo.all || []

  function getColType(colName) {
    if ((colInfo.numeric || []).includes(colName)) return 'numeric'
    if ((colInfo.datetime || []).includes(colName)) return 'datetime'
    return 'categorical'
  }

  function handleFile(file) {
    if (!file) return
    setError('')
    setUploading(true)
    setUploadProgress(0)
    uploadCSV(file, (e) => {
      if (e.lengthComputable) setUploadProgress(Math.round(e.loaded / e.total * 100))
    })
      .then((data) => {
        setDataset(data)
        setEncoding({})
        setChartType('scatter')
      })
      .catch((e) => setError(e.message))
      .finally(() => { setUploading(false); setUploadProgress(0) })
  }

  function autoFill() {
    if (!dataset) return
    const { numeric = [], categorical = [], datetime = [] } = colInfo
    const auto = {}
    if (chartType === 'scatter') {
      auto.x = numeric[0] || allCols[0] || ''
      auto.y = numeric[1] || numeric[0] || allCols[1] || ''
      if (categorical[0]) auto.color = categorical[0]
    } else if (chartType === 'bar') {
      auto.x = categorical[0] || allCols[0] || ''
      auto.y = numeric[0] || allCols[1] || ''
      if (categorical[1]) auto.color = categorical[1]
    } else if (chartType === 'line') {
      auto.x = datetime[0] || categorical[0] || allCols[0] || ''
      auto.y = numeric[0] || allCols[1] || ''
      if (categorical[0] && auto.x !== categorical[0]) auto.color = categorical[0]
    } else if (chartType === 'parallel') {
      auto.columns = numeric.slice(0, Math.min(5, numeric.length))
    } else if (chartType === 'heatmap') {
      auto.x = categorical[0] || allCols[0] || ''
      auto.y = categorical[1] || allCols[1] || ''
      auto.color = numeric[0] || ''
    } else if (chartType === 'sankey') {
      auto.source = categorical[0] || allCols[0] || ''
      auto.target = categorical[1] || allCols[1] || ''
    }
    setEncoding(auto)
  }

  async function generate() {
    setError('')
    setGenerating(true)
    try {
      let body
      if (useDirectSpec) {
        body = { spec: JSON.parse(specJson) }
      } else {
        body = {
          dataset_id: dataset.dataset_id,
          chart_type: chartType,
          encoding,
          width,
          height,
        }
      }
      const res = await createSession(body)
      onSessionCreated(res)
    } catch (e) {
      setError(e.message)
    } finally {
      setGenerating(false)
    }
  }

  async function applyDemoCase(demoCase) {
    setError('')
    setGenerating(true)
    try {
      const res = await createSession({ spec: demoCase.spec, case_id: demoCase.id })
      onSessionCreated(res)
      setRunMode(demoCase.mode)
      setPresetQueryDraft(demoCase.prompt)
    } catch (e) {
      setError(e.message)
    } finally {
      setGenerating(false)
    }
  }

  const encFields = ENCODING_FIELDS[chartType] || []

  return (
    <div className="flex flex-col overflow-hidden" style={{ height: '100%' }}>
      <div className="panel-header">
        <div className="header-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" width="16" height="16">
            <path d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/>
          </svg>
          <span>{t.dataAndEncoding}</span>
        </div>
      </div>

      <div className="flex flex-col gap-2 overflow-y-auto p-2" style={{ flex: 1 }}>

        {/* mode toggle */}
        <div>
          <div className="section-label">{t.inputMode}</div>
          <div className="mode-toggle">
            <button className={!useDirectSpec ? 'active' : ''} onClick={() => setUseDirectSpec(false)}>{t.csvUpload}</button>
            <button className={useDirectSpec ? 'active' : ''} onClick={() => setUseDirectSpec(true)}>{t.pasteSpec}</button>
          </div>
        </div>

        {useDirectSpec ? (
          <div>
            <div className="section-label">{t.vegaJson}</div>
            <textarea
              className="textarea font-mono"
              style={{ minHeight: 136 }}
              placeholder='{"$schema": "...", "mark": "bar", ...}'
              value={specJson}
              onChange={e => setSpecJson(e.target.value)}
            />
            <div className="text-xs text-muted mt-1" style={{ color: 'var(--text-dim)' }}>{t.pasteSpecSizeHint}</div>
          </div>
        ) : (
          <>
            {/* drop zone */}
            <div>
              <div className="section-label">{t.csvFile}</div>
              <div
                className={`drop-zone ${dragOver ? 'drag-over' : ''}`}
                onClick={() => fileRef.current?.click()}
                onDragOver={e => { e.preventDefault(); setDragOver(true) }}
                onDragLeave={() => setDragOver(false)}
                onDrop={e => { e.preventDefault(); setDragOver(false); handleFile(e.dataTransfer.files[0]) }}
              >
                <input ref={fileRef} type="file" accept=".csv" style={{ display: 'none' }}
                  onChange={e => handleFile(e.target.files[0])} />
                {uploading ? (
                  <div className="flex flex-col items-center gap-2">
                    <div className="spinner" />
                    <span className="text-sm text-muted">{t.uploading} {uploadProgress}%</span>
                  </div>
                ) : dataset ? (
                  <div>
                    <div className="font-semibold" style={{ color: 'var(--accent)' }}>{dataset.filename}</div>
                    <div className="text-sm text-muted mt-1">{dataset.row_count.toLocaleString()} {t.rows} / {allCols.length} {t.cols}</div>
                  </div>
                ) : (
                  <div>
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.5" style={{ margin: '0 auto 6px', display: 'block', opacity: 0.5 }}>
                      <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
                      <polyline points="17 8 12 3 7 8" />
                      <line x1="12" y1="3" x2="12" y2="15" />
                    </svg>
                    <div className="text-sm text-muted">{t.dragDropCsv}</div>
                  </div>
                )}
              </div>
              <div className="text-xs text-muted mt-1" style={{ color: 'var(--text-dim)' }}>{t.uploadSizeHint}</div>
            </div>

            {/* column info */}
            {dataset && (
              <div>
                <div className="section-label">{t.columns}</div>
                <div className="flex gap-1" style={{ flexWrap: 'wrap' }}>
                  {allCols.map(c => <ColumnTag key={c} name={c} type={getColType(c)} />)}
                </div>
              </div>
            )}

            {/* chart type */}
            <div>
              <div className="section-label">{t.chartType}</div>
              <select className="select" value={chartType} onChange={e => { setChartType(e.target.value); setEncoding({}) }}>
                {CHART_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
              </select>
            </div>

            {/* encoding */}
            {dataset && (
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="section-label" style={{ marginBottom: 0 }}>{t.encoding}</span>
                  <button className="btn btn-ghost btn-sm" onClick={autoFill}>{t.autoFill}</button>
                </div>
                <div className="flex flex-col gap-2">
                  {encFields.map(field => (
                    <div key={field}>
                      <label className="text-xs text-muted" style={{ display: 'block', marginBottom: 3 }}>
                        {field.toUpperCase()}
                      </label>
                      {field === 'columns' ? (
                        <select
                          className="select"
                          multiple
                          size={4}
                          value={encoding.columns || []}
                          onChange={e => {
                            const vals = Array.from(e.target.selectedOptions, o => o.value)
                            setEncoding(prev => ({ ...prev, columns: vals }))
                          }}
                        >
                          {allCols.map(c => <option key={c} value={c}>{c}</option>)}
                        </select>
                      ) : (
                        <select
                          className="select"
                          value={encoding[field] || ''}
                          onChange={e => setEncoding(prev => ({ ...prev, [field]: e.target.value || undefined }))}
                        >
                          <option value="">-- {t.none} --</option>
                          {allCols.map(c => <option key={c} value={c}>{c}</option>)}
                        </select>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* size */}
            <div className="flex gap-2">
              <div style={{ flex: 1 }}>
                <label className="section-label">{t.width}</label>
                <input className="input" type="number" value={width} min={200} max={1600}
                  onChange={e => setWidth(+e.target.value)} />
              </div>
              <div style={{ flex: 1 }}>
                <label className="section-label">{t.height}</label>
                <input className="input" type="number" value={height} min={150} max={1200}
                  onChange={e => setHeight(+e.target.value)} />
              </div>
            </div>
          </>
        )}

        {error && <div className="text-danger text-sm">{error}</div>}

        {(() => {
          const needCsv = !useDirectSpec && !dataset
          const needSpec = useDirectSpec && !specJson.trim()
          const canGenerate = !needCsv && !needSpec && !generating
          return (
            <>
              {!canGenerate && !generating && (
                <div className="text-dim text-xs" style={{ marginBottom: 6, lineHeight: 1.4 }}>
                  {t.generateViewHint}
                </div>
              )}
              <button
                className="btn btn-primary w-full"
                disabled={!canGenerate}
                onClick={generate}
                style={{ padding: '10px 14px', fontSize: 13 }}
                title={!canGenerate ? t.generateViewHint : undefined}
              >
                {generating ? (
                  <><div className="spinner" style={{ width: 13, height: 13 }} /> {t.generating}</>
                ) : (
                  <>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" stroke="none">
                      <polygon points="5,3 19,12 5,21" />
                    </svg>
                    {t.generateView}
                  </>
                )}
              </button>
            </>
          )
        })()}

        {/* predefined demo cases */}
        <div className="data-panel-section">
          <div className="section-label">{t.demoCasesTitle}</div>
          <div className="demo-case-list">
            {DEMO_CASES.map((item) => (
              <button
                key={item.id}
                className="demo-case-card"
                onClick={() => applyDemoCase(item)}
                disabled={generating}
              >
                <div className="demo-case-head">
                  <span className="demo-case-title">{item.title}</span>
                  <span className="demo-case-mode">{(item.mode === 'copilot' || item.mode === 'autonomous') ? t.autonomous : t.goalOriented}</span>
                </div>
                <div className="demo-case-subtitle">{item.subtitle}</div>
              </button>
            ))}
          </div>
          <div className="text-xs text-muted mt-1" style={{ color: 'var(--text-dim)', lineHeight: 1.2 }}>
            One click loads chart and starter prompt.
          </div>
        </div>

      </div>
    </div>
  )
}
