# Implementation Milestones

## M1: Foundations

- Finalize architecture/contracts/rules docs
- Scaffold FastAPI backend with health and route endpoints
- Build frontend shell with map-first layout and core controls

## M2: Deterministic Core

- Implement Mapbox route adapter with 3 alternatives
- Implement scenic scoring engine
- Return selected route + score breakdown + explanation placeholder

## M3: Agent Integration

- Add LangGraph state graph with required nodes
- Add structured-output validation for intent/explanation
- Integrate refinement loop with localStorage memory

## M4: Quality Hardening

- Add API/unit integration tests
- Validate p95 response under 5 seconds
- Polish mobile responsiveness and error states

## MVP Exit Criteria

- Geolocation + manual fallback
- 3 route alternatives generated and scored
- Best route rendered with explanation
- Conversational refinement works across refresh in same browser
