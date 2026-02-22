export function LoaderOverlay({
  label,
  inline = false,
}: {
  label?: string
  inline?: boolean
}) {
  return (
    <div className={`loader-overlay ${inline ? 'inline' : ''}`} role="status" aria-live="polite">
      <div className="loader-card">
        <div className="banter-loader">
          {Array.from({ length: 9 }).map((_, index) => (
            <div key={index} className="banter-loader__box" />
          ))}
        </div>
        {label && <div className="loader-label">{label}</div>}
      </div>
    </div>
  )
}
