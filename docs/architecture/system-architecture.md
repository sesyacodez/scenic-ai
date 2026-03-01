# System Architecture

## Objective

Deliver an AI-powered scenic walking planner demo that is deterministic where required (routing/scoring/contracts) and agentic where useful (intent parsing and explanation).

## Topology

- Frontend: Next.js App Router (`scenic-ai/`)
- Backend API: FastAPI (`backend/`)
- Agent orchestration: LangGraph in backend process
- Routing provider: Mapbox Directions API

## Request Flow

1. User submits duration + preferences (and optional natural-language refinement)
2. Frontend calls FastAPI endpoint
3. Backend obtains origin from client payload (browser geolocation) or manual input
4. LangGraph workflow executes:
   - Intent parsing node
   - Constraint structuring node
   - Route generation tool node
   - Scenic scoring tool node
   - Route ranking node
   - Explanation generation node
5. Backend returns structured JSON with:
   - alternatives (3)
   - selected route
   - score breakdown
   - explanation text
6. Frontend renders route and explanation

## Service Boundaries

- Frontend owns UI state, map rendering, and local session memory
- Backend owns route generation, scoring logic, and agent workflow
- External APIs are wrapped by backend adapters; frontend never calls Mapbox directly for routing

## State Model

- Session refinement memory is persisted in browser `localStorage`
- Stored memory includes:
  - `schemaVersion`
  - latest constraints
  - last selected route metadata
  - recent user refinement messages

## Error Strategy

- Input validation failure: `422`
- Upstream provider transient issue: `503` with retryable error code
- No viable route: `200` with `status=no_route` and user-safe explanation
- Backend exception: `500` with trace ID

## Performance Target

- P50 end-to-end route generation: ≤ 3.0s
- P95 end-to-end route generation: ≤ 5.0s

## Security and Privacy Scope

- Anonymous access for MVP
- No long-term storage of precise location history on server
- Client memory can be cleared by user action
