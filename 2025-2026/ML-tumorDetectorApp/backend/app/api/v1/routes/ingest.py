# app/api/v1/routes/ingest.py
from fastapi import APIRouter, Depends, File, UploadFile, status, HTTPException, Form
from sqlalchemy.orm import Session
from app.models.case import Case

from app.schemas.case import StringIn
from app.core.db import get_db
from app.services.ingest import (
    create_case_and_ingest_batch,
    ingest_batch_into_existing_case,
)

from pathlib import Path
import os

router = APIRouter(tags=["ingest"])


@router.post("/ingest/nifti/batch", status_code=status.HTTP_201_CREATED)
def ingest_new_case_batch(
    display_name: str | None = Form(None),
    expert_note: str | None = Form(None),
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    return create_case_and_ingest_batch(db=db, files=files,
                                        display_name=display_name,
                                        expert_note=expert_note)

@router.post("/ingest/{case_id}/nifti/batch", status_code=status.HTTP_201_CREATED)
def ingest_existing_case_batch(
    case_id: str,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    return ingest_batch_into_existing_case(db=db, case_id=case_id, files=files)

@router.post("/ingest/{case_id}/rename", status_code=status.HTTP_201_CREATED)
def rename_case(payload : StringIn, case_id : str, db : Session = Depends(get_db)):
    case = db.get(Case,case_id)
    if not case :
        raise HTTPException(status_code=404, detail="Case not found")
    case.display_name = payload.str_input
    db.commit()
    db.refresh(case)
    return {"id": case.id, "display_name": case.display_name}

@router.post("/ingest/{case_id}/add_note", status_code=status.HTTP_201_CREATED)
def add_note(payload : StringIn,case_id : str, db : Session = Depends(get_db)):
    case = db.get(Case,case_id)
    if not case :
        raise HTTPException(status_code=404, detail="Case not found")
    case.expert_note = payload.str_input
    db.commit()
    db.refresh(case)
    return {"id": case.id, "expert_note": case.expert_note}
