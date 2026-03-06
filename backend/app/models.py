from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Location(BaseModel):
    lat: float
    lng: float
    label: str | None = None


class LocationSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=120)
    limit: int = Field(default=5, ge=1, le=8)
    proximityLat: float | None = Field(default=None, ge=-90, le=90)
    proximityLng: float | None = Field(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def validate_proximity_pair(self) -> "LocationSearchRequest":
        has_lat = self.proximityLat is not None
        has_lng = self.proximityLng is not None
        if has_lat != has_lng:
            raise ValueError("proximityLat and proximityLng must be provided together")
        return self


class ReverseGeocodeRequest(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class LocationSearchResult(BaseModel):
    id: str
    label: str
    fullLabel: str
    location: Location


class LocationSearchResponse(BaseModel):
    results: list[LocationSearchResult]


class Preferences(BaseModel):
    nature: float = Field(ge=0, le=1)
    water: float = Field(ge=0, le=1)
    historic: float = Field(ge=0, le=1)
    quiet: float = Field(ge=0, le=1)
    viewpoints: float = Field(ge=0, le=1)
    culture: float = Field(ge=0, le=1)
    cafes: float = Field(ge=0, le=1)


class Constraints(BaseModel):
    avoidBusyRoads: bool = False
    includeMustSees: bool = False


class RouteGenerateRequest(BaseModel):
    origin: Location
    destination: Location | None = None
    waypoints: list[Location] = Field(default_factory=list, max_length=3)
    durationMinutes: int | None = Field(default=None, ge=10, le=480)
    preferences: Preferences
    constraints: Constraints = Field(default_factory=Constraints)
    sessionId: str = Field(min_length=3)
    refinementText: str | None = None


class RouteRefineRequest(BaseModel):
    sessionId: str = Field(min_length=3)
    message: str = Field(min_length=2, max_length=500)
    origin: Location | None = None
    destination: Location | None = None
    waypoints: list[Location] | None = Field(default=None, max_length=3)
    durationMinutes: int | None = Field(default=None, ge=10, le=480)
    activeRouteId: str | None = None
    preferences: Preferences | None = None
    constraints: Constraints = Field(default_factory=Constraints)


class ScoreBreakdown(BaseModel):
    nature: float = Field(ge=0, le=1)
    water: float = Field(ge=0, le=1)
    historic: float = Field(ge=0, le=1)
    quiet: float = Field(ge=0, le=1)
    viewpoints: float = Field(ge=0, le=1)
    culture: float = Field(ge=0, le=1)
    cafes: float = Field(ge=0, le=1)


class TagObjectMatch(BaseModel):
    objectId: str
    objectType: str
    name: str | None = None
    lat: float | None = None
    lng: float | None = None
    matchedBy: list[str] = Field(default_factory=list)
    tags: dict[str, str] = Field(default_factory=dict)


class ScoreDebug(BaseModel):
    contextAvailable: bool
    poiContextFetchFailed: bool = False
    natureFeatureCount: int = Field(ge=0)
    waterFeatureCount: int = Field(ge=0)
    historicFeatureCount: int = Field(ge=0)
    busyRoadFeatureCount: int = Field(ge=0)
    viewpointFeatureCount: int = Field(ge=0)
    cultureFeatureCount: int = Field(ge=0)
    cafeFeatureCount: int = Field(ge=0)
    quietFromSpeed: float = Field(ge=0, le=1)
    quietFromRoads: float = Field(ge=0, le=1)
    tagObjectMatches: dict[str, list[TagObjectMatch]] = Field(default_factory=dict)


class Geometry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["LineString"]
    coordinates: list[list[float]]


class RouteResult(BaseModel):
    id: str
    geometry: Geometry
    distanceMeters: int
    durationSeconds: int
    scenicScore: float = Field(ge=0, le=100)
    scoreBreakdown: ScoreBreakdown
    scoreDebug: ScoreDebug | None = None


class Explanation(BaseModel):
    summary: str
    reasons: list[str]


class RouteExplanation(BaseModel):
    routeId: str
    theme: str | None = None
    summary: str
    reasons: list[str]
    locations: list[str] = Field(default_factory=list)


class AppliedWeights(BaseModel):
    nature: float = Field(ge=0.0, le=1.0)
    water: float = Field(ge=0.0, le=1.0)
    historic: float = Field(ge=0.0, le=1.0)
    quiet: float = Field(ge=0.0, le=1.0)
    viewpoints: float = Field(ge=0.0, le=1.0)
    culture: float = Field(ge=0.0, le=1.0)
    cafes: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_sum(self) -> "AppliedWeights":
        total = (
            self.nature
            + self.water
            + self.historic
            + self.quiet
            + self.viewpoints
            + self.culture
            + self.cafes
        )
        if abs(total - 1.0) > 0.001:
            raise ValueError("weights must sum to 1")
        return self


class SelectedPoi(BaseModel):
    id: str
    name: str
    location: Location
    source: str
    confidence: float = Field(ge=0.0, le=1.0)
    relevanceScore: float = Field(ge=0.0, le=1.0)


class RouteGenerateResponse(BaseModel):
    status: Literal["ok", "no_route"]
    requestId: str
    selectedRouteId: str | None
    routes: list[RouteResult]
    explanation: Explanation
    routeExplanations: list[RouteExplanation] = Field(default_factory=list)
    appliedWeights: AppliedWeights
    aiUsed: bool = False
    aiFallbackReason: str | None = None
    selectedPois: list[SelectedPoi] = Field(default_factory=list)
    aiSelectionMode: str | None = None
    aiSelectionLatencyMs: int | None = None


class ErrorBody(BaseModel):
    code: str
    message: str
    retryable: bool


class ErrorResponse(BaseModel):
    status: Literal["error"]
    requestId: str
    error: ErrorBody
