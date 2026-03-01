from __future__ import annotations

from app.models import Geometry, Location


def _offset_point(lat: float, lng: float, delta_lat: float, delta_lng: float) -> list[float]:
    return [lng + delta_lng, lat + delta_lat]


def build_mock_routes(origin: Location) -> list[dict]:
    lat = origin.lat
    lng = origin.lng

    route_a = {
        "id": "route_a",
        "geometry": Geometry(
            type="LineString",
            coordinates=[
                [lng, lat],
                _offset_point(lat, lng, 0.0040, 0.0030),
                _offset_point(lat, lng, 0.0070, 0.0005),
            ],
        ),
        "distanceMeters": 4200,
        "durationSeconds": 2900,
    }

    route_b = {
        "id": "route_b",
        "geometry": Geometry(
            type="LineString",
            coordinates=[
                [lng, lat],
                _offset_point(lat, lng, 0.0030, -0.0040),
                _offset_point(lat, lng, 0.0075, -0.0020),
            ],
        ),
        "distanceMeters": 4700,
        "durationSeconds": 3200,
    }

    route_c = {
        "id": "route_c",
        "geometry": Geometry(
            type="LineString",
            coordinates=[
                [lng, lat],
                _offset_point(lat, lng, -0.0035, 0.0035),
                _offset_point(lat, lng, -0.0070, 0.0010),
            ],
        ),
        "distanceMeters": 3800,
        "durationSeconds": 2600,
    }

    return [route_a, route_b, route_c]
