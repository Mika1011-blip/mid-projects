# mid-projects

Collection of mid-size ML and full-stack projects.

## Structure

- `2025-2026/` : current project set (ML + web apps)

## Project Index

### 2025-2026

#### 1) `2025-2026/analyze_bienetre/`
Housing search assistant built with Streamlit.

Brief:
- scrapes listing data (Bienici),
- computes budget and transport costs,
- uses DistilCamemBERT for listing text checks,
- uses CatBoost for price estimation,
- includes OSM/PostGIS utilities for points of interest.

Stack:
- Python, Streamlit, Pandas, Scikit-learn, CatBoost, Transformers/PyTorch

Project README:
- `2025-2026/analyze_bienetre/README.md`

#### 2) `2025-2026/ML-RetinaAnalysisWebApp/`
Retina analysis web app (Flask backend + ML pipeline notebooks).

Brief:
- image classification workflows for diabetic retinopathy,
- Flask routes for classify/chat/auth/patient management,
- TensorFlow-based preprocessing + inference services,
- Firebase/OpenAI integrations configured by environment variables.

Stack:
- Flask, TensorFlow, OpenCV, Pillow, HTML/CSS templates

Notes:
- `frontend_node (Port-6000)/` exists but is currently empty in this repo snapshot.

Project README:
- `2025-2026/ML-RetinaAnalysisWebApp/README.md`

#### 3) `2025-2026/ML-tumorDetectorApp/`
MRI tumor case ingestion, visualization, and annotation platform.

Brief:
- FastAPI backend for NIfTI ingest/case metadata/slice rendering,
- 3D mesh generation and annotation workflows (apply/undo/redo),
- React + TypeScript frontend with Three.js mesh viewport,
- Docker Compose stack with Postgres + MinIO + backend + frontend.

Stack:
- FastAPI, SQLAlchemy, Alembic, React, TypeScript, Three.js, Docker

Project README:
- `2025-2026/ML-tumorDetectorApp/README.md`

## Repo Notes

- Most projects need local `.env` files and local model/data artifacts to run fully.
- Large artifacts and secrets are intentionally excluded via `.gitignore`.
