# ScenicAI Implementation Docs

This folder is the implementation source of truth for ScenicAI.

## Precedence

When docs conflict, use this order:

1. `docs/PRD.md`
2. `docs/design-brief.md`
3. Architecture and contracts in this folder
4. Engineering rules in this folder

## Decisions Locked for MVP

- Architecture: Next.js frontend + FastAPI backend + LangGraph agent orchestration
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
- [ ] Agent orchestrates parse → constraints → route tool → score tool → rank → explanation
- [ ] Conversational refinements persist for session continuity
- [ ] Response target under 5 seconds for typical requests
- [ ] Mobile-responsive layout with map-first focus
