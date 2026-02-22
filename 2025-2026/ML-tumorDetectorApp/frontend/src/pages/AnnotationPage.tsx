import { useEffect, useMemo, useState } from 'react'

import { LoaderOverlay } from '../components/LoaderOverlay'
import { MeshViewport, type MeshLayerPayload } from '../components/MeshViewport'
import { ThemeToggle } from '../components/ThemeToggle'

type Theme = 'light' | 'dark'

type MeshResponse = {
  case_id: string
  run_pipeline_0?: boolean
  base_layers: MeshLayerPayload[]
  overlay_layers: MeshLayerPayload[]
  external_overlays?: Record<string, null>
  missing_modalities?: string[]
  missing_overlays?: string[]
  skipped_modalities?: string[]
  skipped_overlays?: string[]
}

const BASE_MODALITY_PRIORITY = ['T1CE', 'FLAIR', 'T1', 'T2']
const ALL_OVERLAY_OPTIONS = ['SEG', 'USER', 'MODEL']
const MESH_OVERLAYS_QUERY = 'SEG,USER,MODEL'
const MESH_DOWNSAMPLE = 2

export function AnnotationPage({
  caseId,
  caseDisplayName,
  theme,
  apiBase,
  requestTimeoutMs,
  onToggleTheme,
  onBackHome,
  onOpenExplorer,
}: {
  caseId?: string
  caseDisplayName?: string
  theme: Theme
  apiBase: string
  requestTimeoutMs: number
  onToggleTheme: () => void
  onBackHome: () => void
  onOpenExplorer: () => void
}) {
  const [meshData, setMeshData] = useState<MeshResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedBase, setSelectedBase] = useState<string>('')
  const [selectedOverlay, setSelectedOverlay] = useState<string>('NONE')
  const [baseOpacity, setBaseOpacity] = useState(0.65)
  const [overlayOpacity, setOverlayOpacity] = useState(0.5)
  const [copiedCaseIdHint, setCopiedCaseIdHint] = useState(false)
  const [resolvedDisplayName, setResolvedDisplayName] = useState(caseDisplayName?.trim() || 'Unnamed')

  useEffect(() => {
    setResolvedDisplayName(caseDisplayName?.trim() || 'Unnamed')
  }, [caseDisplayName, caseId])

  useEffect(() => {
    if (!caseId) {
      setMeshData(null)
      setError(null)
      setLoading(false)
      setCopiedCaseIdHint(false)
      setResolvedDisplayName('Unnamed')
      return
    }

    let cancelled = false

    const loadMeshes = async () => {
      setLoading(true)
      setError(null)
      try {
        const response = await fetchWithTimeout(
          `${apiBase}/visualize/${encodeURIComponent(caseId)}/meshes?overlays=${MESH_OVERLAYS_QUERY}&downsample=${MESH_DOWNSAMPLE}`,
          requestTimeoutMs,
        )
        const data = (await response.json().catch(() => ({}))) as MeshResponse & {
          detail?: string
        }
        if (!response.ok) {
          throw new Error(data.detail ?? `HTTP ${response.status}`)
        }
        if (!cancelled) {
          setMeshData(data)
        }
      } catch (err) {
        if (!cancelled) {
          setMeshData(null)
          setError(err instanceof Error ? err.message : 'Failed to load mesh data.')
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    void loadMeshes()
    return () => {
      cancelled = true
    }
  }, [apiBase, caseId, requestTimeoutMs])

  useEffect(() => {
    if (!caseId) return
    let cancelled = false

    const loadDisplayName = async () => {
      try {
        const response = await fetchWithTimeout(
          `${apiBase}/cases/${encodeURIComponent(caseId)}`,
          requestTimeoutMs,
        )
        if (!response.ok) return
        const data = (await response.json().catch(() => ({}))) as { display_name?: string }
        if (!cancelled) {
          setResolvedDisplayName(data.display_name?.trim() || 'Unnamed')
        }
      } catch {
        // Keep existing display name value if detail fetch fails.
      }
    }

    void loadDisplayName()
    return () => {
      cancelled = true
    }
  }, [apiBase, caseId, requestTimeoutMs])

  const availableBaseModalities = useMemo(() => {
    if (!meshData) return []
    const modalities = meshData.base_layers
      .map((layer) => layer.modality?.toUpperCase() ?? extractModalityFromLayerName(layer.name))
      .filter((value): value is string => Boolean(value))
    return Array.from(new Set(modalities))
  }, [meshData])

  useEffect(() => {
    const preferred = pickPreferredBase(availableBaseModalities)
    if (!preferred) {
      setSelectedBase('')
      return
    }
    if (!selectedBase || !availableBaseModalities.includes(selectedBase)) {
      setSelectedBase(preferred)
    }
  }, [availableBaseModalities, selectedBase])

  const overlayOptions = useMemo(() => {
    if (!meshData) return []
    const local = meshData.overlay_layers
      .map((layer) => layer.name.toUpperCase())
      .filter((value): value is string => Boolean(value))
    const external = Object.keys(meshData.external_overlays ?? {}).map((item) => item.toUpperCase())
    return Array.from(new Set([...local, ...external]))
      .filter((value) => ALL_OVERLAY_OPTIONS.includes(value))
      .sort((a, b) => ALL_OVERLAY_OPTIONS.indexOf(a) - ALL_OVERLAY_OPTIONS.indexOf(b))
  }, [meshData])

  useEffect(() => {
    if (selectedOverlay !== 'NONE' && !overlayOptions.includes(selectedOverlay)) {
      setSelectedOverlay('NONE')
    }
  }, [overlayOptions, selectedOverlay])

  const activeBaseLayer = useMemo(
    () => findBaseLayer(meshData?.base_layers ?? [], selectedBase),
    [meshData?.base_layers, selectedBase],
  )

  const activeOverlayLayer = useMemo(
    () =>
      selectedOverlay === 'NONE'
        ? null
        : findOverlayLayer(meshData?.overlay_layers ?? [], selectedOverlay),
    [meshData?.overlay_layers, selectedOverlay],
  )

  const overlayIsExternalUnavailable =
    selectedOverlay !== 'NONE' &&
    !activeOverlayLayer &&
    Boolean(meshData?.external_overlays && selectedOverlay in meshData.external_overlays)

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand-area">
          <div className="brand">
            <span className="brand-dot" />
            <div className="brand-title">Annotation</div>
          </div>
          <ThemeToggle theme={theme} onToggle={onToggleTheme} />
        </div>
        <div className="topbar-actions">
          <button className="btn ghost" onClick={onBackHome}>
            Home
          </button>
          <button className="btn ghost" onClick={onOpenExplorer}>
            Case Explorer
          </button>
        </div>
      </header>

      <div className="annotation-layout annotation-layout--single">
        <main className="annotation-main annotation-main--stack">
          <div className="annotation-controls">
            <div className="annotation-controls-header">
              <div className="annotation-case-block">
                <div className="annotation-case-name">{resolvedDisplayName || 'Unnamed'}</div>
                <div className="annotation-case-id-row">
                  <span className="annotation-case-id">{caseId ?? '-'}</span>
                  {caseId && (
                    <>
                      <button
                        className="id-copy-btn"
                        type="button"
                        title="Copy case id"
                        aria-label="Copy case id"
                        onClick={async () => {
                          await copyTextToClipboard(caseId)
                          setCopiedCaseIdHint(true)
                          window.setTimeout(() => setCopiedCaseIdHint(false), 1200)
                        }}
                      >
                        {'⧉'}
                      </button>
                      {copiedCaseIdHint && <span className="id-copy-hint">copied !</span>}
                    </>
                  )}
                </div>
              </div>
              {caseId && (
                <div className="annotation-header-controls">
                  <div className="field compact-field">
                    <label className="field-label" htmlFor="base-modality">
                      Base modality
                    </label>
                    <select
                      id="base-modality"
                      className="field-input"
                      value={selectedBase}
                      onChange={(event) => setSelectedBase(event.target.value)}
                      disabled={loading || availableBaseModalities.length === 0}
                    >
                      {availableBaseModalities.length === 0 ? (
                        <option value="">No data</option>
                      ) : (
                        availableBaseModalities.map((modality) => (
                          <option key={modality} value={modality}>
                            {modality}
                          </option>
                        ))
                      )}
                    </select>
                  </div>

                  <div className="field compact-field">
                    <label className="field-label" htmlFor="overlay-select">
                      Segmentation overlay
                    </label>
                    <select
                      id="overlay-select"
                      className="field-input"
                      value={selectedOverlay}
                      onChange={(event) => setSelectedOverlay(event.target.value)}
                      disabled={loading}
                    >
                      <option value="NONE">None</option>
                      {overlayOptions.map((overlay) => (
                        <option key={overlay} value={overlay}>
                          {overlay}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              )}
            </div>

            {!caseId && (
              <div className="sidebar-note">
                Select a case from <strong>Case Explorer</strong> to load annotation.
              </div>
            )}

            {error && <div className="sidebar-error">{error}</div>}
            {!error && overlayIsExternalUnavailable && (
              <div className="sidebar-note">
                {selectedOverlay} overlay is external and not available yet.
              </div>
            )}
          </div>

          {caseId && (activeBaseLayer || loading) ? (
            <>
              {activeBaseLayer ? (
                <MeshViewport
                  baseLayer={activeBaseLayer}
                  overlayLayer={activeOverlayLayer}
                  baseOpacity={baseOpacity}
                  overlayOpacity={overlayOpacity}
                  loading={loading}
                  controlsDisabled={loading}
                />
              ) : (
                <div className="mesh-loading-shell">
                  <LoaderOverlay inline label="Loading mesh data..." />
                </div>
              )}
              <div className="annotation-bottom-controls">
                <div className="field compact-field slider-control">
                  <label className="field-label" htmlFor="base-opacity">
                    Base transparency ({Math.round(baseOpacity * 100)}%)
                  </label>
                  <input
                    id="base-opacity"
                    type="range"
                    min={0.05}
                    max={1}
                    step={0.05}
                    value={baseOpacity}
                    onChange={(event) => setBaseOpacity(Number(event.target.value))}
                    disabled={loading}
                  />
                </div>

                <div className="field compact-field slider-control">
                  <label className="field-label" htmlFor="overlay-opacity">
                    Overlay transparency ({Math.round(overlayOpacity * 100)}%)
                  </label>
                  <input
                    id="overlay-opacity"
                    type="range"
                    min={0.05}
                    max={1}
                    step={0.05}
                    value={overlayOpacity}
                    onChange={(event) => setOverlayOpacity(Number(event.target.value))}
                    disabled={loading}
                  />
                </div>
              </div>
            </>
          ) : (
            <div className="empty-state">
              <h2>No data</h2>
              {caseId ? (
                <p>This case has no base modality data (T1CE/FLAIR/T1/T2).</p>
              ) : (
                <p>Select a case in Case Explorer, then click "Open annotation".</p>
              )}
              {!caseId && (
                <button className="btn" onClick={onOpenExplorer}>
                  Open Case Explorer
                </button>
              )}
            </div>
          )}
        </main>
      </div>
    </div>
  )
}

function pickPreferredBase(modalities: string[]) {
  if (!modalities.length) return null
  const normalized = modalities.map((item) => item.toUpperCase())
  for (const candidate of BASE_MODALITY_PRIORITY) {
    if (normalized.includes(candidate)) {
      return candidate
    }
  }
  return normalized[0] ?? null
}

function extractModalityFromLayerName(name: string) {
  if (!name) return ''
  const [prefix, suffix] = name.split(':')
  if (suffix) return suffix.toUpperCase()
  return prefix.toUpperCase()
}

function findBaseLayer(layers: MeshLayerPayload[], modality: string) {
  if (!modality) return null
  const normalized = modality.toUpperCase()
  return (
    layers.find((layer) => (layer.modality ?? '').toUpperCase() === normalized) ??
    layers.find((layer) => extractModalityFromLayerName(layer.name) === normalized) ??
    null
  )
}

function findOverlayLayer(layers: MeshLayerPayload[], overlay: string) {
  const normalized = overlay.toUpperCase()
  return (
    layers.find((layer) => layer.name.toUpperCase() === normalized) ??
    layers.find((layer) => extractModalityFromLayerName(layer.name) === normalized) ??
    null
  )
}

async function fetchWithTimeout(input: string, timeoutMs: number) {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs)
  try {
    return await fetch(input, { signal: controller.signal })
  } finally {
    window.clearTimeout(timeout)
  }
}

async function copyTextToClipboard(value: string) {
  if (!value) return
  try {
    await navigator.clipboard.writeText(value)
  } catch {
    const input = document.createElement('textarea')
    input.value = value
    input.style.position = 'fixed'
    input.style.opacity = '0'
    document.body.appendChild(input)
    input.focus()
    input.select()
    document.execCommand('copy')
    document.body.removeChild(input)
  }
}
