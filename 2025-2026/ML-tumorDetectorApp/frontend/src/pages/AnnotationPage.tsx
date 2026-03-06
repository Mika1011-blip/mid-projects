import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'

import { LoaderOverlay } from '../components/LoaderOverlay'
import {
  MeshViewport,
  type MeshLayerPayload,
} from '../components/MeshViewport'
import { ThemeToggle } from '../components/ThemeToggle'

type Theme = 'light' | 'dark'
type Axis = 'x' | 'y' | 'z'
type Basis = [[number, number, number], [number, number, number], [number, number, number]]

type FrontendVolume = {
  shape: [number, number, number]
  data: Float32Array
  min: number
  max: number
}

type FrontendMaskVolume = {
  shape: [number, number, number]
  data: Uint8Array
}

type MeshResponse = {
  case_id: string
  run_pipeline_0?: boolean
  user_overlay_modality?: string | null
  base_layers: MeshLayerPayload[]
  overlay_layers: MeshLayerPayload[]
  external_overlays?: Record<string, null>
  missing_modalities?: string[]
  missing_overlays?: string[]
  skipped_modalities?: string[]
  skipped_overlays?: string[]
  detail?: string
}

type AnnotationMaskResponse = {
  case_id: string
  modality: string
  shape: number[]
  representation: 'dense' | 'sparse'
  nnz: number
  applied_layers_count: number
  redo_layers_count: number
  indices?: number[][]
  volume?: unknown
  detail?: string
}

type AnnotationApplyResponse = {
  detail?: string
  nnz?: number
  slices_received?: number
  applied_layers_count?: number
  redo_layers_count?: number
}

type AnnotationHistoryResponse = {
  detail?: string
  nnz?: number
  applied_layers_count?: number
  redo_layers_count?: number
}

type AnnotationMaskMeshResponse = {
  case_id: string
  modality: string
  nnz?: number
  layer?: MeshLayerPayload
  detail?: string
}

type AnnotationMaskSummary = {
  nnz: number
  appliedLayersCount: number
  redoLayersCount: number
}

type AppliedMaskState = {
  summary: AnnotationMaskSummary
  volume: FrontendMaskVolume | null
}

type VolumeApiPayload = {
  case_id: string
  run_pipeline_0?: boolean
  available_modalities?: string[]
  missing_modalities?: string[]
  modalities?: Record<
    string,
    {
      shape?: number[]
      volume?: unknown
    }
  >
  detail?: string
}

const BASE_MODALITY_PRIORITY = ['T1CE', 'FLAIR', 'T1', 'T2']
const ALL_OVERLAY_OPTIONS = ['SEG', 'USER', 'MODEL']
const MESH_OVERLAYS_QUERY = 'SEG,MODEL'
const MESH_DOWNSAMPLE = 2
const HEAVY_REQUEST_TIMEOUT_MS = 180000
const ANNOTATION_SLICE_AXIS: Axis = 'z'
const CURRENT_MASK_RGB: [number, number, number] = [245, 158, 11]
const APPLIED_MASK_RGB: [number, number, number] = [59, 130, 246]
const APPLIED_MASK_ALPHA = 77
const EMPTY_MASK_SUMMARY: AnnotationMaskSummary = {
  nnz: 0,
  appliedLayersCount: 0,
  redoLayersCount: 0,
}
const IDENTITY_BASIS: Basis = [
  [1, 0, 0],
  [0, 1, 0],
  [0, 0, 1],
]
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
  const [volumeByModality, setVolumeByModality] = useState<Record<string, FrontendVolume>>({})
  const [volumeLoading, setVolumeLoading] = useState(false)
  const [volumeError, setVolumeError] = useState<string | null>(null)
  const [viewBasis, setViewBasis] = useState<Basis>(() => cloneBasis(IDENTITY_BASIS))
  const [sliceCount, setSliceCount] = useState(0)
  const [sliceIndex, setSliceIndex] = useState(0)
  const [sliceImageUrl, setSliceImageUrl] = useState<string | null>(null)
  const [baseSliceThumbUrls, setBaseSliceThumbUrls] = useState<string[]>([])
  const [sliceThumbUrls, setSliceThumbUrls] = useState<string[]>([])
  const [sliceLoading, setSliceLoading] = useState(false)
  const [sliceError, setSliceError] = useState<string | null>(null)
  const [sliceApplyLoading, setSliceApplyLoading] = useState(false)
  const [sliceApplyMessage, setSliceApplyMessage] = useState<string | null>(null)
  const [historyActionLoading, setHistoryActionLoading] = useState(false)
  const [userMeshLoading, setUserMeshLoading] = useState(false)
  const [appliedMaskSummary, setAppliedMaskSummary] = useState<AnnotationMaskSummary>(EMPTY_MASK_SUMMARY)
  const [maskStatusLoading, setMaskStatusLoading] = useState(false)
  const [maskStatusError, setMaskStatusError] = useState<string | null>(null)
  const [brushSize, setBrushSize] = useState(10)
  const [brushOpacity, setBrushOpacity] = useState(0.7)
  const [annotationRevision, setAnnotationRevision] = useState(0)
  const [appliedAnnotationRevision, setAppliedAnnotationRevision] = useState(0)
  const heavyRequestTimeoutMs = Math.max(requestTimeoutMs, HEAVY_REQUEST_TIMEOUT_MS)
  const rotationTrackingLabel = useMemo(
    () => describeViewBasisFromOriginal(viewBasis),
    [viewBasis],
  )
  const isViewAtOriginal = useMemo(() => isSameBasis(viewBasis, IDENTITY_BASIS), [viewBasis])

  const sliceImageRef = useRef<HTMLImageElement | null>(null)
  const drawCanvasRef = useRef<HTMLCanvasElement | null>(null)
  const annotationMaskRef = useRef<FrontendMaskVolume | null>(null)
  const appliedAnnotationMaskRef = useRef<FrontendMaskVolume | null>(null)
  const drawingRef = useRef(false)
  const lastPointRef = useRef<{ x: number; y: number } | null>(null)

  const fetchMeshData = useCallback(
    async (targetCaseId: string) => {
      const params = new URLSearchParams({
        overlays: MESH_OVERLAYS_QUERY,
        downsample: String(MESH_DOWNSAMPLE),
        run_pipeline_0: 'false',
      })
      const response = await fetchWithTimeout(
        `${apiBase}/visualize/${encodeURIComponent(targetCaseId)}/meshes?${params.toString()}`,
        heavyRequestTimeoutMs,
      )
      const data = (await response.json().catch(() => ({}))) as MeshResponse
      if (!response.ok) {
        throw new Error(data.detail ?? `HTTP ${response.status}`)
      }
      return data
    },
    [apiBase, heavyRequestTimeoutMs],
  )

  const setAppliedMaskVolume = useCallback((nextVolume: FrontendMaskVolume | null) => {
    appliedAnnotationMaskRef.current = nextVolume
    setAppliedAnnotationRevision((prev) => prev + 1)
  }, [])

  const fetchAppliedMaskState = useCallback(
    async (targetCaseId: string, targetModality: string): Promise<AppliedMaskState> => {
      const response = await fetchWithTimeout(
        `${apiBase}/annotation/mask/${encodeURIComponent(targetCaseId)}?modality=${encodeURIComponent(
          targetModality,
        )}&representation=sparse`,
        requestTimeoutMs,
      )
      const data = (await response.json().catch(() => ({}))) as AnnotationMaskResponse
      if (response.status === 404) {
        return {
          summary: EMPTY_MASK_SUMMARY,
          volume: null,
        }
      }
      if (!response.ok) {
        throw new Error(data.detail ?? `HTTP ${response.status}`)
      }
      const summary: AnnotationMaskSummary = {
        nnz: Number(data.nnz ?? 0),
        appliedLayersCount: Number(data.applied_layers_count ?? 0),
        redoLayersCount: Number(data.redo_layers_count ?? 0),
      }
      let volume: FrontendMaskVolume | null = null
      try {
        volume = buildMaskVolumeFromSparse(data.shape, data.indices ?? [])
      } catch {
        volume = null
      }
      return { summary, volume }
    },
    [apiBase, requestTimeoutMs],
  )

  const removeUserOverlayFromMeshData = useCallback(() => {
    setMeshData((prev) => {
      if (!prev) return prev
      const filteredOverlays = prev.overlay_layers.filter((layer) => {
        const key = extractModalityFromLayerName(layer.name).toUpperCase()
        return key !== 'USER' && layer.name.toUpperCase() !== 'USER'
      })
      return {
        ...prev,
        overlay_layers: filteredOverlays,
        user_overlay_modality: null,
      }
    })
    setSelectedOverlay((prev) => (prev === 'USER' ? 'NONE' : prev))
  }, [])

  useEffect(() => {
    setResolvedDisplayName(caseDisplayName?.trim() || 'Unnamed')
  }, [caseDisplayName, caseId])

  useEffect(() => {
    if (!caseId) {
      setMeshData(null)
      setError(null)
      setLoading(false)
      setUserMeshLoading(false)
      setMaskStatusLoading(false)
      setMaskStatusError(null)
      setAppliedMaskSummary(EMPTY_MASK_SUMMARY)
      setAppliedMaskVolume(null)
      setCopiedCaseIdHint(false)
      setResolvedDisplayName('Unnamed')
      return
    }

    let cancelled = false

    const loadMeshes = async () => {
      setLoading(true)
      setError(null)
      try {
        const data = await fetchMeshData(caseId)
        if (!cancelled) {
          setMeshData(data)
          setError(null)
        }
      } catch (err) {
        if (!cancelled) {
          setMeshData(null)
          if (isAbortError(err)) {
            setError(`Mesh request timed out after ${Math.round(heavyRequestTimeoutMs / 1000)}s.`)
          } else {
            setError(err instanceof Error ? err.message : 'Failed to load mesh data.')
          }
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
  }, [caseId, fetchMeshData, heavyRequestTimeoutMs])

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

  useEffect(() => {
    if (!caseId) {
      setVolumeByModality({})
      setVolumeLoading(false)
      setVolumeError(null)
      setUserMeshLoading(false)
      setAppliedMaskSummary(EMPTY_MASK_SUMMARY)
      setAppliedMaskVolume(null)
      setMaskStatusError(null)
      setMaskStatusLoading(false)
      setViewBasis(cloneBasis(IDENTITY_BASIS))
      return
    }
    setVolumeByModality({})
    setVolumeLoading(false)
    setVolumeError(null)
    setUserMeshLoading(false)
    setAppliedMaskSummary(EMPTY_MASK_SUMMARY)
    setAppliedMaskVolume(null)
    setMaskStatusError(null)
    setMaskStatusLoading(false)
    setViewBasis(cloneBasis(IDENTITY_BASIS))
  }, [caseId])

  useEffect(() => {
    if (!caseId || !selectedBase) {
      return
    }
    const modalityKey = selectedBase.toUpperCase()
    if (volumeByModality[modalityKey]) {
      return
    }

    let cancelled = false
    const loadSelectedVolume = async () => {
      setVolumeLoading(true)
      setVolumeError(null)
      try {
        const response = await fetchWithTimeout(
          `${apiBase}/annotation/get_volume/${encodeURIComponent(caseId)}?run_pipeline_0=true&modality=${encodeURIComponent(modalityKey)}`,
          heavyRequestTimeoutMs,
        )
        const payload = (await response.json().catch(() => ({}))) as VolumeApiPayload
        if (!response.ok) {
          throw new Error(payload.detail ?? `HTTP ${response.status}`)
        }

        const rawModalities = payload.modalities ?? {}
        const selected = rawModalities[modalityKey]
        if (!selected?.shape || !selected?.volume) {
          throw new Error(`No 3D volume returned for modality ${modalityKey}.`)
        }
        const parsedVolume = parseFrontendVolume(selected.shape, selected.volume)

        if (!cancelled) {
          setVolumeByModality((prev) => ({ ...prev, [modalityKey]: parsedVolume }))
        }
      } catch (err) {
        if (!cancelled) {
          if (isAbortError(err)) {
            setVolumeError(`Volume request timed out after ${Math.round(heavyRequestTimeoutMs / 1000)}s.`)
          } else {
            setVolumeError(err instanceof Error ? err.message : `Failed to load 3D volume for ${modalityKey}.`)
          }
        }
      } finally {
        if (!cancelled) {
          setVolumeLoading(false)
        }
      }
    }

    void loadSelectedVolume()
    return () => {
      cancelled = true
    }
  }, [apiBase, caseId, selectedBase, volumeByModality, heavyRequestTimeoutMs])

  const availableBaseModalities = useMemo(() => {
    if (meshData) {
      const meshModalities = meshData.base_layers
        .map((layer) => layer.modality?.toUpperCase() ?? extractModalityFromLayerName(layer.name))
        .filter((value): value is string => Boolean(value))
      if (meshModalities.length) {
        return Array.from(new Set(meshModalities))
      }
    }
    const loadedModalities = Object.keys(volumeByModality).map((item) => item.toUpperCase())
    return Array.from(new Set(loadedModalities))
  }, [meshData, volumeByModality])

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

  useEffect(() => {
    if (!caseId || !selectedBase) {
      setMaskStatusLoading(false)
      setMaskStatusError(null)
      setAppliedMaskSummary(EMPTY_MASK_SUMMARY)
      setAppliedMaskVolume(null)
      return
    }
    let cancelled = false
    const loadMaskSummary = async () => {
      setMaskStatusLoading(true)
      setAppliedMaskSummary(EMPTY_MASK_SUMMARY)
      setAppliedMaskVolume(null)
      try {
        const state = await fetchAppliedMaskState(caseId, selectedBase)
        if (!cancelled) {
          setAppliedMaskSummary(state.summary)
          setAppliedMaskVolume(state.volume)
          setMaskStatusError(null)
        }
      } catch (err) {
        if (!cancelled) {
          setAppliedMaskSummary(EMPTY_MASK_SUMMARY)
          setAppliedMaskVolume(null)
          if (isAbortError(err)) {
            setMaskStatusError(`Mask request timed out after ${Math.round(requestTimeoutMs / 1000)}s.`)
          } else {
            setMaskStatusError(err instanceof Error ? err.message : 'Failed to fetch merged annotation mask.')
          }
        }
      } finally {
        if (!cancelled) {
          setMaskStatusLoading(false)
        }
      }
    }
    void loadMaskSummary()
    return () => {
      cancelled = true
    }
  }, [caseId, fetchAppliedMaskState, requestTimeoutMs, selectedBase, setAppliedMaskVolume])

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
  const activeVolume = useMemo(() => {
    const key = selectedBase.toUpperCase()
    return volumeByModality[key] ?? null
  }, [selectedBase, volumeByModality])
  const viewShape = useMemo(() => (activeVolume ? getViewShape(activeVolume.shape, viewBasis) : null), [activeVolume, viewBasis])
  const sliceIndices = useMemo(() => Array.from({ length: sliceCount }, (_, idx) => idx), [sliceCount])

  useEffect(() => {
    if (!activeVolume) {
      annotationMaskRef.current = null
      setAnnotationRevision(0)
      return
    }
    const [sx, sy, sz] = activeVolume.shape
    annotationMaskRef.current = {
      shape: [sx, sy, sz],
      data: new Uint8Array(sx * sy * sz),
    }
    setAnnotationRevision((prev) => prev + 1)
  }, [activeVolume, selectedBase, caseId])

  useEffect(() => {
    // Switching base modality starts a fresh annotation volume.
    setSliceApplyMessage(null)
  }, [selectedBase])

  useEffect(() => {
    if (!activeVolume || !viewShape) {
      setSliceCount(0)
      setSliceIndex(0)
      setSliceImageUrl(null)
      setBaseSliceThumbUrls([])
      setSliceThumbUrls([])
      setSliceError(volumeError)
      setSliceLoading(false)
      return
    }

    const axisDim = axisToDim(ANNOTATION_SLICE_AXIS)
    const count = Math.max(0, viewShape[axisDim] ?? 0)
    setSliceCount(count)
    setSliceIndex((prev) => clamp(prev, 0, Math.max(0, count - 1)))
    if (count <= 0) {
      setSliceError('No slices available for selected modality.')
      setSliceImageUrl(null)
      setBaseSliceThumbUrls([])
      setSliceThumbUrls([])
    } else {
      setSliceError(volumeError)
    }
  }, [activeVolume, viewShape, volumeError])

  useEffect(() => {
    if (!activeVolume || !viewShape || sliceCount <= 0) {
      setSliceImageUrl(null)
      setSliceLoading(false)
      return
    }
    try {
      setSliceLoading(true)
      const imageUrl = renderSliceDataUrl(activeVolume, viewBasis, ANNOTATION_SLICE_AXIS, sliceIndex)
      setSliceImageUrl(imageUrl)
      setSliceError(volumeError)
    } catch (err) {
      setSliceImageUrl(null)
      setSliceError(err instanceof Error ? err.message : 'Failed to render slice image from 3D volume.')
    } finally {
      setSliceLoading(false)
    }
  }, [activeVolume, viewBasis, sliceIndex, sliceCount, volumeError, viewShape])

  useEffect(() => {
    if (!activeVolume || !viewShape || sliceCount <= 0) {
      setBaseSliceThumbUrls([])
      return
    }
    try {
      const thumbs = sliceIndices.map((idx) =>
        renderBaseSliceThumbDataUrl(activeVolume, viewBasis, ANNOTATION_SLICE_AXIS, idx),
      )
      setBaseSliceThumbUrls(thumbs)
    } catch {
      setBaseSliceThumbUrls([])
    }
  }, [activeVolume, viewBasis, sliceCount, sliceIndices, viewShape])

  useEffect(() => {
    const activeMask = annotationMaskRef.current
    const appliedMask = appliedAnnotationMaskRef.current
    if (!activeVolume || !viewShape || sliceCount <= 0 || (!activeMask && !appliedMask)) {
      setSliceThumbUrls([])
      return
    }
    try {
      const thumbs = sliceIndices.map((idx) =>
        renderCombinedMaskSliceThumbDataUrl(
          activeMask,
          appliedMask,
          viewBasis,
          ANNOTATION_SLICE_AXIS,
          idx,
        ),
      )
      setSliceThumbUrls(thumbs)
    } catch {
      setSliceThumbUrls([])
    }
  }, [activeVolume, viewBasis, sliceCount, sliceIndices, viewShape, annotationRevision, appliedAnnotationRevision])

  const clearCanvasPixels = () => {
    const canvas = drawCanvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.clearRect(0, 0, canvas.width, canvas.height)
  }

  const syncDrawingCanvas = () => {
    const image = sliceImageRef.current
    const canvas = drawCanvasRef.current
    if (!image || !canvas) return
    const width = Math.max(1, Math.round(image.naturalWidth || image.clientWidth))
    const height = Math.max(1, Math.round(image.naturalHeight || image.clientHeight))
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width
      canvas.height = height
    }
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.lineCap = 'round'
    ctx.lineJoin = 'round'
    ctx.strokeStyle = `rgba(${CURRENT_MASK_RGB[0]}, ${CURRENT_MASK_RGB[1]}, ${CURRENT_MASK_RGB[2]}, ${brushOpacity})`
    ctx.fillStyle = `rgba(${CURRENT_MASK_RGB[0]}, ${CURRENT_MASK_RGB[1]}, ${CURRENT_MASK_RGB[2]}, ${brushOpacity})`
    ctx.lineWidth = brushSize
  }

  const paintAnnotationSliceOnCanvas = () => {
    const canvas = drawCanvasRef.current
    const activeMask = annotationMaskRef.current
    const appliedMask = appliedAnnotationMaskRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    clearCanvasPixels()
    if (!activeVolume) return
    if (!activeMask && !appliedMask) return

    const renderShape = activeMask?.shape ?? appliedMask?.shape
    if (!renderShape) return
    const [sx, sy, sz] = renderShape
    const viewDims = getViewShape([sx, sy, sz], viewBasis)
    const axisDim = axisToDim(ANNOTATION_SLICE_AXIS)
    const [rowDim, colDim] = planeDimsForAxis(ANNOTATION_SLICE_AXIS)
    const viewK = clamp(sliceIndex, 0, Math.max(0, viewDims[axisDim] - 1))
    const height = canvas.height
    const width = canvas.width
    const srcHeight = Math.max(1, viewDims[rowDim])
    const srcWidth = Math.max(1, viewDims[colDim])
    const image = new ImageData(width, height)
    const currentAlpha = Math.round(255 * brushOpacity)

    for (let r = 0; r < height; r += 1) {
      const srcR = Math.min(srcHeight - 1, Math.floor((r / Math.max(height, 1)) * srcHeight))
      for (let c = 0; c < width; c += 1) {
        const srcC = Math.min(srcWidth - 1, Math.floor((c / Math.max(width, 1)) * srcWidth))
        const viewCoord: [number, number, number] = [0, 0, 0]
        viewCoord[axisDim] = viewK
        viewCoord[rowDim] = srcR
        viewCoord[colDim] = srcC
        const [cx, cy, cz] = viewToCanonicalCoord(viewCoord, renderShape, viewBasis)
        const flat = (cx * sy + cy) * sz + cz
        const appliedOn = Boolean(appliedMask && isMaskVoxelOn(appliedMask, flat))
        const currentOn = Boolean(activeMask && isMaskVoxelOn(activeMask, flat))
        if (appliedOn || currentOn) {
          const out = (r * width + c) * 4
          if (appliedOn) {
            image.data[out] = APPLIED_MASK_RGB[0]
            image.data[out + 1] = APPLIED_MASK_RGB[1]
            image.data[out + 2] = APPLIED_MASK_RGB[2]
            image.data[out + 3] = APPLIED_MASK_ALPHA
          }
          if (currentOn) {
            image.data[out] = CURRENT_MASK_RGB[0]
            image.data[out + 1] = CURRENT_MASK_RGB[1]
            image.data[out + 2] = CURRENT_MASK_RGB[2]
            image.data[out + 3] = currentAlpha
          }
        }
      }
    }
    ctx.putImageData(image, 0, 0)
  }

  const commitCanvasToAnnotationVolume = () => {
    const canvas = drawCanvasRef.current
    const activeMask = annotationMaskRef.current
    if (!canvas || !activeMask || !activeVolume) return false
    const ctx = canvas.getContext('2d')
    if (!ctx) return false

    const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height)
    const [sx, sy, sz] = activeMask.shape
    const viewDims = getViewShape([sx, sy, sz], viewBasis)
    const axisDim = axisToDim(ANNOTATION_SLICE_AXIS)
    const [rowDim, colDim] = planeDimsForAxis(ANNOTATION_SLICE_AXIS)
    const viewK = clamp(sliceIndex, 0, Math.max(0, viewDims[axisDim] - 1))
    const height = canvas.height
    const width = canvas.width
    const srcHeight = Math.max(1, viewDims[rowDim])
    const srcWidth = Math.max(1, viewDims[colDim])

    let changed = false
    for (let r = 0; r < height; r += 1) {
      const srcR = Math.min(srcHeight - 1, Math.floor((r / Math.max(height, 1)) * srcHeight))
      for (let c = 0; c < width; c += 1) {
        const pixelOffset = (r * width + c) * 4
        const red = imageData.data[pixelOffset] ?? 0
        const green = imageData.data[pixelOffset + 1] ?? 0
        const blue = imageData.data[pixelOffset + 2] ?? 0
        const alpha = imageData.data[(r * width + c) * 4 + 3] ?? 0
        if (alpha <= 0) continue
        // Ignore blue applied-mask overlay; commit only current orange strokes.
        const looksLikeCurrentMask = red >= 120 && green >= 80 && red > blue
        if (!looksLikeCurrentMask) continue
        const srcC = Math.min(srcWidth - 1, Math.floor((c / Math.max(width, 1)) * srcWidth))
        const viewCoord: [number, number, number] = [0, 0, 0]
        viewCoord[axisDim] = viewK
        viewCoord[rowDim] = srcR
        viewCoord[colDim] = srcC
        const [cx, cy, cz] = viewToCanonicalCoord(viewCoord, activeMask.shape, viewBasis)
        const flat = (cx * sy + cy) * sz + cz
        if (activeMask.data[flat] === 0) {
          activeMask.data[flat] = 1
          changed = true
        }
      }
    }
    if (changed) {
      setAnnotationRevision((prev) => prev + 1)
    }
    return changed
  }

  const resetAnnotationMaskVolume = () => {
    const activeMask = annotationMaskRef.current
    if (!activeMask) return
    activeMask.data.fill(0)
    setAnnotationRevision((prev) => prev + 1)
  }

  const clearCurrentSliceMask = () => {
    resetAnnotationMaskVolume()
    paintAnnotationSliceOnCanvas()
  }

  useEffect(() => {
    syncDrawingCanvas()
    paintAnnotationSliceOnCanvas()
  }, [brushSize, brushOpacity, sliceImageUrl, viewBasis, sliceIndex, annotationRevision, appliedAnnotationRevision, selectedBase])

  useEffect(() => {
    setSliceApplyMessage(null)
  }, [viewBasis, selectedBase, annotationRevision])

  const toCanvasPoint = (event: ReactPointerEvent<HTMLCanvasElement>) => {
    const canvas = event.currentTarget
    const rect = canvas.getBoundingClientRect()
    const scaleX = canvas.width / Math.max(rect.width, 1)
    const scaleY = canvas.height / Math.max(rect.height, 1)
    return {
      x: (event.clientX - rect.left) * scaleX,
      y: (event.clientY - rect.top) * scaleY,
    }
  }

  const drawSegment = (from: { x: number; y: number }, to: { x: number; y: number }) => {
    const canvas = drawCanvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.beginPath()
    ctx.moveTo(from.x, from.y)
    ctx.lineTo(to.x, to.y)
    ctx.stroke()
  }

  const startDrawing = (event: ReactPointerEvent<HTMLCanvasElement>) => {
    if (!sliceImageUrl) return
    syncDrawingCanvas()
    const point = toCanvasPoint(event)
    drawingRef.current = true
    lastPointRef.current = point
    event.currentTarget.setPointerCapture(event.pointerId)

    const canvas = drawCanvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.beginPath()
    ctx.arc(point.x, point.y, Math.max(brushSize / 2, 1), 0, Math.PI * 2)
    ctx.fill()
  }

  const continueDrawing = (event: ReactPointerEvent<HTMLCanvasElement>) => {
    if (!drawingRef.current) return
    const point = toCanvasPoint(event)
    const last = lastPointRef.current ?? point
    drawSegment(last, point)
    lastPointRef.current = point
  }

  const stopDrawing = (event: ReactPointerEvent<HTMLCanvasElement>) => {
    drawingRef.current = false
    lastPointRef.current = null
    commitCanvasToAnnotationVolume()
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId)
    }
  }

  const handleRotateLeft = () => {
    setViewBasis((prev) => rotateBasis(prev, 'left'))
  }

  const handleRotateRight = () => {
    setViewBasis((prev) => rotateBasis(prev, 'right'))
  }

  const handleRotateUp = () => {
    setViewBasis((prev) => rotateBasis(prev, 'up'))
  }

  const handleRotateDown = () => {
    setViewBasis((prev) => rotateBasis(prev, 'down'))
  }

  const handleResetRotation = () => {
    setViewBasis(cloneBasis(IDENTITY_BASIS))
  }

  const refreshAppliedStateAfterMutation = useCallback(
    async (targetCaseId: string, targetModality: string) => {
      const state = await fetchAppliedMaskState(targetCaseId, targetModality)
      setAppliedMaskSummary(state.summary)
      setAppliedMaskVolume(state.volume)
      setMaskStatusError(null)
      removeUserOverlayFromMeshData()
    },
    [fetchAppliedMaskState, removeUserOverlayFromMeshData, setAppliedMaskVolume],
  )

  const handleGenerateUserMesh = async () => {
    if (!caseId || !selectedBase) return
    setUserMeshLoading(true)
    setSliceApplyMessage(null)
    try {
      const response = await fetchWithTimeout(
        `${apiBase}/annotation/mask/${encodeURIComponent(caseId)}/mesh?modality=${encodeURIComponent(
          selectedBase,
        )}&downsample=${MESH_DOWNSAMPLE}&run_pipeline_0=false`,
        heavyRequestTimeoutMs,
      )
      const data = (await response.json().catch(() => ({}))) as AnnotationMaskMeshResponse
      if (!response.ok) {
        throw new Error(data.detail ?? `HTTP ${response.status}`)
      }
      if (!data.layer) {
        throw new Error('Invalid USER mesh response.')
      }

      setMeshData((prev) => {
        if (!prev) return prev
        const filteredOverlays = prev.overlay_layers.filter((layer) => {
          const key = extractModalityFromLayerName(layer.name).toUpperCase()
          return key !== 'USER' && layer.name.toUpperCase() !== 'USER'
        })
        return {
          ...prev,
          overlay_layers: [...filteredOverlays, data.layer as MeshLayerPayload],
          user_overlay_modality: data.modality?.toUpperCase() ?? selectedBase,
        }
      })
      setSelectedOverlay('USER')
      setSliceApplyMessage(`Generated USER mesh for ${selectedBase} (${data.nnz ?? 0} voxels).`)
    } catch (err) {
      setSliceApplyMessage(err instanceof Error ? err.message : 'Failed to generate USER annotation mesh.')
    } finally {
      setUserMeshLoading(false)
    }
  }

  const handleApplySlice = async () => {
    if (!caseId || !selectedBase) return
    commitCanvasToAnnotationVolume()
    const activeMask = annotationMaskRef.current
    if (!activeMask) {
      setSliceApplyMessage('Mask volume is not initialized.')
      return
    }
    const annotationSlices = extractAnnotationSlicesPayload(activeMask)
    if (!annotationSlices.length) {
      setSliceApplyMessage('Nothing to apply. Draw on the slice first.')
      return
    }

    setSliceApplyLoading(true)
    setSliceApplyMessage(null)
    try {
      const response = await fetchWithTimeout(
        `${apiBase}/annotation/apply/${encodeURIComponent(caseId)}`,
        requestTimeoutMs,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            modality: selectedBase,
            axis: ANNOTATION_SLICE_AXIS,
            k: sliceIndex,
            rot90: 0,
            flip_x: false,
            flip_y: false,
            view_basis: viewBasis,
            width: 1,
            height: 1,
            rle: [],
            annotation_shape: activeMask.shape,
            annotation_slices: annotationSlices,
          }),
        },
      )
      const data = (await response.json().catch(() => ({}))) as AnnotationApplyResponse
      if (!response.ok) {
        throw new Error(data.detail ?? `HTTP ${response.status}`)
      }
      await refreshAppliedStateAfterMutation(caseId, selectedBase)
      setSliceApplyMessage(
        `Applied full mask (${data.nnz ?? 0} voxels across ${data.slices_received ?? annotationSlices.length} slices). Layers: ${data.applied_layers_count ?? appliedMaskSummary.appliedLayersCount}.`,
      )
      resetAnnotationMaskVolume()
      paintAnnotationSliceOnCanvas()
    } catch (err) {
      setSliceApplyMessage(err instanceof Error ? err.message : 'Failed to apply slice annotation.')
    } finally {
      setSliceApplyLoading(false)
    }
  }

  const handleUndoLayer = async () => {
    if (!caseId || !selectedBase) return
    setHistoryActionLoading(true)
    setSliceApplyMessage(null)
    try {
      const response = await fetchWithTimeout(
        `${apiBase}/annotation/undo/${encodeURIComponent(caseId)}?modality=${encodeURIComponent(selectedBase)}`,
        requestTimeoutMs,
        { method: 'POST' },
      )
      const data = (await response.json().catch(() => ({}))) as AnnotationHistoryResponse
      if (!response.ok) {
        throw new Error(data.detail ?? `HTTP ${response.status}`)
      }
      await refreshAppliedStateAfterMutation(caseId, selectedBase)
      setSliceApplyMessage(
        `Undo complete. Applied layers: ${data.applied_layers_count ?? 0}. Redo layers: ${data.redo_layers_count ?? 0}.`,
      )
    } catch (err) {
      setSliceApplyMessage(err instanceof Error ? err.message : 'Failed to undo annotation layer.')
    } finally {
      setHistoryActionLoading(false)
    }
  }

  const handleRedoLayer = async () => {
    if (!caseId || !selectedBase) return
    setHistoryActionLoading(true)
    setSliceApplyMessage(null)
    try {
      const response = await fetchWithTimeout(
        `${apiBase}/annotation/redo/${encodeURIComponent(caseId)}?modality=${encodeURIComponent(selectedBase)}`,
        requestTimeoutMs,
        { method: 'POST' },
      )
      const data = (await response.json().catch(() => ({}))) as AnnotationHistoryResponse
      if (!response.ok) {
        throw new Error(data.detail ?? `HTTP ${response.status}`)
      }
      await refreshAppliedStateAfterMutation(caseId, selectedBase)
      setSliceApplyMessage(
        `Redo complete. Applied layers: ${data.applied_layers_count ?? 0}. Redo layers: ${data.redo_layers_count ?? 0}.`,
      )
    } catch (err) {
      setSliceApplyMessage(err instanceof Error ? err.message : 'Failed to redo annotation layer.')
    } finally {
      setHistoryActionLoading(false)
    }
  }

  const sliceBusy = sliceLoading || volumeLoading || maskStatusLoading || userMeshLoading

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
                        Copy
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
            {!error && volumeError && <div className="sidebar-error">{volumeError}</div>}
            {!error && !volumeError && maskStatusError && <div className="sidebar-error">{maskStatusError}</div>}
            {!error && selectedBase && !maskStatusError && (
              <div className="sidebar-note">
                Applied mask ({selectedBase}): {appliedMaskSummary.nnz} voxels | layers {appliedMaskSummary.appliedLayersCount} | redo {appliedMaskSummary.redoLayersCount}
              </div>
            )}
            {!error && selectedBase && (
              <div className="sidebar-note">
                Overlay colors: current draft = orange, applied history = blue.
              </div>
            )}
            {!error && overlayIsExternalUnavailable && (
              <div className="sidebar-note">
                {selectedOverlay} overlay is external and not available yet.
              </div>
            )}
            {!error && meshData?.user_overlay_modality && (
              <div className="sidebar-note">
                USER mesh modality: {meshData.user_overlay_modality}
              </div>
            )}
          </div>

          {caseId && (activeBaseLayer || activeVolume || loading || volumeLoading) ? (
            <div className="annotation-workspace">
              <section className="annotation-column annotation-column--mesh">
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
                    <LoaderOverlay inline label={loading ? 'Loading mesh data...' : 'No mesh available'} />
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
              </section>

              <aside className="annotation-column annotation-column--slice">
                <div className="annotation-slice-stage">
                  {sliceBusy && (
                    <div className="annotation-slice-loading">
                      <LoaderOverlay inline label="Loading slice projection..." />
                    </div>
                  )}
                  {sliceError && !sliceBusy && <div className="sidebar-error">{sliceError}</div>}
                  {!sliceError && sliceImageUrl && (
                    <div className="annotation-slice-image-shell">
                      <img
                        ref={sliceImageRef}
                        src={sliceImageUrl}
                        alt={`Slice ${sliceIndex}`}
                        onLoad={syncDrawingCanvas}
                        draggable={false}
                      />
                      <canvas
                        ref={drawCanvasRef}
                        className="annotation-draw-canvas"
                        onPointerDown={startDrawing}
                        onPointerMove={continueDrawing}
                        onPointerUp={stopDrawing}
                        onPointerLeave={stopDrawing}
                        onPointerCancel={stopDrawing}
                      />
                    </div>
                  )}
                  {!sliceBusy && !sliceError && !sliceImageUrl && (
                    <div className="empty-state">
                      <h2>No slice</h2>
                      <p>Select a modality to load slices for annotation.</p>
                    </div>
                  )}
                </div>

                <div className="annotation-slice-controls">
                  <div className="annotation-slice-title-row">
                    <h3>Slice Annotation</h3>
                    <span>
                      {selectedBase || '-'} | Slice {sliceCount > 0 ? sliceIndex : '-'}
                    </span>
                  </div>

                  <div className="annotation-slice-rotate-row">
                    <button className="mesh-tool-button" type="button" onClick={handleRotateLeft} disabled={sliceBusy}>
                      Rotate Left
                    </button>
                    <button className="mesh-tool-button" type="button" onClick={handleRotateRight} disabled={sliceBusy}>
                      Rotate Right
                    </button>
                    <button className="mesh-tool-button" type="button" onClick={handleRotateUp} disabled={sliceBusy}>
                      Rotate Up
                    </button>
                    <button className="mesh-tool-button" type="button" onClick={handleRotateDown} disabled={sliceBusy}>
                      Rotate Down
                    </button>
                    <button
                      className="mesh-tool-button"
                      type="button"
                      onClick={handleResetRotation}
                      disabled={sliceBusy || isViewAtOriginal}
                    >
                      Reset view
                    </button>
                    <div className="annotation-rotate-state">
                      {rotationTrackingLabel}
                    </div>
                  </div>

                  <div className="annotation-slice-gallery" role="listbox" aria-label="Slice gallery">
                    {sliceIndices.map((idx) => (
                      <button
                        key={idx}
                        className={`annotation-slice-thumb ${idx === sliceIndex ? 'active' : ''}`}
                        type="button"
                        onClick={() => setSliceIndex(idx)}
                        aria-selected={idx === sliceIndex}
                        disabled={sliceBusy}
                      >
                        <div className="annotation-slice-thumb-preview">
                          <img
                            className="annotation-slice-thumb-base"
                            loading="lazy"
                            src={baseSliceThumbUrls[idx] ?? ''}
                            alt={`Slice ${idx} base`}
                          />
                          <img
                            className="annotation-slice-thumb-overlay"
                            loading="lazy"
                            src={sliceThumbUrls[idx] ?? ''}
                            alt={`Slice ${idx} annotation`}
                          />
                        </div>
                        <span>{idx}</span>
                      </button>
                    ))}
                  </div>

                  <div className="annotation-slice-grid">
                    <div className="field compact-field slider-control">
                      <label className="field-label" htmlFor="brush-size">
                        Brush size ({brushSize}px)
                      </label>
                      <input
                        id="brush-size"
                        type="range"
                        min={1}
                        max={48}
                        step={1}
                        value={brushSize}
                        onChange={(event) => setBrushSize(Number(event.target.value))}
                      />
                    </div>
                    <div className="field compact-field slider-control">
                      <label className="field-label" htmlFor="brush-opacity">
                        Brush opacity ({Math.round(brushOpacity * 100)}%)
                      </label>
                      <input
                        id="brush-opacity"
                        type="range"
                        min={0.1}
                        max={1}
                        step={0.05}
                        value={brushOpacity}
                        onChange={(event) => setBrushOpacity(Number(event.target.value))}
                      />
                    </div>
                  </div>

                  <div className="annotation-slice-actions">
                    <button className="btn ghost small" type="button" onClick={clearCurrentSliceMask}>
                      Clear drawing
                    </button>
                    <button
                      className="btn ghost small"
                      type="button"
                      onClick={handleGenerateUserMesh}
                      disabled={sliceApplyLoading || historyActionLoading || sliceBusy || appliedMaskSummary.appliedLayersCount <= 0}
                    >
                      {userMeshLoading ? 'Generating...' : 'Generate USER mesh'}
                    </button>
                    <button
                      className="btn ghost small"
                      type="button"
                      onClick={handleUndoLayer}
                      disabled={sliceApplyLoading || historyActionLoading || userMeshLoading || sliceBusy || appliedMaskSummary.appliedLayersCount <= 0}
                    >
                      {historyActionLoading ? 'Working...' : 'Undo apply'}
                    </button>
                    <button
                      className="btn ghost small"
                      type="button"
                      onClick={handleRedoLayer}
                      disabled={sliceApplyLoading || historyActionLoading || userMeshLoading || sliceBusy || appliedMaskSummary.redoLayersCount <= 0}
                    >
                      {historyActionLoading ? 'Working...' : 'Redo apply'}
                    </button>
                    <button
                      className="btn small"
                      type="button"
                      onClick={handleApplySlice}
                      disabled={sliceApplyLoading || historyActionLoading || userMeshLoading || sliceBusy || !sliceImageUrl}
                    >
                      {sliceApplyLoading ? 'Applying...' : 'Apply change'}
                    </button>
                  </div>

                  {sliceApplyMessage && <div className="sidebar-note">{sliceApplyMessage}</div>}
                </div>
              </aside>
            </div>
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

function clamp(value: number, min: number, max: number) {
  if (!Number.isFinite(value)) return min
  return Math.max(min, Math.min(max, Math.round(value)))
}

function axisToDim(axis: Axis) {
  if (axis === 'x') return 0
  if (axis === 'y') return 1
  return 2
}

function planeDimsForAxis(axis: Axis): [number, number] {
  if (axis === 'x') return [1, 2]
  if (axis === 'y') return [0, 2]
  return [0, 1]
}

function getAxisFromVector(vector: [number, number, number]): [0 | 1 | 2, 1 | -1] {
  if (vector[0] !== 0) return [0, vector[0] > 0 ? 1 : -1]
  if (vector[1] !== 0) return [1, vector[1] > 0 ? 1 : -1]
  return [2, vector[2] > 0 ? 1 : -1]
}

function getViewShape(canonicalShape: [number, number, number], basis: Basis): [number, number, number] {
  const viewShape: [number, number, number] = [canonicalShape[0], canonicalShape[1], canonicalShape[2]]
  for (let d = 0; d < 3; d += 1) {
    const [axis] = getAxisFromVector(basis[d])
    viewShape[d] = canonicalShape[axis]
  }
  return viewShape
}

function viewToCanonicalCoord(
  viewCoord: [number, number, number],
  canonicalShape: [number, number, number],
  basis: Basis,
): [number, number, number] {
  const canonical: [number, number, number] = [0, 0, 0]
  for (let d = 0; d < 3; d += 1) {
    const [axis, sign] = getAxisFromVector(basis[d])
    const v = viewCoord[d]
    canonical[axis] = sign > 0 ? v : canonicalShape[axis] - 1 - v
  }
  return canonical
}

function parseFrontendVolume(shapeRaw: number[], rawVolume: unknown): FrontendVolume {
  if (!Array.isArray(rawVolume)) {
    throw new Error('Invalid volume payload: expected 3D array.')
  }
  const xPlanes = rawVolume as unknown[]
  const sx = xPlanes.length
  const sy = sx > 0 && Array.isArray(xPlanes[0]) ? (xPlanes[0] as unknown[]).length : 0
  const sz =
    sx > 0 && sy > 0 && Array.isArray((xPlanes[0] as unknown[])[0]) ? ((xPlanes[0] as unknown[])[0] as unknown[]).length : 0
  const shape: [number, number, number] = [
    Math.max(1, Math.floor(shapeRaw[0] ?? sx ?? 0) || sx),
    Math.max(1, Math.floor(shapeRaw[1] ?? sy ?? 0) || sy),
    Math.max(1, Math.floor(shapeRaw[2] ?? sz ?? 0) || sz),
  ]

  const data = new Float32Array(shape[0] * shape[1] * shape[2])
  let min = Number.POSITIVE_INFINITY
  let max = Number.NEGATIVE_INFINITY

  let ptr = 0
  for (let x = 0; x < shape[0]; x += 1) {
    const yPlanes = (xPlanes[x] as unknown[]) ?? []
    for (let y = 0; y < shape[1]; y += 1) {
      const zLine = (yPlanes[y] as unknown[]) ?? []
      for (let z = 0; z < shape[2]; z += 1) {
        const value = Number(zLine[z] ?? 0)
        const safe = Number.isFinite(value) ? value : 0
        data[ptr] = safe
        ptr += 1
        if (safe < min) min = safe
        if (safe > max) max = safe
      }
    }
  }

  if (!Number.isFinite(min)) min = 0
  if (!Number.isFinite(max) || max <= min) max = min + 1
  return { shape, data, min, max }
}

function buildMaskVolumeFromSparse(shapeRaw: number[], indicesRaw: number[][]): FrontendMaskVolume {
  if (!Array.isArray(shapeRaw) || shapeRaw.length !== 3) {
    throw new Error('Invalid mask shape payload.')
  }
  const shape: [number, number, number] = [
    Math.max(1, Math.floor(Number(shapeRaw[0]) || 0)),
    Math.max(1, Math.floor(Number(shapeRaw[1]) || 0)),
    Math.max(1, Math.floor(Number(shapeRaw[2]) || 0)),
  ]
  const [sx, sy, sz] = shape
  const data = new Uint8Array(sx * sy * sz)
  for (const item of indicesRaw ?? []) {
    if (!Array.isArray(item) || item.length < 3) continue
    const x = Math.floor(Number(item[0]))
    const y = Math.floor(Number(item[1]))
    const z = Math.floor(Number(item[2]))
    if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) continue
    if (x < 0 || x >= sx || y < 0 || y >= sy || z < 0 || z >= sz) continue
    const flat = (x * sy + y) * sz + z
    data[flat] = 1
  }
  return { shape, data }
}

function renderSliceDataUrl(volume: FrontendVolume, basis: Basis, axis: Axis, sliceIndex: number): string {
  const rendered = renderSliceRgba(volume, basis, axis, sliceIndex)
  return rgbaToPngDataUrl(rendered.width, rendered.height, rendered.rgba)
}

function renderBaseSliceThumbDataUrl(
  volume: FrontendVolume,
  basis: Basis,
  axis: Axis,
  sliceIndex: number,
  maxSize = 96,
): string {
  const rendered = renderSliceRgba(volume, basis, axis, sliceIndex, maxSize)
  return rgbaToPngDataUrl(rendered.width, rendered.height, rendered.rgba)
}

function renderCombinedMaskSliceThumbDataUrl(
  currentMaskVolume: FrontendMaskVolume | null,
  appliedMaskVolume: FrontendMaskVolume | null,
  basis: Basis,
  axis: Axis,
  sliceIndex: number,
  maxSize = 96,
): string {
  const rendered = renderCombinedMaskSliceRgba(
    currentMaskVolume,
    appliedMaskVolume,
    basis,
    axis,
    sliceIndex,
    maxSize,
  )
  return rgbaToPngDataUrl(rendered.width, rendered.height, rendered.rgba)
}

function renderSliceRgba(
  volume: FrontendVolume,
  basis: Basis,
  axis: Axis,
  sliceIndex: number,
  maxSize?: number,
): { width: number; height: number; rgba: Uint8ClampedArray } {
  const canonicalShape = volume.shape
  const viewShape = getViewShape(canonicalShape, basis)
  const axisDim = axisToDim(axis)
  const [rowDim, colDim] = planeDimsForAxis(axis)

  const srcHeight = Math.max(1, viewShape[rowDim])
  const srcWidth = Math.max(1, viewShape[colDim])
  const k = clamp(sliceIndex, 0, Math.max(0, viewShape[axisDim] - 1))

  let width = srcWidth
  let height = srcHeight
  if (maxSize && maxSize > 0) {
    const longest = Math.max(srcWidth, srcHeight)
    if (longest > maxSize) {
      const scale = maxSize / longest
      width = Math.max(1, Math.round(srcWidth * scale))
      height = Math.max(1, Math.round(srcHeight * scale))
    }
  }

  const rgba = new Uint8ClampedArray(width * height * 4)
  const range = Math.max(1e-6, volume.max - volume.min)

  for (let r = 0; r < height; r += 1) {
    const srcR = Math.min(srcHeight - 1, Math.floor((r / height) * srcHeight))
    for (let c = 0; c < width; c += 1) {
      const srcC = Math.min(srcWidth - 1, Math.floor((c / width) * srcWidth))
      const viewCoord: [number, number, number] = [0, 0, 0]
      viewCoord[axisDim] = k
      viewCoord[rowDim] = srcR
      viewCoord[colDim] = srcC

      const [cx, cy, cz] = viewToCanonicalCoord(viewCoord, canonicalShape, basis)
      const flatIndex = (cx * canonicalShape[1] + cy) * canonicalShape[2] + cz
      const raw = volume.data[flatIndex] ?? volume.min
      const normalized = Math.max(0, Math.min(1, (raw - volume.min) / range))
      const gray = Math.round(normalized * 255)
      const out = (r * width + c) * 4
      rgba[out] = gray
      rgba[out + 1] = gray
      rgba[out + 2] = gray
      rgba[out + 3] = 255
    }
  }

  return { width, height, rgba }
}

function renderCombinedMaskSliceRgba(
  currentMaskVolume: FrontendMaskVolume | null,
  appliedMaskVolume: FrontendMaskVolume | null,
  basis: Basis,
  axis: Axis,
  sliceIndex: number,
  maxSize?: number,
): { width: number; height: number; rgba: Uint8ClampedArray } {
  const canonicalShape: [number, number, number] = currentMaskVolume?.shape ?? appliedMaskVolume?.shape ?? [1, 1, 1]
  const viewShape = getViewShape(canonicalShape, basis)
  const axisDim = axisToDim(axis)
  const [rowDim, colDim] = planeDimsForAxis(axis)

  const srcHeight = Math.max(1, viewShape[rowDim])
  const srcWidth = Math.max(1, viewShape[colDim])
  const k = clamp(sliceIndex, 0, Math.max(0, viewShape[axisDim] - 1))

  let width = srcWidth
  let height = srcHeight
  if (maxSize && maxSize > 0) {
    const longest = Math.max(srcWidth, srcHeight)
    if (longest > maxSize) {
      const scale = maxSize / longest
      width = Math.max(1, Math.round(srcWidth * scale))
      height = Math.max(1, Math.round(srcHeight * scale))
    }
  }

  const rgba = new Uint8ClampedArray(width * height * 4)

  for (let r = 0; r < height; r += 1) {
    const srcR = Math.min(srcHeight - 1, Math.floor((r / Math.max(height, 1)) * srcHeight))
    for (let c = 0; c < width; c += 1) {
      const srcC = Math.min(srcWidth - 1, Math.floor((c / Math.max(width, 1)) * srcWidth))
      const viewCoord: [number, number, number] = [0, 0, 0]
      viewCoord[axisDim] = k
      viewCoord[rowDim] = srcR
      viewCoord[colDim] = srcC
      const [cx, cy, cz] = viewToCanonicalCoord(viewCoord, canonicalShape, basis)
      const flatIndex = (cx * canonicalShape[1] + cy) * canonicalShape[2] + cz
      const currentOn = isMaskVoxelOn(currentMaskVolume, flatIndex)
      const appliedOn = isMaskVoxelOn(appliedMaskVolume, flatIndex)

      const out = (r * width + c) * 4
      if (appliedOn || currentOn) {
        if (appliedOn) {
          rgba[out] = APPLIED_MASK_RGB[0]
          rgba[out + 1] = APPLIED_MASK_RGB[1]
          rgba[out + 2] = APPLIED_MASK_RGB[2]
          rgba[out + 3] = APPLIED_MASK_ALPHA
        }
        if (currentOn) {
          rgba[out] = CURRENT_MASK_RGB[0]
          rgba[out + 1] = CURRENT_MASK_RGB[1]
          rgba[out + 2] = CURRENT_MASK_RGB[2]
          rgba[out + 3] = 77
        }
      } else {
        rgba[out] = 0
        rgba[out + 1] = 0
        rgba[out + 2] = 0
        rgba[out + 3] = 0
      }
    }
  }

  return { width, height, rgba }
}

function isMaskVoxelOn(maskVolume: FrontendMaskVolume | null | undefined, flatIndex: number): boolean {
  if (!maskVolume) return false
  return (maskVolume.data[flatIndex] ?? 0) > 0
}

function rgbaToPngDataUrl(width: number, height: number, rgba: Uint8ClampedArray): string {
  const canvas = document.createElement('canvas')
  canvas.width = Math.max(1, width)
  canvas.height = Math.max(1, height)
  const ctx = canvas.getContext('2d')
  if (!ctx) return ''
  const image = ctx.createImageData(canvas.width, canvas.height)
  image.data.set(rgba)
  ctx.putImageData(image, 0, 0)
  return canvas.toDataURL('image/png')
}

function negateBasisVector(vector: [number, number, number]): [number, number, number] {
  return [-vector[0], -vector[1], -vector[2]]
}

function cloneBasisVector(vector: [number, number, number]): [number, number, number] {
  return [vector[0], vector[1], vector[2]]
}

function cloneBasis(basis: Basis): Basis {
  return [
    cloneBasisVector(basis[0]),
    cloneBasisVector(basis[1]),
    cloneBasisVector(basis[2]),
  ]
}

function isSameBasis(a: Basis, b: Basis): boolean {
  for (let i = 0; i < 3; i += 1) {
    for (let j = 0; j < 3; j += 1) {
      if (a[i][j] !== b[i][j]) {
        return false
      }
    }
  }
  return true
}

function formatBasisVector(vector: [number, number, number]) {
  if (vector[0] !== 0) return `${vector[0] > 0 ? '+' : '-'}X`
  if (vector[1] !== 0) return `${vector[1] > 0 ? '+' : '-'}Y`
  return `${vector[2] > 0 ? '+' : '-'}Z`
}

function describeViewBasisFromOriginal(basis: Basis) {
  if (isSameBasis(basis, IDENTITY_BASIS)) {
    return 'Viewpoint: original'
  }
  return `Viewpoint delta: X ${formatBasisVector(basis[0])}, Y ${formatBasisVector(basis[1])}, Z ${formatBasisVector(basis[2])}`
}

function rotateBasis(
  basis: Basis,
  direction: 'left' | 'right' | 'up' | 'down',
): Basis {
  const x = cloneBasisVector(basis[0])
  const y = cloneBasisVector(basis[1])
  const z = cloneBasisVector(basis[2])
  if (direction === 'left') {
    return [cloneBasisVector(z), cloneBasisVector(y), negateBasisVector(x)]
  }
  if (direction === 'right') {
    return [negateBasisVector(z), cloneBasisVector(y), cloneBasisVector(x)]
  }
  if (direction === 'up') {
    return [cloneBasisVector(x), cloneBasisVector(z), negateBasisVector(y)]
  }
  return [cloneBasisVector(x), negateBasisVector(z), cloneBasisVector(y)]
}

function encodeBinaryMaskRle(
  width: number,
  height: number,
  isOn: (flatPixelIndex: number) => boolean,
) {
  const totalPixels = width * height
  const rle: number[] = []
  let runStart = -1
  let runLength = 0

  for (let pixelIndex = 0; pixelIndex < totalPixels; pixelIndex += 1) {
    const on = isOn(pixelIndex)
    if (on) {
      if (runStart < 0) {
        runStart = pixelIndex
        runLength = 1
      } else {
        runLength += 1
      }
      continue
    }

    if (runStart >= 0) {
      rle.push(runStart, runLength)
      runStart = -1
      runLength = 0
    }
  }

  if (runStart >= 0) {
    rle.push(runStart, runLength)
  }
  return rle
}

function extractAnnotationSlicesPayload(maskVolume: FrontendMaskVolume) {
  const [sx, sy, sz] = maskVolume.shape
  const slices: Array<{ axis: Axis; k: number; width: number; height: number; rle: number[] }> = []
  for (let k = 0; k < sz; k += 1) {
    let hasPositive = false
    for (let x = 0; x < sx && !hasPositive; x += 1) {
      for (let y = 0; y < sy; y += 1) {
        const flat = (x * sy + y) * sz + k
        if (maskVolume.data[flat] > 0) {
          hasPositive = true
          break
        }
      }
    }
    if (!hasPositive) continue

    const width = sy
    const height = sx
    const rle = encodeBinaryMaskRle(width, height, (flatPixelIndex) => {
      const x = Math.floor(flatPixelIndex / width)
      const y = flatPixelIndex % width
      const flat = (x * sy + y) * sz + k
      return maskVolume.data[flat] > 0
    })
    if (rle.length > 0) {
      slices.push({
        axis: 'z',
        k,
        width,
        height,
        rle,
      })
    }
  }
  return slices
}

async function fetchWithTimeout(input: string, timeoutMs: number, init?: RequestInit) {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs)
  try {
    return await fetch(input, { ...init, signal: controller.signal })
  } finally {
    window.clearTimeout(timeout)
  }
}

function isAbortError(error: unknown) {
  if (error instanceof DOMException) {
    return error.name === 'AbortError'
  }
  if (!error || typeof error !== 'object') return false
  return 'name' in error && (error as { name?: string }).name === 'AbortError'
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

