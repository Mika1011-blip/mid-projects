"""
Mesh service:
- download NIfTI from S3 object key(s)
- optional pipeline_0 preprocessing
- build meshes for all available base modalities and overlay modalities
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

import nibabel as nib
import numpy as np
from fastapi import HTTPException
from skimage.measure import marching_cubes

from app.core.config import settings
from app.schemas.mesh import MeshLayer
from app.services.pipeline import pipeline_0
from app.services.storage_s3 import get_s3_client
from app.utils.filesystem import named_tempfile


S3ObjectKey = str
ModalityImages = dict[str, nib.Nifti1Image]

BASE_MODALITIES = ("T1CE", "FLAIR", "T1", "T2")
OVERLAY_MODALITIES = ("SEG",)


def _downsample3d(vol: np.ndarray, factor: int) -> np.ndarray:
    if factor <= 1:
        return vol
    return vol[::factor, ::factor, ::factor]


def _infer_nifti_suffix(object_key: str) -> str:
    key_l = object_key.lower()
    if key_l.endswith(".nii.gz"):
        return ".nii.gz"
    return ".nii"


@contextmanager
def download_nifti_from_s3(object_key: S3ObjectKey) -> Iterator[str]:
    """
    Download NIfTI from S3/MinIO object key to a temporary local file path.
    """
    suffix = _infer_nifti_suffix(object_key)
    with named_tempfile(suffix=suffix) as tmp_path:
        s3 = get_s3_client()
        try:
            s3.download_file(settings.S3_BUCKET, object_key, tmp_path)
        except Exception as exc:
            raise HTTPException(
                status_code=404,
                detail=f"NIfTI source not found in S3: {object_key}",
            ) from exc
        yield tmp_path


def _load_nifti_from_s3(object_key: S3ObjectKey) -> nib.Nifti1Image:
    """
    Return a fully materialized NIfTI image so temporary file cleanup is safe.
    """
    with download_nifti_from_s3(object_key) as local_path:
        img = nib.load(local_path)
        data = np.asanyarray(img.dataobj)
        out = nib.Nifti1Image(data, img.affine, header=img.header.copy())
        out.set_data_dtype(img.get_data_dtype())
        return out


def _volume_and_spacing(src: S3ObjectKey | nib.Nifti1Image) -> tuple[np.ndarray, list[float]]:
    if isinstance(src, nib.Nifti1Image):
        img = src
    else:
        img = _load_nifti_from_s3(src)

    vol = img.get_fdata(dtype=np.float32)
    spacings = list(map(float, img.header.get_zooms()[:3]))

    vol = np.nan_to_num(vol, nan=0.0, posinf=0.0, neginf=0.0)
    if vol.ndim != 3:
        raise HTTPException(
            status_code=422,
            detail=f"NIfTI volume must be 3D for meshing; got shape={tuple(vol.shape)}",
        )
    return vol, spacings


def _normalize_source_uris(source_uris: dict[str, str] | None) -> dict[str, str]:
    if not source_uris:
        return {}
    normalized: dict[str, str] = {}
    for key, value in source_uris.items():
        if not value:
            continue
        normalized[str(key).upper()] = str(value)
    return normalized


def _preprocess_0_volume_and_spacing(
    modalities: ModalityImages,
    run_pipeline_0: bool = False,
) -> ModalityImages:
    """
    Optionally run pipeline_0 across all loaded modalities before meshing.
    """
    if not run_pipeline_0:
        return modalities

    result = pipeline_0(modalities=modalities, template_ref_bool=False)
    if not result.get("success"):
        raise HTTPException(
            status_code=422,
            detail=f"pipeline_0 failed: {result.get('error', 'unknown error')}",
        )
    processed = result.get("preprocessed")
    if not isinstance(processed, dict) or not processed:
        raise HTTPException(status_code=422, detail="pipeline_0 returned empty output")
    return processed


def build_brain_mesh(
    src: S3ObjectKey | nib.Nifti1Image,
    *,
    downsample: int = 2,
    level: float | None = None,
    level_percentile: float = 80.0,
) -> MeshLayer:
    vol, spacing = _volume_and_spacing(src)
    ds_vol = _downsample3d(vol, factor=downsample)
    spacing_ds = [s * downsample for s in spacing]

    vmin, vmax = float(np.min(ds_vol)), float(np.max(ds_vol))
    if vmax <= vmin:
        raise HTTPException(status_code=422, detail="Volume has no intensity variation for meshing.")

    if level is None:
        level = float(np.percentile(ds_vol, level_percentile))
    if not (vmin < level < vmax):
        level = float((vmin + vmax) * 0.5)

    verts, faces, _, _ = marching_cubes(ds_vol, level=level)
    return MeshLayer(
        name="brain",
        space="voxel",
        spacing=spacing_ds,
        vertices=verts.astype(float).tolist(),
        faces=faces.astype(int).tolist(),
    )


def build_mask_mesh(
    src: S3ObjectKey | nib.Nifti1Image,
    *,
    name: str = "SEG",
    downsample: int = 1,
) -> MeshLayer:
    vol, spacing = _volume_and_spacing(src)
    vol_ds = _downsample3d(vol, factor=downsample)
    spacing_ds = [s * downsample for s in spacing]

    mask = (vol_ds > 0).astype(np.uint8)
    if not np.any(mask):
        raise HTTPException(status_code=422, detail=f"Mask '{name}' has no positive voxels.")

    verts, faces, _, _ = marching_cubes(mask, level=0.5)
    return MeshLayer(
        name=name,
        space="voxel",
        spacing=spacing_ds,
        vertices=verts.astype(float).tolist(),
        faces=faces.astype(int).tolist(),
    )


def build_case_meshes(
    source_uris: dict[str, str] | None,
    *,
    downsample: int = 2,
    level: float | None = None,
    overlays: set[str] | None = None,
    run_pipeline_0: bool = False,
) -> dict[str, Any]:
    """
    Build all available meshes for one case.

    Returns:
    - base_layers: meshes for available T1CE/FLAIR/T1/T2
    - overlay_layers: meshes for requested available overlays from source_uris
    - missing_modalities: base modalities missing in this case
    - missing_overlays: requested overlays missing in this case
    - skipped_*: failed mesh builds that were skipped
    """
    uri_map = _normalize_source_uris(source_uris)

    available_base_modalities = [m for m in BASE_MODALITIES if m in uri_map]
    missing_modalities = [m for m in BASE_MODALITIES if m not in uri_map]
    if not available_base_modalities:
        raise HTTPException(
            status_code=422,
            detail=(
                "Case has no available base modality. "
                "At least one of T1CE, FLAIR, T1, or T2 is required; overlays alone are not enough."
            ),
        )

    if overlays is None:
        requested_overlays = set(OVERLAY_MODALITIES)
    else:
        requested_overlays = {x.upper() for x in overlays}
    requested_overlays = {x for x in requested_overlays if x in OVERLAY_MODALITIES}
    missing_overlays = [m for m in OVERLAY_MODALITIES if m in requested_overlays and m not in uri_map]
    available_overlays = [m for m in OVERLAY_MODALITIES if m in requested_overlays and m in uri_map]

    keys_to_load = tuple(available_base_modalities + available_overlays)

    loaded: ModalityImages = {k: _load_nifti_from_s3(uri_map[k]) for k in keys_to_load}
    preprocessed = _preprocess_0_volume_and_spacing(loaded, run_pipeline_0=run_pipeline_0)

    base_layers: list[dict[str, Any]] = []
    overlay_layers: list[dict[str, Any]] = []
    skipped_modalities: list[str] = []
    skipped_overlays: list[str] = []

    for modality in available_base_modalities:
        img = preprocessed.get(modality)
        if img is None:
            continue
        try:
            layer = build_brain_mesh(img, downsample=downsample, level=level)
            base_layers.append({**layer.model_dump(), "name": f"brain:{modality}", "modality": modality})
        except HTTPException:
            skipped_modalities.append(modality)

    for overlay in available_overlays:
        img = preprocessed.get(overlay)
        if img is None:
            continue
        try:
            layer = build_mask_mesh(img, name=overlay, downsample=max(1, downsample))
            overlay_layers.append(layer.model_dump())
        except HTTPException:
            skipped_overlays.append(overlay)

    return {
        "base_layers": base_layers,
        "overlay_layers": overlay_layers,
        "missing_modalities": missing_modalities,
        "missing_overlays": missing_overlays,
        "skipped_modalities": skipped_modalities,
        "skipped_overlays": skipped_overlays,
    }
