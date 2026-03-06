from __future__ import annotations

import math
from dataclasses import dataclass

import networkx as nx
import osmnx as ox

from app.models import Constraints, Geometry, Location


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

CAFE_AMENITY_TAGS = {"cafe", "restaurant", "pub", "bar"}

SPORT_LEISURE_TAGS = {"pitch", "sports_centre", "stadium", "track", "fitness_centre", "golf_course"}

SPORT_AMENITY_TAGS = {"sports_centre", "stadium"}

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

WALKING_SPEED_MPS = 1.35

DEBUG_TAG_KEYS = (
    "nature",
    "water",
    "historic",
    "busyRoad",
    "viewpoints",
    "culture",
    "cafes",
)


@dataclass(slots=True)
class EdgeFeatures:
    nature: int
    water: int
    historic: int
    busyRoad: int
    viewpoints: int
    culture: int
    cafes: int

    @property
    def scenic_score(self) -> float:
        return float(
            self.nature
            + self.water
            + self.historic
            + self.viewpoints
            + self.culture
            + self.cafes
            - self.busyRoad
        )


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

    return math.degrees(lat2), math.degrees(lon2)


def _is_sports_related(tags: dict) -> bool:
    leisure = tags.get("leisure")
    amenity = tags.get("amenity")
    return leisure in SPORT_LEISURE_TAGS or amenity in SPORT_AMENITY_TAGS or bool(tags.get("sport"))


def _first_tag_value(value: object) -> str | None:
    if isinstance(value, list):
        return str(value[0]) if value else None
    if isinstance(value, str):
        return value
    return None


def _extract_edge_features(tags: dict) -> EdgeFeatures:
    natural = _first_tag_value(tags.get("natural"))
    leisure = _first_tag_value(tags.get("leisure"))
    landuse = _first_tag_value(tags.get("landuse"))
    waterway = _first_tag_value(tags.get("waterway"))
    highway = _first_tag_value(tags.get("highway"))
    historic = _first_tag_value(tags.get("historic"))
    tourism = _first_tag_value(tags.get("tourism"))
    amenity = _first_tag_value(tags.get("amenity"))

    nature = int(
        natural in NATURE_NATURAL_TAGS or leisure in NATURE_LEISURE_TAGS or landuse in NATURE_LANDUSE_TAGS
    )
    water = int(natural in WATER_NATURAL_TAGS or bool(waterway) or landuse in WATER_LANDUSE_TAGS or bool(tags.get("water")))
    historic_count = int(bool(historic))
    busy_road = int(highway in BUSY_HIGHWAY_TAGS)
    viewpoints = int(tourism in VIEWPOINT_TOURISM_TAGS)

    is_culture_feature = tourism in CULTURE_TOURISM_TAGS or amenity in CULTURE_AMENITY_TAGS or historic in CULTURE_HISTORIC_TAGS
    culture = int(is_culture_feature and not _is_sports_related(tags))
    cafes = int(amenity in CAFE_AMENITY_TAGS)

    return EdgeFeatures(
        nature=nature,
        water=water,
        historic=historic_count,
        busyRoad=busy_road,
        viewpoints=viewpoints,
        culture=culture,
        cafes=cafes,
    )


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


def _edge_center(edge_data: dict, graph: nx.MultiDiGraph, u: int, v: int) -> tuple[float | None, float | None]:
    edge_geometry = edge_data.get("geometry")
    if edge_geometry is not None and len(edge_geometry.coords) > 0:
        midpoint_index = len(edge_geometry.coords) // 2
        midpoint_lng, midpoint_lat = edge_geometry.coords[midpoint_index]
        return float(midpoint_lat), float(midpoint_lng)

    node_u = graph.nodes.get(u, {})
    node_v = graph.nodes.get(v, {})
    if "x" in node_u and "y" in node_u and "x" in node_v and "y" in node_v:
        midpoint_lng = (float(node_u["x"]) + float(node_v["x"])) / 2.0
        midpoint_lat = (float(node_u["y"]) + float(node_v["y"])) / 2.0
        return midpoint_lat, midpoint_lng

    return None, None


def _edge_debug_object(
    graph: nx.MultiDiGraph,
    u: int,
    v: int,
    edge_key: object,
    edge_data: dict,
    matched_by: list[str],
) -> dict:
    lat, lng = _edge_center(edge_data=edge_data, graph=graph, u=u, v=v)
    tag_values = _extract_debug_tags(edge_data)
    return {
        "objectId": f"edge:{u}->{v}:{edge_key}",
        "objectType": "edge",
        "name": tag_values.get("name"),
        "lat": lat,
        "lng": lng,
        "matchedBy": sorted(matched_by),
        "tags": tag_values,
    }


def _build_route_geometry(
    graph: nx.MultiDiGraph,
    path_nodes: list[int],
) -> tuple[list[list[float]], float, dict[str, int], dict[str, list[dict]]]:
    coordinates: list[list[float]] = []
    total_length = 0.0
    aggregate = {
        "nature": 0,
        "water": 0,
        "historic": 0,
        "busyRoad": 0,
        "viewpoints": 0,
        "culture": 0,
        "cafes": 0,
    }
    feature_objects = {key: [] for key in DEBUG_TAG_KEYS}
    seen_by_tag = {key: set() for key in DEBUG_TAG_KEYS}

    for index in range(len(path_nodes) - 1):
        u = path_nodes[index]
        v = path_nodes[index + 1]
        edge_bundle = graph.get_edge_data(u, v)
        if not edge_bundle:
            continue

        selected_edge_key, selected_edge = min(
            edge_bundle.items(), key=lambda item: item[1].get("weight", item[1].get("length", 1.0))
        )
        edge_length = float(selected_edge.get("length", 0.0))
        total_length += edge_length

        features = selected_edge.get("scenic_features", {})
        for key in aggregate:
            aggregate[key] += int(features.get(key, 0))

        matched_by = [key for key in DEBUG_TAG_KEYS if int(features.get(key, 0)) > 0]
        if matched_by:
            debug_object = _edge_debug_object(
                graph=graph,
                u=u,
                v=v,
                edge_key=selected_edge_key,
                edge_data=selected_edge,
                matched_by=matched_by,
            )
            object_signature = str(debug_object["objectId"])
            for matched_tag in matched_by:
                if object_signature in seen_by_tag[matched_tag]:
                    continue
                if len(feature_objects[matched_tag]) >= 25:
                    continue
                seen_by_tag[matched_tag].add(object_signature)
                feature_objects[matched_tag].append(debug_object)

        edge_geometry = selected_edge.get("geometry")
        if edge_geometry is not None:
            edge_points = [[float(lng), float(lat)] for lng, lat in edge_geometry.coords]
        else:
            edge_points = [
                [float(graph.nodes[u]["x"]), float(graph.nodes[u]["y"])],
                [float(graph.nodes[v]["x"]), float(graph.nodes[v]["y"])],
            ]

        if not coordinates:
            coordinates.extend(edge_points)
        else:
            if coordinates[-1] == edge_points[0]:
                coordinates.extend(edge_points[1:])
            else:
                coordinates.extend(edge_points)

    return coordinates, total_length, aggregate, feature_objects


def _nearest_node_simple(graph: nx.MultiDiGraph, lat: float, lng: float) -> int:
    closest_node: int | None = None
    closest_distance = float("inf")

    for node_id, node_data in graph.nodes(data=True):
        node_lat = float(node_data.get("y", 0.0))
        node_lng = float(node_data.get("x", 0.0))
        distance_sq = (node_lat - lat) ** 2 + (node_lng - lng) ** 2
        if distance_sq < closest_distance:
            closest_distance = distance_sq
            closest_node = int(node_id)

    if closest_node is None:
        raise ValueError("Unable to locate nearest graph node")

    return closest_node


def _route_accuracy_score(route: dict, target_distance: float, target_duration_seconds: int) -> float:
    distance_error = abs(route["distanceMeters"] - target_distance) / max(target_distance, 1.0)
    duration_error = abs(route["durationSeconds"] - target_duration_seconds) / max(target_duration_seconds, 1)
    point_count = len(route["geometry"].coordinates)
    shape_detail = min(point_count / 40.0, 1.0)

    distance_component = 1.0 - min(distance_error, 1.0)
    duration_component = 1.0 - min(duration_error, 1.0)

    return 0.48 * distance_component + 0.47 * duration_component + 0.05 * shape_detail


def _dedupe_routes(routes: list[dict]) -> list[dict]:
    seen: set[tuple[int, int, tuple[float, float], tuple[float, float]]] = set()
    unique: list[dict] = []
    for route in routes:
        coords = route["geometry"].coordinates
        signature = (
            int(round(route["distanceMeters"] / 25.0)),
            int(round(route["durationSeconds"] / 15.0)),
            (round(coords[0][0], 5), round(coords[0][1], 5)),
            (round(coords[-1][0], 5), round(coords[-1][1], 5)),
        )
        if signature in seen:
            continue
        seen.add(signature)
        unique.append(route)
    return unique


def _annotate_graph_edges(
    graph: nx.MultiDiGraph,
    constraints: Constraints,
    scenic_k: float,
    feature_weights: dict[str, float] | None = None,
) -> None:
    fw = feature_weights or {}
    for _, _, _, edge_data in graph.edges(keys=True, data=True):
        features = _extract_edge_features(edge_data)
        scenic_score = (
            fw.get("nature", 1.0) * features.nature
            + fw.get("water", 1.0) * features.water
            + fw.get("historic", 1.0) * features.historic
            + fw.get("viewpoints", 1.0) * features.viewpoints
            + fw.get("culture", 1.0) * features.culture
            + fw.get("cafes", 1.0) * features.cafes
            - fw.get("busyRoad", 1.0) * features.busyRoad
        )
        length = float(edge_data.get("length", 1.0))
        weight = length / (1.0 + scenic_k * max(scenic_score, 0.0))

        if constraints.avoidBusyRoads and features.busyRoad:
            weight = float("inf")

        edge_data["weight"] = weight
        edge_data["scenic_score"] = scenic_score
        edge_data["scenic_features"] = {
            "nature": features.nature,
            "water": features.water,
            "historic": features.historic,
            "busyRoad": features.busyRoad,
            "viewpoints": features.viewpoints,
            "culture": features.culture,
            "cafes": features.cafes,
        }


def build_graph_routes(
    origin: Location,
    duration_minutes: int,
    constraints: Constraints,
    scenic_k: float = 1.0,
    feature_weights: dict[str, float] | None = None,
) -> list[dict]:
    target_distance = max(1_200.0, min(9_000.0, duration_minutes * 75.0))
    target_duration_seconds = duration_minutes * 60

    search_radius = int(max(1200, min(10000, target_distance * 1.35)))
    graph = ox.graph_from_point(
        center_point=(origin.lat, origin.lng),
        dist=search_radius,
        network_type="walk",
        simplify=True,
        retain_all=False,
    )

    if graph.number_of_nodes() == 0:
        return []

    _annotate_graph_edges(
        graph=graph,
        constraints=constraints,
        scenic_k=max(0.0, scenic_k),
        feature_weights=feature_weights,
    )

    origin_node = _nearest_node_simple(graph, lat=origin.lat, lng=origin.lng)
    candidate_specs = [
        (15.0, 0.47),
        (75.0, 0.53),
        (135.0, 0.60),
        (195.0, 0.54),
        (255.0, 0.58),
        (315.0, 0.50),
    ]

    routes: list[dict] = []
    for bearing, distance_factor in candidate_specs:
        destination_lat, destination_lng = _destination_for_walk(
            origin=origin,
            distance_meters=target_distance * distance_factor,
            bearing_deg=bearing,
        )

        try:
            destination_node = _nearest_node_simple(graph, lat=destination_lat, lng=destination_lng)
            path_nodes = nx.shortest_path(graph, source=origin_node, target=destination_node, weight="weight")
        except (nx.NetworkXNoPath, nx.NodeNotFound, ValueError):
            continue

        if len(path_nodes) < 2:
            continue

        coordinates, total_length, edge_features, edge_feature_objects = _build_route_geometry(
            graph=graph,
            path_nodes=path_nodes,
        )
        if len(coordinates) < 2 or total_length <= 0:
            continue

        duration_seconds = int(total_length / WALKING_SPEED_MPS)
        routes.append(
            {
                "geometry": Geometry(type="LineString", coordinates=coordinates),
                "distanceMeters": int(total_length),
                "durationSeconds": duration_seconds,
                "edgeFeatures": edge_features,
                "edgeFeatureObjects": edge_feature_objects,
                "graphContextAvailable": True,
            }
        )

    deduped = _dedupe_routes(routes)
    ranked = sorted(
        deduped,
        key=lambda route: _route_accuracy_score(route, target_distance, target_duration_seconds),
        reverse=True,
    )[:3]

    for index, route in enumerate(ranked, start=1):
        route["id"] = f"route_{index}"

    return ranked