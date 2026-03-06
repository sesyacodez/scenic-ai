# AI Waypoint Selection Workflow

## Scope

LangGraph is used only in the optional must-see POI ranking step.
Route generation, scenic scoring, route ranking, and explanation construction are deterministic backend services.

## When It Runs

AI waypoint selection is attempted only when all conditions are true:

- `AI_POI_SELECTOR_ENABLED=true`
- destination is provided
- user did not provide waypoints
- `GOOGLE_PLACES_API_KEY` is configured

Otherwise, planning continues without AI-selected waypoints.

## Pipeline

1. Candidate retrieval
   - Query Google Places Text Search around route midpoint
   - Merge and dedupe candidates by place id

2. Deterministic filtering
   - Enforce geographic validity and detour constraints
   - Drop candidates that violate duration/leg-distance constraints

3. Deterministic ranking baseline
   - Compute heuristic relevance from rating, rating count, must-see type bonus, and preference-type matches

4. Optional LangGraph ranking
   - If OpenRouter/OpenAI key is present and `AI_POI_LANGGRAPH_ENABLED=true`, run a single-node LangGraph that asks the LLM to return ordered place ids in strict JSON
   - If this step fails, use heuristic ordering

5. Waypoint handoff
   - Select up to `max_new_waypoints` POIs
   - Return waypoint coordinates and selected POI metadata to planner

## Output Contract (Selection Step)

Selection returns:

- `selectedWaypoints`: waypoint list used for route generation
- `selectedPois`: named POIs with confidence/relevance metadata
- `aiUsed`: whether AI selection was applied
- `aiFallbackReason`: reason when AI path was skipped/unavailable
- `aiSelectionMode`: `langgraph`, `heuristic`, or skip/unavailable mode code
- `aiSelectionLatencyMs`: selection latency in milliseconds

## Determinism Policy

- Deterministic only:
  - route generation
  - scenic scoring and score breakdown
  - route ranking and winner selection
  - refinement transforms
- Optional LLM use:
  - POI ordering only
- LLM or provider failure must never block route planning
