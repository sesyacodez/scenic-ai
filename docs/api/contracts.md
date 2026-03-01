# API Contracts (MVP)

Base URL: `/api/v1`

## POST `/route/generate`

Generate 3 scenic route alternatives and select the best one.

### Request

```json
{
  "origin": { "lat": 51.5074, "lng": -0.1278 },
  "durationMinutes": 45,
  "preferences": {
    "nature": 0.7,
    "water": 0.4,
    "historic": 0.6,
    "quiet": 0.8
  },
  "constraints": {
    "avoidBusyRoads": true
  },
  "sessionId": "anon-session-uuid",
  "refinementText": "more nature and slightly shorter"
}
```

### Response

```json
{
  "status": "ok",
  "requestId": "req_123",
  "selectedRouteId": "route_b",
  "routes": [
    {
      "id": "route_a",
      "geometry": { "type": "LineString", "coordinates": [[-0.1, 51.5], [-0.11, 51.51]] },
      "distanceMeters": 5100,
      "durationSeconds": 2600,
      "scenicScore": 78.4,
      "scoreBreakdown": {
        "nature": 0.81,
        "water": 0.34,
        "historic": 0.55,
        "quiet": 0.73
      }
    }
  ],
  "explanation": {
    "summary": "Selected route balances parks and low-traffic streets.",
    "reasons": [
      "Highest weighted scenic score for requested preferences",
      "Avoids major roads in final 60% of route"
    ]
  },
  "appliedWeights": {
    "nature": 0.35,
    "water": 0.15,
    "historic": 0.20,
    "quiet": 0.30
  }
}
```

## POST `/route/refine`

Apply conversational refinement to last known constraints.

### Request

```json
{
  "sessionId": "anon-session-uuid",
  "message": "make it shorter and add more water"
}
```

### Response

Same schema as `/route/generate`.

## GET `/health`

### Response

```json
{
  "status": "ok",
  "service": "scenicai-backend"
}
```

## Error Envelope

```json
{
  "status": "error",
  "requestId": "req_123",
  "error": {
    "code": "INVALID_INPUT",
    "message": "durationMinutes must be between 10 and 180",
    "retryable": false
  }
}
```

## Contract Rules

- `routes` length must be exactly 3 for MVP success path
- `geometry` must be valid GeoJSON `LineString`
- `scenicScore` range is `[0, 100]`
- `appliedWeights` must sum to `1.0 ± 0.001`
