"""
Mesh service:
- download NIfTI from S3 object key(s)
- optional pipeline_0 preprocessing
- build meshes for all available base modalities and overlay modalities
"""

from __future__ import annotations

from typing import Any

import nibabel as nib
import numpy as np
from fastapi import HTTPException
from skimage.measure import marching_cubes

from app.schemas.mesh import MeshLayer
from app.utils.mesh_helpers import normalize_source_uris, preprocess_modalities_pipeline_0
from app.utils.nifti import downsample3d, load_nifti_from_s3, volume_and_spacing


S3ObjectKey = str
ModalityImages = dict[str, nib.Nifti1Image]

BASE_MODALITIES = ("T1CE", "FLAIR", "T1", "T2")
OVERLAY_MODALITIES = ("SEG",)


def load_case_modalities(
    source_uris: dict[str, str] | None,
    *,
    overlays: set[str] | None = None,
    run_pipeline_0: bool = False,
) -> dict[str, Any]:
    """
    Load requested case modalities from S3 and optionally run pipeline_0.

    Returns:
    - preprocessed: dict[str, nib.Nifti1Image]
    - available_base_modalities / missing_modalities
    - available_overlays / missing_overlays
    """
    uri_map = normalize_source_uris(source_uris)

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
    loaded: ModalityImages = {k: load_nifti_from_s3(uri_map[k]) for k in keys_to_load}
    preprocessed = preprocess_modalities_pipeline_0(loaded, run_pipeline_0=run_pipeline_0)

    return {
        "preprocessed": preprocessed,
        "available_base_modalities": available_base_modalities,
        "missing_modalities": missing_modalities,
        "available_overlays": available_overlays,
        "missing_overlays": missing_overlays,
    }


def build_brain_mesh(
    src: S3ObjectKey | nib.Nifti1Image,
    *,
    downsample: int = 2,
    level: float | None = None,
    level_percentile: float = 80.0,
) -> MeshLayer:
    vol, spacing = volume_and_spacing(src)
    ds_vol = downsample3d(vol, factor=downsample)
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
    vol, spacing = volume_and_spacing(src)
    vol_ds = downsample3d(vol, factor=downsample)
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
    include_preprocessed: bool = False,
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
    loaded_case = load_case_modalities(
        source_uris,
        overlays=overlays,
        run_pipeline_0=run_pipeline_0,
    )
    preprocessed: ModalityImages = loaded_case["preprocessed"]
    available_base_modalities: list[str] = loaded_case["available_base_modalities"]
    missing_modalities: list[str] = loaded_case["missing_modalities"]
    available_overlays: list[str] = loaded_case["available_overlays"]
    missing_overlays: list[str] = loaded_case["missing_overlays"]

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

    output = {
        "base_layers": base_layers,
        "overlay_layers": overlay_layers,
        "missing_modalities": missing_modalities,
        "missing_overlays": missing_overlays,
        "skipped_modalities": skipped_modalities,
        "skipped_overlays": skipped_overlays,
    }
    if include_preprocessed:
        output["preprocessed"] = preprocessed
    return output
