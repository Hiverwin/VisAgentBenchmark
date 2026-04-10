import { useEffect, useMemo, useRef, useState } from 'react'
import t from '../locale.js'

const EDGE_COLORS = {
  agent_tool: 'var(--accent)',
  undo: 'var(--accent-purple)',
  reset: '#f0ad4e',
  human_interrupt: 'var(--danger)',
}

const EDGE_LABELS = {
  agent_tool: { text: 'Tool', title: 'Model tool action' },
  undo: { text: 'Undo', title: 'Model undo' },
  reset: { text: 'Reset', title: 'Model reset' },
  human_interrupt: { text: 'Human', title: 'Human interrupt' },
}

function computeLayout(graph) {
  const nodes = Array.isArray(graph?.nodes) ? graph.nodes : []
  const edges = Array.isArray(graph?.edges) ? graph.edges : []
  const byId = new Map(nodes.map(n => [n.id, n]))
  const out = new Map()
  const inc = new Map()
  for (const e of edges) {
    if (!e?.from_id || !e?.to_id) continue
    if (!out.has(e.from_id)) out.set(e.from_id, [])
    out.get(e.from_id).push(e)
    inc.set(e.to_id, (inc.get(e.to_id) || 0) + 1)
  }

  const root = graph?.baseline_node_id || nodes[0]?.id
  const depth = new Map()
  const q = []
  if (root) {
    depth.set(root, 0)
    q.push(root)
  }

  // BFS depth ignoring self-loop interrupts
  while (q.length) {
    const cur = q.shift()
    const d = depth.get(cur) || 0
    const es = out.get(cur) || []
    for (const e of es) {
      if (e.edge_type === 'human_interrupt' && e.from_id === e.to_id) continue
      const nxt = e.to_id
      if (!byId.has(nxt)) continue
      const nd = d + 1
      if (!depth.has(nxt) || nd < depth.get(nxt)) {
        depth.set(nxt, nd)
        q.push(nxt)
      }
    }
  }

  // Group nodes by depth
  const groups = new Map()
  for (const n of nodes) {
    const d = depth.get(n.id)
    if (d == null) continue
    if (!groups.has(d)) groups.set(d, [])
    groups.get(d).push(n)
  }

  // Stable ordering within depth
  for (const [d, arr] of groups.entries()) {
    arr.sort((a, b) => String(a.label || '').localeCompare(String(b.label || '')) || String(a.id).localeCompare(String(b.id)))
    groups.set(d, arr)
  }

  const maxDepth = Math.max(0, ...Array.from(groups.keys()))
  const nodeW = 220
  const nodeH = 42
  const colGap = 90
  const rowGap = 18
  const margin = 24

  const positions = new Map()
  for (let d = 0; d <= maxDepth; d++) {
    const arr = groups.get(d) || []
    for (let i = 0; i < arr.length; i++) {
      positions.set(arr[i].id, {
        x: margin + d * (nodeW + colGap),
        y: margin + i * (nodeH + rowGap),
      })
    }
  }

  const width = margin * 2 + (maxDepth + 1) * nodeW + maxDepth * colGap
  const height = margin * 2 + Math.max(1, ...Array.from(groups.values()).map(a => a.length)) * nodeH
    + Math.max(0, Math.max(0, ...Array.from(groups.values()).map(a => a.length - 1))) * rowGap

  // interrupt counts per node (self-loop edges)
  const interruptCount = new Map()
  for (const e of edges) {
    if (e?.edge_type === 'human_interrupt' && e.from_id && e.from_id === e.to_id) {
      interruptCount.set(e.from_id, (interruptCount.get(e.from_id) || 0) + 1)
    }
  }

  return { nodes, edges, byId, positions, width, height, nodeW, nodeH, interruptCount, root }
}

function stableStringify(value) {
  const seen = new WeakSet()
  function _walk(v) {
    if (v == null) return v
    if (typeof v !== 'object') return v
    if (seen.has(v)) return null
    seen.add(v)
    if (Array.isArray(v)) return v.map(_walk)
    const keys = Object.keys(v).sort()
    const out = {}
    for (const k of keys) out[k] = _walk(v[k])
    return out
  }
  return JSON.stringify(_walk(value))
}

export default function TrajectoryModal({ sessionId, open, onClose, specHistory = [], currentSpec = null, onSelectRecord }) {
  const [graph, setGraph] = useState(null)
  const [recordByHash, setRecordByHash] = useState(new Map())
  const [indexing, setIndexing] = useState(false)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState('')
  const [pos, setPos] = useState({ x: 0, y: 0 })
  const dragRef = useRef({ dragging: false, startX: 0, startY: 0, baseX: 0, baseY: 0 })

  function summarizeValues(values) {
    if (Array.isArray(values)) {
      const n = values.length
      const fields = n > 0 && values[0] && typeof values[0] === 'object'
        ? Object.keys(values[0]).sort()
        : []
      return { __values_summary__: true, count: n, fields }
    }
    return values
  }

  function canonicalizeViewState(spec) {
    if (!spec || typeof spec !== 'object') return {}
    // Deep clone via JSON; drop volatile keys
    const s = JSON.parse(JSON.stringify(spec))
    for (const k of ['current_image', 'images', '_last_render', 'timestamp']) delete s[k]
    const dataObj = s.data
    if (dataObj && typeof dataObj === 'object' && !Array.isArray(dataObj) && 'values' in dataObj) {
      s.data = { ...dataObj, values: summarizeValues(dataObj.values) }
    } else if (Array.isArray(dataObj)) {
      s.data = dataObj.map(d => (d && typeof d === 'object' && 'values' in d) ? ({ ...d, values: summarizeValues(d.values) }) : d)
    }
    return s
  }

  async function sha1Hex(text) {
    const enc = new TextEncoder()
    const buf = enc.encode(text)
    const digest = await crypto.subtle.digest('SHA-1', buf)
    const bytes = Array.from(new Uint8Array(digest))
    return bytes.map(b => b.toString(16).padStart(2, '0')).join('')
  }

  async function refresh() {
    if (!sessionId) return
    setLoading(true)
    setErr('')
    try {
      const res = await fetch(`/api/sessions/${sessionId}`)
      const data = await res.json()
      if (!res.ok) throw new Error(data?.detail || res.statusText)
      setGraph(data?.provenance_graph || null)
    } catch (e) {
      setErr(e.message || String(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!open) return
    refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, sessionId])

  // Build state_hash -> specHistory record map (so clicking behaves exactly like the timeline)
  useEffect(() => {
    if (!open) return
    let cancelled = false
    ;(async () => {
      setIndexing(true)
      try {
        const records = Array.isArray(specHistory) ? [...specHistory] : []
        if (currentSpec) {
          records.push({
            spec_id: `current_${Date.now()}`,
            iteration: null,
            tool_name: 'current',
            spec: currentSpec,
            timestamp: Date.now(),
          })
        }
        const pairs = await Promise.all(records.map(async (rec) => {
          if (!rec?.spec) return [null, null]
          const canon = canonicalizeViewState(rec.spec)
          const payload = stableStringify(canon)
          const h = await sha1Hex(payload)
          return [h, rec]
        }))
        const m = new Map()
        for (const [h, rec] of pairs) {
          if (!h || !rec) continue
          const prev = m.get(h)
          if (!prev || (rec.timestamp || 0) >= (prev.timestamp || 0)) m.set(h, rec)
        }
        if (!cancelled) setRecordByHash(m)
      } finally {
        if (!cancelled) setIndexing(false)
      }
    })()
    return () => { cancelled = true }
  }, [open, specHistory, currentSpec])

  const layout = useMemo(() => computeLayout(graph), [graph])

  function onHeaderDown(e) {
    // Don't start dragging when clicking on buttons/interactive elements in header
    if (e.target?.closest?.('button')) return
    if (e.button !== 0) return
    dragRef.current = {
      dragging: true,
      startX: e.clientX,
      startY: e.clientY,
      baseX: pos.x,
      baseY: pos.y,
    }
    e.preventDefault()
  }

  useEffect(() => {
    function onMove(e) {
      if (!dragRef.current.dragging) return
      const dx = e.clientX - dragRef.current.startX
      const dy = e.clientY - dragRef.current.startY
      setPos({ x: dragRef.current.baseX + dx, y: dragRef.current.baseY + dy })
    }
    function onUp() {
      dragRef.current.dragging = false
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [pos.x, pos.y])

  if (!open) return null

  function handleNodeClick(n) {
    const h = n?.state_hash
    if (!h) return
    const rec = recordByHash.get(h)
    if (rec && typeof onSelectRecord === 'function') {
      onSelectRecord(rec)
      onClose?.()
    }
  }

  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      background: 'rgba(0,0,0,0.35)',
      zIndex: 50,
      display: 'block',
      padding: 24,
    }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose?.() }}
    >
      <div style={{
        position: 'absolute',
        left: '50%',
        top: '50%',
        transform: `translate(calc(-50% + ${pos.x}px), calc(-50% + ${pos.y}px))`,
        width: 'min(1100px, 96vw)',
        height: 'min(700px, 86vh)',
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 14,
        boxShadow: '0 20px 60px rgba(0,0,0,0.35)',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}>
        <div
          onMouseDown={onHeaderDown}
          style={{
          padding: '10px 12px',
          borderBottom: '1px solid var(--border)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 12,
          cursor: 'move',
          userSelect: 'none',
        }}>
          <div style={{ fontWeight: 700, color: 'var(--text)' }}>{t.trajectoryTitle}</div>
          <div className="flex gap-2">
            <button className="btn btn-ghost btn-sm" onClick={refresh} disabled={loading}>{loading ? t.loading : t.refresh}</button>
            <button className="btn btn-ghost btn-sm" onClick={onClose}>{t.close}</button>
          </div>
        </div>

        <div style={{ padding: '10px 12px', borderBottom: '1px solid var(--border)', fontSize: 12, color: 'var(--text-dim)' }}>
          {t.trajectoryLegend}{' '}
          <span style={{ color: EDGE_COLORS.agent_tool, fontWeight: 600 }}>{t.legendTool}</span>,{' '}
          <span style={{ color: EDGE_COLORS.undo, fontWeight: 600 }}>{t.legendUndo}</span>,{' '}
          <span style={{ color: EDGE_COLORS.reset, fontWeight: 600 }}>{t.legendReset}</span>,{' '}
          <span style={{ color: EDGE_COLORS.human_interrupt, fontWeight: 600 }}>{t.legendHumanInterrupt}</span>
          {indexing && (
            <span style={{ marginLeft: 10, color: 'var(--text-dim)' }}>{t.trajectoryIndexing}</span>
          )}
        </div>

        <div style={{ flex: 1, minHeight: 0, overflow: 'auto', background: 'var(--surface2)' }}>
          {err ? (
            <div style={{ padding: 16, color: 'var(--danger)', fontSize: 12 }}>{err}</div>
          ) : !graph ? (
            <div style={{ padding: 16, color: 'var(--text-dim)', fontSize: 12 }}>{t.noTrajectoryYet}</div>
          ) : (
            <svg width={layout.width} height={layout.height} style={{ display: 'block' }}>
              <defs>
                <marker id="trajArrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                  <path d="M 0 0 L 10 5 L 0 10 z" fill="currentColor" />
                </marker>
                <marker id="trajArrowRed" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                  <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--danger)" />
                </marker>
              </defs>
              {/* edges */}
              {layout.edges.map((e) => {
                const a = layout.positions.get(e.from_id)
                const b = layout.positions.get(e.to_id)
                if (!a || !b) return null
                const isSelfLoop = e.edge_type === 'human_interrupt' && e.from_id === e.to_id
                const x1 = a.x + layout.nodeW
                const y1 = a.y + layout.nodeH / 2
                const x2 = b.x
                const y2 = b.y + layout.nodeH / 2
                const stroke = EDGE_COLORS[e.edge_type] || 'var(--border-strong)'
                const label = EDGE_LABELS[e.edge_type]?.text || ''
                const title = EDGE_LABELS[e.edge_type]?.title || e.edge_type

                // self-loop (human interrupt) is rendered on the node itself to avoid being covered by node rect
                if (isSelfLoop) return null

                const mx = (x1 + x2) / 2
                const d = `M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`
                return (
                  <g key={e.id || `${e.from_id}-${e.to_id}-${e.timestamp}`}>
                    <title>{title}</title>
                    <path
                      d={d}
                      fill="none"
                      stroke={stroke}
                      strokeWidth="2"
                      opacity="0.9"
                      style={{ color: stroke }}
                      markerEnd="url(#trajArrow)"
                    />
                    {label && (
                      <>
                        <rect x={mx - 22} y={((y1 + y2) / 2) - 9} width="44" height="16" rx="8" fill="rgba(255,255,255,0.82)" stroke="rgba(0,0,0,0.08)" />
                        <text x={mx} y={((y1 + y2) / 2) + 3} fontSize="10" fontWeight="800" textAnchor="middle" fill="var(--text)">{label}</text>
                      </>
                    )}
                  </g>
                )
              })}

              {/* nodes */}
              {layout.nodes.map((n) => {
                const p = layout.positions.get(n.id)
                if (!p) return null
                const isBaseline = n.id === layout.root
                const interrupts = layout.interruptCount.get(n.id) || 0
                const label = String(n.label || (isBaseline ? 'baseline' : 'state'))
                const clickable = !indexing && n?.state_hash && recordByHash.has(n.state_hash)
                return (
                  <g
                    key={n.id}
                    transform={`translate(${p.x}, ${p.y})`}
                    onClick={() => clickable && handleNodeClick(n)}
                    style={{ cursor: clickable ? 'pointer' : 'default' }}
                  >
                    <rect x="0" y="0" width={layout.nodeW} height={layout.nodeH} rx="10"
                      fill="var(--surface)"
                      stroke={isBaseline ? 'var(--accent)' : 'var(--border)'}
                      strokeWidth={isBaseline ? 2 : 1}
                      opacity={clickable ? 1 : 0.75}
                    />
                    <text x="12" y="18" fontSize="12" fontWeight="700" fill="var(--text)">
                      {label.length > 26 ? `${label.slice(0, 26)}…` : label}
                    </text>
                    <text x="12" y="34" fontSize="10" fill="var(--text-dim)">
                      {n.state_hash ? `hash ${String(n.state_hash).slice(0, 8)}` : ''}
                    </text>
                    {interrupts > 0 && (
                      <g>
                        {/* human interrupt loop icon */}
                        <path
                          d={`M ${layout.nodeW - 54} 10 C ${layout.nodeW - 24} 0, ${layout.nodeW - 18} 26, ${layout.nodeW - 46} 26`}
                          fill="none"
                          stroke="var(--danger)"
                          strokeWidth="2"
                          strokeDasharray="4 3"
                          markerEnd="url(#trajArrowRed)"
                          opacity="0.95"
                        />
                        <rect x={layout.nodeW - 68} y="10" width="46" height="14" rx="7" fill="rgba(239,68,68,0.14)" stroke="rgba(239,68,68,0.45)" />
                        <text x={layout.nodeW - 45} y="21" fontSize="10" fontWeight="800" textAnchor="middle" fill="var(--danger)">Human</text>
                        <text x={layout.nodeW - 14} y="22" fontSize="10" fontWeight="800" textAnchor="end" fill="var(--danger)">{interrupts}×</text>
                      </g>
                    )}
                  </g>
                )
              })}
            </svg>
          )}
        </div>
      </div>
    </div>
  )
}

