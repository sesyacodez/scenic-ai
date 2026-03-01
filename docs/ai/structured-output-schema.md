# Structured Output Schema Rules

## Goal

Prevent hallucinated or malformed agent output by enforcing strict JSON schema validation at each LLM boundary.

## LLM Output Objects

### `IntentDelta`

```json
{
  "durationAdjustmentMinutes": -10,
  "weightAdjustments": {
    "nature": 0.1,
    "water": 0.2,
    "historic": -0.1,
    "quiet": 0.0
  },
  "avoidBusyRoads": true,
  "notes": "User requested shorter route with more water"
}
```

### `ExplanationOutput`

```json
{
  "summary": "Selected route favors riverside paths and quieter streets.",
  "reasons": [
    "Top scenic score after applying user preferences",
    "Best quietness score among candidate routes"
  ]
}
```

## Validation Rules

- Reject unknown fields (`additionalProperties: false`)
- Reject missing required fields
- Reject numeric values outside expected ranges
- On validation failure:
  1. retry once with schema reminder
  2. fallback to deterministic default transform

## Safety Rules

- Never invent landmarks not present in route analysis
- Explanations must only reference computed scoring data
- Output language should be short, factual, and user-trust-oriented
