# LangGraph Agent Workflow

## Graph Nodes

1. `intent_parse`
   - Input: user text + current constraints
   - Output: structured intent deltas (e.g., shorter, more water)

2. `constraint_structure`
   - Input: parsed intent + defaults
   - Output: canonical constraints object

3. `graph_construction`
   - Input: origin + target duration + constraints
   - Output: weighted street graph + edge feature map

4. `route_optimization`
   - Input: weighted graph + planner weighting parameters
   - Output: 3 candidate graph paths (Mapbox probe fallback if graph build fails)

5. `scenic_score_tool`
   - Input: graph paths + edge-level scenic features + preference weights
   - Output: scored route list with component scores

6. `route_rank`
   - Input: scored routes
   - Output: selected route id + ordered list

7. `explanation_gen`
   - Input: selected route + score breakdown + constraints
   - Output: short transparent explanation

## State Contract

```json
{
  "origin": { "lat": 0, "lng": 0 },
  "durationMinutes": 45,
  "preferences": { "nature": 0.25, "water": 0.25, "historic": 0.25, "quiet": 0.25 },
  "constraints": { "avoidBusyRoads": false },
  "candidateRoutes": [],
  "scoredRoutes": [],
  "selectedRouteId": null,
  "explanation": null
}
```

## Transition Rules

- Every node must write typed outputs to state
- Any node validation failure routes to `error_exit`
- Planner manages graph-weighting parameters (`k`, avoid-busy hard exclusion)
- If graph construction/pathfinding fails, workflow falls back to Mapbox probe mode
- If fallback returns <3 routes, workflow uses deterministic mock fallback

## Determinism Policy

- Routing and scoring nodes are deterministic
- LLM is allowed only in:
  - intent parsing
  - explanation text generation
- LLM outputs must be schema-validated before state write
