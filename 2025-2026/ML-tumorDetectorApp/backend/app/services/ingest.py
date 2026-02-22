from __future__ import annotations

from typing import Optional
from fastapi import UploadFile, HTTPException
from sqlalchemy.orm import Session
import shutil
import re
from dataclasses import dataclass

from app.models import Case
from app.core.config import settings
from app.services.storage_s3 import get_s3_client
from app.utils.filesystem import named_tempfile
from app.services.nifti_metadata import extract_metadata, validate_tumor_presence
from app.services.pipeline import pipeline_0

ALLOWED_SUFFIX = (".nii", ".nii.gz")
ALLOWED_MODALITIES = ("T1CE","FLAIR","T1","T2","SEG")
_MODALITY_RE = re.compile(r"(?<![A-Z0-9])(T1CE|FLAIR|T1|T2|SEG)(?![A-Z0-9])", re.IGNORECASE)

def get_safe_name(filename: str, suffix: str) -> str:
    match = _MODALITY_RE.search(filename or "")
    if match:
        return f"{match.group(1).upper()}{suffix}"
    return filename

def validate_and_get_suffix(filename: str) -> str:
    name = (filename or "").lower()
    if name.endswith(".nii.gz"):
        return ".nii.gz"
    if name.endswith(".nii"):
        return ".nii"
    raise HTTPException(status_code=400, detail=f"Invalid file extension. Allowed: {', '.join(ALLOWED_SUFFIX)}")


@dataclass
class ParsedFile:
    file: UploadFile
    modality: str
    suffix: str
    safe_name: str


def _parse_and_validate_files(files: list[UploadFile],
                              *,
                              existing_modalities: set[str] | None = None):
    if not files or len(files) < 1:
        raise HTTPException(status_code=400, detail="At least 1 file is required.")

    parsed: list[ParsedFile] = []
    seen: set[str] = set()

    # loop and validate file name
    for file in files :
        fname = file.filename
        if not fname :
            raise HTTPException(status_code=400, detail="Missing filename.")
        suffix = validate_and_get_suffix(fname)
        # get modality type (t1ce,flair,t1,t2)
        match = _MODALITY_RE.search(fname or "")
        if not match:
            raise HTTPException(status_code=400, detail=f"Cannot detect modality from filename: {fname}")
        modality_key = match.group(1).upper()

        if modality_key in seen:
            raise HTTPException(status_code=400, detail=f"Duplicate modality in batch: {modality_key}")

        if existing_modalities and modality_key in existing_modalities:
            raise HTTPException(status_code=400, detail=f"Modality already exists in case: {modality_key}")

        seen.add(modality_key)
        safe_name = get_safe_name(filename=fname,suffix=suffix)
        parsed.append(ParsedFile(file=file, modality=modality_key,suffix=suffix, safe_name=safe_name))
    return parsed
def _ensure_case_dicts(case: Case) -> None:
    case.source_uris = dict(case.source_uris or {})
    case.metadata_json = dict(case.metadata_json or {})
    case.metadata_statuses = dict(case.metadata_statuses or {})

def _upload_files_into_cases(*,
                             case: Case, parsed_files: list[ParsedFile]):
    s3_client = get_s3_client()
    case_id = str(case.id)

    uploaded_items: list[dict] = []
    uploaded_keys: list[str] = []

    for f in parsed_files :
        key = f.modality
        object_key = f"cases/{case_id}/{f.safe_name}"
        with named_tempfile(suffix=f.suffix) as tmp_path:
            with open(tmp_path, "wb") as out:
                shutil.copyfileobj(f.file.file, out)

            s3_client.upload_file(
                Bucket=settings.S3_BUCKET,
                Filename=tmp_path,
                Key=object_key,
            )
            uploaded_keys.append(object_key)
            try:
                metadata = extract_metadata(tmp_path)
                if key == "SEG":
                    case.has_tumor = "YES" if validate_tumor_presence(tmp_path) else "NO"
                case.metadata_json[key] = metadata
                case.metadata_statuses[key] = "OK"
            except Exception as e:
                case.metadata_json[key] = {"error": type(e).__name__}
                case.metadata_statuses[key] = "FAILED"

            case.source_uris[key] = object_key

        uploaded_items.append(
            {"key": key, "object_key": object_key, "status": case.metadata_statuses[key]}
        )

    return uploaded_items, uploaded_keys

def create_case_and_ingest_batch(
                                db: Session,
                                display_name : str | None,
                                expert_note : str |None,
                                files: list[UploadFile]
                                ):
    parsed = _parse_and_validate_files(files)

    case = Case(source_type="NIFTI")
    if display_name is not None :
        case.display_name = str(display_name)
    if expert_note is not None :
        case.expert_note = str(expert_note)
    db.add(case)
    db.flush()  # get case.id without committing

    _ensure_case_dicts(case)

    uploaded_keys: list[str] = []
    try:
        uploaded_items, uploaded_keys = _upload_files_into_cases(case=case, parsed_files=parsed)
        db.commit()
        db.refresh(case)
        return {"case_id": str(case.id), "uploaded": uploaded_items}
    except Exception as e:
        db.rollback()
        s3_client = get_s3_client()
        for key in uploaded_keys:
            try:
                s3_client.delete_object(Bucket=settings.S3_BUCKET, Key=key)
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=f"Batch upload failed: {type(e).__name__}")
    finally:
        for f in files:
            try:
                f.file.close()
            except Exception:
                pass


def ingest_batch_into_existing_case(db: Session, case_id: str, files: list[UploadFile]):
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found.")

    _ensure_case_dicts(case)
    existing = set(case.source_uris.keys())

    parsed = _parse_and_validate_files(files, existing_modalities=existing)

    uploaded_keys: list[str] = []
    try:
        uploaded_items, uploaded_keys = _upload_files_into_cases(case=case, parsed_files=parsed)
        db.commit()
        db.refresh(case)
        return {"case_id": str(case.id), "uploaded": uploaded_items}
    except Exception as e:
        db.rollback()
        s3_client = get_s3_client()
        for key in uploaded_keys:
            try:
                s3_client.delete_object(Bucket=settings.S3_BUCKET, Key=key)
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=f"Batch upload failed: {type(e).__name__}")
    finally:
        for f in files:
            try:
                f.file.close()
            except Exception:
                pass
