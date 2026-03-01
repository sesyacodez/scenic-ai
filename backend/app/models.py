from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Location(BaseModel):
    lat: float
    lng: float


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


class RouteGenerateRequest(BaseModel):
    origin: Location
    durationMinutes: int = Field(ge=10, le=180)
    preferences: Preferences
    constraints: Constraints = Field(default_factory=Constraints)
    sessionId: str = Field(min_length=3)
    refinementText: str | None = None


class RouteRefineRequest(BaseModel):
    sessionId: str = Field(min_length=3)
    message: str = Field(min_length=2, max_length=500)
    origin: Location | None = None
    durationMinutes: int | None = Field(default=None, ge=10, le=180)
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


class RouteGenerateResponse(BaseModel):
    status: Literal["ok", "no_route"]
    requestId: str
    selectedRouteId: str | None
    routes: list[RouteResult]
    explanation: Explanation
    appliedWeights: AppliedWeights


class ErrorBody(BaseModel):
    code: str
    message: str
    retryable: bool


class ErrorResponse(BaseModel):
    status: Literal["error"]
    requestId: str
    error: ErrorBody
