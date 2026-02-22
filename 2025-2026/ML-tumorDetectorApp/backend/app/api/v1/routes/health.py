from __future__ import annotations
from fastapi import APIRouter
from app.core.db import ping_db

router = APIRouter()

#check liveness
@router.get("/health")
def liveness():
    return {"status": "ok"}

#check readiness
@router.get("/db/health")
def readiness_db():
    return {"status": "ok", "db_ok": ping_db()}