from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
import numpy as np
import nibabel as nib
from pathlib import Path
from nibabel.orientations import aff2axcodes


Axis = Literal["x", "y", "z"]
NiftiSource = str | Path | nib.spatialimages.SpatialImage

_AXIS_TO_DIM = {"x": 0, "y": 1, "z": 2}

@dataclass(frozen=True)
class PreviewRenderResult:
    axis:Axis
    dim:int
    shape:list[int] # full nifti shape
    count:int # number of slices
    frames_rgb:np.ndarray # slices (H,W,3) or (N,H,W,3), dtype=uint8
    used_windowing:bool
    window: dict | None # window mask if applied

@dataclass(frozen=True)
class AnnotationResult:
    axis: Axis
    dim: int
    shape: list[int]
    count: int
    spacing: tuple[float, float, float]
    affine: np.ndarray
    orientation: tuple[str, str, str]
    frames: np.ndarray  # (H,W) or (N,H,W), float32
    used_windowing: bool
    window: dict | None


def _load_volume(nifti_source: NiftiSource, volume_index: int = 0):
    if isinstance(nifti_source, nib.spatialimages.SpatialImage):
        nifti = nifti_source
    elif isinstance(nifti_source, (str, Path)):
        nifti = nib.load(str(nifti_source))
    else:
        raise TypeError(
            "nifti_source must be a path-like string/Path or a nibabel SpatialImage"
        )
    shape = list(nifti.shape)

    if len(shape) < 3:
        raise ValueError(f"Expected >=3D NIfTI, got shape={shape}")

    data = np.asanyarray(nifti.dataobj, dtype=np.float32)
    if len(shape) > 3:
        if volume_index < 0 or volume_index >= shape[3]:
            raise ValueError(f"volume_index out of range: {volume_index}")
        data = data[..., volume_index]
        shape = list(data.shape)

    spacing = tuple(nifti.header.get_zooms()[:3])
    affine = nifti.affine
    orientation = aff2axcodes(affine)
    return data, shape, spacing, affine, orientation

def _compute_window(
    data: np.ndarray,
    *,
    apply_windowing: bool,
    low_pct: float,
    high_pct: float,
    ignore_zero_background: bool = True,
):
    finite = np.isfinite(data)
    if ignore_zero_background:
        finite &= data != 0
    masked = data[finite]
    if masked.size == 0:
        masked = data[np.isfinite(data)]
    if masked.size == 0:
        raise ValueError("No finite values in NIfTI volume")

    if apply_windowing:
        lo = float(np.percentile(masked, low_pct))
        hi = float(np.percentile(masked, high_pct))
        window = {"low_pct": low_pct, "high_pct": high_pct, "lo": lo, "hi": hi}
    else:
        lo = float(np.min(masked))
        hi = float(np.max(masked))
        window = None

    return lo, hi, window

def render_slices_rgb(
        nifti_path : NiftiSource,
        *,
        axis:Axis="z",
        preview_index : int | None = None,
        apply_windowing : bool = False,
        low_pct: float = 1.0,# pct -> percentile
        high_pct: float = 99.0,
        gamma: float = 1.1,
        ignore_zero_background: bool = True,
):
    """
    Workflow :
    1) sanity
    2) map axis to dimension
    3) 2 cases : return 1 single slice or all slices
    4) display transformation
        - apply window if True else min/max normalize
        - convert to uint8 grayscale
        - stacks to RGB (frontend preferred solution)
    5) return in class PreviewRenderResult
    """

    data, shape, _spacing, _affine, _orientation = _load_volume(nifti_path, volume_index=0)

    axis = axis.lower()
    if axis not in _AXIS_TO_DIM:
        raise ValueError(f"Invalid axis {axis}. Allowed: {list(_AXIS_TO_DIM)}")

    axis_dim = _AXIS_TO_DIM[axis]
    count = shape[axis_dim]

    def get_slice(sl_i):
        if axis_dim == 0:
            return np.asanyarray(data[sl_i,:,:],dtype=np.float32)
        elif axis_dim == 1:
            return np.asanyarray(data[:,sl_i,:],dtype=np.float32)
        else :
            return np.asanyarray(data[:,:,sl_i],dtype=np.float32)
        
    lo, hi, window = _compute_window(
        data,
        apply_windowing=apply_windowing,
        low_pct=low_pct,
        high_pct=high_pct,
        ignore_zero_background=ignore_zero_background,
    )

    def transform_slice(sl: np.ndarray) -> np.ndarray:
        if hi <= lo:
            scaled = np.zeros(sl.shape, dtype=np.uint8)
        elif apply_windowing:
            clipped = np.clip(sl, lo, hi)
            norm = (clipped - lo) / (hi - lo)
            norm = np.clip(norm, 0.0, 1.0)
            if gamma and gamma != 1.0:
                norm = np.power(norm, 1.0 / gamma)
            scaled = (norm * 255.0).astype(np.uint8)
        else:
            norm = (sl - lo) / (hi - lo)
            norm = np.clip(norm, 0.0, 1.0)
            if gamma and gamma != 1.0:
                norm = np.power(norm, 1.0 / gamma)
            scaled = (norm * 255.0).astype(np.uint8)
        return np.stack([scaled, scaled, scaled], axis=-1)
    # render single slice
    if preview_index is not None:
        k = max(0, min(int(preview_index), count - 1))
        sl = get_slice(k)
        rgb = transform_slice(sl)
        return PreviewRenderResult(
            axis=axis, dim=axis_dim, shape=shape, count=count,
            frames_rgb=rgb,
            used_windowing=apply_windowing,
            window=window,
        )
    # render all slices
    frames = []
    representative_win = None
    for k in range(count):
        sl = get_slice(k)
        rgb = transform_slice(sl)
        frames.append(rgb)
    stack = np.stack(frames, axis=0)
    return PreviewRenderResult(
                                axis=axis, dim=axis_dim, shape=shape, count=count,
                                frames_rgb=stack,
                                used_windowing=apply_windowing,
                                window=window,
                            )

def render_slices_annotation(
        nifti_path: NiftiSource,
        *,
        axis: Axis = "z",
        preview_index: int | None = None,
        volume_index: int = 0,
        apply_windowing: bool = False,
        low_pct: float = 1.0,
        high_pct: float = 99.0,
):
    """
    Annotation-ready rendering:
    - returns raw float32 slices + affine/spacing/orientation
    - optional global window info for UI (no intensity loss)
    """
    data, shape, spacing, affine, orientation = _load_volume(nifti_path, volume_index=volume_index)

    axis = axis.lower()
    if axis not in _AXIS_TO_DIM:
        raise ValueError(f"Invalid axis {axis}. Allowed: {list(_AXIS_TO_DIM)}")

    axis_dim = _AXIS_TO_DIM[axis]
    count = shape[axis_dim]

    def get_slice(sl_i):
        if axis_dim == 0:
            return np.asanyarray(data[sl_i, :, :], dtype=np.float32)
        if axis_dim == 1:
            return np.asanyarray(data[:, sl_i, :], dtype=np.float32)
        return np.asanyarray(data[:, :, sl_i], dtype=np.float32)

    lo, hi, window = _compute_window(
        data,
        apply_windowing=apply_windowing,
        low_pct=low_pct,
        high_pct=high_pct,
    )

    if preview_index is not None:
        k = max(0, min(int(preview_index), count - 1))
        sl = get_slice(k)
        return AnnotationResult(
            axis=axis,
            dim=axis_dim,
            shape=shape,
            count=count,
            spacing=spacing,
            affine=affine,
            orientation=orientation,
            frames=sl,
            used_windowing=apply_windowing,
            window=window,
        )

    frames = [get_slice(k) for k in range(count)]
    stack = np.stack(frames, axis=0)
    return AnnotationResult(
        axis=axis,
        dim=axis_dim,
        shape=shape,
        count=count,
        spacing=spacing,
        affine=affine,
        orientation=orientation,
        frames=stack,
        used_windowing=apply_windowing,
        window=window,
    )
