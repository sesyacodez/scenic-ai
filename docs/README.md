# ScenicAI Implementation Docs

This folder is the implementation source of truth for ScenicAI.

## Precedence

When docs conflict, use this order:

1. Architecture and contracts in this folder
2. Engineering rules in this folder
3. `docs/PRD.md` (product intent)
4. `docs/design-brief.md` (design intent)

## Decisions Locked for MVP

- Architecture: Next.js frontend + FastAPI backend + deterministic route/scoring services + optional LangGraph POI ranking
- Routing provider: Mapbox Directions API (`mapbox/walking`)
- Conversation persistence: browser `localStorage` (versioned schema)
- Auth: anonymous demo (no login)

## Implementation Map

- System architecture: `docs/architecture/system-architecture.md`
- API contracts: `docs/api/contracts.md`
- Agent workflow: `docs/ai/agent-workflow.md`
- Structured output schema: `docs/ai/structured-output-schema.md`
- Scoring engine: `docs/scoring/scenic-scoring-spec.md`
- Engineering rules: `docs/rules/engineering-rules.md`
- Milestones: `docs/implementation/milestones.md`

## Requirement Coverage Checklist

- [ ] Browser geolocation with manual fallback
- [ ] Generate 3 route alternatives
- [ ] Scenic score per route using weighted criteria
- [ ] Optional AI selects must-see waypoint when destination is present
- [ ] Route generation + scoring + ranking remain deterministic without LLM
- [ ] Conversational refinements persist for session continuity
- [ ] Response target under 5 seconds for typical requests
- [ ] Mobile-responsive layout with map-first focus
