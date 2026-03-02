from __future__ import annotations

import math
import os
from typing import Iterable

import httpx

from app.models import Constraints, Geometry, Location


MAPBOX_DIRECTIONS_BASE = "https://api.mapbox.com/directions/v5/mapbox/walking"


def _is_valid_location(location: Location | None) -> bool:
    if location is None:
        return False

    if not (math.isfinite(location.lat) and math.isfinite(location.lng)):
        return False

    if not (-90.0 <= location.lat <= 90.0 and -180.0 <= location.lng <= 180.0):
        return False

    return True


def _is_placeholder_location(location: Location) -> bool:
    return abs(location.lat) < 1e-9 and abs(location.lng) < 1e-9


def _sanitize_stops(points: Iterable[Location]) -> list[Location]:
    sanitized: list[Location] = []
    for point in points:
        if not _is_valid_location(point):
            continue
        if _is_placeholder_location(point):
            continue
        sanitized.append(point)
    return sanitized


def _destination_for_walk(origin: Location, distance_meters: float, bearing_deg: float) -> tuple[float, float]:
    radius = 6_371_000.0
    bearing = math.radians(bearing_deg)
    lat1 = math.radians(origin.lat)
    lon1 = math.radians(origin.lng)
    delta = distance_meters / radius

    lat2 = math.asin(
        math.sin(lat1) * math.cos(delta) + math.cos(lat1) * math.sin(delta) * math.cos(bearing)
    )
    lon2 = lon1 + math.atan2(
        math.sin(bearing) * math.sin(delta) * math.cos(lat1),
        math.cos(delta) - math.sin(lat1) * math.sin(lat2),
    )

    return (math.degrees(lat2), math.degrees(lon2))


async def _request_directions(
    client: httpx.AsyncClient,
    token: str,
    origin: Location,
    destination: tuple[float, float],
    use_alternatives: bool,
) -> list[dict]:
    destination_lat, destination_lng = destination
    coordinates = f"{origin.lng},{origin.lat};{destination_lng},{destination_lat}"

    params = {
        "alternatives": "true" if use_alternatives else "false",
        "geometries": "geojson",
        "overview": "full",
        "steps": "false",
        "access_token": token,
    }

    response = await client.get(f"{MAPBOX_DIRECTIONS_BASE}/{coordinates}", params=params)
    response.raise_for_status()
    data = response.json()

    if data.get("code") != "Ok":
        return []

    routes = data.get("routes", [])
    normalized: list[dict] = []

    for route in routes:
        geometry_data = route.get("geometry")
        if not geometry_data or geometry_data.get("type") != "LineString":
            continue

        normalized.append(
            {
                "geometry": Geometry(type="LineString", coordinates=geometry_data.get("coordinates", [])),
                "distanceMeters": int(route.get("distance", 0)),
                "durationSeconds": int(route.get("duration", 0)),
            }
        )

    return normalized


async def _request_directions_for_stops(
    client: httpx.AsyncClient,
    token: str,
    points: list[Location],
    use_alternatives: bool,
) -> list[dict]:
    if len(points) < 2:
      return []

    coordinates = ";".join(f"{point.lng},{point.lat}" for point in points)
    params = {
        "alternatives": "true" if use_alternatives else "false",
        "geometries": "geojson",
        "overview": "full",
        "steps": "false",
        "access_token": token,
    }

    response = await client.get(f"{MAPBOX_DIRECTIONS_BASE}/{coordinates}", params=params)
    response.raise_for_status()
    data = response.json()

    if data.get("code") != "Ok":
        return []

    routes = data.get("routes", [])
    normalized: list[dict] = []
    for route in routes:
        geometry_data = route.get("geometry")
        if not geometry_data or geometry_data.get("type") != "LineString":
            continue

        normalized.append(
            {
                "geometry": Geometry(type="LineString", coordinates=geometry_data.get("coordinates", [])),
                "distanceMeters": int(route.get("distance", 0)),
                "durationSeconds": int(route.get("duration", 0)),
            }
        )

    return normalized


def _dedupe_routes(routes: list[dict]) -> list[dict]:
    seen: set[tuple[int, int]] = set()
    result: list[dict] = []

    for route in routes:
        signature = (route["distanceMeters"], route["durationSeconds"])
        if signature in seen:
            continue
        seen.add(signature)
        result.append(route)

    return result


def _is_valid_route(route: dict) -> bool:
    geometry = route.get("geometry")
    coordinates = geometry.coordinates if geometry else []
    return (
        isinstance(coordinates, list)
        and len(coordinates) >= 2
        and route.get("distanceMeters", 0) > 0
        and route.get("durationSeconds", 0) > 0
    )


def _route_accuracy_score(route: dict, target_distance: float, target_duration_seconds: int) -> float:
    distance_error = abs(route["distanceMeters"] - target_distance) / max(target_distance, 1.0)
    duration_error = abs(route["durationSeconds"] - target_duration_seconds) / max(target_duration_seconds, 1)
    point_count = len(route["geometry"].coordinates)
    shape_detail = min(point_count / 40.0, 1.0)

    distance_component = 1.0 - min(distance_error, 1.0)
    duration_component = 1.0 - min(duration_error, 1.0)

    return 0.48 * distance_component + 0.47 * duration_component + 0.05 * shape_detail


async def build_mapbox_probe_routes(
    origin: Location,
    duration_minutes: int,
    constraints: Constraints,
) -> list[dict]:
    if not _is_valid_location(origin) or _is_placeholder_location(origin):
        return []

    token = os.getenv("MAPBOX_ACCESS_TOKEN", "").strip()
    if not token:
        return []

    target_distance = max(1_200.0, min(9_000.0, duration_minutes * 75.0))
    target_duration_seconds = duration_minutes * 60
    candidate_specs = [
        (25.0, 0.46, True),
        (100.0, 0.52, True),
        (175.0, 0.57, False),
        (255.0, 0.50, False),
        (325.0, 0.62, False),
    ]
    if constraints.avoidBusyRoads:
        candidate_specs = [
            (40.0, 0.44, True),
            (125.0, 0.50, True),
            (205.0, 0.56, False),
            (285.0, 0.49, False),
            (345.0, 0.60, False),
        ]

    timeout = httpx.Timeout(6.0, connect=3.0)
    all_routes: list[dict] = []

    async with httpx.AsyncClient(timeout=timeout) as client:
        for bearing, distance_factor, use_alternatives in candidate_specs:
            destination = _destination_for_walk(origin, target_distance * distance_factor, bearing)
            try:
                all_routes.extend(
                    await _request_directions(
                        client=client,
                        token=token,
                        origin=origin,
                        destination=destination,
                        use_alternatives=use_alternatives,
                    )
                )
            except httpx.HTTPError:
                continue

            if len(all_routes) >= 7:
                break

    deduped = [route for route in _dedupe_routes(all_routes) if _is_valid_route(route)]
    ranked = sorted(
        deduped,
        key=lambda route: _route_accuracy_score(route, target_distance, target_duration_seconds),
        reverse=True,
    )[:3]

    for index, route in enumerate(ranked, start=1):
        route["id"] = f"route_{index}"

    return ranked


def _post_process_routes(routes: list[dict]) -> list[dict]:
    for index, route in enumerate(routes, start=1):
        route["id"] = f"route_{index}"
    return routes


async def build_mapbox_routes(
    origin: Location,
    duration_minutes: int,
    constraints: Constraints,
    destination: Location | None = None,
    waypoints: list[Location] | None = None,
) -> list[dict]:
    if not _is_valid_location(origin) or _is_placeholder_location(origin):
        return []

    if destination is not None:
        token = os.getenv("MAPBOX_ACCESS_TOKEN", "").strip()
        if not token:
            return []

        if not _is_valid_location(destination) or _is_placeholder_location(destination):
            return []

        intermediate_waypoints = _sanitize_stops(waypoints or [])
        stops = [origin, *intermediate_waypoints, destination]
        timeout = httpx.Timeout(6.0, connect=3.0)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                routes = await _request_directions_for_stops(
                    client=client,
                    token=token,
                    points=stops,
                    use_alternatives=True,
                )
        except httpx.HTTPError:
            return []

        deduped = [route for route in _dedupe_routes(routes) if _is_valid_route(route)]
        for index, route in enumerate(deduped[:3], start=1):
            route["id"] = f"route_{index}"
        return deduped[:3]

    try:
        from app.core.graph_routing import build_graph_routes
    except Exception:
        return []

    scenic_k = float(os.getenv("GRAPH_SCENIC_K", "1.0"))
    try:
        graph_routes = build_graph_routes(
            origin=origin,
            duration_minutes=duration_minutes,
            constraints=constraints,
            scenic_k=scenic_k,
        )
    except Exception:
        return []

    return _post_process_routes(graph_routes)
