from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import select

import uuid
import io
from PIL import Image
import numpy as np

from app.core.config import settings
from app.services.storage_s3 import get_s3_client
from app.utils.filesystem import named_tempfile
from app.core.db import get_db
from app.models import Case
from app.utils.rgb_to_png import rgb_to_png_bytes
from app.services.render_slices import render_slices_rgb, render_slices_annotation

router = APIRouter()
_PREFERRED_MODALITIES = ("T1CE", "FLAIR", "T1", "T2", "SEG")


def _pick_source_uri(case: Case, modality: str | None = None) -> str:
    source_uris = dict(case.source_uris or {})
    if not source_uris:
        raise HTTPException(status_code=409, detail="Case has no source_uris")
    if modality:
        key = modality.upper()
        if key not in source_uris:
            available = ", ".join(sorted(source_uris.keys()))
            raise HTTPException(status_code=404, detail=f"Unknown modality '{modality}'. Available: {available}")
        return source_uris[key]
    if len(source_uris) == 1:
        return next(iter(source_uris.values()))
    for key in _PREFERRED_MODALITIES:
        if key in source_uris:
            return source_uris[key]
    return next(iter(source_uris.values()))

@router.get("/cases/{case_id}/metadata")
def case_metadata(case_id:uuid.UUID,db:Session=Depends(get_db)):
    case = db.get(Case,case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return {
        "metadata_json": case.metadata_json,
        "metadata_statuses": case.metadata_statuses,
    }
@router.get("/cases/{case_id}/created_at")
def case_metadata(case_id:uuid.UUID,db:Session=Depends(get_db)):
    case = db.get(Case,case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return {
        "created_at": case.created_at,
    }
@router.get("/cases/{case_id}/source_uris")
def case_metadata(case_id:uuid.UUID,db:Session=Depends(get_db)):
    case = db.get(Case,case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return {
        "source_uris": dict(case.source_uris or {}),
    }

@router.get("/cases/{case_id}/preview")
def get_case_preview(
    case_id: uuid.UUID,
    axis: str = "z",
    preview_index: str | None = None,
    apply_windowing: bool = True,
    gamma: float = 1.1,
    modality: str | None = None,
    db: Session = Depends(get_db),
):
    # db lookup + sanity
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    source_uri = _pick_source_uri(case, modality)

    if preview_index in (None, "", "all"):
        preview_idx: int | None = None
    else:
        try:
            preview_idx = int(preview_index)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="preview_index must be an integer or 'all'") from exc

    s3 = get_s3_client()
    suffix = ".nii.gz" if source_uri.endswith(".nii.gz") else ".nii"
    with named_tempfile(suffix=suffix) as tmp_path:
        try:
            s3.download_file(settings.S3_BUCKET, source_uri, tmp_path)
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"Object download failed: {type(e).__name__}")
        try:
            rendered = render_slices_rgb(
                nifti_path=tmp_path,
                axis=axis,
                preview_index=preview_idx,
                apply_windowing=apply_windowing,
                gamma=gamma,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Render failed: {type(e).__name__}")

    if preview_idx is not None:
        png = rgb_to_png_bytes(rendered.frames_rgb)
        return Response(content=png, media_type="image/png")

    frames = [Image.fromarray(frame, mode="RGB") for frame in rendered.frames_rgb]
    if not frames:
        raise HTTPException(status_code=500, detail="No frames rendered")
    buf = io.BytesIO()
    frames[0].save(
        buf,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=60,
        loop=0,
    )
    return Response(content=buf.getvalue(), media_type="image/gif")


@router.get("/cases/{case_id}/annotation-preview")
def get_case_annotation_preview(
    case_id: uuid.UUID,
    axis: str = "z",
    slice_index: str | None = None,
    volume_index: int = 0,
    apply_windowing: bool = False,
    format: str = "image",
    modality: str | None = None,
    db: Session = Depends(get_db),
):
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    source_uri = _pick_source_uri(case, modality)

    if slice_index in (None, "", "all"):
        slice_idx: int | None = None
    else:
        try:
            slice_idx = int(slice_index)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="slice_index must be an integer or 'all'") from exc

    s3 = get_s3_client()
    suffix = ".nii.gz" if source_uri.endswith(".nii.gz") else ".nii"
    with named_tempfile(suffix=suffix) as tmp_path:
        try:
            s3.download_file(settings.S3_BUCKET, source_uri, tmp_path)
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"Object download failed: {type(e).__name__}")
        try:
            rendered = render_slices_annotation(
                nifti_path=tmp_path,
                axis=axis,
                preview_index=slice_idx,
                volume_index=volume_index,
                apply_windowing=apply_windowing,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Render failed: {type(e).__name__}")

    fmt = format.lower()
    if fmt == "json":
        slice_data = rendered.frames.astype("float32").tolist()
        return {
            "axis": rendered.axis,
            "dim": rendered.dim,
            "shape": rendered.shape,
            "count": rendered.count,
            "slice_index": slice_idx,
            "spacing": [float(v) for v in rendered.spacing],
            "orientation": [str(v) for v in rendered.orientation],
            "affine": [[float(v) for v in row] for row in rendered.affine.tolist()],
            "used_windowing": rendered.used_windowing,
            "window": rendered.window,
            "slice": slice_data,
        }

    def to_uint8(arr: np.ndarray) -> np.ndarray:
        window = rendered.window
        if window:
            lo = float(window["lo"])
            hi = float(window["hi"])
        else:
            finite = np.isfinite(arr)
            if not finite.any():
                return np.zeros(arr.shape, dtype=np.uint8)
            lo = float(np.min(arr[finite]))
            hi = float(np.max(arr[finite]))
        if hi <= lo:
            return np.zeros(arr.shape, dtype=np.uint8)
        norm = (arr - lo) / (hi - lo)
        norm = np.clip(norm, 0.0, 1.0)
        return (norm * 255.0).astype(np.uint8)

    def to_uint16(arr: np.ndarray) -> np.ndarray:
        window = rendered.window
        if window:
            lo = float(window["lo"])
            hi = float(window["hi"])
        else:
            finite = np.isfinite(arr)
            if not finite.any():
                return np.zeros(arr.shape, dtype=np.uint16)
            lo = float(np.min(arr[finite]))
            hi = float(np.max(arr[finite]))
        if hi <= lo:
            return np.zeros(arr.shape, dtype=np.uint16)
        norm = (arr - lo) / (hi - lo)
        norm = np.clip(norm, 0.0, 1.0)
        return (norm * 65535.0).astype(np.uint16)

    if slice_idx is not None:
        if fmt == "png16":
            gray16 = to_uint16(rendered.frames)
            img16 = Image.fromarray(gray16, mode="I;16")
            buf16 = io.BytesIO()
            img16.save(buf16, format="PNG")
            return Response(content=buf16.getvalue(), media_type="image/png")
        gray = to_uint8(rendered.frames)
        img = Image.fromarray(gray, mode="L")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return Response(content=buf.getvalue(), media_type="image/png")

    frames = [Image.fromarray(to_uint8(frame), mode="L") for frame in rendered.frames]
    if not frames:
        raise HTTPException(status_code=500, detail="No frames rendered")
    buf = io.BytesIO()
    frames[0].save(
        buf,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=60,
        loop=0,
    )
    return Response(content=buf.getvalue(), media_type="image/gif")

@router.get("/cases/get_all")
def list_all_cases(
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(
            Case.id,
            Case.created_at,
            Case.source_type,
            Case.display_name,
            Case.has_tumor,
        )
        .order_by(Case.created_at.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return [
        {
            "id": str(row.id),
            "created_at": row.created_at,
            "source_type": row.source_type,
            "display_name": row.display_name,
            "has_tumor": row.has_tumor,
        }
        for row in rows
    ]


@router.get("/cases/{case_id}")
def get_case(case_id: uuid.UUID, db: Session = Depends(get_db)):
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return {
        "id": str(case.id),
        "created_at": case.created_at,
        "source_type": case.source_type,
        "display_name": case.display_name,
        "expert_note": case.expert_note,
        "has_tumor": case.has_tumor,
        "source_uris": dict(case.source_uris or {}),
        "metadata_json": dict(case.metadata_json or {}),
        "metadata_statuses": dict(case.metadata_statuses or {}),
    }
