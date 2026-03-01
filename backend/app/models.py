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


class ScoreBreakdown(BaseModel):
    nature: float = Field(ge=0, le=1)
    water: float = Field(ge=0, le=1)
    historic: float = Field(ge=0, le=1)
    quiet: float = Field(ge=0, le=1)


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


class Explanation(BaseModel):
    summary: str
    reasons: list[str]


class AppliedWeights(BaseModel):
    nature: float = Field(ge=0.05, le=0.7)
    water: float = Field(ge=0.05, le=0.7)
    historic: float = Field(ge=0.05, le=0.7)
    quiet: float = Field(ge=0.05, le=0.7)

    @model_validator(mode="after")
    def validate_sum(self) -> "AppliedWeights":
        total = self.nature + self.water + self.historic + self.quiet
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
