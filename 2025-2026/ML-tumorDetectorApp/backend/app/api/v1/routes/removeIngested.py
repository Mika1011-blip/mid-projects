from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.models.case import Case
from app.core.config import settings
from app.core.db import get_db
from app.services.removeIngested import remove_case
from app.services.storage_s3 import get_s3_client

router = APIRouter(tags=["ingest"])

@router.delete("/removeIngested/{case_id}", status_code=status.HTTP_200_OK)
def remove_ingested_case(case_id: str, db: Session = Depends(get_db)) -> dict:
    remove_case(case_id=case_id, db=db)
    return {"detail": "case_deleted", "case_id": case_id}

@router.delete("/removeIngested/{case_id}/{source_uri:path}", status_code=status.HTTP_200_OK)
def remove_ingested_minio_file(
    case_id: str,
    source_uri: str,
    db: Session = Depends(get_db),
) -> dict:
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    source_uris = dict(case.source_uris or {})
    metadata_json = dict(case.metadata_json or {})
    metadata_statuses = dict(case.metadata_statuses or {})
    key_to_remove = next((k for k, v in source_uris.items() if v == source_uri), None)
    if key_to_remove is None:
        raise HTTPException(status_code=404, detail="File not found in case")

    s3_client = get_s3_client()
    try:
        s3_client.delete_object(
            Bucket=settings.S3_BUCKET,
            Key=source_uri,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed deleting file {source_uri}") from e

    try:
        metadata_json.pop(key_to_remove, None)
        metadata_statuses[key_to_remove] = "PENDING"
        source_uris.pop(key_to_remove, None)
        case.metadata_json = metadata_json
        case.metadata_statuses = metadata_statuses
        case.source_uris = source_uris
        if str(key_to_remove) == "SEG":
            case.has_tumor = "UNDETERMINED"
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed deleting file {source_uri} from case {case_id}",
        ) from e

    return {
        "detail": "file_deleted",
        "case_id": case_id,
        "source_uri": source_uri,
        "modality": key_to_remove,
    }