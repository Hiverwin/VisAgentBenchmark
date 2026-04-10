import { useEffect, useMemo, useRef, useState } from 'react'
import t from '../locale.js'

const EDGE_COLORS = {
  baseline: 'var(--border-strong)',
  agent_tool: 'var(--accent)',
  continue: 'var(--accent)',
  branch: '#7b4cb8',
  human_interrupt: '#7b4cb8',
  jump_back: 'var(--warning)',
  reset: 'var(--warning)',
  undo: 'var(--warning)',
}

const ACTION_COLORS = {
  baseline: 'var(--text-dim)',
  tool_call: 'var(--accent)',
  reset: 'var(--warning)',
  undo: 'var(--warning)',
  user_query: '#7b4cb8',
  answer: 'var(--success)',
  clarify: 'var(--accent-purple)',
}

function computeLayout(graph) {
  const nodes = Array.isArray(graph?.nodes) ? [...graph.nodes] : []
  const edges = Array.isArray(graph?.edges) ? [...graph.edges] : []
  nodes.sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0))
  edges.sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0))

  const byId = new Map(nodes.map((n) => [n.id, n]))
  const out = new Map()
  for (const e of edges) {
    if (!e?.from_id || !e?.to_id) continue
    if (!out.has(e.from_id)) out.set(e.from_id, [])
    out.get(e.from_id).push(e)
  }

  const root = graph?.baseline_node_id || nodes[0]?.id
  const depth = new Map()
  const q = []
  if (root) {
    depth.set(root, 0)
    q.push(root)
  }

  while (q.length) {
    const cur = q.shift()
    const d = depth.get(cur) || 0
    for (const e of out.get(cur) || []) {
      if (e.edge_type === 'jump_back' || e.edge_type === 'reset' || e.edge_type === 'undo') continue
      if (!byId.has(e.to_id)) continue
      const nd = d + 1
      if (!depth.has(e.to_id) || nd < depth.get(e.to_id)) {
        depth.set(e.to_id, nd)
        q.push(e.to_id)
      }
    }
  }

  const groups = new Map()
  for (const n of nodes) {
    const d = depth.get(n.id)
    if (d == null) continue
    if (!groups.has(d)) groups.set(d, [])
    groups.get(d).push(n)
  }
  for (const [d, arr] of groups.entries()) {
    arr.sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0))
    groups.set(d, arr)
  }

  const maxDepth = Math.max(0, ...Array.from(groups.keys()))
  const nodeW = 190
  const nodeH = 40
  const colGap = 52
  const rowGap = 18
  const margin = 16
  const positions = new Map()
  for (let d = 0; d <= maxDepth; d += 1) {
    const arr = groups.get(d) || []
    for (let i = 0; i < arr.length; i += 1) {
      positions.set(arr[i].id, {
        x: margin + d * (nodeW + colGap),
        y: margin + i * (nodeH + rowGap),
      })
    }
  }

  const width = margin * 2 + (maxDepth + 1) * nodeW + maxDepth * colGap
  const maxRows = Math.max(1, ...Array.from(groups.values()).map((a) => a.length))
  const height = margin * 2 + maxRows * nodeH + Math.max(0, maxRows - 1) * rowGap
  return { nodes, edges, positions, width, height, nodeW, nodeH, root }
}

function resolveSpecRecordForNode(node, specHistory, currentSpec, currentNodeId) {
  const list = Array.isArray(specHistory) ? specHistory : []
  if (!list.length) {
    return currentSpec && node.id === currentNodeId ? { spec: currentSpec } : null
  }
  const iteration = Number.isFinite(node.iteration) ? node.iteration : null
  const tool = String(node.tool_name || '')

  let candidates = iteration == null ? list.slice() : list.filter((r) => Number.isFinite(r.iteration) && r.iteration === iteration)
  if (tool) {
    const byTool = candidates.filter((r) => String(r.tool_name || '') === tool)
    if (byTool.length) candidates = byTool
  }
  if (!candidates.length && iteration != null) {
    candidates = list.filter((r) => Number.isFinite(r.iteration) && r.iteration <= iteration)
  }
  if (!candidates.length && node.action_type === 'baseline') {
    candidates = list.filter((r) => String(r.tool_name || '') === 'baseline')
  }
  if (!candidates.length && node.id === currentNodeId && currentSpec) {
    return { spec: currentSpec, spec_id: 'current_fallback', iteration }
  }
  if (!candidates.length) return null
  candidates.sort((a, b) => (b.timestamp || 0) - (a.timestamp || 0))
  return candidates[0]
}

function createTrajectorySteps(graph, specHistory, currentSpec) {
  const nodes = Array.isArray(graph?.nodes) ? [...graph.nodes] : []
  const edges = Array.isArray(graph?.edges) ? [...graph.edges] : []
  nodes.sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0))
  edges.sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0))

  const incomingEdgeByNode = new Map()
  for (const e of edges) {
    incomingEdgeByNode.set(e.to_id, e)
  }

  const nodeSteps = nodes.map((node) => {
    const incoming = incomingEdgeByNode.get(node.id) || null
    const specRecord = resolveSpecRecordForNode(node, specHistory, currentSpec, graph?.current_node_id)
    return {
      kind: 'node',
      node,
      incoming,
      specRecord,
      key: node.id,
      displayTool: node.tool_name || node.action_type || 'state',
      displayMessage: node.message_preview || '',
      iteration: Number.isFinite(node.iteration) ? node.iteration : null,
      current: node.id === graph?.current_node_id,
    }
  })
  const byId = new Map(nodes.map((n) => [n.id, n]))
  const jumpSteps = edges
    .filter((e) => e.edge_type === 'jump_back' || e.edge_type === 'reset' || e.edge_type === 'undo')
    .map((e) => {
      const source = byId.get(e.from_id)
      const target = byId.get(e.to_id)
      const jumpType = e.jump_type && e.jump_type !== 'none' ? e.jump_type : (e.semantic_type || e.edge_type || 'jump_back')
      return {
        kind: 'jump',
        key: `jump-${e.id}`,
        edge: e,
        source,
        target,
        timestamp: e.timestamp || 0,
        displayTool: jumpType,
        displayMessage: e.message_preview || `${jumpType} -> ${target?.tool_name || target?.label || e.to_id}`,
        iteration: Number.isFinite(e.iteration) ? e.iteration : null,
      }
    })
  const merged = [...nodeSteps, ...jumpSteps]
  merged.sort((a, b) => {
    const ta = a.kind === 'node' ? (a.node.timestamp || 0) : (a.timestamp || 0)
    const tb = b.kind === 'node' ? (b.node.timestamp || 0) : (b.timestamp || 0)
    return ta - tb
  })
  return merged
}

function edgeStyle(edgeType) {
  if (edgeType === 'jump_back' || edgeType === 'reset' || edgeType === 'undo') {
    return { strokeWidth: 1.8, strokeDasharray: '4 3' }
  }
  if (edgeType === 'branch' || edgeType === 'human_interrupt') {
    return { strokeWidth: 1.5, strokeDasharray: '3 2' }
  }
  return { strokeWidth: 1.4, strokeDasharray: undefined }
}

function clampZoom(v) {
  if (!Number.isFinite(v)) return 1
  return Math.max(0.5, Math.min(2.4, v))
}

export default function InteractionTrajectoryPanel({
  sessionId,
  specHistory = [],
  provenanceRevision = 0,
  currentSpec = null,
  onSelectSpec,
  onSelectIteration,
}) {
  const [graph, setGraph] = useState(null)
  const [selectedNodeId, setSelectedNodeId] = useState(null)
  const [selectedEdgeId, setSelectedEdgeId] = useState(null)
  const [hoveredStep, setHoveredStep] = useState(null)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState('')
  const [zoom, setZoom] = useState(1)
  const [nodeOffsets, setNodeOffsets] = useState({})
  const graphViewportRef = useRef(null)
  const panRef = useRef({ dragging: false, sx: 0, sy: 0, sl: 0, st: 0 })
  const dragNodeRef = useRef(null)
  const lastAutoCenteredNodeRef = useRef(null)

  useEffect(() => {
    if (!sessionId) {
      setGraph(null)
      return
    }
    let cancelled = false
    ;(async () => {
      setLoading(true)
      setErr('')
      try {
        const res = await fetch(`/api/sessions/${sessionId}`)
        const data = await res.json()
        if (!res.ok) throw new Error(data?.detail || res.statusText)
        if (!cancelled) setGraph(data?.provenance_graph || null)
      } catch (e) {
        if (!cancelled) setErr(e.message || String(e))
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [sessionId, specHistory.length, provenanceRevision])

  const layout = useMemo(() => computeLayout(graph), [graph])
  const steps = useMemo(() => createTrajectorySteps(graph, specHistory, currentSpec), [graph, specHistory, currentSpec])
  const scaledWidth = Math.max(200, layout.width * zoom)
  const scaledHeight = Math.max(160, layout.height * zoom)

  function sanitizeTrajectoryLabel(value) {
    const raw = String(value || '').trim()
    if (!raw) return raw
    if (raw.toLowerCase() === 'baseline') return 'initial'
    return raw.replace(/\biter\b/gi, 'step')
  }

  function nodePos(nodeId) {
    const p = layout.positions.get(nodeId)
    if (!p) return null
    const o = nodeOffsets[nodeId] || { x: 0, y: 0 }
    return { x: p.x + o.x, y: p.y + o.y }
  }

  function selectStep(step) {
    if (!step) return
    if (step.kind === 'jump') {
      setSelectedEdgeId(step.edge?.id || null)
      setSelectedNodeId(step.target?.id || null)
      if (onSelectIteration && Number.isFinite(step.iteration)) onSelectIteration(step.iteration)
      const targetNodeStep = steps.find((s) => s.kind === 'node' && s.node.id === step.target?.id)
      if (targetNodeStep?.specRecord?.spec && onSelectSpec) onSelectSpec(targetNodeStep.specRecord.spec)
      return
    }
    const node = step.node
    setSelectedNodeId(node.id)
    setSelectedEdgeId(null)
    if (onSelectIteration && Number.isFinite(step.iteration)) onSelectIteration(step.iteration)
    if (step.specRecord?.spec && onSelectSpec) onSelectSpec(step.specRecord.spec)
  }

  function centerOnCurrentNode() {
    if (!graphViewportRef.current || !graph?.current_node_id) return
    const pos = nodePos(graph.current_node_id)
    if (!pos) return
    const viewport = graphViewportRef.current
    viewport.scrollLeft = Math.max(0, pos.x * zoom - viewport.clientWidth / 2 + (layout.nodeW * zoom) / 2)
    viewport.scrollTop = Math.max(0, pos.y * zoom - viewport.clientHeight / 2 + (layout.nodeH * zoom) / 2)
  }

  useEffect(() => {
    const nodeId = graph?.current_node_id
    if (!nodeId) return
    if (nodeId === lastAutoCenteredNodeRef.current) return
    lastAutoCenteredNodeRef.current = nodeId
    requestAnimationFrame(() => centerOnCurrentNode())
  }, [graph?.current_node_id, zoom, layout.width, layout.height])

  function fitGraph() {
    if (!graphViewportRef.current || !layout.width || !layout.height) return
    const viewport = graphViewportRef.current
    const z = clampZoom(Math.min(viewport.clientWidth / (layout.width + 40), viewport.clientHeight / (layout.height + 40)))
    setZoom(z)
    requestAnimationFrame(() => {
      viewport.scrollLeft = Math.max(0, (layout.width * z - viewport.clientWidth) / 2)
      viewport.scrollTop = Math.max(0, (layout.height * z - viewport.clientHeight) / 2)
    })
  }

  function onWheelZoom(e) {
    if (!e.ctrlKey) return
    e.preventDefault()
    const next = clampZoom(zoom + (e.deltaY > 0 ? -0.08 : 0.08))
    setZoom(next)
  }

  function startPan(e) {
    if (!graphViewportRef.current) return
    if (e.button !== 0) return
    if (dragNodeRef.current) return
    panRef.current = {
      dragging: true,
      sx: e.clientX,
      sy: e.clientY,
      sl: graphViewportRef.current.scrollLeft,
      st: graphViewportRef.current.scrollTop,
    }
    graphViewportRef.current.style.cursor = 'grabbing'
  }

  function movePan(e) {
    if (dragNodeRef.current) {
      const dr = dragNodeRef.current
      const dx = (e.clientX - dr.sx) / zoom
      const dy = (e.clientY - dr.sy) / zoom
      if (Math.abs(dx) > 1 || Math.abs(dy) > 1) dr.moved = true
      setNodeOffsets((prev) => ({
        ...prev,
        [dr.nodeId]: {
          x: dr.ox + dx,
          y: dr.oy + dy,
        },
      }))
      return
    }
    if (!panRef.current.dragging || !graphViewportRef.current) return
    const dx = e.clientX - panRef.current.sx
    const dy = e.clientY - panRef.current.sy
    graphViewportRef.current.scrollLeft = panRef.current.sl - dx
    graphViewportRef.current.scrollTop = panRef.current.st - dy
  }

  function stopPan() {
    if (!graphViewportRef.current) return
    const dragState = dragNodeRef.current
    if (dragState && !dragState.moved) {
      const nodeStep = steps.find((s) => s.kind === 'node' && s.node.id === dragState.nodeId)
      if (nodeStep) selectStep(nodeStep)
    }
    panRef.current.dragging = false
    dragNodeRef.current = null
    graphViewportRef.current.style.cursor = 'grab'
  }

  function startNodeDrag(e, nodeId) {
    if (e.button !== 0) return
    e.stopPropagation()
    const existing = nodeOffsets[nodeId] || { x: 0, y: 0 }
    dragNodeRef.current = {
      nodeId,
      sx: e.clientX,
      sy: e.clientY,
      ox: existing.x,
      oy: existing.y,
      moved: false,
    }
    if (graphViewportRef.current) graphViewportRef.current.style.cursor = 'grabbing'
  }

  return (
    <div className="flex flex-col overflow-hidden" style={{ height: '100%', background: 'var(--surface)' }}>
      <div className="panel-header">
        <div className="header-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" width="16" height="16">
            <path d="M4 18V8M12 18V6M20 18V10" />
            <circle cx="4" cy="6" r="2" />
            <circle cx="12" cy="4" r="2" />
            <circle cx="20" cy="8" r="2" />
          </svg>
          <span>{t.interactionTrajectory}</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <button className="btn btn-ghost btn-sm" onClick={() => setZoom((z) => clampZoom(z - 0.1))}>-</button>
          <span className="text-xs text-dim" style={{ minWidth: 40, textAlign: 'center' }}>{Math.round(zoom * 100)}%</span>
          <button className="btn btn-ghost btn-sm" onClick={() => setZoom((z) => clampZoom(z + 0.1))}>+</button>
          <button className="btn btn-ghost btn-sm" onClick={fitGraph}>Fit</button>
          <button className="btn btn-ghost btn-sm" onClick={() => setNodeOffsets({})}>Reset layout</button>
          <button className="btn btn-ghost btn-sm" onClick={centerOnCurrentNode} disabled={!graph?.current_node_id}>
            Center current
          </button>
          {loading ? <span className="text-xs text-dim">{t.loading}</span> : null}
        </div>
      </div>

      <div style={{ padding: '10px 12px', borderBottom: '1px solid var(--border)', fontSize: 11, color: 'var(--text-dim)' }}>
        {t.trajectoryLegend}{' '}
        <span style={{ color: EDGE_COLORS.continue, fontWeight: 700 }}>{t.legendTool}</span>,{' '}
        <span style={{ color: EDGE_COLORS.branch, fontWeight: 700 }}>{t.legendHumanInterrupt}</span>,{' '}
        <span style={{ color: EDGE_COLORS.jump_back, fontWeight: 700 }}>{t.legendReset}</span> /{' '}
        <span style={{ color: EDGE_COLORS.jump_back, fontWeight: 700 }}>{t.legendUndo}</span>
      </div>

      <div className="flex flex-col overflow-hidden" style={{ flex: 1, minHeight: 0 }}>
        <div
          ref={graphViewportRef}
          onMouseDown={startPan}
          onMouseMove={movePan}
          onMouseUp={stopPan}
          onMouseLeave={stopPan}
          onWheel={onWheelZoom}
          style={{
            flex: '1 1 0',
            minHeight: 220,
            overflow: 'auto',
            padding: '8px 10px',
            background: 'var(--surface2)',
            borderBottom: '1px solid var(--border)',
            cursor: 'grab',
          }}
        >
          {err ? <div className="text-danger text-sm">{err}</div> : null}
          {!err && (!graph || !layout.nodes.length) ? (
            <div style={{ color: 'var(--text-dim)', fontSize: 12, padding: '8px 0' }}>{t.noTrajectoryYet}</div>
          ) : null}
          {!err && graph && layout.nodes.length > 0 ? (
            <svg width={scaledWidth} height={scaledHeight} style={{ display: 'block' }}>
              <defs>
                <marker id="trajArrowMain" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                  <path d="M 0 0 L 10 5 L 0 10 z" fill="currentColor" />
                </marker>
              </defs>
              <g transform={`scale(${zoom})`}>
              {layout.edges.map((e) => {
                const a = nodePos(e.from_id)
                const b = nodePos(e.to_id)
                if (!a || !b) return null
                if (e.edge_type === 'human_interrupt' && e.from_id === e.to_id) return null
                const x1 = a.x + layout.nodeW
                const y1 = a.y + layout.nodeH / 2
                const x2 = b.x
                const y2 = b.y + layout.nodeH / 2
                const stroke = EDGE_COLORS[e.edge_type] || EDGE_COLORS[e.semantic_type] || 'var(--border-strong)'
                const style = edgeStyle(e.edge_type)
                const isJump = e.edge_type === 'jump_back' || e.edge_type === 'reset' || e.edge_type === 'undo'
                const cx = isJump
                  ? Math.min(x1, x2) - Math.max(50, Math.abs(x1 - x2) * 0.35)
                  : (x1 + x2) / 2
                const d = `M ${x1} ${y1} C ${cx} ${y1}, ${cx} ${y2}, ${x2} ${y2}`
                const edgeSelected = selectedEdgeId && e.id === selectedEdgeId
                return (
                  <g key={e.id || `${e.from_id}-${e.to_id}-${e.timestamp}`}>
                    <path
                      d={d}
                      fill="none"
                      stroke={stroke}
                      strokeWidth={edgeSelected ? style.strokeWidth + 1 : style.strokeWidth}
                      strokeDasharray={style.strokeDasharray}
                      style={{ color: stroke, cursor: 'pointer' }}
                      markerEnd="url(#trajArrowMain)"
                      opacity={edgeSelected ? 1 : 0.95}
                      onClick={(evt) => {
                        evt.stopPropagation()
                        setSelectedEdgeId(e.id || null)
                        const jumpStep = steps.find((s) => s.kind === 'jump' && s.edge?.id === e.id)
                        if (jumpStep) setHoveredStep(jumpStep)
                      }}
                    />
                  </g>
                )
              })}
              {layout.nodes.map((n) => {
                const p = nodePos(n.id)
                if (!p) return null
                const selected = selectedNodeId === n.id
                const current = graph?.current_node_id === n.id
                const action = String(n.action_type || 'tool_call')
                const nodeColor = ACTION_COLORS[action] || 'var(--accent)'
                const title = sanitizeTrajectoryLabel(String(n.tool_name || n.label || action))
                const outgoing = (layout.edges || []).filter((e) => e.from_id === n.id)
                const hasHumanBranch = outgoing.some((e) => e.edge_type === 'branch' || e.semantic_type === 'human_interrupt')
                const resetCount = outgoing.filter((e) => e.edge_type === 'jump_back' && (e.jump_type === 'reset' || e.semantic_type === 'reset')).length
                const undoCount = outgoing.filter((e) => e.edge_type === 'jump_back' && (e.jump_type === 'undo' || e.semantic_type === 'undo')).length
                return (
                  <g
                    key={n.id}
                    transform={`translate(${p.x}, ${p.y})`}
                    onMouseDown={(evt) => startNodeDrag(evt, n.id)}
                    style={{ cursor: 'pointer' }}
                  >
                    <rect
                      x="0"
                      y="0"
                      width={layout.nodeW}
                      height={layout.nodeH}
                      rx="7"
                      fill="var(--surface)"
                      stroke={selected ? 'var(--accent)' : current ? nodeColor : 'var(--border)'}
                      strokeWidth={selected ? 2 : current ? 1.8 : 1}
                    />
                    <circle cx="11" cy="13" r="3.5" fill={nodeColor} />
                    <text x="20" y="16" fontSize="10" fontWeight="700" fill="var(--text)">
                      {title.length > 22 ? `${title.slice(0, 22)}...` : title}
                    </text>
                    {!Number.isFinite(n.iteration) && sanitizeTrajectoryLabel(action) ? (
                      <text x="10" y="30" fontSize="9" fill="var(--text-dim)">
                        {sanitizeTrajectoryLabel(action)}
                      </text>
                    ) : null}
                    {hasHumanBranch ? (
                      <g>
                        <rect x={layout.nodeW - 66} y={4} width={40} height={13} rx={6} fill="rgba(123,76,184,0.16)" stroke="#7b4cb8" />
                        <text x={layout.nodeW - 46} y={13} fontSize="8.5" textAnchor="middle" fill="#7b4cb8" fontWeight="700">Human</text>
                      </g>
                    ) : null}
                    {resetCount > 0 ? (
                      <g>
                        <rect x={layout.nodeW - 24} y={4} width={20} height={13} rx={6} fill="rgba(171,123,53,0.16)" stroke="var(--warning)" />
                        <text x={layout.nodeW - 14} y={13} fontSize="8.5" textAnchor="middle" fill="var(--warning)" fontWeight="700">
                          R
                        </text>
                      </g>
                    ) : null}
                    {undoCount > 0 ? (
                      <g>
                        <rect x={layout.nodeW - 24} y={19} width={20} height={13} rx={6} fill="rgba(171,123,53,0.11)" stroke="var(--warning)" />
                        <text x={layout.nodeW - 14} y={28} fontSize="8.5" textAnchor="middle" fill="var(--warning)" fontWeight="700">
                          U
                        </text>
                      </g>
                    ) : null}
                    {(selected || current) ? (
                      <g>
                        <title>Drag node directly</title>
                      </g>
                    ) : null}
                  </g>
                )
              })}
              </g>
            </svg>
          ) : null}
        </div>

        <div style={{ flex: '0 0 170px', minHeight: 120, overflow: 'hidden', padding: '8px 10px', background: 'var(--surface)' }} />

        <div style={{ borderTop: '1px solid var(--border)', padding: '6px 10px', fontSize: 11, color: 'var(--text-dim)', minHeight: 34 }}>
          {hoveredStep ? (
            hoveredStep.kind === 'jump' ? (
              <span>
                Jump {hoveredStep.edge?.jump_type || hoveredStep.edge?.semantic_type || 'jump_back'} | from {sanitizeTrajectoryLabel(hoveredStep.source?.tool_name || hoveredStep.edge?.from_id)}
                {' '}to {sanitizeTrajectoryLabel(hoveredStep.target?.tool_name || hoveredStep.edge?.to_id)}
              </span>
            ) : (
              <span>
                {sanitizeTrajectoryLabel(hoveredStep.node.action_type)} | {sanitizeTrajectoryLabel(hoveredStep.displayTool)}
                {hoveredStep.node?.branch_id ? ` | branch ${hoveredStep.node.branch_id}` : ''}
                {hoveredStep.node.message_preview ? ` | ${hoveredStep.node.message_preview}` : ''}
              </span>
            )
          ) : (
            <span>Hover to preview details. Click to sync chart view and agent iteration.</span>
          )}
        </div>
      </div>
    </div>
  )
}
