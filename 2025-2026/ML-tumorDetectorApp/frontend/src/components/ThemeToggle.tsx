type Theme = 'light' | 'dark'

export function ThemeToggle({
  theme,
  onToggle,
}: {
  theme: Theme
  onToggle: () => void
}) {
  return (
    <button className={`theme-toggle ${theme}`} onClick={onToggle} aria-label="Toggle theme">
      <span className="toggle-icon">
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <circle cx="12" cy="12" r="4.5" fill="currentColor" />
          <path
            d="M12 2.5v2.2M12 19.3v2.2M4.7 4.7l1.6 1.6M17.7 17.7l1.6 1.6M2.5 12h2.2M19.3 12h2.2M4.7 19.3l1.6-1.6M17.7 6.3l1.6-1.6"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
          />
        </svg>
      </span>
      <span className="toggle-icon">
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path
            d="M15.4 2.9a8.6 8.6 0 1 0 5.7 14.7A9.3 9.3 0 1 1 15.4 2.9z"
            fill="currentColor"
          />
        </svg>
      </span>
      <span className="toggle-thumb" />
    </button>
  )
}
