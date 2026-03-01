# LangGraph Agent Workflow

## Graph Nodes

1. `intent_parse`
   - Input: user text + current constraints
   - Output: structured intent deltas (e.g., shorter, more water)

2. `constraint_structure`
   - Input: parsed intent + defaults
   - Output: canonical constraints object

3. `route_tool`
   - Input: origin + target duration + constraints
   - Output: 3 candidate routes from Mapbox

4. `scenic_score_tool`
   - Input: candidate routes + preference weights
   - Output: scored route list with component scores

5. `route_rank`
   - Input: scored routes
   - Output: selected route id + ordered list

6. `explanation_gen`
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
- If route tool returns <3 routes, workflow retries once with relaxed constraints
- If still <3 routes, return `status=no_route` safely

## Determinism Policy

- Routing and scoring nodes are deterministic
- LLM is allowed only in:
  - intent parsing
  - explanation text generation
- LLM outputs must be schema-validated before state write
