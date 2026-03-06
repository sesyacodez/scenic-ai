# System Architecture

## Objective

Deliver an AI-assisted scenic walking planner demo that is deterministic where required (routing, scoring, ranking, contracts) and optional-AI where useful (must-see waypoint suggestion).

## Topology

- Frontend: Next.js App Router (`scenic-ai/`)
- Backend API: FastAPI (`backend/`)
- Deterministic routing engines in backend:
  - OSM graph routing (`osmnx` + `networkx`) for no-destination walks
  - Mapbox Directions API (`mapbox/walking`) for destination/waypoint routes
- Optional AI module in backend:
  - Google Places candidate retrieval
  - LangGraph + LLM ranking of POI candidates (fallback to deterministic heuristic)

## Request Flow

1. User submits duration + preferences (and optional natural-language refinement)
2. Frontend calls FastAPI endpoint
3. Backend obtains origin from client payload (browser geolocation) or manual input
4. Backend runs planning pipeline (`_plan_routes`):
   - Optional must-see waypoint selection when destination is present and no user waypoints were provided
   - Deterministic route candidate generation
   - Deterministic scenic scoring and ranking
   - Explanation assembly with deterministic reason strings
5. Backend returns structured JSON with:
   - alternatives (3)
   - selected route
   - score breakdown
   - explanation text
   - applied weights
   - AI selection metadata (`aiUsed`, `aiFallbackReason`, selected POIs)
6. Frontend renders route and explanation

## Service Boundaries

- Frontend owns UI state, map rendering, and local session memory
- Backend owns route generation, scoring logic, and optional POI AI selection
- External APIs are wrapped by backend adapters; frontend never calls Mapbox or Google Places directly

## State Model

- Session refinement memory is persisted in browser `localStorage`
- Stored memory includes:
  - `schemaVersion`
  - latest constraints
  - last selected route metadata
  - recent user refinement messages

## Error Strategy

- Input validation failure: `422`
- Upstream geocoding/search issue: `502`
- No viable route: `200` with `status=no_route` and user-safe explanation
- Backend exception: `500`

## Fallback Strategy

- If destination routing returns fewer than 3 routes, backend falls back to Mapbox probe mode
- If probe mode still returns fewer than 3 routes, backend falls back to deterministic mock routes
- If AI waypoint selection is unavailable (no key/provider failure/disabled), planning continues without AI waypoint insertion

## Performance Target

- P50 end-to-end route generation: ≤ 3.0s
- P95 end-to-end route generation: ≤ 5.0s

## Security and Privacy Scope

- Anonymous access for MVP
- No long-term storage of precise location history on server
- Client memory can be cleared by user action
