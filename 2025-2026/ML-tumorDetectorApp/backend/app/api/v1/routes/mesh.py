from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import select
import uuid

from app.core.db import get_db
from app.models import Case
from app.services.mesh import build_case_meshes

router = APIRouter(tags=["mesh"])
LOCAL_OVERLAYS = {"SEG"}
EXTERNAL_OVERLAYS = {"USER", "MODEL"}
ALLOWED_OVERLAYS = LOCAL_OVERLAYS | EXTERNAL_OVERLAYS

def _parse_csv(param: str | None) -> list[str]:
    if not param:
        return []
    return [x.strip().upper() for x in param.split(",") if x.strip()]


@router.get("/visualize/{case_id}/meshes")
def get_case_meshes(
    case_id: uuid.UUID,
    overlays: str | None = Query("SEG,USER,MODEL", description="Comma list: SEG,USER,MODEL"),
    downsample: int = Query(2, ge=1, le=8),
    level: float | None = Query(None),
    run_pipeline_0: bool = Query(True, description="Apply pipeline_0 before meshing"),
    db: Session = Depends(get_db),
):
    case = db.execute(select(Case).where(Case.id == case_id)).scalar_one_or_none()
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    uris = case.source_uris or {}
    if not uris:
        raise HTTPException(status_code=422, detail="Case has no source_uris")

    requested_overlays = set(_parse_csv(overlays))
    requested_overlays = {x for x in requested_overlays if x in ALLOWED_OVERLAYS}
    requested_local_overlays = requested_overlays & LOCAL_OVERLAYS
    requested_external_overlays = requested_overlays & EXTERNAL_OVERLAYS

    meshes = build_case_meshes(
        source_uris=uris,
        downsample=downsample,
        level=level,
        overlays=requested_local_overlays,
        run_pipeline_0=run_pipeline_0,
    )

    return {
        "case_id": str(case_id),
        "run_pipeline_0": run_pipeline_0,
        "external_overlays": {name: None for name in sorted(requested_external_overlays)},
        **meshes,
    }
