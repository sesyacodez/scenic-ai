# API Contracts (MVP)

Base URL: `/api/v1`

## POST `/route/generate`

Generate 3 scenic route alternatives and select the best one.

### Request

```json
{
  "origin": { "lat": 51.5074, "lng": -0.1278, "label": "London" },
  "destination": { "lat": 51.5154, "lng": -0.0922, "label": "St Paul's Cathedral" },
  "waypoints": [],
  "durationMinutes": 45,
  "preferences": {
    "nature": 0.7,
    "water": 0.4,
    "historic": 0.6,
    "quiet": 0.8,
    "viewpoints": 0.5,
    "culture": 0.5,
    "cafes": 0.3
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
  "selectedRouteId": "route_2",
  "routes": [
    {
      "id": "route_1",
      "geometry": { "type": "LineString", "coordinates": [[-0.1, 51.5], [-0.11, 51.51]] },
      "distanceMeters": 5100,
      "durationSeconds": 2600,
      "scenicScore": 78.4,
      "scoreBreakdown": {
        "nature": 0.81,
        "water": 0.34,
        "historic": 0.55,
        "quiet": 0.73,
        "viewpoints": 0.52,
        "culture": 0.49,
        "cafes": 0.31
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
    "quiet": 0.10,
    "viewpoints": 0.10,
    "culture": 0.06,
    "cafes": 0.04
  },
  "aiUsed": true,
  "aiFallbackReason": null,
  "selectedPois": [
    {
      "id": "ChIJ...",
      "name": "Tower Bridge",
      "location": { "lat": 51.5055, "lng": -0.0754, "label": "Tower Bridge" },
      "source": "google_places",
      "confidence": 0.92,
      "relevanceScore": 0.86
    }
  ],
  "aiSelectionMode": "langgraph",
  "aiSelectionLatencyMs": 423
}
```

## POST `/route/refine`

Apply conversational refinement to last known constraints.

### Request

```json
{
  "sessionId": "anon-session-uuid",
  "message": "make it shorter and add more water",
  "origin": { "lat": 51.5074, "lng": -0.1278 },
  "destination": { "lat": 51.5154, "lng": -0.0922 },
  "waypoints": [],
  "durationMinutes": 45,
  "preferences": {
    "nature": 0.7,
    "water": 0.4,
    "historic": 0.6,
    "quiet": 0.8,
    "viewpoints": 0.5,
    "culture": 0.5,
    "cafes": 0.3
  },
  "constraints": { "avoidBusyRoads": true }
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

Note: this envelope is defined in backend models but not yet emitted by all handlers.

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

- `routes` length target is 3 on success; backend may return fewer only when route providers fail before fallback completion
- `geometry` must be valid GeoJSON `LineString`
- `scenicScore` range is `[0, 100]`
- `appliedWeights` must sum to `1.0 ± 0.001`
- `preferences` and `scoreBreakdown` include 7 dimensions: `nature`, `water`, `historic`, `quiet`, `viewpoints`, `culture`, `cafes`
