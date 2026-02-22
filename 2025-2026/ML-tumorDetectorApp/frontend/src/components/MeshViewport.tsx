import { useCallback, useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { TransformControls } from 'three/examples/jsm/controls/TransformControls.js'
import { LoaderOverlay } from './LoaderOverlay'

export type MeshLayerPayload = {
  name: string
  space: string
  spacing: number[]
  vertices: number[][]
  faces: number[][]
  modality?: string
}

export function MeshViewport({
  baseLayer,
  overlayLayer,
  baseOpacity,
  overlayOpacity,
  loading = false,
  controlsDisabled = false,
}: {
  baseLayer: MeshLayerPayload
  overlayLayer: MeshLayerPayload | null
  baseOpacity: number
  overlayOpacity: number
  loading?: boolean
  controlsDisabled?: boolean
}) {
  const hostRef = useRef<HTMLDivElement | null>(null)
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null)
  const controlsRef = useRef<OrbitControls | null>(null)
  const pivotRef = useRef<THREE.Group | null>(null)
  const dragActiveRef = useRef(false)
  const transformRef = useRef<TransformControls | null>(null)
  const transformHelperRef = useRef<THREE.Object3D | null>(null)
  const axesHelperRef = useRef<THREE.AxesHelper | null>(null)
  const radiusRef = useRef(1)
  const centerRef = useRef(new THREE.Vector3(0, 0, 0))
  const [interactionMode, setInteractionMode] = useState<'orbit' | 'axis'>('orbit')
  const [showAxes, setShowAxes] = useState(true)

  const applyCameraPreset = useCallback(() => {
    const camera = cameraRef.current
    const controls = controlsRef.current
    if (!camera || !controls) return
    const pivot = pivotRef.current

    const radius = radiusRef.current || 1
    const center = centerRef.current

    if (pivot) {
      // Reset model rotation/transform to original orientation.
      pivot.position.set(0, 0, 0)
      pivot.rotation.set(0, 0, 0)
      pivot.scale.set(1, 1, 1)
      pivot.updateMatrixWorld(true)
    }

    camera.position.set(center.x + radius * 1.8, center.y + radius * 1.25, center.z + radius * 1.8)
    camera.up.set(0, 1, 0)

    controls.target.copy(center)
    camera.lookAt(center)
    controls.update()
  }, [])

  useEffect(() => {
    const host = hostRef.current
    if (!host) return

    const scene = new THREE.Scene()
    scene.background = new THREE.Color(0x000000)

    const camera = new THREE.PerspectiveCamera(52, 1, 0.1, 20000)
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false })
    renderer.setPixelRatio(window.devicePixelRatio || 1)
    renderer.domElement.style.display = 'block'
    renderer.domElement.style.width = '100%'
    renderer.domElement.style.height = '100%'

    while (host.firstChild) {
      host.removeChild(host.firstChild)
    }
    host.appendChild(renderer.domElement)

    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.dampingFactor = 0.08
    controls.enablePan = true
    controls.panSpeed = 0.8
    controls.rotateSpeed = 0.95
    controls.zoomSpeed = 1.0
    controls.mouseButtons = {
      LEFT: THREE.MOUSE.ROTATE,
      MIDDLE: THREE.MOUSE.DOLLY,
      RIGHT: THREE.MOUSE.PAN,
    }

    controls.enabled = !controlsDisabled

    cameraRef.current = camera
    controlsRef.current = controls

    const lightA = new THREE.HemisphereLight(0xffffff, 0x1e293b, 0.75)
    const lightB = new THREE.DirectionalLight(0xffffff, 0.9)
    lightB.position.set(1, 1.5, 2)
    scene.add(lightA, lightB)

    // Use a dedicated pivot at world origin for rotation gizmo.
    // Meshes are centered inside meshGroup; pivot stays at center.
    const pivotGroup = new THREE.Group()
    const meshGroup = new THREE.Group()
    pivotGroup.add(meshGroup)
    scene.add(pivotGroup)
    pivotRef.current = pivotGroup

    const baseGeometry = buildGeometry(baseLayer)
    const baseMaterial = new THREE.MeshStandardMaterial({
      color: modalityColor(baseLayer.modality ?? baseLayer.name),
      transparent: true,
      opacity: baseOpacity,
      roughness: 0.75,
      metalness: 0.0,
      side: THREE.DoubleSide,
    })
    const baseMesh = new THREE.Mesh(baseGeometry, baseMaterial)
    meshGroup.add(baseMesh)

    let overlayMesh: THREE.Mesh | null = null
    let overlayGeometry: THREE.BufferGeometry | null = null
    let overlayMaterial: THREE.MeshStandardMaterial | null = null
    if (overlayLayer) {
      overlayGeometry = buildGeometry(overlayLayer)
      overlayMaterial = new THREE.MeshStandardMaterial({
        color: overlayColor(overlayLayer.name),
        transparent: true,
        opacity: overlayOpacity,
        roughness: 0.5,
        metalness: 0.0,
        side: THREE.DoubleSide,
      })
      overlayMesh = new THREE.Mesh(overlayGeometry, overlayMaterial)
      meshGroup.add(overlayMesh)
    }

    const resize = () => {
      const width = Math.max(1, host.clientWidth)
      const height = Math.max(1, host.clientHeight)
      renderer.setSize(width, height, false)
      camera.aspect = width / height
      camera.updateProjectionMatrix()
    }

    resize()

    const box = new THREE.Box3().setFromObject(meshGroup)
    const size = box.getSize(new THREE.Vector3())
    const center = box.getCenter(new THREE.Vector3())
    const radius = Math.max(size.x, size.y, size.z) || 1

    const axesHelper = new THREE.AxesHelper(Math.max(20, radius * 0.55))
    axesHelper.visible = showAxes
    scene.add(axesHelper)
    axesHelperRef.current = axesHelper

    const transform = new TransformControls(camera, renderer.domElement)
    transform.setMode('rotate')
    transform.setSize(0.6)
    transform.attach(pivotGroup)
    transform.enabled = !controlsDisabled && interactionMode === 'axis'
    const transformHelper = transform.getHelper()
    transformHelper.visible = interactionMode === 'axis'
    scene.add(transformHelper)
    transformRef.current = transform
    transformHelperRef.current = transformHelper

    const onDraggingChanged = (event: { value?: unknown }) => {
      dragActiveRef.current = Boolean(event.value)
      controls.enabled = !dragActiveRef.current && !controlsDisabled
    }
    transform.addEventListener('dragging-changed', onDraggingChanged)

    meshGroup.position.sub(center)
    centerRef.current.set(0, 0, 0)
    radiusRef.current = radius
    controls.minDistance = Math.max(0.1, radius * 0.35)
    controls.maxDistance = Math.max(2, radius * 8)
    applyCameraPreset()
    camera.near = Math.max(0.01, radius / 100)
    camera.far = radius * 20
    camera.updateProjectionMatrix()
    controls.update()

    let frameId = 0
    const renderLoop = () => {
      controls.update()
      renderer.render(scene, camera)
      frameId = window.requestAnimationFrame(renderLoop)
    }
    renderLoop()

    const observer = new ResizeObserver(() => {
      resize()
    })
    observer.observe(host)

    const onKeyDown = (event: KeyboardEvent) => {
      if (controlsDisabled) return
      if (event.key === 'r' || event.key === 'R') {
        applyCameraPreset()
      } else if (event.key === 'g' || event.key === 'G') {
        setInteractionMode((prev) => (prev === 'orbit' ? 'axis' : 'orbit'))
      } else if (event.key === 'x' || event.key === 'X') {
        setShowAxes((prev) => !prev)
      }
    }
    window.addEventListener('keydown', onKeyDown)

    return () => {
      window.removeEventListener('keydown', onKeyDown)
      observer.disconnect()
      window.cancelAnimationFrame(frameId)
      transform.removeEventListener('dragging-changed', onDraggingChanged)
      controls.dispose()
      cameraRef.current = null
      controlsRef.current = null
      pivotRef.current = null
      transformRef.current = null
      transformHelperRef.current = null
      axesHelperRef.current = null
      baseGeometry.dispose()
      baseMaterial.dispose()
      if (overlayMesh) {
        meshGroup.remove(overlayMesh)
      }
      scene.remove(transformHelper)
      transform.dispose()
      scene.remove(axesHelper)
      overlayGeometry?.dispose()
      overlayMaterial?.dispose()
      renderer.dispose()
      if (renderer.domElement.parentNode === host) {
        host.removeChild(renderer.domElement)
      }
    }
  }, [
    applyCameraPreset,
    baseLayer,
    overlayLayer,
    baseOpacity,
    overlayOpacity,
    controlsDisabled,
  ])

  useEffect(() => {
    if (controlsRef.current) {
      controlsRef.current.enabled = !controlsDisabled && !dragActiveRef.current
    }
    if (transformRef.current) {
      const enabled = !controlsDisabled && interactionMode === 'axis'
      transformRef.current.enabled = enabled
    }
    if (transformHelperRef.current) {
      transformHelperRef.current.visible = !controlsDisabled && interactionMode === 'axis'
    }
  }, [interactionMode, controlsDisabled])

  useEffect(() => {
    if (axesHelperRef.current) {
      axesHelperRef.current.visible = showAxes
    }
  }, [showAxes])

  return (
    <div className="mesh-viewer">
      <div className="mesh-canvas-wrap">
        <div ref={hostRef} className={`mesh-canvas ${controlsDisabled ? 'disabled' : ''}`} />
        {loading && <LoaderOverlay inline label="Loading mesh data..." />}
      </div>
      <div className="mesh-toolbar">
        <button
          className={`mesh-tool-button ${interactionMode === 'axis' ? 'active' : ''}`}
          type="button"
          onClick={() => setInteractionMode((prev) => (prev === 'orbit' ? 'axis' : 'orbit'))}
          disabled={controlsDisabled}
        >
          Axis rotate ({interactionMode === 'axis' ? 'On' : 'Off'}) [G]
        </button>
        <button
          className={`mesh-tool-button ${showAxes ? 'active' : ''}`}
          type="button"
          onClick={() => setShowAxes((prev) => !prev)}
          disabled={controlsDisabled}
        >
          Axes ({showAxes ? 'On' : 'Off'}) [X]
        </button>
        <button className="mesh-tool-button" type="button" onClick={applyCameraPreset} disabled={controlsDisabled}>
          Reset (R)
        </button>
        <span className="mesh-hint">Mouse: L-rotate, wheel-zoom, R-pan, axis-gizmo drag</span>
      </div>
    </div>
  )
}

function buildGeometry(layer: MeshLayerPayload) {
  const vertices = layer.vertices ?? []
  const faces = layer.faces ?? []
  const spacing = layer.spacing ?? [1, 1, 1]

  const positions = new Float32Array(vertices.length * 3)
  vertices.forEach((vertex, index) => {
    positions[index * 3] = (vertex[0] ?? 0) * (spacing[0] ?? 1)
    positions[index * 3 + 1] = (vertex[1] ?? 0) * (spacing[1] ?? 1)
    positions[index * 3 + 2] = (vertex[2] ?? 0) * (spacing[2] ?? 1)
  })

  const indices = new Uint32Array(faces.length * 3)
  faces.forEach((face, index) => {
    indices[index * 3] = face[0] ?? 0
    indices[index * 3 + 1] = face[1] ?? 0
    indices[index * 3 + 2] = face[2] ?? 0
  })

  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))
  geometry.setIndex(new THREE.BufferAttribute(indices, 1))
  geometry.computeVertexNormals()
  return geometry
}

function modalityColor(modality: string) {
  const normalized = modality.includes(':')
    ? modality.split(':').pop() ?? modality
    : modality
  const map: Record<string, number> = {
    T1CE: 0xd6d9de,
    FLAIR: 0xd9dde2,
    T1: 0xcfd3d9,
    T2: 0xd4d8de,
  }
  return map[normalized.toUpperCase()] ?? 0xd2d6dc
}

function overlayColor(overlay: string) {
  const normalized = overlay.includes(':')
    ? overlay.split(':').pop() ?? overlay
    : overlay
  const map: Record<string, number> = {
    SEG: 0xff3b30,
    USER: 0xff8a3d,
    MODEL: 0xffd24a,
  }
  return map[normalized.toUpperCase()] ?? 0xff3b30
}
