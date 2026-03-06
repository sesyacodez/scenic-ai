# Engineering Rules

## Scope

These rules govern all MVP implementation work.

## Frontend Rules

- Use App Router patterns consistently
- Keep map as primary visual region (60–70% desktop focus)
- Do not introduce heavy dashboard-style UI
- Use composition patterns over boolean-prop explosion in reusable components

## Performance Rules

- Avoid async waterfalls in API and data-fetching paths
- Keep route generation response under 5 seconds at P95
- Defer non-critical UI updates when route is being generated

## State Rules

- Persist conversational session in `localStorage` with explicit `schemaVersion`
- Store minimal state required for refinement continuity
- Include a clear reset action for session memory

## Backend Rules

- FastAPI request and response models must be typed and validated
- Keep API contracts backward-compatible within `/api/v1`
- Route/scoring logic must be deterministic and testable without LLM

## Agent Rules

- LLM calls are optional and currently limited to POI ordering in AI waypoint selection
- Deterministic route generation, scoring, and ranking must never depend on LLM availability
- LLM outputs must be strict-JSON parsed and validated before use
- If AI selection fails, deterministic planning must continue without AI-selected waypoints

## UX and Accessibility Rules

- All controls have labels and keyboard operability
- Respect reduced-motion user preference
- Provide explicit error and loading states
