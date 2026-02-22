export function FilePicker({
  files,
  onChange,
  hint,
}: {
  files: File[]
  onChange: (files: File[]) => void
  hint?: string
}) {
  return (
    <div className="file-picker">
      <label className="file-input">
        <input
          type="file"
          multiple
          accept=".nii,.nii.gz"
          onChange={(event) => onChange(Array.from(event.target.files ?? []))}
        />
        <span>Choose files</span>
      </label>
      {hint && <div className="file-hint">{hint}</div>}
      <div className="file-list">
        {files.length === 0 ? (
          <div className="file-empty">No files selected.</div>
        ) : (
          files.map((file, index) => (
            <div key={`${file.name}-${index}`} className="file-item">
              <span>{file.name}</span>
              <div className="file-actions">
                <span className="file-size">{formatBytes(file.size)}</span>
                <button
                  type="button"
                  className="file-remove"
                  onClick={() => {
                    const next = files.filter((_, fileIndex) => fileIndex !== index)
                    onChange(next)
                  }}
                >
                  Remove
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

function formatBytes(bytes: number) {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`
}
