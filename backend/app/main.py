from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI

from app.models import (
    Explanation,
    RouteGenerateRequest,
    RouteGenerateResponse,
    RouteRefineRequest,
    RouteResult,
)
from app.services.mock_routes import build_mock_routes
from app.services.scoring import score_routes

app = FastAPI(title="ScenicAI Backend", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "scenicai-backend"}


@app.post("/api/v1/route/generate", response_model=RouteGenerateResponse)
def generate_route(payload: RouteGenerateRequest) -> RouteGenerateResponse:
    request_id = f"req_{uuid4().hex[:10]}"
    candidates = build_mock_routes(payload.origin)
    ranked, weights = score_routes(candidates, payload.preferences)

    routes = [RouteResult(**route) for route in ranked]
    selected = routes[0]

    explanation = Explanation(
        summary="Selected route balances your scenic preferences while avoiding busier segments.",
        reasons=[
            "Highest weighted scenic score among the candidate routes",
            "Matches your current preference weighting profile",
        ],
    )

    return RouteGenerateResponse(
        status="ok",
        requestId=request_id,
        selectedRouteId=selected.id,
        routes=routes,
        explanation=explanation,
        appliedWeights=weights,
    )


@app.post("/api/v1/route/refine", response_model=RouteGenerateResponse)
def refine_route(payload: RouteRefineRequest) -> RouteGenerateResponse:
    request_id = f"req_{uuid4().hex[:10]}"

    explanation = Explanation(
        summary="Refinement endpoint scaffold is active.",
        reasons=[
            "Session-aware refinement pipeline will be connected in next milestone",
            f"Captured message: {payload.message}",
        ],
    )

    return RouteGenerateResponse(
        status="no_route",
        requestId=request_id,
        selectedRouteId=None,
        routes=[],
        explanation=explanation,
        appliedWeights={"nature": 0.25, "water": 0.25, "historic": 0.25, "quiet": 0.25},
    )
