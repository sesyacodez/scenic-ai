# ScenicAI Backend

FastAPI backend for ScenicAI demo.

## Run

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Endpoints

- `GET /health`
- `POST /api/v1/route/generate`
- `POST /api/v1/route/refine`
