# ScenicAI Backend

FastAPI backend for ScenicAI demo.

## Environment

- Copy `.env.example` to `backend/.env`
- Set `MAPBOX_ACCESS_TOKEN`

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
