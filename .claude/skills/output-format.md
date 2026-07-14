# Skill: Output Format

## Purpose

Enforce consistent JSON output formatting across all agents in the pipeline. Every agent references this skill to ensure uniform data representation.

## Formatting Rules

### Monetary Values

- Currency: USD
- Precision: 2 decimal places
- Format: raw number, no currency symbols or commas
- Example: `85000.00` not `$85,000` or `85000`

### Percentages

- Precision: 1 decimal place
- Format: raw number representing the percentage value, not decimal
- Example: `27.5` not `0.275` or `27.5%`

### Dates

- Format: ISO 8601 (`YYYY-MM-DD`)
- Example: `"2025-07-15"` not `"July 15, 2025"` or `"07/15/2025"`

### Velocity / Duration

- Unit: days
- Precision: 1 decimal place
- Example: `12.3` not `"12.3 days"`

### Counts

- Format: integers, no decimal places
- Example: `42` not `42.0`

### Ratios and Multipliers (e.g., ROI)

- Precision: 2 decimal places
- Format: raw number representing the multiplier
- Example: `5.30` for 5.3x ROI, `-0.30` for negative ROI

### Ranks

- Format: integer, 1-indexed
- Rank 1 = highest/best
- No ties — use tiebreaker rules defined in each agent's rulebook

## JSON Structure Rules

### File Format

- Pretty-printed JSON with 2-space indentation
- UTF-8 encoding
- Single root object (not an array)

### Naming Conventions

- All keys in `snake_case`
- No abbreviations unless universally understood (e.g., `roi`, `mql`, `sql`, `pct`)
- Consistent key names across agents: `pipeline_credited`, `deal_size`, `deal_outcome`, `touchpoint_count`

### Null Handling

- Use `null` for missing or not-applicable values
- Do not use empty strings, `0`, or `-1` as null substitutes
- Example: a channel with zero spend has `"roi": null` (division by zero), not `"roi": 0`

### Metadata Block

Every agent output includes a top-level `metadata` object with at minimum:

- `run_id`: string — identifies the pipeline run
- `generated_date`: string — ISO 8601 timestamp of when the output was created
- `agent`: string — agent identifier (e.g., `"01-attribution-modeling"`)

### Data Type Tags

Agents 1–4 tag sections with `"_data_type": "computed"` for deterministic calculations. Agent 5 tags sections with `"_data_type": "interpretive"` for synthesized narrative. The `_data_type` field appears at the section level, not on individual fields.
