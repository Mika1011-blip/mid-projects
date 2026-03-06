from __future__ import annotations

import uuid
from threading import Lock
from typing import Any, Literal

import nibabel as nib
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query
from nibabel.orientations import aff2axcodes
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import Case
from app.schemas.annotation import AnnotationSlicePayload, ApplySlicePayload
from app.services.mesh import build_case_meshes, build_mask_mesh, load_case_modalities


router = APIRouter(tags=["annotation"])
ModalityImages = dict[str, nib.Nifti1Image]
ALLOWED_MODALITIES = ("T1CE", "T1", "T2", "FLAIR")
ALLOWED_MODALITY_SET = set(ALLOWED_MODALITIES)
LOCAL_OVERLAYS = {"SEG"}
EXTERNAL_OVERLAYS = {"USER", "MODEL"}
ALLOWED_OVERLAYS = LOCAL_OVERLAYS | EXTERNAL_OVERLAYS
AXIS_TO_DIM = {"x": 0, "y": 1, "z": 2}

_ANNOTATION_LAYER_STORE: dict[str, dict[str, Any]] = {}
_ANNOTATION_LAYER_STORE_LOCK = Lock()


def _serialize_nifti(img: nib.Nifti1Image) -> dict[str, object]:
    data = np.asanyarray(img.dataobj)
    if np.issubdtype(data.dtype, np.floating):
        data = np.nan_to_num(data, nan=0.0, posinf=0.0, neginf=0.0)
    return {
        "shape": [int(v) for v in img.shape],
        "spacing": [float(v) for v in img.header.get_zooms()[:3]],
        "affine": [[float(v) for v in row] for row in img.affine.tolist()],
        "orientation": [str(v) for v in aff2axcodes(img.affine)],
        "dtype": str(data.dtype),
        "volume": data.tolist(),
    }


def _parse_csv(param: str | None) -> list[str]:
    if not param:
        return []
    return [x.strip().upper() for x in param.split(",") if x.strip()]


def _decode_rle_mask(width: int, height: int, rle: list[int]) -> np.ndarray:
    if len(rle) % 2 != 0:
        raise HTTPException(status_code=422, detail="Invalid RLE payload: expected pairs of [start, length]")

    total = width * height
    flat = np.zeros(total, dtype=np.uint8)
    for idx in range(0, len(rle), 2):
        start = int(rle[idx])
        length = int(rle[idx + 1])
        if start < 0 or length < 0 or start + length > total:
            raise HTTPException(status_code=422, detail="Invalid RLE payload: out-of-range run")
        if length > 0:
            flat[start : start + length] = 1
    return flat.reshape((height, width))


def _expected_slice_shape(shape: tuple[int, int, int], axis: Literal["x", "y", "z"]) -> tuple[int, int]:
    if axis == "x":
        return int(shape[1]), int(shape[2])
    if axis == "y":
        return int(shape[0]), int(shape[2])
    return int(shape[0]), int(shape[1])


def _inverse_slice_transform(mask: np.ndarray, rot90: int, flip_x: bool, flip_y: bool) -> np.ndarray:
    out = mask
    if flip_x:
        out = np.fliplr(out)
    if flip_y:
        out = np.flipud(out)
    inv_rot = (-rot90) % 4
    if inv_rot:
        out = np.rot90(out, k=inv_rot)
    return out


def _slice_to_sparse_indices(mask: np.ndarray, axis: Literal["x", "y", "z"], k: int) -> list[list[int]]:
    coords = np.argwhere(mask > 0)
    if axis == "x":
        return [[int(k), int(i), int(j)] for i, j in coords]
    if axis == "y":
        return [[int(i), int(k), int(j)] for i, j in coords]
    return [[int(i), int(j), int(k)] for i, j in coords]


def _parse_view_basis(view_basis: list[list[int]] | None) -> tuple[list[int], list[int]]:
    # Default basis: view axes align with canonical x/y/z.
    if view_basis is None:
        return [0, 1, 2], [1, 1, 1]
    if len(view_basis) != 3 or any(len(row) != 3 for row in view_basis):
        raise HTTPException(status_code=422, detail="Invalid view_basis: expected 3x3 matrix")

    axis_map: list[int] = []
    axis_signs: list[int] = []
    used_axes: set[int] = set()
    for row in view_basis:
        non_zero = [idx for idx, value in enumerate(row) if int(value) != 0]
        if len(non_zero) != 1:
            raise HTTPException(status_code=422, detail="Invalid view_basis: each row must have exactly one non-zero")
        axis = int(non_zero[0])
        sign = int(row[axis])
        if sign not in (-1, 1):
            raise HTTPException(status_code=422, detail="Invalid view_basis: non-zero entries must be -1 or 1")
        if axis in used_axes:
            raise HTTPException(status_code=422, detail="Invalid view_basis: duplicate canonical axis mapping")
        used_axes.add(axis)
        axis_map.append(axis)
        axis_signs.append(sign)
    if len(used_axes) != 3:
        raise HTTPException(status_code=422, detail="Invalid view_basis: missing canonical axis mapping")
    return axis_map, axis_signs


def _view_shape_from_basis(shape: tuple[int, int, int], axis_map: list[int]) -> tuple[int, int, int]:
    return int(shape[axis_map[0]]), int(shape[axis_map[1]]), int(shape[axis_map[2]])


def _view_voxel_to_canonical(
    view_voxel: tuple[int, int, int],
    canonical_shape: tuple[int, int, int],
    axis_map: list[int],
    axis_signs: list[int],
) -> tuple[int, int, int]:
    out = [0, 0, 0]
    for view_dim in range(3):
        canonical_dim = int(axis_map[view_dim])
        sign = int(axis_signs[view_dim])
        v = int(view_voxel[view_dim])
        out[canonical_dim] = v if sign > 0 else int(canonical_shape[canonical_dim] - 1 - v)
    return int(out[0]), int(out[1]), int(out[2])


def _slice_to_sparse_indices_oriented(
    mask: np.ndarray,
    axis: Literal["x", "y", "z"],
    k: int,
    canonical_shape: tuple[int, int, int],
    axis_map: list[int],
    axis_signs: list[int],
) -> list[list[int]]:
    coords = np.argwhere(mask > 0)
    out: list[list[int]] = []
    for i, j in coords:
        if axis == "x":
            view_voxel = (int(k), int(i), int(j))
        elif axis == "y":
            view_voxel = (int(i), int(k), int(j))
        else:
            view_voxel = (int(i), int(j), int(k))
        cx, cy, cz = _view_voxel_to_canonical(view_voxel, canonical_shape, axis_map, axis_signs)
        out.append([int(cx), int(cy), int(cz)])
    return out


def _validate_shape3(shape_raw: list[int] | None) -> tuple[int, int, int] | None:
    if shape_raw is None:
        return None
    if len(shape_raw) != 3:
        raise HTTPException(status_code=422, detail="Invalid annotation_shape. Expected exactly 3 dimensions.")
    shape = tuple(int(v) for v in shape_raw)
    if any(v <= 0 for v in shape):
        raise HTTPException(status_code=422, detail="Invalid annotation_shape. Dimensions must be > 0.")
    return shape


def _reconstruct_annotation_volume_from_slices(
    shape: tuple[int, int, int],
    slices: list[AnnotationSlicePayload],
) -> np.ndarray:
    volume = np.zeros(shape, dtype=np.uint8)
    for item in slices:
        axis = item.axis
        dim = AXIS_TO_DIM[axis]
        max_k = shape[dim] - 1
        if item.k > max_k:
            raise HTTPException(
                status_code=422,
                detail=f"Slice index out of range for axis {axis}: max={max_k}",
            )
        expected_shape = _expected_slice_shape(shape, axis)
        mask = _decode_rle_mask(item.width, item.height, item.rle)
        if tuple(mask.shape) != tuple(expected_shape):
            raise HTTPException(
                status_code=422,
                detail=f"Mask shape mismatch for axis {axis} k={item.k}. Expected {expected_shape}, got {tuple(mask.shape)}",
            )
        if axis == "x":
            volume[int(item.k), :, :] = np.maximum(volume[int(item.k), :, :], mask.astype(np.uint8))
        elif axis == "y":
            volume[:, int(item.k), :] = np.maximum(volume[:, int(item.k), :], mask.astype(np.uint8))
        else:
            volume[:, :, int(item.k)] = np.maximum(volume[:, :, int(item.k)], mask.astype(np.uint8))
    return volume


def _volume_to_sparse_indices(mask_volume: np.ndarray) -> list[list[int]]:
    coords = np.argwhere(mask_volume > 0)
    return [[int(i), int(j), int(k)] for i, j, k in coords]


def _normalize_modality(modality: str) -> str:
    key = str(modality).strip().upper()
    if key not in ALLOWED_MODALITY_SET:
        raise HTTPException(status_code=422, detail="Invalid modality. Allowed values: T1CE, T1, T2, FLAIR")
    return key


def _session_key(case_id: uuid.UUID, modality: str) -> str:
    return f"{case_id}:{modality}"


def _get_annotation_session_snapshot(case_id: uuid.UUID, modality: str) -> dict[str, Any] | None:
    key = _session_key(case_id, modality)
    with _ANNOTATION_LAYER_STORE_LOCK:
        session = _ANNOTATION_LAYER_STORE.get(key)
        if not session:
            return None
        shape_raw = session.get("shape") or []
        shape = tuple(int(v) for v in shape_raw) if len(shape_raw) == 3 else None
        return {
            "shape": shape,
            "applied_layers": list(session.get("applied_layers", [])),
            "redo_layers": list(session.get("redo_layers", [])),
        }


def _volume_from_applied_layers(shape: tuple[int, int, int], layers: list[dict[str, Any]]) -> np.ndarray:
    volume = np.zeros(shape, dtype=np.uint8)
    sx, sy, sz = shape
    for layer in layers:
        coords = layer.get("indices") or []
        if not coords:
            continue
        try:
            arr = np.asarray(coords, dtype=np.int64)
        except Exception:
            continue
        if arr.ndim != 2 or arr.shape[1] != 3:
            continue
        valid = (
            (arr[:, 0] >= 0)
            & (arr[:, 0] < sx)
            & (arr[:, 1] >= 0)
            & (arr[:, 1] < sy)
            & (arr[:, 2] >= 0)
            & (arr[:, 2] < sz)
        )
        arr = arr[valid]
        if arr.size == 0:
            continue
        volume[arr[:, 0], arr[:, 1], arr[:, 2]] = 1
    return volume


def _resolve_user_overlay_modality(case_id: uuid.UUID, user_modality: str | None) -> str | None:
    if user_modality:
        return _normalize_modality(user_modality)
    with _ANNOTATION_LAYER_STORE_LOCK:
        for modality in ALLOWED_MODALITIES:
            key = _session_key(case_id, modality)
            session = _ANNOTATION_LAYER_STORE.get(key)
            if session and session.get("applied_layers"):
                return modality
    return None


@router.get("/visualize/{case_id}/meshes")
def get_case_meshes(
    case_id: uuid.UUID,
    overlays: str | None = Query("SEG,USER,MODEL", description="Comma list: SEG,USER,MODEL"),
    downsample: int = Query(2, ge=1, le=8),
    level: float | None = Query(None),
    user_modality: str | None = Query(
        None,
        description="Optional modality key for USER overlay mesh: T1CE | T1 | T2 | FLAIR",
    ),
    run_pipeline_0: bool = Query(True, description="Apply pipeline_0 before meshing"),
    db: Session = Depends(get_db),
):
    case = db.execute(select(Case).where(Case.id == case_id)).scalar_one_or_none()
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    uris = case.source_uris or {}
    if not uris:
        raise HTTPException(status_code=422, detail="Case has no source_uris")

    requested_overlays = set(_parse_csv(overlays))
    requested_overlays = {x for x in requested_overlays if x in ALLOWED_OVERLAYS}
    requested_local_overlays = requested_overlays & LOCAL_OVERLAYS
    requested_external_overlays = requested_overlays & EXTERNAL_OVERLAYS

    meshes = build_case_meshes(
        source_uris=uris,
        downsample=downsample,
        level=level,
        overlays=requested_local_overlays,
        run_pipeline_0=run_pipeline_0,
    )

    external_overlays = {name: None for name in sorted(requested_external_overlays)}
    user_overlay_modality: str | None = None
    if "USER" in requested_external_overlays:
        resolved_modality = _resolve_user_overlay_modality(case_id, user_modality)
        if resolved_modality:
            snapshot = _get_annotation_session_snapshot(case_id, resolved_modality)
            shape = snapshot.get("shape") if snapshot else None
            layers = snapshot.get("applied_layers") if snapshot else []
            if shape and layers:
                user_mask = _volume_from_applied_layers(shape, layers)
                if np.any(user_mask):
                    loaded_case = load_case_modalities(
                        uris,
                        overlays=set(),
                        run_pipeline_0=run_pipeline_0,
                    )
                    ref_img = loaded_case["preprocessed"].get(resolved_modality)
                    if ref_img is not None and tuple(int(v) for v in ref_img.shape[:3]) == tuple(shape):
                        user_img = nib.Nifti1Image(user_mask.astype(np.uint8), ref_img.affine, header=ref_img.header.copy())
                        user_img.set_data_dtype(np.uint8)
                        try:
                            user_layer = build_mask_mesh(user_img, name="USER", downsample=max(1, downsample))
                            meshes["overlay_layers"].append(user_layer.model_dump())
                            external_overlays.pop("USER", None)
                            user_overlay_modality = resolved_modality
                        except HTTPException:
                            pass

    return {
        "case_id": str(case_id),
        "run_pipeline_0": run_pipeline_0,
        "user_overlay_modality": user_overlay_modality,
        "external_overlays": external_overlays,
        **meshes,
    }


@router.get("/annotation/get_volume/{case_id}")
def get_case_preprocessed_volumes(
    case_id: uuid.UUID,
    run_pipeline_0: bool = Query(True, description="Apply pipeline_0 to all loaded modalities"),
    modality: str | None = Query(
        None,
        description="Optional single modality key: T1CE | T1 | T2 | FLAIR (uppercase)",
    ),
    db: Session = Depends(get_db),
):
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    loaded_case = load_case_modalities(
        case.source_uris,
        overlays=set(),
        run_pipeline_0=run_pipeline_0,
    )
    preprocessed: ModalityImages = loaded_case["preprocessed"]

    preprocessed_allowed = {
        key: img
        for key, img in preprocessed.items()
        if key.upper() in ALLOWED_MODALITY_SET
    }
    if not preprocessed_allowed:
        raise HTTPException(
            status_code=422,
            detail="No supported modalities available after preprocessing. Expected: T1CE, T1, T2, FLAIR",
        )
    available_modalities = [m for m in ALLOWED_MODALITIES if m in preprocessed_allowed]
    missing_modalities = [m for m in ALLOWED_MODALITIES if m not in preprocessed_allowed]

    if modality:
        key = modality.upper()
        if key not in ALLOWED_MODALITY_SET:
            raise HTTPException(
                status_code=422,
                detail="Invalid modality. Allowed values: T1CE, T1, T2, FLAIR",
            )
        if key not in preprocessed_allowed:
            available = ", ".join(available_modalities)
            raise HTTPException(status_code=404, detail=f"Unknown modality '{modality}'. Available: {available}")
        selected_modalities = {key: preprocessed_allowed[key]}
    else:
        selected_modalities = preprocessed_allowed

    payload = {
        key: _serialize_nifti(selected_modalities[key])
        for key in sorted(selected_modalities.keys())
    }
    return {
        "case_id": str(case_id),
        "run_pipeline_0": run_pipeline_0,
        "available_modalities": available_modalities,
        "missing_modalities": missing_modalities,
        "modalities": payload,
    }


@router.get("/annotation/mask/{case_id}")
def get_merged_annotation_mask(
    case_id: uuid.UUID,
    modality: str = Query(..., description="Modality key: T1CE | T1 | T2 | FLAIR"),
    representation: Literal["dense", "sparse"] = Query("dense"),
    db: Session = Depends(get_db),
):
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    modality_key = _normalize_modality(modality)
    snapshot = _get_annotation_session_snapshot(case_id, modality_key)
    if not snapshot or not snapshot.get("shape"):
        raise HTTPException(status_code=404, detail="No applied annotation layers for this case/modality")

    shape = tuple(int(v) for v in snapshot["shape"])
    applied_layers = snapshot.get("applied_layers", [])
    redo_layers = snapshot.get("redo_layers", [])
    mask_volume = _volume_from_applied_layers(shape, applied_layers)
    nnz = int(np.count_nonzero(mask_volume))

    payload: dict[str, Any] = {
        "case_id": str(case_id),
        "modality": modality_key,
        "shape": [int(v) for v in shape],
        "representation": representation,
        "nnz": nnz,
        "applied_layers_count": len(applied_layers),
        "redo_layers_count": len(redo_layers),
    }
    if representation == "dense":
        payload["volume"] = mask_volume.astype(np.uint8).tolist()
    else:
        payload["indices"] = _volume_to_sparse_indices(mask_volume)
    return payload


@router.get("/annotation/mask/{case_id}/mesh")
def get_merged_annotation_mask_mesh(
    case_id: uuid.UUID,
    modality: str = Query(..., description="Modality key: T1CE | T1 | T2 | FLAIR"),
    downsample: int = Query(2, ge=1, le=8),
    run_pipeline_0: bool = Query(True, description="Apply pipeline_0 for reference spacing/orientation"),
    db: Session = Depends(get_db),
):
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    modality_key = _normalize_modality(modality)
    snapshot = _get_annotation_session_snapshot(case_id, modality_key)
    if not snapshot or not snapshot.get("shape"):
        raise HTTPException(status_code=404, detail="No applied annotation layers for this case/modality")

    shape = tuple(int(v) for v in snapshot["shape"])
    applied_layers = snapshot.get("applied_layers", [])
    redo_layers = snapshot.get("redo_layers", [])
    mask_volume = _volume_from_applied_layers(shape, applied_layers)
    if not np.any(mask_volume):
        raise HTTPException(status_code=422, detail="Merged annotation mask has no positive voxels.")

    loaded_case = load_case_modalities(
        case.source_uris,
        overlays=set(),
        run_pipeline_0=run_pipeline_0,
    )
    ref_img = loaded_case["preprocessed"].get(modality_key)
    if ref_img is None:
        raise HTTPException(status_code=404, detail=f"Modality '{modality_key}' not available.")
    if tuple(int(v) for v in ref_img.shape[:3]) != tuple(shape):
        raise HTTPException(
            status_code=422,
            detail=f"Mask shape mismatch with reference modality. mask={shape}, ref={tuple(int(v) for v in ref_img.shape[:3])}",
        )

    mask_img = nib.Nifti1Image(mask_volume.astype(np.uint8), ref_img.affine, header=ref_img.header.copy())
    mask_img.set_data_dtype(np.uint8)
    layer = build_mask_mesh(mask_img, name="USER", downsample=max(1, downsample))
    return {
        "case_id": str(case_id),
        "modality": modality_key,
        "nnz": int(np.count_nonzero(mask_volume)),
        "applied_layers_count": len(applied_layers),
        "redo_layers_count": len(redo_layers),
        "layer": layer.model_dump(),
    }


@router.post("/annotation/undo/{case_id}")
def undo_annotation_layer(
    case_id: uuid.UUID,
    modality: str = Query(..., description="Modality key: T1CE | T1 | T2 | FLAIR"),
    db: Session = Depends(get_db),
):
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    modality_key = _normalize_modality(modality)
    key = _session_key(case_id, modality_key)
    with _ANNOTATION_LAYER_STORE_LOCK:
        session = _ANNOTATION_LAYER_STORE.get(key)
        if not session or not session.get("applied_layers"):
            raise HTTPException(status_code=409, detail="No applied layers to undo.")
        undone_layer = session["applied_layers"].pop()
        session["redo_layers"].append(undone_layer)
        shape_raw = session.get("shape") or []
        shape = tuple(int(v) for v in shape_raw) if len(shape_raw) == 3 else None
        applied_layers = list(session.get("applied_layers", []))
        applied_count = len(applied_layers)
        redo_count = len(session.get("redo_layers", []))

    mask_volume = _volume_from_applied_layers(shape, applied_layers) if shape else np.zeros((1, 1, 1), dtype=np.uint8)
    return {
        "case_id": str(case_id),
        "modality": modality_key,
        "action": "undo",
        "undone_mode": str(undone_layer.get("mode", "")),
        "nnz": int(np.count_nonzero(mask_volume)),
        "applied_layers_count": applied_count,
        "redo_layers_count": redo_count,
    }


@router.post("/annotation/redo/{case_id}")
def redo_annotation_layer(
    case_id: uuid.UUID,
    modality: str = Query(..., description="Modality key: T1CE | T1 | T2 | FLAIR"),
    db: Session = Depends(get_db),
):
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    modality_key = _normalize_modality(modality)
    key = _session_key(case_id, modality_key)
    with _ANNOTATION_LAYER_STORE_LOCK:
        session = _ANNOTATION_LAYER_STORE.get(key)
        if not session or not session.get("redo_layers"):
            raise HTTPException(status_code=409, detail="No redo layers available.")
        redone_layer = session["redo_layers"].pop()
        session["applied_layers"].append(redone_layer)
        shape_raw = session.get("shape") or []
        shape = tuple(int(v) for v in shape_raw) if len(shape_raw) == 3 else None
        applied_layers = list(session.get("applied_layers", []))
        applied_count = len(applied_layers)
        redo_count = len(session.get("redo_layers", []))

    mask_volume = _volume_from_applied_layers(shape, applied_layers) if shape else np.zeros((1, 1, 1), dtype=np.uint8)
    return {
        "case_id": str(case_id),
        "modality": modality_key,
        "action": "redo",
        "redone_mode": str(redone_layer.get("mode", "")),
        "nnz": int(np.count_nonzero(mask_volume)),
        "applied_layers_count": applied_count,
        "redo_layers_count": redo_count,
    }


@router.post("/annotation/apply/{case_id}")
def apply_slice_delta(
    case_id: uuid.UUID,
    payload: ApplySlicePayload,
    db: Session = Depends(get_db),
):
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    modality = _normalize_modality(payload.modality)

    loaded_case = load_case_modalities(
        case.source_uris,
        overlays=set(),
        run_pipeline_0=payload.run_pipeline_0,
    )
    preprocessed: ModalityImages = loaded_case["preprocessed"]

    if modality not in preprocessed:
        available = ", ".join(sorted([m for m in preprocessed.keys() if m in ALLOWED_MODALITY_SET]))
        raise HTTPException(status_code=404, detail=f"Modality '{modality}' not available. Available: {available}")

    img = preprocessed[modality]
    shape = tuple(int(v) for v in img.shape[:3])
    session_key = _session_key(case_id, modality)
    axis = payload.axis

    if payload.annotation_slices:
        requested_shape = _validate_shape3(payload.annotation_shape)
        if requested_shape is not None and tuple(requested_shape) != tuple(shape):
            raise HTTPException(
                status_code=422,
                detail=f"annotation_shape mismatch. Expected {shape}, got {requested_shape}",
            )
        mask_volume = _reconstruct_annotation_volume_from_slices(shape, payload.annotation_slices)
        indices = _volume_to_sparse_indices(mask_volume)
        layer = {
            "mode": "full_volume_from_slices",
            "modality": modality,
            "axis": axis,
            "k": int(payload.k),
            "rot90": int(payload.rot90) % 4,
            "flip_x": bool(payload.flip_x),
            "flip_y": bool(payload.flip_y),
            "view_basis": payload.view_basis,
            "shape": [int(v) for v in shape],
            "nnz": len(indices),
            "slices_received": len(payload.annotation_slices),
            "indices": indices,
        }
    else:
        axis_map, axis_signs = _parse_view_basis(payload.view_basis)
        view_shape = _view_shape_from_basis(shape, axis_map)
        axis_dim = AXIS_TO_DIM[axis]
        max_k = int(view_shape[axis_dim] - 1)
        if payload.k > max_k:
            raise HTTPException(status_code=422, detail=f"Slice index out of range for axis {axis}: max={max_k}")

        expected_shape = _expected_slice_shape(view_shape, axis)
        input_mask = _decode_rle_mask(payload.width, payload.height, payload.rle)
        if tuple(input_mask.shape) != tuple(expected_shape):
            raise HTTPException(
                status_code=422,
                detail=f"Mask shape mismatch. Expected {expected_shape}, got {tuple(input_mask.shape)}",
            )

        rot90 = int(payload.rot90) % 4
        canonical_mask = _inverse_slice_transform(
            input_mask,
            rot90=rot90,
            flip_x=bool(payload.flip_x),
            flip_y=bool(payload.flip_y),
        )
        if tuple(canonical_mask.shape) != tuple(expected_shape):
            raise HTTPException(
                status_code=422,
                detail=f"Transformed mask shape mismatch. Expected {expected_shape}, got {tuple(canonical_mask.shape)}",
            )

        indices = _slice_to_sparse_indices_oriented(
            canonical_mask,
            axis=axis,
            k=int(payload.k),
            canonical_shape=shape,
            axis_map=axis_map,
            axis_signs=axis_signs,
        )
        layer = {
            "mode": "single_slice_delta",
            "modality": modality,
            "axis": axis,
            "k": int(payload.k),
            "rot90": rot90,
            "flip_x": bool(payload.flip_x),
            "flip_y": bool(payload.flip_y),
            "view_basis": payload.view_basis,
            "shape": [int(v) for v in shape],
            "nnz": len(indices),
            "indices": indices,  # sparse 3D coordinates
        }

    with _ANNOTATION_LAYER_STORE_LOCK:
        session = _ANNOTATION_LAYER_STORE.setdefault(
            session_key,
            {"shape": [int(v) for v in shape], "applied_layers": [], "redo_layers": []},
        )
        if session.get("shape") != [int(v) for v in shape]:
            session["shape"] = [int(v) for v in shape]
            session["applied_layers"] = []
            session["redo_layers"] = []
        session["applied_layers"].append(layer)
        session["redo_layers"] = []
        applied_count = len(session["applied_layers"])
        redo_count = len(session["redo_layers"])

    return {
        "case_id": str(case_id),
        "modality": modality,
        "axis": axis,
        "k": int(payload.k),
        "mode": layer.get("mode"),
        "slices_received": int(layer.get("slices_received", 0)),
        "nnz": len(indices),
        "applied_layers_count": applied_count,
        "redo_layers_count": redo_count,
    }
