from __future__ import annotations

import os
import socket
import logging
from pathlib import Path
from uuid import uuid4

import httpx
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


def _load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = value.strip().strip('"').strip("'")


env_file = Path(__file__).resolve().parents[1] / ".env"
if load_dotenv is not None:
    load_dotenv(env_file)
else:
    _load_env_file(env_file)

from app.models import (
    Constraints,
    Explanation,
    Location,
    LocationSearchRequest,
    LocationSearchResponse,
    Preferences,
    ReverseGeocodeRequest,
    RouteGenerateRequest,
    RouteGenerateResponse,
    RouteRefineRequest,
    RouteResult,
)
from app.services.location_search import reverse_geocode, search_locations
from app.services.ai_poi_selector import select_must_see_waypoints
from app.services.mapbox_routes import build_mapbox_probe_routes, build_mapbox_routes
from app.services.mock_routes import build_mock_routes
from app.services.scoring import score_routes

app = FastAPI(title="ScenicAI Backend", version="0.1.0")
logger = logging.getLogger("scenicai.backend")

cors_allow_origins_env = os.getenv("CORS_ALLOW_ORIGINS", "")
configured_cors_origins = {origin.strip() for origin in cors_allow_origins_env.split(",") if origin.strip()}
dev_ports = (3000, 3001, 5173)
hostname = socket.gethostname()
default_dev_origins = {
    origin
    for port in dev_ports
    for origin in (
        f"http://localhost:{port}",
        f"http://127.0.0.1:{port}",
        f"http://[::1]:{port}",
        f"http://{hostname}:{port}",
    )
}
cors_allow_origins = sorted(configured_cors_origins | default_dev_origins)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allow_origins,
    allow_origin_regex=r"https?://((localhost|127\.0\.0\.1|\[::1\]|0\.0\.0\.0|10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[0-1])(?:\.\d{1,3}){2})|([a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*))(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "scenicai-backend"}


@app.post("/api/v1/location/search", response_model=LocationSearchResponse)
async def location_search(payload: LocationSearchRequest) -> LocationSearchResponse:
    try:
        results = await search_locations(
            query=payload.query,
            limit=payload.limit,
            proximity_lat=payload.proximityLat,
            proximity_lng=payload.proximityLng,
        )
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail=f"Location search provider unavailable: {error}") from error

    return LocationSearchResponse(results=results)


@app.post("/api/v1/location/reverse", response_model=LocationSearchResponse)
async def location_reverse(payload: ReverseGeocodeRequest) -> LocationSearchResponse:
    try:
        result = await reverse_geocode(lat=payload.lat, lng=payload.lng)
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail=f"Reverse geocoding provider unavailable: {error}") from error

    return LocationSearchResponse(results=[result] if result is not None else [])


def _clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def _is_placeholder_location(location: Location) -> bool:
    return abs(location.lat) < 1e-9 and abs(location.lng) < 1e-9


def _validate_route_points(origin: Location, destination: Location | None, waypoints: list[Location]) -> None:
    if _is_placeholder_location(origin):
        raise HTTPException(
            status_code=422,
            detail="Origin coordinates are invalid. Please pick a valid origin from suggestions or use current location.",
        )

    if destination is not None and _is_placeholder_location(destination):
        raise HTTPException(
            status_code=422,
            detail="Destination coordinates are invalid. Please select a destination from suggestions.",
        )

    for index, waypoint in enumerate(waypoints, start=1):
        if _is_placeholder_location(waypoint):
            raise HTTPException(
                status_code=422,
                detail=f"Waypoint {index} coordinates are invalid. Please select a valid waypoint from suggestions.",
            )


def _apply_refinement(
    message: str,
    duration_minutes: int,
    preferences: Preferences,
    constraints: Constraints,
) -> tuple[int, Preferences, Constraints, list[str]]:
    lowered = message.lower()
    reasons: list[str] = [f"Applied refinement: {message}"]

    updated_duration = duration_minutes
    if "shorter" in lowered or "short" in lowered:
        updated_duration = max(10, duration_minutes - 10)
        reasons.append("Reduced target duration")
    elif "longer" in lowered or "long" in lowered:
        updated_duration = min(180, duration_minutes + 10)
        reasons.append("Increased target duration")

    nature = preferences.nature
    water = preferences.water
    historic = preferences.historic
    quiet = preferences.quiet
    viewpoints = preferences.viewpoints
    culture = preferences.culture
    cafes = preferences.cafes

    if "more nature" in lowered:
        nature += 0.25
        reasons.append("Increased nature weighting")
    if "more water" in lowered:
        water += 0.25
        reasons.append("Increased water weighting")
    if "more historic" in lowered:
        historic += 0.25
        reasons.append("Increased historic weighting")
    if "quieter" in lowered or "more quiet" in lowered:
        quiet += 0.25
        reasons.append("Increased quiet weighting")
    if "more views" in lowered or "more viewpoint" in lowered:
        viewpoints += 0.25
        reasons.append("Increased viewpoints weighting")
    if "more culture" in lowered or "more museum" in lowered:
        culture += 0.25
        reasons.append("Increased culture weighting")
    if "more cafes" in lowered or "more cafe" in lowered:
        cafes += 0.25
        reasons.append("Increased cafes weighting")

    updated_constraints = constraints
    if "avoid busy" in lowered or "less traffic" in lowered:
        updated_constraints = constraints.model_copy(update={"avoidBusyRoads": True})
        reasons.append("Enabled busy-road avoidance")

    updated_preferences = Preferences(
        nature=_clamp(nature, 0.0, 1.0),
        water=_clamp(water, 0.0, 1.0),
        historic=_clamp(historic, 0.0, 1.0),
        quiet=_clamp(quiet, 0.0, 1.0),
        viewpoints=_clamp(viewpoints, 0.0, 1.0),
        culture=_clamp(culture, 0.0, 1.0),
        cafes=_clamp(cafes, 0.0, 1.0),
    )

    return updated_duration, updated_preferences, updated_constraints, reasons


async def _plan_routes(
    request_id: str,
    origin,
    destination,
    waypoints,
    duration_minutes: int,
    preferences: Preferences,
    constraints: Constraints,
    extra_reasons: list[str] | None = None,
    refinement_text: str | None = None,
) -> RouteGenerateResponse:
    ai_used = False
    ai_fallback_reason: str | None = None
    selected_pois = []
    ai_selection_mode: str | None = None
    ai_selection_latency_ms: int | None = None
    route_waypoints = waypoints

    if destination is not None:
        (
            route_waypoints,
            selected_pois,
            ai_used,
            ai_fallback_reason,
            ai_selection_mode,
            ai_selection_latency_ms,
        ) = await select_must_see_waypoints(
            origin=origin,
            destination=destination,
            waypoints=waypoints,
            duration_minutes=duration_minutes,
            preferences=preferences,
            refinement_text=refinement_text,
            max_new_waypoints=1,
        )

    logger.info(
        "route_request_id=%s ai_used=%s ai_selection_mode=%s ai_selection_latency_ms=%s ai_fallback_reason=%s selected_poi_count=%s",
        request_id,
        ai_used,
        ai_selection_mode,
        ai_selection_latency_ms,
        ai_fallback_reason,
        len(selected_pois),
    )

    candidates = await build_mapbox_routes(
        origin=origin,
        duration_minutes=duration_minutes,
        constraints=constraints,
        destination=destination,
        waypoints=route_waypoints,
    )

    used_probe_fallback = False
    used_mock_fallback = False
    if len(candidates) < 3:
        used_probe_fallback = True
        candidates = await build_mapbox_probe_routes(
            origin=origin,
            duration_minutes=duration_minutes,
            constraints=constraints,
        )

    if len(candidates) < 3:
        used_mock_fallback = True
        candidates = build_mock_routes(origin)

    ranked, weights = await score_routes(candidates, preferences)

    routes = [RouteResult(**route) for route in ranked]
    selected = routes[0]

    reasons = [
        "Highest weighted scenic score among the candidate routes",
        "Matches your current preference weighting profile",
    ]
    if constraints.avoidBusyRoads:
        reasons.append("Applied busy-road avoidance preference")
    if used_probe_fallback:
        reasons.append("Used legacy probe routing fallback after graph construction failure")
    if used_mock_fallback:
        reasons.append("Used deterministic mock fallback due to route provider availability")
    if ai_used and selected_pois:
        reasons.append("Included an AI-selected must-see waypoint before deterministic route generation")
    elif ai_fallback_reason:
        reasons.append(ai_fallback_reason)
    if extra_reasons:
        reasons = extra_reasons + reasons

    explanation = Explanation(
        summary="Selected route balances your scenic preferences while avoiding busier segments.",
        reasons=reasons[:3],
    )

    return RouteGenerateResponse(
        status="ok",
        requestId=request_id,
        selectedRouteId=selected.id,
        routes=routes,
        explanation=explanation,
        appliedWeights=weights,
        aiUsed=ai_used,
        aiFallbackReason=ai_fallback_reason,
        selectedPois=selected_pois,
        aiSelectionMode=ai_selection_mode,
        aiSelectionLatencyMs=ai_selection_latency_ms,
    )


@app.post("/api/v1/route/generate", response_model=RouteGenerateResponse)
async def generate_route(payload: RouteGenerateRequest) -> RouteGenerateResponse:
    request_id = f"req_{uuid4().hex[:10]}"
    _validate_route_points(
        origin=payload.origin,
        destination=payload.destination,
        waypoints=payload.waypoints,
    )
    return await _plan_routes(
        request_id=request_id,
        origin=payload.origin,
        destination=payload.destination,
        waypoints=payload.waypoints,
        duration_minutes=payload.durationMinutes,
        preferences=payload.preferences,
        constraints=payload.constraints,
        refinement_text=payload.refinementText,
    )


@app.post("/api/v1/route/refine", response_model=RouteGenerateResponse)
async def refine_route(payload: RouteRefineRequest) -> RouteGenerateResponse:
    request_id = f"req_{uuid4().hex[:10]}"

    if payload.origin is None:
        return RouteGenerateResponse(
            status="no_route",
            requestId=request_id,
            selectedRouteId=None,
            routes=[],
            explanation=Explanation(
                summary="Refinement needs a current starting location.",
                reasons=["Provide location and generate once before refining"],
            ),
            appliedWeights={
                "nature": 0.143,
                "water": 0.143,
                "historic": 0.143,
                "quiet": 0.143,
                "viewpoints": 0.143,
                "culture": 0.143,
                "cafes": 0.142,
            },
        )

    _validate_route_points(
        origin=payload.origin,
        destination=payload.destination,
        waypoints=payload.waypoints or [],
    )

    base_duration = payload.durationMinutes if payload.durationMinutes is not None else 45
    base_preferences = (
        payload.preferences
        if payload.preferences is not None
        else Preferences(
            nature=1 / 7,
            water=1 / 7,
            historic=1 / 7,
            quiet=1 / 7,
            viewpoints=1 / 7,
            culture=1 / 7,
            cafes=1 / 7,
        )
    )

    updated_duration, updated_preferences, updated_constraints, refinement_reasons = _apply_refinement(
        message=payload.message,
        duration_minutes=base_duration,
        preferences=base_preferences,
        constraints=payload.constraints,
    )

    return await _plan_routes(
        request_id=request_id,
        origin=payload.origin,
        destination=payload.destination,
        waypoints=payload.waypoints or [],
        duration_minutes=updated_duration,
        preferences=updated_preferences,
        constraints=updated_constraints,
        extra_reasons=refinement_reasons,
        refinement_text=payload.message,
    )
