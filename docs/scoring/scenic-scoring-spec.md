# Scenic Scoring Specification

## Formula

$$
ScenicScore = 100 \times (w_n N + w_w W + w_h H + w_q Q + w_v V + w_c C + w_f F)
$$

Where:

- $N$ = nature score in `[0,1]`
- $W$ = water score in `[0,1]`
- $H$ = historic score in `[0,1]`
- $Q$ = quietness score in `[0,1]`
- $V$ = viewpoints score in `[0,1]`
- $C$ = culture score in `[0,1]`
- $F$ = cafes score in `[0,1]`
- weights sum to `1.0`

## Component Definitions

- Nature: normalized proximity/density to parks, green areas, and natural features along path
- Water: normalized proximity to water bodies, rivers, and waterways along path
- Historic: normalized landmark density or heritage POIs nearby
- Quietness: inverse proxy of high-traffic / major road exposure (25% speed-based, 75% busy-road inverse)
- Viewpoints: normalized density of designated viewpoints along path
- Culture: normalized density of museums, galleries, theatres, and cultural landmarks along path
- Cafes: normalized density of cafes, restaurants, and pubs along path

## Weight Rules

- Each weight in `[0.0, 1.0]`
- Sum must equal `1.0 ± 0.001`
- Agent may adjust weights from defaults based on user intent

## Ranking Rules

1. Highest `ScenicScore`
2. If tie within `0.5`, prefer lower major-road exposure
3. If still tie, prefer closer duration to target

## Explainability Output

Every selected route must return:

- overall score
- per-component breakdown (all 7 dimensions)
- top 2 reason strings grounded in computed data
