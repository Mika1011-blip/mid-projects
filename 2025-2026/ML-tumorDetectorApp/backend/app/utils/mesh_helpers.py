"""
Reusable mesh-related helpers shared by mesh service and routes.
"""

from __future__ import annotations

import nibabel as nib
from fastapi import HTTPException

from app.services.pipeline import pipeline_0


ModalityImages = dict[str, nib.Nifti1Image]


def normalize_source_uris(source_uris: dict[str, str] | None) -> dict[str, str]:
    if not source_uris:
        return {}
    normalized: dict[str, str] = {}
    for key, value in source_uris.items():
        if not value:
            continue
        normalized[str(key).upper()] = str(value)
    return normalized


def preprocess_modalities_pipeline_0(
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
