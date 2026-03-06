from __future__ import annotations

import os
import json
import re
import socket
import logging
import importlib
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
    RouteExplanation,
    RouteGenerateRequest,
    RouteGenerateResponse,
    RouteRefineRequest,
    RouteResult,
    SelectedPoi,
)
from app.services.location_search import reverse_geocode, search_locations
from app.services.ai_poi_selector import select_must_see_waypoints
from app.services.mapbox_routes import build_mapbox_probe_routes, build_mapbox_routes
from app.services.mock_routes import build_mock_routes
from app.services.scoring import score_routes


GOOGLE_PLACES_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
NARRATIVE_CANDIDATE_MAX = 12
JOURNEY_NARRATIVE_MIN_LOCATIONS = 3
JOURNEY_NARRATIVE_MAX_LOCATIONS = 4
TOP_RATED_CAFE_MIN_RATING = 4.4
TOP_RATED_CAFE_MIN_REVIEWS = 120

LANDMARK_TYPES = {
    "tourist_attraction",
    "historical_landmark",
    "museum",
    "monument",
    "art_gallery",
}

PARK_TYPES = {
    "park",
    "botanical_garden",
    "garden",
    "national_park",
}

CAFE_TYPES = {
    "cafe",
    "bakery",
    "coffee_shop",
}


def _parse_location_line(location_line: str) -> tuple[str, float | None, float | None]:
    text = location_line.strip()
    if ":" in text:
        text = text.split(":", 1)[1].strip()

    coordinate_match = re.search(r"\((-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)\)\s*$", text)
    if coordinate_match:
        name = text[: coordinate_match.start()].strip()
        try:
            lat = float(coordinate_match.group(1))
            lng = float(coordinate_match.group(2))
        except ValueError:
            lat = None
            lng = None
        return name or text, lat, lng

    return text, None, None


def _classify_candidate(types: set[str], rating: float, rating_count: int) -> str | None:
    if types.intersection(LANDMARK_TYPES):
        return "landmark"
    if types.intersection(PARK_TYPES):
        return "park"
    if types.intersection(CAFE_TYPES) and rating >= TOP_RATED_CAFE_MIN_RATING and rating_count >= TOP_RATED_CAFE_MIN_REVIEWS:
        return "top_rated_cafe"
    return None


def _build_notable_attribute(
    category: str,
    editorial_text: str,
    rating: float,
    rating_count: int,
) -> str:
    cleaned_editorial = " ".join(editorial_text.split())
    if cleaned_editorial:
        return cleaned_editorial

    if category == "landmark":
        return "known as one of the area's iconic cultural highlights"
    if category == "park":
        return "popular for greenery, open views, and a calm walking atmosphere"
    if category == "top_rated_cafe":
        return f"well-reviewed by visitors ({rating:.1f}/5 from {rating_count} reviews)"
    return "a noteworthy local stop"


async def _enrich_candidate_from_places(
    client: httpx.AsyncClient,
    api_key: str,
    name: str,
    lat: float | None,
    lng: float | None,
) -> dict | None:
    payload: dict = {
        "textQuery": name,
        "maxResultCount": 1,
        "languageCode": "en",
    }
    if lat is not None and lng is not None:
        payload["locationBias"] = {
            "circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": 1200.0,
            }
        }

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": (
            "places.displayName,places.primaryType,places.types,places.rating,"
            "places.userRatingCount,places.editorialSummary"
        ),
    }

    try:
        response = await client.post(GOOGLE_PLACES_TEXT_SEARCH_URL, headers=headers, json=payload)
        response.raise_for_status()
    except httpx.HTTPError:
        return None

    places = response.json().get("places", [])
    if not places:
        return None

    place = places[0]
    display_name = ((place.get("displayName") or {}).get("text") or "").strip() or name
    primary_type = str(place.get("primaryType") or "").strip()
    raw_types = place.get("types") if isinstance(place.get("types"), list) else []
    types = {str(item) for item in raw_types if isinstance(item, str)}
    if primary_type:
        types.add(primary_type)

    rating = float(place.get("rating") or 0.0)
    rating_count = int(place.get("userRatingCount") or 0)
    category = _classify_candidate(types=types, rating=rating, rating_count=rating_count)
    if category is None:
        return None

    editorial_text = ((place.get("editorialSummary") or {}).get("text") or "").strip()
    notable_attribute = _build_notable_attribute(
        category=category,
        editorial_text=editorial_text,
        rating=rating,
        rating_count=rating_count,
    )

    return {
        "name": display_name,
        "category": category,
        "notableAttribute": notable_attribute,
        "rating": rating,
        "ratingCount": rating_count,
    }


def _fallback_filter_without_api(name: str) -> str | None:
    lowered = name.lower()
    landmark_keywords = ("museum", "frame", "fort", "heritage", "landmark", "academy", "tower")
    park_keywords = ("park", "garden", "reserve")
    cafe_keywords = ("cafe", "coffee", "roastery", "bakery")

    if any(keyword in lowered for keyword in landmark_keywords):
        return "landmark"
    if any(keyword in lowered for keyword in park_keywords):
        return "park"
    if any(keyword in lowered for keyword in cafe_keywords):
        return "top_rated_cafe"
    return None


async def _prepare_iconic_narrative_locations(
    selected_pois: list[SelectedPoi],
    covered_location_lines: list[str],
    landmark_lines: list[str],
) -> list[dict]:
    raw_candidates: list[tuple[str, float | None, float | None]] = []

    # Preserve journey-first order: route stops first, then explicit POIs, then nearby landmarks.
    for line in covered_location_lines:
        name, lat, lng = _parse_location_line(line)
        raw_candidates.append((name, lat, lng))

    for poi in selected_pois:
        raw_candidates.append((poi.name, poi.location.lat, poi.location.lng))

    for line in landmark_lines:
        name, lat, lng = _parse_location_line(line)
        raw_candidates.append((name, lat, lng))

    deduped: list[tuple[str, float | None, float | None]] = []
    seen: set[str] = set()
    for name, lat, lng in raw_candidates:
        normalized = name.strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append((name.strip(), lat, lng))
        if len(deduped) >= NARRATIVE_CANDIDATE_MAX:
            break

    api_key = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()
    enriched: list[dict] = []

    if api_key:
        timeout = httpx.Timeout(5.5, connect=2.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            for name, lat, lng in deduped:
                item = await _enrich_candidate_from_places(
                    client=client,
                    api_key=api_key,
                    name=name,
                    lat=lat,
                    lng=lng,
                )
                if item is not None:
                    enriched.append(item)
    else:
        for name, _lat, _lng in deduped:
            category = _fallback_filter_without_api(name)
            if category is None:
                continue
            enriched.append(
                {
                    "name": name,
                    "category": category,
                    "notableAttribute": "known locally as a worthwhile stop",
                    "rating": 0.0,
                    "ratingCount": 0,
                }
            )

    enriched_by_name = {
        str(item.get("name", "")).strip().lower(): item
        for item in enriched
        if isinstance(item.get("name"), str) and str(item.get("name")).strip()
    }

    ordered_filtered: list[dict] = []
    added: set[str] = set()
    for name, _lat, _lng in deduped:
        key = name.strip().lower()
        enriched_item = enriched_by_name.get(key)
        if enriched_item is None:
            continue
        if key in added:
            continue
        added.add(key)
        ordered_filtered.append(enriched_item)
        if len(ordered_filtered) >= JOURNEY_NARRATIVE_MAX_LOCATIONS:
            break

    return ordered_filtered

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


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


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


def _normalize_preferences(preferences: Preferences) -> Preferences:
    values = {
        "nature": _clamp(preferences.nature, 0.0, 1.0),
        "water": _clamp(preferences.water, 0.0, 1.0),
        "historic": _clamp(preferences.historic, 0.0, 1.0),
        "quiet": _clamp(preferences.quiet, 0.0, 1.0),
        "viewpoints": _clamp(preferences.viewpoints, 0.0, 1.0),
        "culture": _clamp(preferences.culture, 0.0, 1.0),
        "cafes": _clamp(preferences.cafes, 0.0, 1.0),
    }
    total = sum(values.values())
    if total <= 1e-9:
        return Preferences(
            nature=1 / 7,
            water=1 / 7,
            historic=1 / 7,
            quiet=1 / 7,
            viewpoints=1 / 7,
            culture=1 / 7,
            cafes=1 / 7,
        )
    return Preferences(**{key: value / total for key, value in values.items()})


def _location_text(location: Location, fallback_name: str) -> str:
    label = (location.label or "").strip() or fallback_name
    return f"{label} ({location.lat:.5f}, {location.lng:.5f})"


def _build_covered_location_lines(destination: Location | None, waypoints: list[Location]) -> list[str]:
    lines: list[str] = []
    for index, waypoint in enumerate(waypoints, start=1):
        lines.append(f"Waypoint {index}: {_location_text(waypoint, f'Waypoint {index}')}")
    if destination is not None:
        lines.append(f"Destination: {_location_text(destination, 'Destination')}")
    return lines


def _extract_route_landmark_lines(route: RouteResult, max_items: int = 4) -> list[str]:
    score_debug = route.scoreDebug
    if score_debug is None or not score_debug.tagObjectMatches:
        return []

    lines: list[str] = []
    seen: set[str] = set()
    ordered_tags = ("viewpoints", "historic", "culture", "nature", "water")
    for tag in ordered_tags:
        matches = score_debug.tagObjectMatches.get(tag, [])
        for match in matches:
            name = (match.name or "").strip()
            if not name:
                continue
            if name.lower() in seen:
                continue
            seen.add(name.lower())
            if isinstance(match.lat, (float, int)) and isinstance(match.lng, (float, int)):
                lines.append(f"{name} ({match.lat:.5f}, {match.lng:.5f})")
            else:
                lines.append(name)
            if len(lines) >= max_items:
                return lines
    return lines


def _to_location_name(location_line: str) -> str:
    text = location_line.strip()
    if ":" in text:
        text = text.split(":", 1)[1].strip()
    text = re.sub(r"\s*\(-?\d+(?:\.\d+)?,\s*-?\d+(?:\.\d+)?\)\s*$", "", text).strip()
    return text


def _top_preference_labels(route: RouteResult) -> list[str]:
    labels = {
        "nature": "nature",
        "water": "waterfront",
        "historic": "history",
        "quiet": "calmer streets",
        "viewpoints": "viewpoints",
        "culture": "culture",
        "cafes": "cafe stops",
    }
    top_keys = _top_breakdown_labels(route)
    return [labels.get(key, key) for key in top_keys]


def _limit_sentences(text: str, max_sentences: int = 4) -> str:
    normalized = " ".join(text.split())
    if not normalized:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", normalized)
    return " ".join(parts[:max_sentences]).strip()


def _sanitize_explanation_paragraph(text: str) -> str:
    cleaned = text.replace("Route path", "").replace("route path", "")
    cleaned = cleaned.replace("Origin", "").replace("origin", "")
    cleaned = cleaned.replace("Exact Locations", "").replace("exact locations", "")
    cleaned = cleaned.replace("why this route was selected", "").replace("why this route", "")
    cleaned = cleaned.replace("I picked this route", "").replace("chosen by the algorithm", "")
    cleaned = re.sub(r"\b\d+(?:\.\d+)?\s*/\s*100\b", "", cleaned)
    cleaned = re.sub(r"\bscored\s*\d+(?:\.\d+)?\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*\(-?\d+(?:\.\d+)?,\s*-?\d+(?:\.\d+)?\)", "", cleaned)
    cleaned = cleaned.replace("\n", " ").replace("*", " ").replace("-", " ")
    cleaned = " ".join(cleaned.split())
    return _limit_sentences(cleaned, max_sentences=4)


def _build_location_anchor_payload(destination: Location | None, waypoints: list[Location]) -> list[dict]:
    anchors: list[dict] = []
    for index, waypoint in enumerate(waypoints, start=1):
        anchors.append(
            {
                "kind": f"waypoint_{index}",
                "name": (waypoint.label or f"Waypoint {index}").strip() or f"Waypoint {index}",
                "lat": round(waypoint.lat, 6),
                "lng": round(waypoint.lng, 6),
            }
        )

    if destination is not None:
        anchors.append(
            {
                "kind": "destination",
                "name": (destination.label or "Destination").strip() or "Destination",
                "lat": round(destination.lat, 6),
                "lng": round(destination.lng, 6),
            }
        )
    return anchors


def _build_fallback_selected_explanation(
    selected_route: RouteResult,
    covered_location_lines: list[str],
    landmark_lines: list[str],
    iconic_locations: list[dict] | None = None,
) -> Explanation:
    top_prefs = _top_preference_labels(selected_route)
    pref_text = " and ".join(top_prefs[:2]) if top_prefs else "your preferences"
    place_names = [_to_location_name(item) for item in covered_location_lines if _to_location_name(item)]
    landmark_names = [_to_location_name(item) for item in landmark_lines if _to_location_name(item)]

    if iconic_locations:
        names_with_desc = [
            (
                str(item.get("name", "")).strip(),
                str(item.get("notableAttribute", "")).strip(),
            )
            for item in iconic_locations
            if str(item.get("name", "")).strip()
        ][:JOURNEY_NARRATIVE_MAX_LOCATIONS]
        if len(names_with_desc) >= JOURNEY_NARRATIVE_MIN_LOCATIONS:
            first_name, first_desc = names_with_desc[0]
            second_name, second_desc = names_with_desc[1]
            third_name, third_desc = names_with_desc[2]
            fourth_segment = ""
            if len(names_with_desc) >= 4:
                fourth_name, fourth_desc = names_with_desc[3]
                fourth_segment = f" Before you wrap up, {fourth_name} adds another layer with {fourth_desc}."

            summary = (
                f"Begin by soaking in {first_name}, where {first_desc}. "
                f"Then make your way to {second_name}, known for {second_desc}, as the mood shifts naturally into the next stretch. "
                f"From there, continue toward {third_name}, where {third_desc}, tying the journey together in a way that feels intentionally local." 
                f"{fourth_segment}"
            )
            return Explanation(summary=_limit_sentences(summary, max_sentences=4), reasons=[])

    if place_names:
        place_text = ", ".join(place_names[:2])
        place_sentence = (
            f"You are about to wander through {place_text}, where the neighborhood atmosphere and local texture "
            "make the walk feel personal and memorable."
        )
    elif landmark_names:
        landmark_text = ", ".join(landmark_names[:2])
        place_sentence = (
            f"Along the way, places like {landmark_text} add a sense of story and character that turns this into "
            "more than just a point-to-point walk."
        )
    else:
        place_sentence = (
            "Expect a scenic rhythm with a relaxed flow that is easy to enjoy on foot."
        )

    summary = (
        f"You are in for a route that leans into {pref_text} with a smooth, inviting pace. "
        f"{place_sentence} "
        "Think of it as a local-style stroll designed for moments you will actually want to linger in."
    )
    return Explanation(summary=_limit_sentences(summary, max_sentences=4), reasons=[])


def _count_distinct_location_mentions(summary: str, location_names: list[str]) -> int:
    normalized_summary = summary.lower()
    count = 0
    for name in location_names:
        cleaned = name.strip().lower()
        if not cleaned:
            continue
        if cleaned in normalized_summary:
            count += 1
    return count


def _top_breakdown_labels(route: RouteResult) -> list[str]:
    entries = [
        ("nature", route.scoreBreakdown.nature),
        ("water", route.scoreBreakdown.water),
        ("historic", route.scoreBreakdown.historic),
        ("quiet", route.scoreBreakdown.quiet),
        ("viewpoints", route.scoreBreakdown.viewpoints),
        ("culture", route.scoreBreakdown.culture),
        ("cafes", route.scoreBreakdown.cafes),
    ]
    entries.sort(key=lambda item: item[1], reverse=True)
    return [label for label, _ in entries[:2]]


async def _ai_parse_refinement(
    message: str,
    duration_minutes: int,
    preferences: Preferences,
    constraints: Constraints,
) -> tuple[int, Preferences, Constraints, list[str], bool, str | None]:
    if not _env_flag("AI_REFINEMENT_ENABLED", True):
        return duration_minutes, preferences, constraints, [], False, "AI refinement disabled"

    llm_api_key = os.getenv("OPENROUTER_API_KEY", "").strip() or os.getenv("OPENAI_API_KEY", "").strip()
    if not llm_api_key:
        return duration_minutes, preferences, constraints, [], False, "AI refinement unavailable: missing API key"

    try:
        chat_openai_module = importlib.import_module("langchain_openai")
    except Exception:
        return duration_minutes, preferences, constraints, [], False, "AI refinement unavailable: dependency missing"

    ChatOpenAI = getattr(chat_openai_module, "ChatOpenAI", None)
    if ChatOpenAI is None:
        return duration_minutes, preferences, constraints, [], False, "AI refinement unavailable: invalid client"

    llm = ChatOpenAI(
        model=os.getenv("AI_REFINEMENT_MODEL", os.getenv("AI_POI_SELECTOR_MODEL", "google/gemma-3-12b-it:free")),
        temperature=0,
        timeout=8,
        api_key=llm_api_key,
        base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
    )

    pref_payload = {
        "nature": preferences.nature,
        "water": preferences.water,
        "historic": preferences.historic,
        "quiet": preferences.quiet,
        "viewpoints": preferences.viewpoints,
        "culture": preferences.culture,
        "cafes": preferences.cafes,
    }

    prompt = (
        "You convert a route refinement message into strict JSON. "
        "Return only JSON with shape "
        "{\"durationDeltaMinutes\": number, \"boost\": string[], \"reduce\": string[], "
        "\"avoidBusyRoads\": boolean|null, \"reasons\": string[]}. "
        "Allowed boost/reduce values: nature, water, historic, quiet, viewpoints, culture, cafes. "
        "durationDeltaMinutes must be one of -20,-15,-10,-5,0,5,10,15,20."
    )

    try:
        response = await llm.ainvoke(
            [
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "message": message,
                            "durationMinutes": duration_minutes,
                            "preferences": pref_payload,
                            "constraints": {"avoidBusyRoads": constraints.avoidBusyRoads},
                        }
                    ),
                },
            ]
        )

        content = str(response.content).strip()
        if content.startswith("```") and content.endswith("```"):
            lines = content.splitlines()
            if len(lines) >= 3:
                content = "\n".join(lines[1:-1]).strip()
        parsed = json.loads(content)
    except Exception:
        return duration_minutes, preferences, constraints, [], False, "AI refinement unavailable: parse failed"

    if not isinstance(parsed, dict):
        return duration_minutes, preferences, constraints, [], False, "AI refinement unavailable: invalid schema"

    duration_delta = parsed.get("durationDeltaMinutes", 0)
    if not isinstance(duration_delta, int):
        duration_delta = 0
    duration_delta = max(-20, min(20, duration_delta))
    rounded_delta = int(round(duration_delta / 5.0) * 5)

    allowed_keys = {"nature", "water", "historic", "quiet", "viewpoints", "culture", "cafes"}
    boosts = [key for key in parsed.get("boost", []) if isinstance(key, str) and key in allowed_keys]
    reduces = [key for key in parsed.get("reduce", []) if isinstance(key, str) and key in allowed_keys]

    next_duration = max(10, min(180, duration_minutes + rounded_delta))
    delta_map = {key: 0.0 for key in allowed_keys}
    for key in boosts:
        delta_map[key] += 0.20
    for key in reduces:
        delta_map[key] -= 0.15

    next_preferences = Preferences(
        nature=preferences.nature + delta_map["nature"],
        water=preferences.water + delta_map["water"],
        historic=preferences.historic + delta_map["historic"],
        quiet=preferences.quiet + delta_map["quiet"],
        viewpoints=preferences.viewpoints + delta_map["viewpoints"],
        culture=preferences.culture + delta_map["culture"],
        cafes=preferences.cafes + delta_map["cafes"],
    )
    next_preferences = _normalize_preferences(next_preferences)

    avoid_busy = parsed.get("avoidBusyRoads")
    if isinstance(avoid_busy, bool):
        next_constraints = constraints.model_copy(update={"avoidBusyRoads": avoid_busy})
    else:
        next_constraints = constraints

    reasons_raw = parsed.get("reasons") if isinstance(parsed.get("reasons"), list) else []
    reasons = [reason for reason in reasons_raw if isinstance(reason, str) and reason.strip()][:3]
    if not reasons:
        reasons = [f"Applied AI refinement: {message}"]

    return next_duration, next_preferences, next_constraints, reasons, True, None


def _apply_refinement_heuristic(
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

    updated_preferences = _normalize_preferences(
        Preferences(
        nature=_clamp(nature, 0.0, 1.0),
        water=_clamp(water, 0.0, 1.0),
        historic=_clamp(historic, 0.0, 1.0),
        quiet=_clamp(quiet, 0.0, 1.0),
        viewpoints=_clamp(viewpoints, 0.0, 1.0),
        culture=_clamp(culture, 0.0, 1.0),
        cafes=_clamp(cafes, 0.0, 1.0),
        )
    )

    return updated_duration, updated_preferences, updated_constraints, reasons


async def _build_ai_selected_explanation(
    selected_route: RouteResult,
    all_routes: list[RouteResult],
    anchor_points: list[dict],
    iconic_locations: list[dict],
    covered_location_names: list[str],
    landmark_names: list[str],
    constraints: Constraints,
    ai_waypoint_note: str | None,
) -> Explanation | None:
    if not _env_flag("AI_ROUTE_EXPLANATION_ENABLED", True):
        return None

    llm_api_key = os.getenv("OPENROUTER_API_KEY", "").strip() or os.getenv("OPENAI_API_KEY", "").strip()
    if not llm_api_key:
        return None

    try:
        chat_openai_module = importlib.import_module("langchain_openai")
    except Exception:
        return None

    ChatOpenAI = getattr(chat_openai_module, "ChatOpenAI", None)
    if ChatOpenAI is None:
        return None

    llm = ChatOpenAI(
        model=os.getenv("AI_ROUTE_EXPLANATION_MODEL", os.getenv("AI_POI_SELECTOR_MODEL", "google/gemma-3-12b-it:free")),
        temperature=0.35,
        timeout=8,
        api_key=llm_api_key,
        base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
    )

    route_snapshot = [
        {
            "id": route.id,
            "routeMood": _top_preference_labels(route),
        }
        for route in all_routes
    ]

    prompt = (
        "You are describing a journey from start to finish. You must include at least 3-4 of the provided "
        "landmarks/cafes in the narrative to give a full picture of the route. Begin by ..., then make your way "
        "to ..., and finally stop at ... style transitions should be used to reflect the order the stops appear. "
        "You are an enthusiastic local travel guide and the route is already chosen; sell the experience instead "
        "of justifying the selection. Connect the atmosphere from one place to the next so the paragraph flows as "
        "one continuous story, not a list. If you fail to include at least 3 distinct locations from the provided "
        "list, your response is considered incomplete. Use anchor coordinates only as inspiration and never output "
        "coordinates, scores, metrics, or list formatting. "
        "Return strict JSON: {\"summary\": string}."
    )

    try:
        response = await llm.ainvoke(
            [
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "selectedRouteId": selected_route.id,
                            "routes": route_snapshot,
                            "anchorPoints": anchor_points,
                            "iconicLocations": iconic_locations,
                            "coveredLocations": covered_location_names,
                            "landmarks": landmark_names,
                            "constraints": {"avoidBusyRoads": constraints.avoidBusyRoads},
                            "aiWaypointNote": ai_waypoint_note or "",
                        }
                    ),
                },
            ]
        )
        content = str(response.content).strip()
        if content.startswith("```") and content.endswith("```"):
            lines = content.splitlines()
            if len(lines) >= 3:
                content = "\n".join(lines[1:-1]).strip()
        summary: str | None = None
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                maybe_summary = parsed.get("summary")
                if isinstance(maybe_summary, str):
                    summary = maybe_summary
        except Exception:
            summary = content

        if not isinstance(summary, str) or not summary.strip():
            return None
        final_summary = _sanitize_explanation_paragraph(summary)
        grounded_sources = [str(item.get("name")) for item in iconic_locations if item.get("name")]
        if not grounded_sources:
            grounded_sources = [item for item in covered_location_names + landmark_names if item]
        if len(grounded_sources) >= JOURNEY_NARRATIVE_MIN_LOCATIONS:
            mention_count = _count_distinct_location_mentions(final_summary, grounded_sources)
            if mention_count < JOURNEY_NARRATIVE_MIN_LOCATIONS:
                return None
        if grounded_sources and not any(source.lower() in final_summary.lower() for source in grounded_sources):
            final_summary = _limit_sentences(
                f"{final_summary} Along the way, you will pass through {', '.join(grounded_sources[:2])}, which adds memorable local character.",
                max_sentences=4,
            )

        if not final_summary:
            return None
        return Explanation(summary=final_summary, reasons=[])
    except Exception:
        return None


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
    def _merge_unique_candidates(primary: list[dict], incoming: list[dict], max_items: int = 3) -> list[dict]:
        merged: list[dict] = []
        seen: set[tuple[int, int]] = set()
        for route in [*primary, *incoming]:
            distance = int(route.get("distanceMeters") or 0)
            duration = int(route.get("durationSeconds") or 0)
            if distance <= 0 or duration <= 0:
                continue
            signature = (distance, duration)
            if signature in seen:
                continue
            seen.add(signature)
            merged.append(route)
            if len(merged) >= max_items:
                break
        return merged

    ai_used = False
    ai_fallback_reason: str | None = None
    selected_pois = []
    ai_selection_mode: str | None = None
    ai_selection_latency_ms: int | None = None
    route_waypoints = waypoints
    alternate_destinations: list[Location] = []

    if destination is not None or constraints.includeMustSees:
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
            max_new_waypoints=2 if constraints.includeMustSees else 1,
            force_must_sees=constraints.includeMustSees,
        )

    route_destination = destination
    routing_waypoints = route_waypoints
    if destination is None and constraints.includeMustSees and selected_pois:
        route_destination = selected_pois[0].location
        alternate_destinations = [poi.location for poi in selected_pois[1:3]]
        destination_signature = (round(route_destination.lat, 5), round(route_destination.lng, 5))
        routing_waypoints = [
            waypoint
            for waypoint in route_waypoints
            if (round(waypoint.lat, 5), round(waypoint.lng, 5)) != destination_signature
        ]

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
        destination=route_destination,
        waypoints=routing_waypoints,
    )

    if route_destination is not None and not candidates:
        return RouteGenerateResponse(
            status="no_route",
            requestId=request_id,
            selectedRouteId=None,
            routes=[],
            explanation=Explanation(
                summary="Could not build a walking route to the selected must-see destination from this starting point.",
                reasons=["Try a nearby start point or disable must-see forcing for this run"],
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
            aiUsed=ai_used,
            aiFallbackReason=ai_fallback_reason,
            selectedPois=selected_pois,
            aiSelectionMode=ai_selection_mode,
            aiSelectionLatencyMs=ai_selection_latency_ms,
        )

    if route_destination is not None and 0 < len(candidates) < 3:
        variant_plan: list[tuple[Location, list[Location]]] = []

        if routing_waypoints:
            variant_plan.append((route_destination, []))
            for waypoint in routing_waypoints[:2]:
                variant_plan.append((route_destination, [waypoint]))

        for alt_destination in alternate_destinations:
            variant_plan.append((alt_destination, []))

        for variant_destination, variant_waypoints in variant_plan:
            variant_destination_signature = (round(variant_destination.lat, 5), round(variant_destination.lng, 5))
            if variant_destination_signature == (round(route_destination.lat, 5), round(route_destination.lng, 5)) and variant_waypoints == routing_waypoints:
                continue

            supplemental = await build_mapbox_routes(
                origin=origin,
                duration_minutes=duration_minutes,
                constraints=constraints,
                destination=variant_destination,
                waypoints=variant_waypoints,
            )
            candidates = _merge_unique_candidates(candidates, supplemental, max_items=3)
            if len(candidates) >= 3:
                break

    if route_destination is None and len(candidates) < 3:
        candidates = await build_mapbox_probe_routes(
            origin=origin,
            duration_minutes=duration_minutes,
            constraints=constraints,
        )

    if route_destination is None and len(candidates) < 3:
        candidates = build_mock_routes(origin)

    ranked, weights = await score_routes(candidates, preferences)

    for index, route in enumerate(ranked, start=1):
        route["id"] = f"route_{index}"

    routes = [RouteResult(**route) for route in ranked]
    selected = routes[0]

    covered_location_lines = _build_covered_location_lines(destination=route_destination, waypoints=routing_waypoints)
    location_anchor_points = _build_location_anchor_payload(destination=route_destination, waypoints=routing_waypoints)
    selected_landmark_lines = _extract_route_landmark_lines(selected)
    if ai_used and selected_pois:
        for poi in selected_pois:
            poi_line = f"{poi.name} ({poi.location.lat:.5f}, {poi.location.lng:.5f})"
            if poi_line not in selected_landmark_lines:
                selected_landmark_lines.append(poi_line)

    covered_location_names = [_to_location_name(item) for item in covered_location_lines]
    selected_landmark_names = [_to_location_name(item) for item in selected_landmark_lines]
    iconic_locations = await _prepare_iconic_narrative_locations(
        selected_pois=selected_pois,
        covered_location_lines=covered_location_lines,
        landmark_lines=selected_landmark_lines,
    )

    explanation = _build_fallback_selected_explanation(
        selected_route=selected,
        covered_location_lines=covered_location_lines,
        landmark_lines=selected_landmark_lines,
        iconic_locations=iconic_locations,
    )

    if routes:
        ai_waypoint_note = None
        if ai_used and selected_pois:
            poi_names = ", ".join(poi.name for poi in selected_pois)
            ai_waypoint_note = f"AI waypoint picks: {poi_names}"
        ai_explanation = await _build_ai_selected_explanation(
            selected_route=selected,
            all_routes=routes,
            anchor_points=location_anchor_points,
            iconic_locations=iconic_locations,
            covered_location_names=covered_location_names,
            landmark_names=selected_landmark_names,
            constraints=constraints,
            ai_waypoint_note=ai_waypoint_note,
        )
        if ai_explanation is not None:
            explanation = ai_explanation

    if extra_reasons and "you asked" not in explanation.summary.lower():
        explanation = Explanation(
            summary=_limit_sentences(
                f"{explanation.summary} You asked for a refinement, so this version reflects that direction.",
                max_sentences=4,
            ),
            reasons=[],
        )

    route_explanations: list[RouteExplanation] = []
    for route in routes:
        top_labels = _top_preference_labels(route)
        top_text = " and ".join(top_labels)
        route_landmarks = _extract_route_landmark_lines(route)
        route_locations = covered_location_lines if covered_location_lines else route_landmarks
        route_location_names = [_to_location_name(item) for item in route_locations if _to_location_name(item)]
        route_landmark_names = [_to_location_name(item) for item in route_landmarks if _to_location_name(item)]
        location_text = ", ".join(route_location_names[:2])
        landmark_text = ", ".join(route_landmark_names[:2])
        if location_text:
            summary = (
                f"This walk leans into {top_text} and carries you naturally through {location_text}, "
                "with a pace that feels easy and enjoyable."
            )
        elif landmark_text:
            summary = (
                f"This walk brings out {top_text}, with highlights like {landmark_text} adding personality "
                "and a strong sense of place."
            )
        else:
            summary = (
                f"This walk brings a balanced {top_text} experience, with a scenic flow that feels more like a "
                "local recommendation than a generic route."
            )
        route_explanations.append(
            RouteExplanation(
                routeId=route.id,
                summary=_limit_sentences(summary, max_sentences=4),
                reasons=[],
                locations=route_locations,
            )
        )

    selected_route_index = next((index for index, route in enumerate(route_explanations) if route.routeId == selected.id), -1)
    if selected_route_index >= 0:
        selected_locations = route_explanations[selected_route_index].locations
        route_explanations[selected_route_index] = RouteExplanation(
            routeId=selected.id,
            summary=explanation.summary,
            reasons=[],
            locations=selected_locations,
        )

    return RouteGenerateResponse(
        status="ok",
        requestId=request_id,
        selectedRouteId=selected.id,
        routes=routes,
        explanation=explanation,
        routeExplanations=route_explanations,
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

    (
        updated_duration,
        updated_preferences,
        updated_constraints,
        refinement_reasons,
        ai_refinement_used,
        ai_refinement_fallback,
    ) = await _ai_parse_refinement(
        message=payload.message,
        duration_minutes=base_duration,
        preferences=base_preferences,
        constraints=payload.constraints,
    )

    if not ai_refinement_used:
        updated_duration, updated_preferences, updated_constraints, refinement_reasons = _apply_refinement_heuristic(
            message=payload.message,
            duration_minutes=base_duration,
            preferences=base_preferences,
            constraints=payload.constraints,
        )
        if ai_refinement_fallback:
            refinement_reasons = [f"AI refinement fallback: {ai_refinement_fallback}", *refinement_reasons]
    else:
        refinement_reasons = ["Applied AI interpretation of your refinement request", *refinement_reasons]

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
