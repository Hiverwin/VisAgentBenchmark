export function WorkspaceContainer({ children }) {
  return <div className="workspace-grid">{children}</div>
}

export function SideRailPanel({ children, className = '' }) {
  return <section className={`glass-panel panel-shell side-rail ${className}`.trim()}>{children}</section>
}

export function CenterWorkspace({ top, bottom }) {
  return (
    <section className="center-workspace">
      <div className="glass-panel panel-shell center-top-panel">{top}</div>
      <div className="glass-panel panel-shell center-bottom-panel">{bottom}</div>
    </section>
  )
}
