from __future__ import annotations

from app.models import Geometry, Location


def _offset_point(lat: float, lng: float, delta_lat: float, delta_lng: float) -> list[float]:
    return [lng + delta_lng, lat + delta_lat]


def build_mock_routes(origin: Location, duration_minutes: int = 45) -> list[dict]:
    lat = origin.lat
    lng = origin.lng

    # Scale geometry offsets and metrics proportionally to the target duration.
    scale = max(0.2, duration_minutes / 45.0)
    base_distance = 4200
    base_duration = 2700  # 45 min

    route_a = {
        "id": "route_a",
        "geometry": Geometry(
            type="LineString",
            coordinates=[
                [lng, lat],
                _offset_point(lat, lng, 0.0040 * scale, 0.0030 * scale),
                _offset_point(lat, lng, 0.0070 * scale, 0.0005 * scale),
            ],
        ),
        "distanceMeters": int(base_distance * scale),
        "durationSeconds": int(base_duration * scale * 1.07),
    }

    route_b = {
        "id": "route_b",
        "geometry": Geometry(
            type="LineString",
            coordinates=[
                [lng, lat],
                _offset_point(lat, lng, 0.0030 * scale, -0.0040 * scale),
                _offset_point(lat, lng, 0.0075 * scale, -0.0020 * scale),
            ],
        ),
        "distanceMeters": int(base_distance * scale * 1.12),
        "durationSeconds": int(base_duration * scale * 1.19),
    }

    route_c = {
        "id": "route_c",
        "geometry": Geometry(
            type="LineString",
            coordinates=[
                [lng, lat],
                _offset_point(lat, lng, -0.0035 * scale, 0.0035 * scale),
                _offset_point(lat, lng, -0.0070 * scale, 0.0010 * scale),
            ],
        ),
        "distanceMeters": int(base_distance * scale * 0.90),
        "durationSeconds": int(base_duration * scale * 0.96),
    }

    return [route_a, route_b, route_c]
