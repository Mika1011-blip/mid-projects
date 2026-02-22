import { ThemeToggle } from '../components/ThemeToggle'

type Theme = 'light' | 'dark'

export function HomePage({
  theme,
  onToggleTheme,
  onOpenExplorer,
}: {
  theme: Theme
  onToggleTheme: () => void
  onOpenExplorer: () => void
}) {
  return (
    <div className="app">
      <header className="topbar">
        <div className="brand-area">
          <div className="brand">
            <span className="brand-dot" />
            <div className="brand-title">Tumor Detector</div>
          </div>
          <ThemeToggle theme={theme} onToggle={onToggleTheme} />
        </div>
      </header>
      <main className="home-main">
        <div className="home-panel">
          <h2>Workspace</h2>
          <p>Open the explorer and select a case to start 3D annotation.</p>
          <div className="home-actions">
            <button className="btn" onClick={onOpenExplorer}>
              Open Case Explorer
            </button>
          </div>
        </div>
      </main>
    </div>
  )
}
