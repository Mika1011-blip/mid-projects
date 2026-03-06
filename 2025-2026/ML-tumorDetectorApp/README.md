# ML-tumorDetectorApp

End-to-end MRI tumor case workflow with:
- NIfTI ingestion and metadata extraction,
- case storage in Postgres + MinIO,
- 2D slice rendering and 3D mesh visualization,
- interactive annotation (apply/undo/redo + mask mesh generation),
- React frontend for case explorer and annotation workspace.

## Architecture
- `backend/`: FastAPI service (`app.main:app`) + Alembic migrations
- `frontend/`: React + TypeScript + Vite + Three.js
- `docker-compose.yml`: local stack orchestration
  - Postgres
  - MinIO
  - backend
  - frontend

## Main backend routes (prefix `/api/v1`)
- Health:
  - `GET /health`
  - `GET /db/health`
- Ingest:
  - `POST /ingest/nifti/batch`
  - `POST /ingest/{case_id}/nifti/batch`
  - `POST /ingest/{case_id}/rename`
  - `POST /ingest/{case_id}/add_note`
- Cases/preview:
  - `GET /cases/get_all`
  - `GET /cases/{case_id}`
  - `GET /cases/{case_id}/preview`
  - `GET /cases/{case_id}/annotation-preview`
- Annotation:
  - `GET /visualize/{case_id}/meshes`
  - `GET /annotation/get_volume/{case_id}`
  - `GET /annotation/mask/{case_id}`
  - `GET /annotation/mask/{case_id}/mesh`
  - `POST /annotation/apply/{case_id}`
  - `POST /annotation/undo/{case_id}`
  - `POST /annotation/redo/{case_id}`

## Required environment variables
Referenced by `docker-compose.yml` and backend settings:
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_DB`
- `DATABASE_URL`
- `S3_ENDPOINT`
- `S3_ACCESS_KEY`
- `S3_SECRET_KEY`
- `S3_BUCKET`
- `S3_REGION`
- `S3_SECURE`
- `MINIO_ROOT_USER`
- `MINIO_ROOT_PASSWORD`
- `VITE_API_BASE` (optional, frontend build arg)

## Quick start (Docker)
```bash
docker compose up --build
```

Services:
- frontend: `http://127.0.0.1:5173`
- backend: `http://127.0.0.1:8000`
- backend docs: `http://127.0.0.1:8000/docs`
- MinIO API: `http://127.0.0.1:9000`
- MinIO Console: `http://127.0.0.1:9001`

## Local development (without Docker)

### Backend
```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

## Notes
- Backend uses NIfTI imaging utilities (`nibabel`, `SimpleITK`) and mesh extraction (`skimage.measure.marching_cubes`).
- Frontend includes a dedicated annotation page and Three.js mesh viewport.
- Large datasets and model artifacts are intentionally excluded by `.gitignore`.
