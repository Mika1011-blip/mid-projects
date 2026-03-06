# LifeIsGood - housing search assistant

Streamlit application for housing search and analysis with:
- budget and transport cost simulation (Paris, Lyon, Marseille),
- Bienici scraping pipeline,
- listing filtering with DistilCamemBERT,
- price estimation with CatBoost,
- points of interest (POI) exploration via OSM/PostGIS.

## Stack
- Python, Streamlit
- Pandas, Scikit-learn, CatBoost
- Transformers + PyTorch (DistilCamemBERT)
- Folium/Plotly/Matplotlib
- Postgres/PostGIS (for OSM module)

## Main structure
- `app.py`: main Streamlit app
- `pages/`: extra pages (analysis, chat, POI)
- `scrape_bienici.py`: listing collection
- `pipeline_0.py`, `pipeline_v.py`: processing pipelines
- `get_DistilCamemBERT.py`: NLP model loading/inference
- `get_catboost.py`: CatBoost training/loading
- `calculs_transports.py`: transport/budget computations
- `osm.py`, `osm_onl.py`: POI extraction logic

## Prerequisites
- Python 3.10+
- Local models/artifacts (not versioned): `models/`
- Local data files (not versioned): `ressources/data/`, generated CSV outputs
- Optional for POI: running PostGIS DB loaded with OSM data

## Setup
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## Run
```bash
streamlit run app.py
```

## Notes
- Full app features require local models and local datasets that are not stored in git.
- OSM features require a configured PostGIS database (see `osm_README.txt`).

## Presentation
- https://www.canva.com/design/DAG857_3sS0/k0WZjOqxyD-EilLFygnm0Q/edit

## Contributors
- Mika
- Leo
- Paul
- Yane
- Naira
