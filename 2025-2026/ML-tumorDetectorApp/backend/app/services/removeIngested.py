from __future__ import annotations

from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.services.storage_s3 import get_s3_client
from app.models.case import Case
from app.core.config import settings


def remove_case(case_id: str, db: Session) -> None:
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    s3_client = get_s3_client()
    source_uris = case.source_uris or {}

    try:
        for source_uri in source_uris.values():
            s3_client.delete_object(
                Bucket=settings.S3_BUCKET,
                Key=str(source_uri),
            )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed deleting files from case {case_id}",
        ) from e
    try:
        db.delete(case)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed deleting case {case_id}",
        ) from e
