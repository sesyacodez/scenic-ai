from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import httpx

from app.models import Location, LocationSearchResult

MAPBOX_GEOCODING_BASE = "https://api.mapbox.com/search/geocode/v6"
MAPBOX_SEARCHBOX_BASE = "https://api.mapbox.com/search/searchbox/v1"


def _get_mapbox_token() -> str:
    return os.getenv("MAPBOX_ACCESS_TOKEN", "").strip()


def _extract_coordinates(feature: dict) -> tuple[float, float] | None:
    properties = feature.get("properties") or {}
    coords = properties.get("coordinates") or {}
    lat = coords.get("latitude")
    lng = coords.get("longitude")

    if isinstance(lat, (float, int)) and isinstance(lng, (float, int)):
        return float(lat), float(lng)

    geometry = feature.get("geometry") or {}
    geometry_coords = geometry.get("coordinates")
    if (
        isinstance(geometry_coords, list)
        and len(geometry_coords) >= 2
        and isinstance(geometry_coords[0], (float, int))
        and isinstance(geometry_coords[1], (float, int))
    ):
        return float(geometry_coords[1]), float(geometry_coords[0])

    return None


async def _retrieve_suggestion(
    client: httpx.AsyncClient,
    token: str,
    session_token: str,
    suggestion: dict,
) -> LocationSearchResult | None:
    mapbox_id = suggestion.get("mapbox_id")
    label = suggestion.get("name")
    full_label = suggestion.get("full_address")

    if not mapbox_id or not label or not full_label:
        return None

    response = await client.get(
        f"{MAPBOX_SEARCHBOX_BASE}/retrieve/{mapbox_id}",
        params={
            "session_token": session_token,
            "access_token": token,
        },
    )
    response.raise_for_status()
    payload = response.json()
    features = payload.get("features", [])
    if not features:
        return None

    first = features[0]
    if not isinstance(first, dict):
        return None

    coords = _extract_coordinates(first)
    if coords is None:
        return None

    lat, lng = coords
    return LocationSearchResult(
        id=str(mapbox_id),
        label=str(label),
        fullLabel=str(full_label),
        location=Location(lat=lat, lng=lng, label=str(full_label)),
    )


async def search_locations(
    query: str,
    limit: int = 5,
    proximity_lat: float | None = None,
    proximity_lng: float | None = None,
) -> list[LocationSearchResult]:
    token = _get_mapbox_token()
    if not token:
        return []

    session_token = uuid4().hex
    provider_limit = max(5, min(10, limit * 2))

    params = {
        "q": query,
        "limit": str(provider_limit),
        "session_token": session_token,
        "access_token": token,
    }
    if proximity_lat is not None and proximity_lng is not None:
        params["proximity"] = f"{proximity_lng},{proximity_lat}"

    timeout = httpx.Timeout(6.0, connect=3.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(f"{MAPBOX_SEARCHBOX_BASE}/suggest", params=params)
            response.raise_for_status()
            payload = response.json()

            suggestions = payload.get("suggestions", [])
            if not isinstance(suggestions, list):
                return []

            tasks = [
                _retrieve_suggestion(client=client, token=token, session_token=session_token, suggestion=suggestion)
                for suggestion in suggestions[:provider_limit]
                if isinstance(suggestion, dict)
            ]
            if not tasks:
                return []

            retrieved = await asyncio.gather(*tasks, return_exceptions=True)
    except httpx.HTTPError:
        return await _search_locations_geocoding(
            query=query,
            limit=limit,
            proximity_lat=proximity_lat,
            proximity_lng=proximity_lng,
            token=token,
        )

    results: list[LocationSearchResult] = []
    for item in retrieved:
        if isinstance(item, Exception) or item is None:
            continue
        results.append(item)

    return results[:limit]


async def _search_locations_geocoding(
    query: str,
    limit: int,
    proximity_lat: float | None,
    proximity_lng: float | None,
    token: str,
) -> list[LocationSearchResult]:
    params = {
        "q": query,
        "access_token": token,
        "autocomplete": "true",
        "limit": str(max(1, min(10, limit))),
    }
    if proximity_lat is not None and proximity_lng is not None:
        params["proximity"] = f"{proximity_lng},{proximity_lat}"

    timeout = httpx.Timeout(5.0, connect=2.5)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(f"{MAPBOX_GEOCODING_BASE}/forward", params=params)
        response.raise_for_status()
        payload = response.json()

    features = payload.get("features", [])
    results: list[LocationSearchResult] = []
    for feature in features:
        if not isinstance(feature, dict):
            continue

        properties = feature.get("properties") or {}
        mapbox_id = feature.get("id")
        name = properties.get("name")
        full_address = properties.get("full_address")
        coords = _extract_coordinates(feature)

        if not mapbox_id or not name or not full_address or coords is None:
            continue

        lat, lng = coords
        results.append(
            LocationSearchResult(
                id=str(mapbox_id),
                label=str(name),
                fullLabel=str(full_address),
                location=Location(lat=lat, lng=lng, label=str(full_address)),
            )
        )

    return results[:limit]


async def reverse_geocode(lat: float, lng: float) -> LocationSearchResult | None:
    token = _get_mapbox_token()
    if not token:
        return None

    params = {
        "longitude": str(lng),
        "latitude": str(lat),
        "access_token": token,
        "limit": "1",
    }

    timeout = httpx.Timeout(5.0, connect=2.5)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(f"{MAPBOX_GEOCODING_BASE}/reverse", params=params)
        response.raise_for_status()
        payload = response.json()

    features = payload.get("features", [])
    if not features:
        return None

    first = features[0]
    if not isinstance(first, dict):
        return None

    properties = first.get("properties") or {}
    coords = _extract_coordinates(first)
    if coords is None:
        return None

    result_label = properties.get("name") or properties.get("full_address") or "Selected location"
    full_label = properties.get("full_address") or str(result_label)
    lat_value, lng_value = coords

    return LocationSearchResult(
        id=str(first.get("id") or f"reverse-{lat}-{lng}"),
        label=str(result_label),
        fullLabel=str(full_label),
        location=Location(lat=lat_value, lng=lng_value, label=str(full_label)),
    )
