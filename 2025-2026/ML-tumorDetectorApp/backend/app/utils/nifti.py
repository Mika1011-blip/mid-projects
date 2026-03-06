"""
Reusable NIfTI helpers for loading from S3 and preparing numeric volumes.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import nibabel as nib
import numpy as np
from fastapi import HTTPException

from app.core.config import settings
from app.services.storage_s3 import get_s3_client
from app.utils.filesystem import named_tempfile


S3ObjectKey = str


def downsample3d(vol: np.ndarray, factor: int) -> np.ndarray:
    if factor <= 1:
        return vol
    return vol[::factor, ::factor, ::factor]


def infer_nifti_suffix(object_key: str) -> str:
    key_l = object_key.lower()
    if key_l.endswith(".nii.gz"):
        return ".nii.gz"
    return ".nii"


@contextmanager
def download_nifti_from_s3(object_key: S3ObjectKey) -> Iterator[str]:
    """
    Download NIfTI from S3/MinIO object key to a temporary local file path.
    """
    suffix = infer_nifti_suffix(object_key)
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


def load_nifti_from_s3(object_key: S3ObjectKey) -> nib.Nifti1Image:
    """
    Return a fully materialized NIfTI image so temporary file cleanup is safe.
    """
    with download_nifti_from_s3(object_key) as local_path:
        img = nib.load(local_path)
        data = np.asanyarray(img.dataobj)
        out = nib.Nifti1Image(data, img.affine, header=img.header.copy())
        out.set_data_dtype(img.get_data_dtype())
        return out


def volume_and_spacing(src: S3ObjectKey | nib.Nifti1Image) -> tuple[np.ndarray, list[float]]:
    if isinstance(src, nib.Nifti1Image):
        img = src
    else:
        img = load_nifti_from_s3(src)

    vol = img.get_fdata(dtype=np.float32)
    spacings = list(map(float, img.header.get_zooms()[:3]))

    vol = np.nan_to_num(vol, nan=0.0, posinf=0.0, neginf=0.0)
    if vol.ndim != 3:
        raise HTTPException(
            status_code=422,
            detail=f"NIfTI volume must be 3D for meshing; got shape={tuple(vol.shape)}",
        )
    return vol, spacings
