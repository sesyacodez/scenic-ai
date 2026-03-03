# ScenicAI Backend

FastAPI backend for ScenicAI demo.

## Environment

- Copy `.env.example` to `backend/.env`
- Set `MAPBOX_ACCESS_TOKEN`
- Set `GOOGLE_PLACES_API_KEY` for must-see waypoint selection
- Optional: set `OPENAI_API_KEY` to enable LangGraph LLM ranking step
- Optional: set `AI_POI_SELECTOR_ENABLED=true|false` and `AI_POI_LANGGRAPH_ENABLED=true|false`

## Run

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Endpoints

- `GET /health`
- `POST /api/v1/location/search`
- `POST /api/v1/location/reverse`
- `POST /api/v1/route/generate`
- `POST /api/v1/route/refine`
