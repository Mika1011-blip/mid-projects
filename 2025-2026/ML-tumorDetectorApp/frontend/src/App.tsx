import { useEffect, useMemo, useState, type ReactNode } from 'react'

import { FilePicker } from './components/FilePicker'
import { LoaderOverlay } from './components/LoaderOverlay'
import { Modal } from './components/Modal'
import { ThemeToggle } from './components/ThemeToggle'
import { AnnotationPage } from './pages/AnnotationPage'
import { HomePage } from './pages/HomePage'

type CaseRecord = {
  id: string
  created_at?: string
  source_type?: string
  display_name?: string
  expert_note?: string
  has_tumor?: string | null
  source_uris?: Record<string, string>
  metadata_json?: Record<string, unknown>
  metadata_statuses?: Record<string, string>
}

type UploadResult = {
  case_id?: string
  uploaded?: Array<{ key: string; object_key: string; status: string }>
  detail?: string
}

type BulkCaseGroup = {
  id: string
  displayName: string
  files: File[]
  status?: 'OK' | 'FAILED' | 'PENDING'
  error?: string
}

type AppRoute =
  | { page: 'home' }
  | { page: 'explorer' }
  | { page: 'annotation'; caseId?: string }

const API_BASE = resolveApiBase()
const CASES_ENDPOINT = `${API_BASE}/cases/get_all`
const CASES_LIST_LIMIT = 500
const PREFERRED_MODALITIES = ['T1CE', 'FLAIR', 'T1', 'T2', 'SEG']
const THEME_STORAGE_KEY = 'mltd-theme'
const REQUEST_TIMEOUT_MS = 30000
const MAX_LIST_RETRIES = 3

type Theme = 'light' | 'dark'

function getInitialTheme(): Theme {
  if (typeof window === 'undefined') return 'light'
  const stored = window.localStorage.getItem(THEME_STORAGE_KEY)
  if (stored === 'light' || stored === 'dark') return stored
  return 'light'
}

function resolveApiBase() {
  const configured = import.meta.env.VITE_API_BASE as string | undefined
  const fallback =
    typeof window !== 'undefined'
      ? `${window.location.protocol}//${window.location.hostname}:8000/api/v1`
      : 'http://127.0.0.1:8000/api/v1'
  const rawBase = configured?.trim() ? configured.trim() : fallback

  // Windows/WSL Docker setups may resolve localhost to ::1 and stall;
  // prefer IPv4 loopback in local browser development.
  if (typeof window !== 'undefined' && window.location.hostname === 'localhost') {
    return rawBase.replace('localhost:8000', '127.0.0.1:8000')
  }
  return rawBase
}

function parseRouteFromHash(hashValue: string): AppRoute {
  const normalized = hashValue.replace(/^#/, '').replace(/^\/+/, '').trim()
  if (!normalized) return { page: 'home' }

  const parts = normalized.split('/')
  const head = parts[0]?.toLowerCase()
  if (head === 'explorer') return { page: 'explorer' }
  if (head === 'annotation') {
    const caseId = decodeURIComponent(parts.slice(1).join('/')).trim()
    return caseId ? { page: 'annotation', caseId } : { page: 'annotation' }
  }
  return { page: 'home' }
}

function readRouteFromLocation(): AppRoute {
  if (typeof window === 'undefined') return { page: 'home' }
  return parseRouteFromHash(window.location.hash)
}

function routeToHash(route: AppRoute): string {
  if (route.page === 'home') return '#/'
  if (route.page === 'explorer') return '#/explorer'
  return route.caseId ? `#/annotation/${encodeURIComponent(route.caseId)}` : '#/annotation'
}

function App() {
  const [route, setRoute] = useState<AppRoute>(readRouteFromLocation)
  const [cases, setCases] = useState<CaseRecord[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [selectedModality, setSelectedModality] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [theme, setTheme] = useState<Theme>(getInitialTheme)

  const [showNewModal, setShowNewModal] = useState(false)
  const [showAppendModal, setShowAppendModal] = useState(false)
  const [newCaseMode, setNewCaseMode] = useState<'single' | 'bulk'>('single')
  const [newCaseFiles, setNewCaseFiles] = useState<File[]>([])
  const [newCaseName, setNewCaseName] = useState('')
  const [newCaseNote, setNewCaseNote] = useState('')
  const [bulkGroups, setBulkGroups] = useState<BulkCaseGroup[]>([])
  const [appendFiles, setAppendFiles] = useState<File[]>([])
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [showRenameModal, setShowRenameModal] = useState(false)
  const [showNoteModal, setShowNoteModal] = useState(false)
  const [renameValue, setRenameValue] = useState('')
  const [noteValue, setNoteValue] = useState('')
  const [noteEditable, setNoteEditable] = useState(false)
  const [renameSaving, setRenameSaving] = useState(false)
  const [noteSaving, setNoteSaving] = useState(false)
  const [renameError, setRenameError] = useState<string | null>(null)
  const [noteError, setNoteError] = useState<string | null>(null)
  const [showDeleteCaseModal, setShowDeleteCaseModal] = useState(false)
  const [showDeleteModalityModal, setShowDeleteModalityModal] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<{ key: string; uri: string } | null>(null)
  const [deleteCaseError, setDeleteCaseError] = useState<string | null>(null)
  const [deleteModalityError, setDeleteModalityError] = useState<string | null>(null)
  const [deletingCase, setDeletingCase] = useState(false)
  const [deletingModality, setDeletingModality] = useState(false)
  const [selectingCases, setSelectingCases] = useState(false)
  const [selectedCaseIds, setSelectedCaseIds] = useState<Set<string>>(new Set())
  const [showBulkDeleteModal, setShowBulkDeleteModal] = useState(false)
  const [bulkDeleteError, setBulkDeleteError] = useState<string | null>(null)
  const [bulkDeleting, setBulkDeleting] = useState(false)
  const [copiedCaseIdHint, setCopiedCaseIdHint] = useState(false)

  const selectedCase = useMemo(
    () => cases.find((item) => item.id === selectedId) ?? null,
    [cases, selectedId],
  )

  const filteredCases = useMemo(() => {
    const term = search.trim().toLowerCase()
    if (!term) return cases
    return cases.filter((item) => {
      const name = item.display_name ?? ''
      return item.id.toLowerCase().includes(term) || name.toLowerCase().includes(term)
    })
  }, [cases, search])

  useEffect(() => {
    if (typeof window === 'undefined') return
    const handleHashChange = () => {
      setRoute(readRouteFromLocation())
    }
    window.addEventListener('hashchange', handleHashChange)
    return () => window.removeEventListener('hashchange', handleHashChange)
  }, [])

  useEffect(() => {
    if (route.page !== 'explorer') return
    void fetchCases()
  }, [route.page])

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(THEME_STORAGE_KEY, theme)
    }
  }, [theme])

  useEffect(() => {
    if (!selectedCase) {
      setSelectedModality(null)
      setCopiedCaseIdHint(false)
      return
    }
    const modalities = collectModalities(selectedCase)
    setSelectedModality(modalities[0] ?? null)
    setRenameValue(selectedCase.display_name ?? '')
    setNoteValue(selectedCase.expert_note ?? '')
    setNoteEditable(false)
    setRenameError(null)
    setNoteError(null)
    setDeleteTarget(null)
    setShowDeleteCaseModal(false)
    setShowDeleteModalityModal(false)
    setDeleteCaseError(null)
    setDeleteModalityError(null)
    setCopiedCaseIdHint(false)
  }, [selectedCase])

  useEffect(() => {
    if (!selectingCases) {
      setSelectedCaseIds(new Set())
    }
  }, [selectingCases])

  useEffect(() => {
    if (!selectedCase || !selectedId) {
      return
    }
    if (hasCaseDetail(selectedCase)) {
      return
    }
    void fetchCaseDetail(selectedId)
  }, [selectedCase, selectedId])

  async function fetchCases() {
    setLoading(true)
    setError(null)
    const endpoint = `${CASES_ENDPOINT}?limit=${CASES_LIST_LIMIT}&offset=0`
    let lastError: unknown = null
    for (let attempt = 0; attempt < MAX_LIST_RETRIES; attempt += 1) {
      try {
        const response = await fetchWithTimeout(endpoint, REQUEST_TIMEOUT_MS)
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`)
        }
        const data = (await response.json()) as CaseRecord[]
        const nextCases = Array.isArray(data) ? data : []
        setCases(nextCases)
        if (selectedId && !nextCases.some((item) => item.id === selectedId)) {
          setSelectedId(null)
        }
        setLoading(false)
        return
      } catch (err) {
        lastError = err
        if (attempt < MAX_LIST_RETRIES - 1) {
          await sleepMs(600 * (attempt + 1))
        }
      }
    }
    setLoading(false)
    setError(
      `Failed to load cases after ${MAX_LIST_RETRIES} attempt(s). ${
        lastError instanceof Error ? lastError.message : 'Check backend status.'
      }`,
    )
  }

  async function fetchCaseDetail(caseId: string) {
    try {
      const response = await fetchWithTimeout(`${API_BASE}/cases/${caseId}`, REQUEST_TIMEOUT_MS)
      if (!response.ok) {
        return
      }
      const detail = (await response.json()) as CaseRecord
      setCases((prev) =>
        prev.map((item) => (item.id === caseId ? { ...item, ...detail } : item)),
      )
    } catch (err) {
      // Keep list responsive even if detail fetch fails
    }
  }

  async function uploadNewCase() {
    if (!newCaseFiles.length) {
      setUploadError('Select at least one NIfTI file.')
      return
    }
    setUploading(true)
    setUploadError(null)
    const form = new FormData()
    const nameValue = newCaseName.trim()
    const noteValue = newCaseNote.trim()
    if (nameValue) form.append('display_name', nameValue)
    if (noteValue) form.append('expert_note', noteValue)
    newCaseFiles.forEach((file) => form.append('files', file))

    try {
      const response = await fetch(`${API_BASE}/ingest/nifti/batch`, {
        method: 'POST',
        body: form,
      })
      const data = (await response.json()) as UploadResult
      if (!response.ok) {
        setUploadError(data.detail ?? 'Upload failed')
      } else {
        closeNewModal()
        await fetchCases()
        if (data.case_id) {
          setSelectedId(data.case_id)
        }
      }
    } catch (err) {
      setUploadError('Upload failed. Check backend logs.')
    } finally {
      setUploading(false)
    }
  }

  async function uploadBulkCases() {
    if (!bulkGroups.length) {
      setUploadError('Select a folder with NIfTI files.')
      return
    }
    setUploading(true)
    setUploadError(null)
    try {
      setBulkGroups((prev) =>
        prev.map((group) => ({
          ...group,
          status: group.files.length ? 'PENDING' : undefined,
          error: undefined,
        })),
      )

      let hasFailure = false
      for (const group of bulkGroups) {
        if (!group.files.length) continue
        const form = new FormData()
        const displayName = group.displayName.trim() || group.id
        if (displayName) form.append('display_name', displayName)
        group.files.forEach((file) => {
          form.append('files', file, getRelativePath(file))
        })

        try {
          const response = await fetch(`${API_BASE}/ingest/nifti/batch`, {
            method: 'POST',
            body: form,
          })
          const data = (await response.json().catch(() => ({}))) as UploadResult
          if (!response.ok) {
            hasFailure = true
            setBulkGroups((prev) =>
              prev.map((item) =>
                item.id === group.id
                  ? { ...item, status: 'FAILED', error: data.detail ?? 'Upload failed' }
                  : item,
              ),
            )
          } else {
            setBulkGroups((prev) =>
              prev.map((item) =>
                item.id === group.id ? { ...item, status: 'OK', error: undefined } : item,
              ),
            )
          }
        } catch (err) {
          hasFailure = true
          setBulkGroups((prev) =>
            prev.map((item) =>
              item.id === group.id
                ? { ...item, status: 'FAILED', error: 'Upload failed' }
                : item,
            ),
          )
        }
      }

      await fetchCases()
      if (!hasFailure) {
        closeNewModal()
      } else {
        setUploadError('Some cases failed to upload. Review and retry if needed.')
      }
    } catch (err) {
      setUploadError('Bulk upload failed. Check backend logs.')
    } finally {
      setUploading(false)
    }
  }

  async function uploadAppendCase() {
    if (!selectedCase) {
      setUploadError('Select a case first.')
      return
    }
    if (!appendFiles.length) {
      setUploadError('Select at least one NIfTI file.')
      return
    }
    setUploading(true)
    setUploadError(null)
    const form = new FormData()
    appendFiles.forEach((file) => form.append('files', file))

    try {
      const response = await fetch(`${API_BASE}/ingest/${selectedCase.id}/nifti/batch`, {
        method: 'POST',
        body: form,
      })
      const data = (await response.json()) as UploadResult
      if (!response.ok) {
        setUploadError(data.detail ?? 'Upload failed')
      } else {
        setShowAppendModal(false)
        setAppendFiles([])
        await fetchCases()
      }
    } catch (err) {
      setUploadError('Upload failed. Check backend logs.')
    } finally {
      setUploading(false)
    }
  }

  async function saveRename() {
    if (!selectedCase) return
    const nextName = renameValue.trim() || 'Unnamed'
    setRenameSaving(true)
    setRenameError(null)
    try {
      await postStringPayload(selectedCase.id, 'rename', nextName)
      await fetchCases()
      setShowRenameModal(false)
    } catch (err) {
      setRenameError('Failed to rename case.')
    } finally {
      setRenameSaving(false)
    }
  }

  async function saveNote() {
    if (!selectedCase) return
    setNoteSaving(true)
    setNoteError(null)
    try {
      await postStringPayload(selectedCase.id, 'add_note', noteValue.trim())
      await fetchCases()
      setShowNoteModal(false)
      setNoteEditable(false)
    } catch (err) {
      setNoteError('Failed to update note.')
    } finally {
      setNoteSaving(false)
    }
  }

  async function deleteCase() {
    if (!selectedCase) return
    setDeletingCase(true)
    setDeleteCaseError(null)
    try {
      const response = await fetch(`${API_BASE}/removeIngested/${selectedCase.id}`, {
        method: 'DELETE',
      })
      if (!response.ok) {
        const data = (await response.json().catch(() => ({}))) as { detail?: string }
        throw new Error(data?.detail ?? 'Failed to delete case.')
      }
      setShowDeleteCaseModal(false)
      setSelectedId(null)
      await fetchCases()
    } catch (err) {
      setDeleteCaseError(err instanceof Error ? err.message : 'Failed to delete case.')
    } finally {
      setDeletingCase(false)
    }
  }

  async function deleteModality() {
    if (!selectedCase || !deleteTarget) return
    setDeletingModality(true)
    setDeleteModalityError(null)
    try {
      const encoded = encodeURIComponent(deleteTarget.uri)
      const response = await fetch(
        `${API_BASE}/removeIngested/${selectedCase.id}/${encoded}`,
        { method: 'DELETE' },
      )
      if (!response.ok) {
        const data = (await response.json().catch(() => ({}))) as { detail?: string }
        throw new Error(data?.detail ?? 'Failed to delete modality.')
      }
      setShowDeleteModalityModal(false)
      setDeleteTarget(null)
      await fetchCases()
    } catch (err) {
      setDeleteModalityError(err instanceof Error ? err.message : 'Failed to delete modality.')
    } finally {
      setDeletingModality(false)
    }
  }

  const toggleSelectMode = () => {
    setSelectingCases((prev) => !prev)
    setShowBulkDeleteModal(false)
    setBulkDeleteError(null)
  }

  const toggleCaseSelection = (caseId: string) => {
    setSelectedCaseIds((prev) => {
      const next = new Set(prev)
      if (next.has(caseId)) {
        next.delete(caseId)
      } else {
        next.add(caseId)
      }
      return next
    })
  }

  const selectAllVisible = () => {
    setSelectedCaseIds(new Set(filteredCases.map((item) => item.id)))
  }

  const deselectAll = () => {
    setSelectedCaseIds(new Set())
  }

  async function deleteSelectedCases() {
    if (!selectedCaseIds.size) return
    setBulkDeleting(true)
    setBulkDeleteError(null)
    let failed = 0
    for (const caseId of selectedCaseIds) {
      try {
        const response = await fetch(`${API_BASE}/removeIngested/${caseId}`, {
          method: 'DELETE',
        })
        if (!response.ok) {
          failed += 1
        }
      } catch {
        failed += 1
      }
    }
    await fetchCases()
    if (failed) {
      setBulkDeleteError(`${failed} case(s) failed to delete.`)
    } else {
      setShowBulkDeleteModal(false)
      setSelectingCases(false)
    }
    setBulkDeleting(false)
  }

  const modalityTiles = selectedCase ? buildModalityTiles(selectedCase) : []

  const handleModeChange = (mode: 'single' | 'bulk') => {
    setNewCaseMode(mode)
    setUploadError(null)
    if (mode === 'single') {
      setBulkGroups([])
    } else {
      setNewCaseFiles([])
      setNewCaseName('')
      setNewCaseNote('')
    }
  }

  const handleBulkSelection = (files: File[]) => {
    const groups = buildBulkGroups(files)
    setBulkGroups(groups)
  }

  const updateBulkName = (groupId: string, value: string) => {
    setBulkGroups((prev) =>
      prev.map((group) => (group.id === groupId ? { ...group, displayName: value } : group)),
    )
  }

  const removeBulkFile = (groupId: string, fileIndex: number) => {
    setBulkGroups((prev) => {
      const next = prev.flatMap((group) => {
        if (group.id !== groupId) return [group]
        const files = group.files.filter((_, idx) => idx !== fileIndex)
        if (!files.length) return []
        return [{ ...group, files }]
      })
      return next
    })
  }

  const closeNewModal = () => {
    setShowNewModal(false)
    setUploadError(null)
    setNewCaseMode('single')
    setNewCaseFiles([])
    setNewCaseName('')
    setNewCaseNote('')
    setBulkGroups([])
  }

  const closeAppendModal = () => {
    setShowAppendModal(false)
    setUploadError(null)
    setAppendFiles([])
  }

  const navigateTo = (next: AppRoute) => {
    setRoute(next)
    if (typeof window !== 'undefined') {
      const nextHash = routeToHash(next)
      if (window.location.hash !== nextHash) {
        window.location.hash = nextHash
      }
    }
  }

  const openHomePage = () => navigateTo({ page: 'home' })

  const openCaseExplorer = (focusCaseId?: string | null) => {
    navigateTo({ page: 'explorer' })
    if (focusCaseId) {
      setSelectedId(focusCaseId)
    }
  }

  const openAnnotationPage = (caseId?: string | null) => {
    if (!caseId) return
    navigateTo({ page: 'annotation', caseId })
  }

  if (route.page === 'home') {
    return (
      <HomePage
        theme={theme}
        onToggleTheme={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
        onOpenExplorer={() => openCaseExplorer()}
      />
    )
  }

  if (route.page === 'annotation') {
    const annotationCaseDisplayName =
      cases.find((item) => item.id === route.caseId)?.display_name ?? undefined
    return (
      <AnnotationPage
        caseId={route.caseId}
        caseDisplayName={annotationCaseDisplayName}
        theme={theme}
        apiBase={API_BASE}
        requestTimeoutMs={REQUEST_TIMEOUT_MS}
        onToggleTheme={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
        onBackHome={openHomePage}
        onOpenExplorer={() => openCaseExplorer(route.caseId ?? null)}
      />
    )
  }

  return (
    <div className="app">
      {loading && route.page === 'explorer' && <LoaderOverlay label="Loading cases..." />}
      <header className="topbar">
        <div className="brand-area">
          <div className="brand">
            <span className="brand-dot" />
            <div>
              <div className="brand-title">Case Explorer</div>
            </div>
          </div>
          <ThemeToggle
            theme={theme}
            onToggle={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
          />
        </div>
        <div className="topbar-actions">
          <button className="btn ghost" onClick={openHomePage}>
            Home
          </button>
          <div className="search">
            <input
              type="text"
              placeholder="Search cases"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
          <button className="btn" onClick={() => setShowNewModal(true)}>
            New Case
          </button>
          <button
            className="btn ghost"
            onClick={() => setShowAppendModal(true)}
            disabled={!selectedCase}
          >
            Add Modalities
          </button>
          <button className="btn ghost" onClick={() => void fetchCases()}>
            Refresh
          </button>
        </div>
      </header>

      <div className="layout case-explorer">
        <aside className="sidebar">
          <div className="sidebar-header">
            <div className="sidebar-title">
              <span>Cases</span>
              <button className="btn text" type="button" onClick={toggleSelectMode}>
                {selectingCases ? 'Cancel select' : 'Select'}
              </button>
            </div>
            <span className="count">{cases.length}</span>
          </div>
          {selectingCases && (
            <div className="sidebar-actions">
              <button className="btn text" type="button" onClick={selectAllVisible}>
                Select all
              </button>
              <button className="btn text" type="button" onClick={deselectAll}>
                Deselect all
              </button>
              <button
                className="btn text danger"
                type="button"
                onClick={() => {
                  setBulkDeleteError(null)
                  setShowBulkDeleteModal(true)
                }}
                disabled={selectedCaseIds.size === 0}
              >
                Delete
              </button>
            </div>
          )}
          {loading && <div className="sidebar-note">Loading cases...</div>}
          {error && <div className="sidebar-error">{error}</div>}
          <div className="case-list">
            {filteredCases.map((item) => (
              <button
                key={item.id}
                className={`case-item ${item.id === selectedId ? 'active' : ''} ${
                  selectingCases && selectedCaseIds.has(item.id) ? 'selected' : ''
                }`}
                onClick={() => {
                  if (selectingCases) {
                    toggleCaseSelection(item.id)
                  } else {
                    setSelectedId(item.id)
                  }
                }}
              >
                <div className="case-title">
                  {selectingCases && (
                    <span
                      className={`case-checkbox ${
                        selectedCaseIds.has(item.id) ? 'checked' : ''
                      }`}
                    />
                  )}
                  <span className="brain-icon" role="img" aria-label="brain">
                    🧠
                  </span>
                  <span className="case-name">{item.display_name ?? 'Unnamed'}</span>
                </div>
                <div className="case-meta">
                  <span className="case-id">{shortId(item.id)}</span>
                  <span
                    className={`tumor-dot ${getTumorStatusKey(item.has_tumor)}`}
                    title={`Tumor: ${formatTumorStatus(item.has_tumor)}`}
                  />
                  <span className="chip">{item.source_type ?? 'NIFTI'}</span>
                </div>
              </button>
            ))}
          </div>
        </aside>

        <main className="main">
          {!selectedCase ? (
            <div className="empty-state">
              <h2>Select a case</h2>
              <p>Pick a folder on the left to inspect its modalities.</p>
            </div>
          ) : (
            <div className="case-detail">
              <div className="case-header">
                <div>
                  <div className="case-label">Case</div>
                  <div className="case-title-row">
                    <div className="case-title-main">{selectedCase.display_name ?? 'Unnamed'}</div>
                    <button
                      className="case-edit-trigger"
                      type="button"
                      onClick={() => {
                        setRenameValue(selectedCase.display_name ?? '')
                        setRenameError(null)
                        setShowRenameModal(true)
                      }}
                      aria-label="Rename case"
                      title="Rename case"
                    >
                      ✎
                    </button>
                  </div>

                  <div className="case-id-sub-row">
                    <span className="case-id-sub">{selectedCase.id}</span>
                    <button
                      className="id-copy-btn"
                      type="button"
                      title="Copy case id"
                      aria-label="Copy case id"
                      onClick={async () => {
                        await copyTextToClipboard(selectedCase.id)
                        setCopiedCaseIdHint(true)
                        window.setTimeout(() => setCopiedCaseIdHint(false), 1200)
                      }}
                    >
                      {'⧉'}
                    </button>
                    {copiedCaseIdHint && <span className="id-copy-hint">copied !</span>}
                  </div>
                  <button
                    className="btn ghost small expert-note-trigger"
                    type="button"
                    onClick={() => {
                      setNoteValue(selectedCase.expert_note ?? '')
                      setNoteEditable(false)
                      setNoteError(null)
                      setShowNoteModal(true)
                    }}
                  >
                    Expert note
                  </button>
                </div>
                <div className="case-info">
                  <div>
                    <span className="label">Tumor</span>
                    <span className={`tumor-status ${getTumorStatusKey(selectedCase.has_tumor)}`}>
                      {formatTumorStatus(selectedCase.has_tumor)}
                    </span>
                  </div>
                  <div>
                    <span className="label">Created</span>
                    <span>{formatDate(selectedCase.created_at, true)}</span>
                  </div>
                  <div>
                    <span className="label">Source</span>
                    <span>{selectedCase.source_type ?? 'NIFTI'}</span>
                  </div>
                  <button
                    className="btn ghost small"
                    type="button"
                    onClick={() => openAnnotationPage(selectedCase.id)}
                  >
                    Open annotation
                  </button>
                  <button
                    className="btn danger small"
                    type="button"
                    onClick={() => {
                      setDeleteCaseError(null)
                      setShowDeleteCaseModal(true)
                    }}
                  >
                    Delete case
                  </button>
                </div>
              </div>

              {selectedCase && selectedModality && (
                <div className="preview-section">
                  <div className="section-title">Previews</div>
                  {selectedCase.source_uris?.[selectedModality] ? (
                    <div className="gif-grid">
                      {(['x', 'y', 'z'] as const).map((axis) => (
                        <div key={axis} className="gif-card">
                          <div className="gif-label">{axis.toUpperCase()} axis</div>
                          <img
                            className="gif-image"
                            src={buildGifUrl(selectedCase.id, selectedModality, axis)}
                            alt={`${selectedModality} ${axis} axis gif`}
                          />
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="empty-state">No data to preview for this modality.</div>
                  )}
                </div>
              )}

              <div className="section-title">Modalities</div>
              <div className="modality-grid">
                {modalityTiles.length === 0 ? (
                  <div className="empty-state">No modalities uploaded yet.</div>
                ) : (
                  modalityTiles.map((tile) => (
                    <button
                      key={tile.key}
                      className={`modality-card ${selectedModality === tile.key ? 'active' : ''}`}
                      onClick={() => setSelectedModality(tile.key)}
                    >
                      <div className="modality-header">
                        <span className="modality-name">{tile.key}</span>
                        <div className="modality-actions">
                          <span className={`status ${tile.status.toLowerCase()}`}>{tile.status}</span>
                          <button
                            type="button"
                            className="modality-delete"
                            disabled={!tile.objectKey}
                            title="Delete modality file"
                            onClick={(event) => {
                              event.stopPropagation()
                              if (!tile.objectKey) return
                              setDeleteTarget({ key: tile.key, uri: tile.objectKey })
                              setDeleteModalityError(null)
                              setShowDeleteModalityModal(true)
                            }}
                          >
                            🗑
                          </button>
                        </div>
                      </div>
                      <div className="modality-body">
                        <div className="object-key">{tile.objectKey ?? 'No object key yet'}</div>
                        <div className="metadata-preview">{tile.metadataPreview}</div>
                      </div>
                    </button>
                  ))
                )}
              </div>

              {selectedModality && (
                <div className="detail-panel">
                  <div className="detail-title">{selectedModality} details</div>
                  {renderMetadataDetails(selectedCase, selectedModality)}
                </div>
              )}

              {/* Slice preview disabled for now */}
            </div>
          )}
        </main>
      </div>

      {showNewModal && (
        <Modal
          title="Create new case"
          subtitle="Upload 1 or more NIfTI files in a single batch"
          onClose={closeNewModal}
        >
          <div className="mode-toggle">
            <button
              className={`btn ghost ${newCaseMode === 'single' ? 'active' : ''}`}
              type="button"
              onClick={() => handleModeChange('single')}
            >
              Single case
            </button>
            <button
              className={`btn ghost ${newCaseMode === 'bulk' ? 'active' : ''}`}
              type="button"
              onClick={() => handleModeChange('bulk')}
            >
              Folder batch
            </button>
          </div>

          {newCaseMode === 'single' ? (
            <>
              <div className="field">
                <label className="field-label" htmlFor="new-case-name">
                  Display name
                </label>
                <input
                  id="new-case-name"
                  className="field-input"
                  type="text"
                  placeholder="Unnamed"
                  value={newCaseName}
                  onChange={(event) => setNewCaseName(event.target.value)}
                />
              </div>
              <div className="field">
                <label className="field-label" htmlFor="new-case-note">
                  Expert note (optional)
                </label>
                <textarea
                  id="new-case-note"
                  className="field-textarea"
                  placeholder="Add an optional note for this case..."
                  value={newCaseNote}
                  onChange={(event) => setNewCaseNote(event.target.value)}
                />
              </div>
              <FilePicker
                files={newCaseFiles}
                onChange={setNewCaseFiles}
                hint="Accepted: .nii, .nii.gz"
              />
            </>
          ) : (
            <>
              <div className="file-picker">
                <label className="file-input">
                  <input
                    type="file"
                    multiple
                    accept=".nii,.nii.gz"
                    // @ts-ignore
                    webkitdirectory="true"
                    onChange={(event) => handleBulkSelection(Array.from(event.target.files ?? []))}
                  />
                  <span>Select folder</span>
                </label>
                <div className="file-hint">
                  Each top-level folder becomes a case. You can rename them below.
                </div>
              </div>
              {bulkGroups.length === 0 ? (
                <div className="file-empty">No case folders detected yet.</div>
              ) : (
                <div className="bulk-groups">
                  {bulkGroups.map((group) => (
                    <div key={group.id} className="bulk-group">
                      <div className="bulk-header">
                        <div>
                          <div className="bulk-title">
                            {group.id}
                            {group.status && (
                              <span
                                className={`bulk-status ${group.status === 'OK' ? 'ok' : group.status === 'FAILED' ? 'failed' : 'pending'}`}
                              >
                                {group.status}
                              </span>
                            )}
                          </div>
                          <div className="bulk-meta">
                            {group.files.length} files
                            {group.error ? ` • ${group.error}` : ''}
                          </div>
                        </div>
                        <div className="field">
                          <label className="field-label">Display name</label>
                          <input
                            className="field-input bulk-input"
                            type="text"
                            value={group.displayName}
                            onChange={(event) => updateBulkName(group.id, event.target.value)}
                          />
                        </div>
                      </div>
                      <div className="bulk-files">
                        {group.files.map((file, index) => (
                          <div key={`${group.id}-${file.name}-${index}`} className="bulk-file">
                            <span>{getRelativePath(file)}</span>
                            <button
                              type="button"
                              className="file-remove"
                              onClick={() => removeBulkFile(group.id, index)}
                            >
                              Remove
                            </button>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
          {uploadError && <div className="form-error">{uploadError}</div>}
          <div className="modal-actions">
            <button className="btn ghost" onClick={closeNewModal}>
              Cancel
            </button>
            {newCaseMode === 'single' ? (
              <button className="btn" onClick={() => void uploadNewCase()} disabled={uploading}>
                {uploading ? 'Uploading...' : 'Create Case'}
              </button>
            ) : (
              <button className="btn" onClick={() => void uploadBulkCases()} disabled={uploading}>
                {uploading ? 'Uploading...' : 'Upload Cases'}
              </button>
            )}
          </div>
        </Modal>
      )}

      {showAppendModal && (
        <Modal
          title="Append modalities"
          subtitle={selectedCase ? `Case ${shortId(selectedCase.id)}` : 'Select a case first'}
          onClose={closeAppendModal}
        >
          <FilePicker files={appendFiles} onChange={setAppendFiles} hint="Add missing modalities" />
          {uploadError && <div className="form-error">{uploadError}</div>}
          <div className="modal-actions">
            <button className="btn ghost" onClick={closeAppendModal}>
              Cancel
            </button>
            <button
              className="btn"
              onClick={() => void uploadAppendCase()}
              disabled={uploading || !selectedCase}
            >
              {uploading ? 'Uploading...' : 'Append'}
            </button>
          </div>
        </Modal>
      )}

      {showRenameModal && selectedCase && (
        <Modal
          title="Rename case"
          subtitle={`Case ${shortId(selectedCase.id)}`}
          onClose={() => setShowRenameModal(false)}
        >
          <div className="field">
            <label className="field-label" htmlFor="rename-input">
              New display name
            </label>
            <input
              id="rename-input"
              className="field-input"
              type="text"
              value={renameValue}
              onChange={(event) => setRenameValue(event.target.value)}
              placeholder="Unnamed"
            />
          </div>
          {renameError && <div className="form-error">{renameError}</div>}
          <div className="modal-actions">
            <button className="btn ghost" onClick={() => setShowRenameModal(false)}>
              Cancel
            </button>
            <button
              className="btn"
              onClick={() => void saveRename()}
              disabled={renameSaving}
            >
              {renameSaving ? 'Saving...' : 'Confirm'}
            </button>
          </div>
        </Modal>
      )}

      {showNoteModal && selectedCase && (
        <Modal
          title="Expert note"
          subtitle={`Case ${shortId(selectedCase.id)}`}
          onClose={() => {
            setShowNoteModal(false)
            setNoteEditable(false)
          }}
        >
          <div className="note-toggle">
            <span className="field-label">Edit mode</span>
            <button
              className="btn ghost small"
              type="button"
              onClick={() => setNoteEditable((prev) => !prev)}
            >
              {noteEditable ? 'Editing' : 'Edit'}
            </button>
          </div>
          <div className="field">
            <textarea
              className="field-textarea"
              value={noteValue}
              onChange={(event) => setNoteValue(event.target.value)}
              placeholder="No expert note yet."
              readOnly={!noteEditable}
            />
          </div>
          {noteError && <div className="form-error">{noteError}</div>}
          <div className="modal-actions">
            <button
              className="btn ghost"
              onClick={() => {
                setShowNoteModal(false)
                setNoteEditable(false)
              }}
            >
              Cancel
            </button>
            <button
              className="btn"
              onClick={() => void saveNote()}
              disabled={noteSaving || !noteEditable}
            >
              {noteSaving ? 'Saving...' : 'Confirm'}
            </button>
          </div>
        </Modal>
      )}

      {showDeleteCaseModal && selectedCase && (
        <Modal
          title="Delete case"
          subtitle="This will remove the case and its files from storage."
          onClose={() => setShowDeleteCaseModal(false)}
        >
          <p className="warning-text">
            Are you sure you want to delete <strong>{selectedCase.display_name ?? 'Unnamed'}</strong>?
          </p>
          {deleteCaseError && <div className="form-error">{deleteCaseError}</div>}
          <div className="modal-actions">
            <button className="btn ghost" onClick={() => setShowDeleteCaseModal(false)}>
              Cancel
            </button>
            <button className="btn danger" onClick={() => void deleteCase()} disabled={deletingCase}>
              {deletingCase ? 'Deleting...' : 'Delete'}
            </button>
          </div>
        </Modal>
      )}

      {showDeleteModalityModal && selectedCase && deleteTarget && (
        <Modal
          title="Delete modality file"
          subtitle={`${deleteTarget.key} - ${shortId(selectedCase.id)}`}
          onClose={() => {
            setShowDeleteModalityModal(false)
            setDeleteTarget(null)
          }}
        >
          <p className="warning-text">
            Remove <strong>{deleteTarget.key}</strong> from this case?
          </p>
          {deleteModalityError && <div className="form-error">{deleteModalityError}</div>}
          <div className="modal-actions">
            <button
              className="btn ghost"
              onClick={() => {
                setShowDeleteModalityModal(false)
                setDeleteTarget(null)
              }}
            >
              Cancel
            </button>
            <button
              className="btn danger"
              onClick={() => void deleteModality()}
              disabled={deletingModality}
            >
              {deletingModality ? 'Deleting...' : 'Delete'}
            </button>
          </div>
        </Modal>
      )}

      {showBulkDeleteModal && (
        <Modal
          title="Delete selected cases"
          subtitle={`Selected: ${selectedCaseIds.size}`}
          onClose={() => setShowBulkDeleteModal(false)}
        >
          <p className="warning-text">
            This will permanently delete the selected cases and their files.
          </p>
          {bulkDeleteError && <div className="form-error">{bulkDeleteError}</div>}
          <div className="modal-actions">
            <button className="btn ghost" onClick={() => setShowBulkDeleteModal(false)}>
              Cancel
            </button>
            <button
              className="btn danger"
              onClick={() => void deleteSelectedCases()}
              disabled={bulkDeleting}
            >
              {bulkDeleting ? 'Deleting...' : 'Delete selected'}
            </button>
          </div>
        </Modal>
      )}
    </div>
  )
}

function collectModalities(item: CaseRecord): string[] {
  const keys = new Set<string>()
  if (item.source_uris) Object.keys(item.source_uris).forEach((key) => keys.add(key))
  if (item.metadata_statuses) Object.keys(item.metadata_statuses).forEach((key) => keys.add(key))
  if (item.metadata_json) Object.keys(item.metadata_json).forEach((key) => keys.add(key))
  return Array.from(keys).sort((a, b) => rankModality(a) - rankModality(b))
}

function rankModality(key: string) {
  const idx = PREFERRED_MODALITIES.indexOf(key.toUpperCase())
  return idx === -1 ? 99 : idx
}

function buildModalityTiles(item: CaseRecord) {
  const modalities = collectModalities(item)
  return modalities.map((key) => {
    const status = item.metadata_statuses?.[key] ?? 'PENDING'
    const objectKey = item.source_uris?.[key]
    const meta = item.metadata_json?.[key]
    return {
      key,
      status,
      objectKey,
      metadataPreview: formatMetadataPreview(meta),
    }
  })
}

function formatMetadataPreview(meta: unknown) {
  if (!meta || typeof meta !== 'object') {
    return 'No metadata yet.'
  }
  const data = meta as Record<string, unknown>
  const parts: string[] = []
  const dtype = toStringValue(data.dtype)
  const shape = formatNumberArray(data.shape)
  const spacing = formatNumberArray(data.spacing)
  const orientation = toStringValue(data.orientation)
  if (dtype) parts.push(`dtype: ${dtype}`)
  if (shape) parts.push(`shape: ${shape}`)
  if (spacing) parts.push(`spacing: ${spacing}`)
  if (orientation) parts.push(`orient: ${orientation}`)
  if (!parts.length) return 'Metadata available.'
  return parts.slice(0, 3).join(' | ')
}

function renderMetadataDetails(item: CaseRecord, key: string): ReactNode {
  const meta = item.metadata_json?.[key]
  if (!meta || typeof meta !== 'object') {
    return <div className="empty-state">No metadata available.</div>
  }

  const data = meta as Record<string, unknown>
  const dtype = toStringValue(data.dtype) ?? '-'
  const shape = formatNumberArray(data.shape) ?? '-'
  const spacing = formatNumberArray(data.spacing) ?? '-'
  const orientation = toStringValue(data.orientation) ?? '-'
  const affine = Array.isArray(data.affine) ? (data.affine as number[][]) : null

  const knownKeys = new Set(['dtype', 'shape', 'spacing', 'orientation', 'affine'])
  const extra = Object.entries(data).filter(([k]) => !knownKeys.has(k))

  return (
    <div className="metadata-detail">
      <div className="metadata-grid">
        <div className="meta-card">
          <div className="meta-label">dtype</div>
          <div className="meta-value">{dtype}</div>
        </div>
        <div className="meta-card">
          <div className="meta-label">shape</div>
          <div className="meta-value">{shape}</div>
        </div>
        <div className="meta-card">
          <div className="meta-label">spacing</div>
          <div className="meta-value">{spacing}</div>
        </div>
        <div className="meta-card">
          <div className="meta-label">orientation</div>
          <div className="meta-value">{orientation}</div>
        </div>
      </div>

      {affine && (
        <div className="affine-block">
          <div className="meta-label">affine</div>
          <div className="affine-table">
            {affine.map((row, rowIdx) => (
              <div key={`${rowIdx}-${key}`} className="affine-row">
                {row.map((value, colIdx) => (
                  <span key={`${rowIdx}-${colIdx}`} className="affine-cell">
                    {formatNumber(value)}
                  </span>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}

      {extra.length > 0 && (
        <div className="extra-block">
          <div className="meta-label">other fields</div>
          <div className="extra-grid">
            {extra.map(([field, value]) => (
              <div key={field} className="extra-item">
                <span className="extra-key">{field}</span>
                <span className="extra-value">{String(value)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <details className="raw-json">
        <summary>Raw JSON</summary>
        <pre>{safeStringify(meta)}</pre>
      </details>
    </div>
  )
}

function safeStringify(value: unknown) {
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function toStringValue(value: unknown) {
  if (typeof value === 'string') return value
  if (typeof value === 'number') return String(value)
  return null
}

function formatNumberArray(value: unknown) {
  if (!Array.isArray(value)) return null
  const parts = value.map((item) => formatNumber(item))
  return parts.join(' x ')
}

function formatNumber(value: unknown) {
  if (typeof value === 'number') return value.toFixed(3).replace(/\.?0+$/, '')
  return String(value)
}

function shortId(id: string) {
  if (id.length <= 10) return id
  return `${id.slice(0, 8)}...${id.slice(-4)}`
}

function formatDate(value?: string, includeTime = false) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.valueOf())) return value
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: '2-digit',
    year: 'numeric',
    hour: includeTime ? '2-digit' : undefined,
    minute: includeTime ? '2-digit' : undefined,
  }).format(date)
}

function getRelativePath(file: File) {
  const rel = (file as File & { webkitRelativePath?: string }).webkitRelativePath
  return rel && rel.length > 0 ? rel : file.name
}

function buildBulkGroups(files: File[]): BulkCaseGroup[] {
  const grouped = new Map<string, File[]>()
  const firstPath = files[0] ? getRelativePath(files[0]) : ''
  const rootCandidate = firstPath.split('/')[0]
  const hasCommonRoot = files.every((file) => {
    const rel = getRelativePath(file)
    return rel.split('/')[0] === rootCandidate
  })

  files.forEach((file) => {
    const relPath = getRelativePath(file)
    const parts = relPath.split('/')
    const folder = hasCommonRoot && parts.length > 1 ? parts[1] : parts[0] || 'Unnamed'
    const list = grouped.get(folder) ?? []
    list.push(file)
    grouped.set(folder, list)
  })
  return Array.from(grouped.entries()).map(([id, groupFiles]) => ({
    id,
    displayName: id,
    files: groupFiles,
  }))
}

function buildGifUrl(caseId: string, modality: string, axis: 'x' | 'y' | 'z') {
  const mod = encodeURIComponent(modality)
  return `${API_BASE}/cases/${caseId}/preview?axis=${axis}&preview_index=all&modality=${mod}`
}

function formatTumorStatus(value?: string | null) {
  if (!value) return 'Undetermined'
  const normalized = value.toUpperCase()
  if (normalized === 'YES' || normalized === 'NO' || normalized === 'UNDETERMINED') {
    return normalized.charAt(0) + normalized.slice(1).toLowerCase()
  }
  return value
}

function getTumorStatusKey(value?: string | null) {
  if (!value) return 'undetermined'
  const normalized = value.toLowerCase()
  if (normalized === 'yes' || normalized === 'no' || normalized === 'undetermined') {
    return normalized
  }
  return 'undetermined'
}

function hasCaseDetail(item: CaseRecord) {
  return (
    item.source_uris !== undefined &&
    item.metadata_json !== undefined &&
    item.metadata_statuses !== undefined
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

function sleepMs(ms: number) {
  return new Promise<void>((resolve) => {
    window.setTimeout(resolve, ms)
  })
}

async function postStringPayload(caseId: string, action: 'rename' | 'add_note', value: string) {
  const response = await fetch(`${API_BASE}/ingest/${caseId}/${action}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ str_input: value }),
  })
  if (!response.ok) {
    let detail = 'Request failed'
    try {
      const data = (await response.json()) as { detail?: string }
      if (data?.detail) detail = data.detail
    } catch {
      // ignore
    }
    throw new Error(detail)
  }
  return response
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

export default App
