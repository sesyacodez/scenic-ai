# Scenic Scoring Specification

## Formula

$$
ScenicScore = 100 \times (w_n N + w_w W + w_h H + w_q Q)
$$

Where:

- $N$ = nature score in `[0,1]`
- $W$ = water score in `[0,1]`
- $H$ = historic score in `[0,1]`
- $Q$ = quietness score in `[0,1]`
- weights sum to `1.0`

## Component Definitions

- Nature: normalized proximity/density to parks and green areas along path
- Water: normalized proximity to water bodies along path
- Historic: normalized landmark density or heritage POIs nearby
- Quietness: inverse proxy of high-traffic / major road exposure

## Weight Rules

- Each weight in `[0.05, 0.70]`
- Sum must equal `1.0 ± 0.001`
- Agent may adjust weights from defaults based on user intent

## Ranking Rules

1. Highest `ScenicScore`
2. If tie within `0.5`, prefer lower major-road exposure
3. If still tie, prefer closer duration to target

## Explainability Output

Every selected route must return:

- overall score
- per-component breakdown
- top 2 reason strings grounded in computed data
