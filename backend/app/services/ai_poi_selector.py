from __future__ import annotations

import json
import math
import os
import importlib
from time import perf_counter
from dataclasses import dataclass
from typing import TypedDict

import httpx

from app.models import Location, Preferences, SelectedPoi

GOOGLE_PLACES_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"

MUST_SEE_TYPES = {
    "tourist_attraction",
    "historical_landmark",
    "museum",
    "monument",
    "art_gallery",
    "park",
    "botanical_garden",
}

PREFERENCE_TYPE_BONUS = {
    "nature": {"park", "botanical_garden"},
    "water": {"tourist_attraction"},
    "historic": {"historical_landmark", "museum", "monument"},
    "quiet": {"park", "botanical_garden"},
    "viewpoints": {"tourist_attraction"},
    "culture": {"museum", "art_gallery", "historical_landmark"},
    "cafes": {"cafe", "bakery"},
}


@dataclass
class _CandidatePlace:
    place_id: str
    name: str
    lat: float
    lng: float
    rating: float
    rating_count: int
    types: set[str]
    source: str = "google_places"


class _AgentState(TypedDict, total=False):
    candidates: list[dict]
    ranked_place_ids: list[str]


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _haversine_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6_371_000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lng2 - lng1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(1e-12, 1.0 - a)))
    return radius * c


def _midpoint(origin: Location, destination: Location | None) -> tuple[float, float]:
    if destination is None:
        return origin.lat, origin.lng
    return (origin.lat + destination.lat) / 2.0, (origin.lng + destination.lng) / 2.0


def _normalize_rating(rating: float) -> float:
    return max(0.0, min(1.0, rating / 5.0))


def _normalize_rating_count(rating_count: int) -> float:
    if rating_count <= 0:
        return 0.0
    return max(0.0, min(1.0, math.log1p(rating_count) / math.log1p(5000)))


def _preference_type_boost(place_types: set[str], preferences: Preferences) -> float:
    pref_map = {
        "nature": preferences.nature,
        "water": preferences.water,
        "historic": preferences.historic,
        "quiet": preferences.quiet,
        "viewpoints": preferences.viewpoints,
        "culture": preferences.culture,
        "cafes": preferences.cafes,
    }

    boost = 0.0
    for pref_key, pref_value in pref_map.items():
        if pref_value <= 0:
            continue
        bonus_types = PREFERENCE_TYPE_BONUS.get(pref_key, set())
        if place_types.intersection(bonus_types):
            boost += min(0.08, 0.08 * pref_value)

    return min(boost, 0.3)


def _heuristic_relevance(place: _CandidatePlace, preferences: Preferences) -> float:
    must_see_bonus = 0.12 if place.types.intersection(MUST_SEE_TYPES) else 0.0
    rating_component = _normalize_rating(place.rating)
    popularity_component = _normalize_rating_count(place.rating_count)
    type_boost = _preference_type_boost(place.types, preferences)

    score = 0.48 * popularity_component + 0.32 * rating_component + must_see_bonus + type_boost
    return max(0.0, min(1.0, score))


def _strip_fenced_json(content: str) -> str:
    stripped = content.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3:
            return "\n".join(lines[1:-1]).strip()
    return stripped


async def _query_google_places(
    client: httpx.AsyncClient,
    api_key: str,
    query: str,
    center_lat: float,
    center_lng: float,
    radius_meters: int,
    max_results: int,
) -> list[_CandidatePlace]:
    payload = {
        "textQuery": query,
        "maxResultCount": max_results,
        "languageCode": "en",
        "locationBias": {
            "circle": {
                "center": {"latitude": center_lat, "longitude": center_lng},
                "radius": float(radius_meters),
            }
        },
    }

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.id,places.displayName,places.location,places.rating,places.userRatingCount,places.primaryType,places.types",
    }

    response = await client.post(GOOGLE_PLACES_TEXT_SEARCH_URL, headers=headers, json=payload)
    response.raise_for_status()
    body = response.json()

    items: list[_CandidatePlace] = []
    for place in body.get("places", []):
        place_id = str(place.get("id") or "").strip()
        display_name = ((place.get("displayName") or {}).get("text") or "").strip()
        location = place.get("location") or {}
        lat = location.get("latitude")
        lng = location.get("longitude")

        if not place_id or not display_name:
            continue
        if not isinstance(lat, (float, int)) or not isinstance(lng, (float, int)):
            continue

        primary_type = place.get("primaryType")
        types_raw = place.get("types") if isinstance(place.get("types"), list) else []
        type_set = {str(item) for item in types_raw if isinstance(item, str)}
        if isinstance(primary_type, str) and primary_type:
            type_set.add(primary_type)

        items.append(
            _CandidatePlace(
                place_id=place_id,
                name=display_name,
                lat=float(lat),
                lng=float(lng),
                rating=float(place.get("rating") or 0.0),
                rating_count=int(place.get("userRatingCount") or 0),
                types=type_set,
            )
        )

    return items


def _deterministic_geo_filter(
    candidates: list[_CandidatePlace],
    origin: Location,
    destination: Location | None,
    duration_minutes: int,
) -> list[_CandidatePlace]:
    if not candidates:
        return []

    max_leg_distance = max(900.0, min(5500.0, duration_minutes * 90.0))

    if destination is None:
        return [
            candidate
            for candidate in candidates
            if _haversine_meters(origin.lat, origin.lng, candidate.lat, candidate.lng) <= max_leg_distance
        ]

    base_distance = _haversine_meters(origin.lat, origin.lng, destination.lat, destination.lng)
    max_detour = max(600.0, min(3000.0, base_distance * 0.45))

    valid: list[_CandidatePlace] = []
    for candidate in candidates:
        origin_to_candidate = _haversine_meters(origin.lat, origin.lng, candidate.lat, candidate.lng)
        candidate_to_destination = _haversine_meters(candidate.lat, candidate.lng, destination.lat, destination.lng)
        detour = origin_to_candidate + candidate_to_destination - base_distance
        if origin_to_candidate <= max_leg_distance and candidate_to_destination <= max_leg_distance and detour <= max_detour:
            valid.append(candidate)

    return valid


async def _rank_with_langgraph(
    candidates: list[_CandidatePlace],
    preferences: Preferences,
    duration_minutes: int,
    refinement_text: str | None,
) -> list[str]:
    if not _env_flag("AI_POI_LANGGRAPH_ENABLED", True):
        return []

    openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not openai_api_key:
        return []

    try:
        chat_openai_module = importlib.import_module("langchain_openai")
        graph_module = importlib.import_module("langgraph.graph")
    except Exception:
        return []

    ChatOpenAI = getattr(chat_openai_module, "ChatOpenAI", None)
    StateGraph = getattr(graph_module, "StateGraph", None)
    START = getattr(graph_module, "START", None)
    END = getattr(graph_module, "END", None)
    if ChatOpenAI is None or StateGraph is None or START is None or END is None:
        return []

    candidate_payload = [
        {
            "id": candidate.place_id,
            "name": candidate.name,
            "rating": round(candidate.rating, 2),
            "ratingCount": candidate.rating_count,
            "types": sorted(candidate.types),
        }
        for candidate in candidates
    ]

    preference_payload = {
        "nature": preferences.nature,
        "water": preferences.water,
        "historic": preferences.historic,
        "quiet": preferences.quiet,
        "viewpoints": preferences.viewpoints,
        "culture": preferences.culture,
        "cafes": preferences.cafes,
    }

    llm = ChatOpenAI(
        model=os.getenv("AI_POI_SELECTOR_MODEL", "gpt-4o-mini"),
        temperature=0,
        timeout=8,
        api_key=openai_api_key,
    )

    async def rank_node(state: _AgentState) -> _AgentState:
        prompt = (
            "You are ranking must-see POIs for a scenic walking route. "
            "Return strict JSON with shape {\"ordered_place_ids\": string[]}. "
            "Rank by real-world popularity and landmark significance, then user preference fit. "
            "Only use place ids provided."
        )
        user_content = json.dumps(
            {
                "durationMinutes": duration_minutes,
                "refinementText": refinement_text or "",
                "preferences": preference_payload,
                "candidates": state.get("candidates", []),
            }
        )

        response = await llm.ainvoke(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_content},
            ]
        )

        parsed = json.loads(_strip_fenced_json(str(response.content)))
        ordered_ids = parsed.get("ordered_place_ids") if isinstance(parsed, dict) else []
        if not isinstance(ordered_ids, list):
            return {"ranked_place_ids": []}

        result: list[str] = []
        for item in ordered_ids:
            if isinstance(item, str):
                result.append(item)
        return {"ranked_place_ids": result}

    graph = StateGraph(_AgentState)
    graph.add_node("rank", rank_node)
    graph.add_edge(START, "rank")
    graph.add_edge("rank", END)

    app = graph.compile()
    try:
        output = await app.ainvoke({"candidates": candidate_payload})
    except Exception:
        return []

    ranked_ids = output.get("ranked_place_ids", []) if isinstance(output, dict) else []
    return [item for item in ranked_ids if isinstance(item, str)]


async def select_must_see_waypoints(
    origin: Location,
    destination: Location | None,
    waypoints: list[Location],
    duration_minutes: int,
    preferences: Preferences,
    refinement_text: str | None = None,
    max_new_waypoints: int = 1,
) -> tuple[list[Location], list[SelectedPoi], bool, str | None, str | None, int | None]:
    started_at = perf_counter()

    def _done(
        selected_waypoints: list[Location],
        selected_pois: list[SelectedPoi],
        ai_used: bool,
        fallback_reason: str | None,
        mode: str | None,
    ) -> tuple[list[Location], list[SelectedPoi], bool, str | None, str | None, int | None]:
        elapsed_ms = int((perf_counter() - started_at) * 1000)
        return selected_waypoints, selected_pois, ai_used, fallback_reason, mode, elapsed_ms

    if not _env_flag("AI_POI_SELECTOR_ENABLED", True):
        return _done(waypoints, [], False, "AI waypoint selection disabled", "disabled")

    if destination is None:
        return _done(
            waypoints,
            [],
            False,
            "AI waypoint selection skipped: destination not provided",
            "skipped_no_destination",
        )

    if waypoints:
        return _done(
            waypoints,
            [],
            False,
            "AI waypoint selection skipped: using user-specified waypoints",
            "skipped_user_waypoints",
        )

    google_api_key = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()
    if not google_api_key:
        return _done(
            waypoints,
            [],
            False,
            "AI waypoint selection unavailable: GOOGLE_PLACES_API_KEY not configured",
            "unavailable_no_google_key",
        )

    center_lat, center_lng = _midpoint(origin, destination)
    radius_meters = max(1200, min(5000, duration_minutes * 100))

    queries = [
        "must see landmarks and iconic attractions",
        "top rated tourist attractions",
        "historic landmarks and monuments",
    ]

    timeout = httpx.Timeout(6.5, connect=2.5)
    deduped: dict[str, _CandidatePlace] = {}

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            for query in queries:
                candidates = await _query_google_places(
                    client=client,
                    api_key=google_api_key,
                    query=query,
                    center_lat=center_lat,
                    center_lng=center_lng,
                    radius_meters=radius_meters,
                    max_results=12,
                )
                for item in candidates:
                    deduped[item.place_id] = item
    except httpx.HTTPError:
        return _done(
            waypoints,
            [],
            False,
            "AI waypoint selection unavailable: places provider request failed",
            "provider_failed",
        )

    candidates = list(deduped.values())
    if not candidates:
        return _done(
            waypoints,
            [],
            False,
            "AI waypoint selection unavailable: no places returned",
            "provider_empty",
        )

    filtered = _deterministic_geo_filter(
        candidates=candidates,
        origin=origin,
        destination=destination,
        duration_minutes=duration_minutes,
    )
    if not filtered:
        return _done(
            waypoints,
            [],
            False,
            "AI waypoint selection unavailable: no places passed geo validation",
            "geo_filtered_empty",
        )

    by_id = {candidate.place_id: candidate for candidate in filtered}
    heuristic_sorted = sorted(
        filtered,
        key=lambda candidate: _heuristic_relevance(candidate=candidate, preferences=preferences),
        reverse=True,
    )

    ranked_ids = await _rank_with_langgraph(
        candidates=heuristic_sorted[:10],
        preferences=preferences,
        duration_minutes=duration_minutes,
        refinement_text=refinement_text,
    )
    ranking_mode = "langgraph" if ranked_ids else "heuristic"

    llm_ranked: list[_CandidatePlace] = []
    for place_id in ranked_ids:
        match = by_id.get(place_id)
        if match is not None:
            llm_ranked.append(match)

    ranked = llm_ranked if llm_ranked else heuristic_sorted
    selected = ranked[:max(0, min(3, max_new_waypoints))]
    if not selected:
        return _done(
            waypoints,
            [],
            False,
            "AI waypoint selection unavailable: empty ranked set",
            ranking_mode,
        )

    selected_pois = [
        SelectedPoi(
            id=place.place_id,
            name=place.name,
            location=Location(lat=place.lat, lng=place.lng, label=place.name),
            source=place.source,
            confidence=round(_normalize_rating(place.rating), 3),
            relevanceScore=round(_heuristic_relevance(place=place, preferences=preferences), 3),
        )
        for place in selected
    ]

    ai_waypoints = [Location(lat=poi.location.lat, lng=poi.location.lng, label=poi.name) for poi in selected_pois]
    return _done(ai_waypoints, selected_pois, True, None, ranking_mode)
