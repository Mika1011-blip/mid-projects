from fastapi import APIRouter
from .routes import health,debug,ingest,cases,removeIngested,mesh
router = APIRouter()
router.include_router(health.router, tags=["health"])
router.include_router(debug.router, tags=["debug"])
router.include_router(ingest.router, tags=["ingest"])
router.include_router(cases.router, tags=["cases"])
router.include_router(removeIngested.router, tags=["removeIngested"])
router.include_router(mesh.router, tags=["mesh"])
