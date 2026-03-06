# ML-RetinaAnalysisWebApp

Retina analysis web app focused on diabetic retinopathy workflows.

This repository currently contains a Flask backend project and ML notebooks.

## Project layout
- `backend_flask (Port-5000)/`: Flask app, routers, services, templates, notebooks
- `frontend_node (Port-6000)/`: reserved frontend folder (currently empty in this working copy)
- `.gitignore`

## Backend capabilities
- Flask app with server-side sessions and CSRF setup (`app/main.py`)
- Retina classification endpoint (`/api/classify`)
- Chat endpoint (`/api/chatgpt`)
- Auth and user management flows (Firebase-based services)
- Patient CRUD endpoints
- TensorFlow-based preprocessing + prediction services

## Backend requirements
From `backend_flask (Port-5000)/requirements.txt`:
- `flask>=2.2.0`
- `tensorflow>=2.10.0,<2.14.0`
- `numpy`
- `opencv-python`
- `Pillow`

Note: additional modules are used in code (for example Flask extensions, Firebase/OpenAI clients). Install missing packages if your environment requires them.

## Run backend
```bash
cd "backend_flask (Port-5000)"
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

Default URL: `http://127.0.0.1:5000`

## Environment and secrets
The backend expects configuration via `.env` and local credential files for Firebase/OpenAI integrations.

Common config keys referenced in code:
- `SECRET_KEY`
- `SESSION_FILE_DIR`
- `FIREBASE_CREDENTIALS`
- `FIREBASE_API_KEY`
- `FIREBASE_AUTH_DOMAIN`
- `FIREBASE_DATABASE_URL`
- `FIREBASE_STORAGE_BUCKET`
- `FIREBASE_PROJECT_ID`
- `FIREBASE_MESSAGING_SENDER_ID`
- `FIREBASE_APP_ID`
- `OPENAI_API_KEY`

## Notes
- Backend includes notebooks under `backend_flask (Port-5000)/jupyter-notebooks/` for preprocessing/training/testing experiments.
- A local sqlite database file exists in this workspace (`RA_webapp.db`) for app data.
