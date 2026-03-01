from __future__ import annotations

from app.models import AppliedWeights, Preferences, ScoreBreakdown


def build_weights(preferences: Preferences) -> AppliedWeights:
    raw = {
        "nature": max(0.05, preferences.nature),
        "water": max(0.05, preferences.water),
        "historic": max(0.05, preferences.historic),
        "quiet": max(0.05, preferences.quiet),
    }
    total = sum(raw.values())
    normalized = {key: value / total for key, value in raw.items()}
    return AppliedWeights(**normalized)


def _mock_breakdown_for_route(route_id: str) -> ScoreBreakdown:
    table = {
        "route_a": ScoreBreakdown(nature=0.78, water=0.42, historic=0.63, quiet=0.74),
        "route_b": ScoreBreakdown(nature=0.64, water=0.83, historic=0.51, quiet=0.61),
        "route_c": ScoreBreakdown(nature=0.87, water=0.38, historic=0.44, quiet=0.79),
    }
    return table[route_id]


def scenic_score(breakdown: ScoreBreakdown, weights: AppliedWeights) -> float:
    score_0_1 = (
        breakdown.nature * weights.nature
        + breakdown.water * weights.water
        + breakdown.historic * weights.historic
        + breakdown.quiet * weights.quiet
    )
    return round(score_0_1 * 100, 2)


def score_routes(routes: list[dict], preferences: Preferences) -> tuple[list[dict], AppliedWeights]:
    weights = build_weights(preferences)
    scored_routes: list[dict] = []

    for route in routes:
        breakdown = _mock_breakdown_for_route(route["id"])
        score = scenic_score(breakdown, weights)
        scored_routes.append(
            {
                **route,
                "scenicScore": score,
                "scoreBreakdown": breakdown,
            }
        )

    ranked = sorted(scored_routes, key=lambda item: item["scenicScore"], reverse=True)
    return ranked, weights
