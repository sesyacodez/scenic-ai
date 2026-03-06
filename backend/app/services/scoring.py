from __future__ import annotations

import asyncio
import hashlib
import math
import os
from collections import OrderedDict, defaultdict

import httpx

_overpass_cache: OrderedDict[str, dict | None] = OrderedDict()
_OVERPASS_CACHE_MAX = 64

from app.models import AppliedWeights, Constraints, Preferences, ScoreBreakdown, ScoreDebug, TagObjectMatch


OVERPASS_INTERPRETER_URL = os.getenv(
    "OVERPASS_INTERPRETER_URL", "https://overpass-api.de/api/interpreter"
)
OVERPASS_INTERPRETER_URLS = [
    url.strip()
    for url in os.getenv(
        "OVERPASS_INTERPRETER_URLS",
        f"{OVERPASS_INTERPRETER_URL},https://overpass.kumi.systems/api/interpreter",
    ).split(",")
    if url.strip()
]

NATURE_NATURAL_TAGS = {
    "wood",
    "tree_row",
    "scrub",
    "grassland",
    "heath",
    "wetland",
    "fell",
}

WATER_NATURAL_TAGS = {"water", "wetland", "bay", "spring", "coastline"}

NATURE_LEISURE_TAGS = {"park", "garden", "nature_reserve"}

NATURE_LANDUSE_TAGS = {"forest", "meadow", "recreation_ground"}

WATER_LANDUSE_TAGS = {"reservoir", "basin"}

VIEWPOINT_TOURISM_TAGS = {"viewpoint"}

CULTURE_TOURISM_TAGS = {"museum", "gallery", "artwork"}

CULTURE_AMENITY_TAGS = {"theatre", "arts_centre", "library"}

CULTURE_HISTORIC_TAGS = {"monument", "memorial", "castle", "archaeological_site", "ruins"}

SPORT_LEISURE_TAGS = {"pitch", "sports_centre", "stadium", "track", "fitness_centre", "golf_course"}

SPORT_AMENITY_TAGS = {"sports_centre", "stadium"}

CAFE_AMENITY_TAGS = {"cafe", "restaurant", "pub", "bar"}

BUSY_HIGHWAY_TAGS = {
    "motorway",
    "motorway_link",
    "trunk",
    "trunk_link",
    "primary",
    "primary_link",
    "secondary",
    "secondary_link",
    "tertiary",
    "tertiary_link",
}

DEBUG_TAG_KEYS = (
    "nature",
    "water",
    "historic",
    "busyRoad",
    "viewpoints",
    "culture",
    "cafes",
)


ROUTE_THEMES: dict[str, dict[str, float]] = {
    "must_see": {
        "nature": 0.12,
        "water": 0.10,
        "historic": 0.22,
        "quiet": 0.08,
        "viewpoints": 0.20,
        "culture": 0.18,
        "cafes": 0.10,
    },
    "cafes_culture": {
        "nature": 0.05,
        "water": 0.05,
        "historic": 0.15,
        "quiet": 0.05,
        "viewpoints": 0.05,
        "culture": 0.30,
        "cafes": 0.35,
    },
    "views_nature": {
        "nature": 0.30,
        "water": 0.20,
        "historic": 0.05,
        "quiet": 0.10,
        "viewpoints": 0.25,
        "culture": 0.05,
        "cafes": 0.05,
    },
}

THEME_ORDER: list[str] = ["must_see", "cafes_culture", "views_nature"]


def build_weights(preferences: Preferences) -> AppliedWeights:
    raw = {
        "nature": max(0.0, preferences.nature),
        "water": max(0.0, preferences.water),
        "historic": max(0.0, preferences.historic),
        "quiet": max(0.0, preferences.quiet),
        "viewpoints": max(0.0, preferences.viewpoints),
        "culture": max(0.0, preferences.culture),
        "cafes": max(0.0, preferences.cafes),
    }

    keys = list(raw.keys())

    total_raw = sum(raw.values())
    if total_raw <= 1e-9:
        return AppliedWeights(**{key: round(1.0 / len(keys), 6) for key in keys})

    normalized = {key: value / total_raw for key, value in raw.items()}
    return AppliedWeights(**normalized)


def _clamp(value: float, min_value: float = 0.0, max_value: float = 1.0) -> float:
    return max(min_value, min(max_value, value))


def _sample_route_points(route: dict, max_points: int = 10) -> list[tuple[float, float]]:
    geometry = route.get("geometry")
    if not geometry:
        return []

    coordinates = geometry.coordinates if hasattr(geometry, "coordinates") else geometry.get("coordinates", [])
    if not coordinates:
        return []

    if len(coordinates) <= max_points:
        return [(coord[1], coord[0]) for coord in coordinates]

    last_index = len(coordinates) - 1
    step = last_index / (max_points - 1)
    indices = sorted({round(step * index) for index in range(max_points)})
    return [(coordinates[index][1], coordinates[index][0]) for index in indices]


def _count_to_score(count: int, scale: float) -> float:
    return _clamp(1.0 - math.exp(-count / max(scale, 1e-6)))


def _build_overpass_query(points: list[tuple[float, float]], radius_meters: int = 180) -> str:
    point_queries: list[str] = []
    for lat, lng in points:
        point_queries.append(f"node(around:{radius_meters},{lat:.6f},{lng:.6f});")
        point_queries.append(f"way(around:{radius_meters},{lat:.6f},{lng:.6f});")

    points_block = "\n    ".join(point_queries)
    return f"""
[out:json][timeout:8];
(
    {points_block}
);
out center tags;
""".strip()


async def _request_overpass_payload(client: httpx.AsyncClient, query: str) -> dict | None:
    cache_key = hashlib.sha256(query.encode()).hexdigest()
    if cache_key in _overpass_cache:
        _overpass_cache.move_to_end(cache_key)
        return _overpass_cache[cache_key]

    headers = {
        "User-Agent": "ScenicAI/0.1 (+https://scenicai.local)",
        "Accept": "application/json",
    }

    for endpoint in OVERPASS_INTERPRETER_URLS:
        for attempt in range(2):
            try:
                response = await client.post(endpoint, data={"data": query}, headers=headers)
                response.raise_for_status()
                payload = response.json()
                _overpass_cache[cache_key] = payload
                if len(_overpass_cache) > _OVERPASS_CACHE_MAX:
                    _overpass_cache.popitem(last=False)
                return payload
            except (httpx.HTTPError, ValueError):
                if attempt < 1:
                    await asyncio.sleep(0.4)
                continue

    _overpass_cache[cache_key] = None
    if len(_overpass_cache) > _OVERPASS_CACHE_MAX:
        _overpass_cache.popitem(last=False)
    return None


def _empty_debug_matches() -> dict[str, list[dict]]:
    return {key: [] for key in DEBUG_TAG_KEYS}


def _stringify_tag_value(value: object) -> str:
    if isinstance(value, list):
        return str(value[0]) if value else ""
    if value is None:
        return ""
    return str(value)


def _extract_debug_tags(tags: dict) -> dict[str, str]:
    debug_keys = (
        "name",
        "natural",
        "leisure",
        "landuse",
        "waterway",
        "highway",
        "historic",
        "tourism",
        "amenity",
        "sport",
        "water",
    )
    extracted: dict[str, str] = {}
    for key in debug_keys:
        value = _stringify_tag_value(tags.get(key))
        if value:
            extracted[key] = value
    return extracted


def _element_to_debug_object(element: dict, tags: dict, matched_by: set[str]) -> dict:
    object_type = str(element.get("type") or "unknown")
    object_id = str(element.get("id") or "unknown")
    lat = element.get("lat")
    lng = element.get("lon")

    if (lat is None or lng is None) and isinstance(element.get("center"), dict):
        center = element["center"]
        lat = center.get("lat")
        lng = center.get("lon")

    tag_values = _extract_debug_tags(tags)
    return {
        "objectId": f"{object_type}:{object_id}",
        "objectType": object_type,
        "name": tag_values.get("name"),
        "lat": float(lat) if lat is not None else None,
        "lng": float(lng) if lng is not None else None,
        "matchedBy": sorted(matched_by),
        "tags": tag_values,
    }


def _attach_debug_match(
    matches_by_tag: dict[str, list[dict]],
    seen_by_tag: dict[str, set[str]],
    debug_object: dict,
    matched_tag: str,
    max_items_per_tag: int = 25,
) -> None:
    if matched_tag not in matches_by_tag:
        return

    object_signature = str(debug_object.get("objectId") or "unknown")
    if object_signature in seen_by_tag[matched_tag]:
        return

    if len(matches_by_tag[matched_tag]) >= max_items_per_tag:
        return

    seen_by_tag[matched_tag].add(object_signature)
    matches_by_tag[matched_tag].append(debug_object)


def _is_sports_related(tags: dict) -> bool:
    leisure = tags.get("leisure")
    amenity = tags.get("amenity")
    return leisure in SPORT_LEISURE_TAGS or amenity in SPORT_AMENITY_TAGS or bool(tags.get("sport"))


def _merge_debug_matches(
    primary: dict[str, list[dict]],
    secondary: dict[str, list[dict]],
    max_items_per_tag: int = 25,
) -> dict[str, list[dict]]:
    merged = _empty_debug_matches()
    for tag in DEBUG_TAG_KEYS:
        seen: set[str] = set()
        for item in primary.get(tag, []):
            signature = str(item.get("objectId") or "unknown")
            if signature in seen:
                continue
            seen.add(signature)
            if len(merged[tag]) < max_items_per_tag:
                merged[tag].append(item)
        for item in secondary.get(tag, []):
            signature = str(item.get("objectId") or "unknown")
            if signature in seen:
                continue
            seen.add(signature)
            if len(merged[tag]) < max_items_per_tag:
                merged[tag].append(item)
    return merged


async def _fetch_overpass_route_context(
    client: httpx.AsyncClient,
    route: dict,
) -> tuple[int, int, int, int, int, int, int, bool, dict[str, list[dict]], bool]:
    points = _sample_route_points(route)
    if not points:
        return 0, 0, 0, 0, 0, 0, 0, False, _empty_debug_matches(), False

    query = _build_overpass_query(points)

    payload = await _request_overpass_payload(client=client, query=query)
    if payload is None:
        return 0, 0, 0, 0, 0, 0, 0, False, _empty_debug_matches(), True

    elements = payload.get("elements", [])
    nature_count = 0
    water_count = 0
    historic_count = 0
    busy_road_count = 0
    viewpoint_count = 0
    culture_count = 0
    cafe_count = 0
    matches_by_tag = _empty_debug_matches()
    seen_by_tag: dict[str, set[str]] = defaultdict(set)

    for element in elements:
        tags = element.get("tags")
        if not isinstance(tags, dict):
            continue

        natural = tags.get("natural")
        leisure = tags.get("leisure")
        landuse = tags.get("landuse")
        waterway = tags.get("waterway")
        highway = tags.get("highway")
        historic = tags.get("historic")
        tourism = tags.get("tourism")
        amenity = tags.get("amenity")
        matched_by: set[str] = set()

        if historic:
            historic_count += 1
            matched_by.add("historic")

        if natural in NATURE_NATURAL_TAGS or leisure in NATURE_LEISURE_TAGS or landuse in NATURE_LANDUSE_TAGS:
            nature_count += 1
            matched_by.add("nature")

        if natural in WATER_NATURAL_TAGS or waterway or landuse in WATER_LANDUSE_TAGS or tags.get("water"):
            water_count += 1
            matched_by.add("water")

        if highway in BUSY_HIGHWAY_TAGS:
            busy_road_count += 1
            matched_by.add("busyRoad")

        if tourism in VIEWPOINT_TOURISM_TAGS:
            viewpoint_count += 1
            matched_by.add("viewpoints")

        is_culture_feature = (
            tourism in CULTURE_TOURISM_TAGS
            or amenity in CULTURE_AMENITY_TAGS
            or historic in CULTURE_HISTORIC_TAGS
        )
        if is_culture_feature and not _is_sports_related(tags):
            culture_count += 1
            matched_by.add("culture")

        if amenity in CAFE_AMENITY_TAGS:
            cafe_count += 1
            matched_by.add("cafes")

        if matched_by:
            debug_object = _element_to_debug_object(element=element, tags=tags, matched_by=matched_by)
            for matched_tag in matched_by:
                _attach_debug_match(matches_by_tag, seen_by_tag, debug_object, matched_tag)

    return (
        nature_count,
        water_count,
        historic_count,
        busy_road_count,
        viewpoint_count,
        culture_count,
        cafe_count,
        True,
        matches_by_tag,
        False,
    )


async def _fetch_route_context(
    client: httpx.AsyncClient,
    route: dict,
) -> tuple[int, int, int, int, int, int, int, bool, dict[str, list[dict]], bool]:
    edge_features = route.get("edgeFeatures")
    if isinstance(edge_features, dict):
        edge_objects_raw = route.get("edgeFeatureObjects")
        edge_objects = edge_objects_raw if isinstance(edge_objects_raw, dict) else _empty_debug_matches()
        (
            nature_count_poi,
            water_count_poi,
            historic_count_poi,
            busy_road_count_poi,
            viewpoint_count_poi,
            culture_count_poi,
            cafe_count_poi,
            has_poi_context,
            poi_matches,
            poi_fetch_failed,
        ) = await _fetch_overpass_route_context(client=client, route=route)
        return (
            int(edge_features.get("nature", 0)) + nature_count_poi,
            int(edge_features.get("water", 0)) + water_count_poi,
            int(edge_features.get("historic", 0)) + historic_count_poi,
            int(edge_features.get("busyRoad", 0)) + busy_road_count_poi,
            int(edge_features.get("viewpoints", 0)) + viewpoint_count_poi,
            int(edge_features.get("culture", 0)) + culture_count_poi,
            int(edge_features.get("cafes", 0)) + cafe_count_poi,
            bool(route.get("graphContextAvailable", True)) or has_poi_context,
            _merge_debug_matches(edge_objects, poi_matches),
            poi_fetch_failed,
        )

    return await _fetch_overpass_route_context(client=client, route=route)


def _breakdown_for_route(
    route: dict,
    nature_count: int,
    water_count: int,
    historic_count: int,
    busy_road_count: int,
    viewpoint_count: int,
    culture_count: int,
    cafe_count: int,
    has_context: bool,
    avoid_busy_roads: bool = False,
) -> tuple[ScoreBreakdown, float, float]:
    speed_mps = route["distanceMeters"] / max(route["durationSeconds"], 1)
    quiet_base = 1.0 - ((speed_mps - 1.1) / 1.1)
    quiet_from_speed = _clamp(0.25 + 0.75 * quiet_base)
    quiet_from_roads = _clamp(1.0 - (busy_road_count / 10.0)) if has_context else 0.0
    quiet = _clamp(0.25 * quiet_from_speed + 0.75 * quiet_from_roads)
    if avoid_busy_roads and has_context and busy_road_count > 0:
        quiet *= 0.7
        quiet = _clamp(quiet)

    if has_context:
        nature = _count_to_score(nature_count, scale=5.0)
        water = _count_to_score(water_count, scale=3.0)
        historic = _count_to_score(historic_count, scale=4.0)
        viewpoints = _count_to_score(viewpoint_count, scale=1.6)
        culture = _count_to_score(culture_count, scale=3.8)
        cafes = _count_to_score(cafe_count, scale=3.8)
    else:
        nature = 0.0
        water = 0.0
        historic = 0.0
        viewpoints = 0.0
        culture = 0.0
        cafes = 0.0

    return (
        ScoreBreakdown(
            nature=round(nature, 3),
            water=round(water, 3),
            historic=round(historic, 3),
            quiet=round(quiet, 3),
            viewpoints=round(viewpoints, 3),
            culture=round(culture, 3),
            cafes=round(cafes, 3),
        ),
        round(quiet_from_speed, 3),
        round(quiet_from_roads, 3),
    )


def scenic_score(breakdown: ScoreBreakdown, weights: AppliedWeights) -> float:
    score_0_1 = (
        breakdown.nature * weights.nature
        + breakdown.water * weights.water
        + breakdown.historic * weights.historic
        + breakdown.quiet * weights.quiet
        + breakdown.viewpoints * weights.viewpoints
        + breakdown.culture * weights.culture
        + breakdown.cafes * weights.cafes
    )
    return round(score_0_1 * 100, 2)


async def score_routes(
    routes: list[dict],
    preferences: Preferences,
    constraints: Constraints | None = None,
) -> tuple[list[dict], AppliedWeights]:
    weights = build_weights(preferences)
    avoid_busy = constraints is not None and constraints.avoidBusyRoads
    scored_routes: list[dict] = []

    timeout = httpx.Timeout(8.0, connect=3.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        route_contexts = await asyncio.gather(
            *[_fetch_route_context(client=client, route=route) for route in routes]
        )

    for route, context in zip(routes, route_contexts):
        (
            nature_count,
            water_count,
            historic_count,
            busy_road_count,
            viewpoint_count,
            culture_count,
            cafe_count,
            has_context,
            tag_object_matches,
            poi_context_fetch_failed,
        ) = context
        breakdown, quiet_from_speed, quiet_from_roads = _breakdown_for_route(
            route,
            nature_count=nature_count,
            water_count=water_count,
            historic_count=historic_count,
            busy_road_count=busy_road_count,
            viewpoint_count=viewpoint_count,
            culture_count=culture_count,
            cafe_count=cafe_count,
            has_context=has_context,
            avoid_busy_roads=avoid_busy,
        )
        score = scenic_score(breakdown, weights)
        scored_routes.append(
            {
                **route,
                "scenicScore": score,
                "scoreBreakdown": breakdown,
                "scoreDebug": ScoreDebug(
                    contextAvailable=has_context,
                    poiContextFetchFailed=poi_context_fetch_failed,
                    natureFeatureCount=nature_count,
                    waterFeatureCount=water_count,
                    historicFeatureCount=historic_count,
                    busyRoadFeatureCount=busy_road_count,
                    viewpointFeatureCount=viewpoint_count,
                    cultureFeatureCount=culture_count,
                    cafeFeatureCount=cafe_count,
                    quietFromSpeed=quiet_from_speed,
                    quietFromRoads=quiet_from_roads,
                    tagObjectMatches={
                        key: [TagObjectMatch(**item) for item in items]
                        for key, items in tag_object_matches.items()
                    },
                ),
            }
        )

    ranked = sorted(
        scored_routes,
        key=lambda item: (
            item["scenicScore"],
            1 if getattr(item["scoreDebug"], "contextAvailable", False) else 0,
        ),
        reverse=True,
    )
    return ranked, weights


async def score_routes_themed(
    routes: list[dict],
    preferences: Preferences | None = None,
    constraints: Constraints | None = None,
) -> tuple[list[tuple[str, dict]], AppliedWeights]:
    """Score routes once, then greedily assign the best candidate per theme.

    Uses *user preferences* for the displayed ``scenicScore`` on each route,
    while theme-specific weights are only used internally for deciding which
    route best fits each theme label.

    Returns a list of ``(theme_key, scored_route_dict)`` tuples in
    ``THEME_ORDER`` and the user-preference ``AppliedWeights``.
    """

    if preferences is not None:
        user_weights = build_weights(preferences)
    else:
        user_weights = build_weights(Preferences(
            nature=1 / 7, water=1 / 7, historic=1 / 7, quiet=1 / 7,
            viewpoints=1 / 7, culture=1 / 7, cafes=1 / 7,
        ))

    avoid_busy = constraints is not None and constraints.avoidBusyRoads

    # --- compute breakdowns once per candidate --------------------------
    timeout = httpx.Timeout(8.0, connect=3.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        route_contexts = await asyncio.gather(
            *[_fetch_route_context(client=client, route=r) for r in routes]
        )

    enriched: list[tuple[dict, ScoreBreakdown]] = []
    for route, context in zip(routes, route_contexts):
        (
            nature_count,
            water_count,
            historic_count,
            busy_road_count,
            viewpoint_count,
            culture_count,
            cafe_count,
            has_context,
            tag_object_matches,
            poi_context_fetch_failed,
        ) = context

        breakdown, quiet_from_speed, quiet_from_roads = _breakdown_for_route(
            route,
            nature_count=nature_count,
            water_count=water_count,
            historic_count=historic_count,
            busy_road_count=busy_road_count,
            viewpoint_count=viewpoint_count,
            culture_count=culture_count,
            cafe_count=cafe_count,
            has_context=has_context,
            avoid_busy_roads=avoid_busy,
        )

        route_with_debug = {
            **route,
            "scoreBreakdown": breakdown,
            "scoreDebug": ScoreDebug(
                contextAvailable=has_context,
                poiContextFetchFailed=poi_context_fetch_failed,
                natureFeatureCount=nature_count,
                waterFeatureCount=water_count,
                historicFeatureCount=historic_count,
                busyRoadFeatureCount=busy_road_count,
                viewpointFeatureCount=viewpoint_count,
                cultureFeatureCount=culture_count,
                cafeFeatureCount=cafe_count,
                quietFromSpeed=quiet_from_speed,
                quietFromRoads=quiet_from_roads,
                tagObjectMatches={
                    key: [TagObjectMatch(**item) for item in items]
                    for key, items in tag_object_matches.items()
                },
            ),
        }
        enriched.append((route_with_debug, breakdown))

    # --- greedy theme assignment ----------------------------------------
    theme_weights_map = {
        theme: AppliedWeights(**ROUTE_THEMES[theme]) for theme in THEME_ORDER
    }

    assigned: list[tuple[str, dict]] = []
    used_indices: set[int] = set()

    for theme in THEME_ORDER:
        tw = theme_weights_map[theme]
        best_idx = -1
        best_score = -1.0
        for idx, (route_dict, bd) in enumerate(enriched):
            if idx in used_indices:
                continue
            s = scenic_score(bd, tw)
            if s > best_score:
                best_score = s
                best_idx = idx
        if best_idx == -1:
            # Fewer candidates than themes — skip instead of reusing
            continue
        if best_idx >= 0:
            route_dict, bd = enriched[best_idx]
            user_score = scenic_score(bd, user_weights)
            route_dict = {**route_dict, "scenicScore": user_score}
            assigned.append((theme, route_dict))
            used_indices.add(best_idx)

    return assigned, user_weights
