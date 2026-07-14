# Skill: Quality Check

## Purpose

Validate every agent's JSON output against its corresponding schema before the pipeline proceeds. This skill is invoked by the orchestrator after each agent completes.

## Schema Location

All schemas are in the `schemas/` directory at the project root:

| Agent | Schema File |
|-------|-------------|
| 01 Attribution Modeling | `schemas/attribution-analysis.schema.json` |
| 02 Funnel Velocity | `schemas/funnel-velocity.schema.json` |
| 03 Channel Performance | `schemas/channel-performance.schema.json` |
| 04 Scenario Planning | `schemas/scenario-analysis.schema.json` |
| 05 Narrative Report | `schemas/executive-narrative.schema.json` |
| 06 Interactive Dashboard | `schemas/dashboard-input.schema.json` (optional) |

## Validation Process

1. Read the agent's output JSON file from its designated output directory
2. Read the corresponding schema from `schemas/`
3. Validate the output against the schema
4. Check for structural completeness: all required top-level sections present, no empty required fields
5. Report result: PASS or FAIL with specific error details

## On Failure

1. Return the specific validation errors to the orchestrator with field paths and descriptions
2. The orchestrator re-runs the agent with the error details appended to the prompt
3. **Maximum 2 retries per agent**
4. After 2 failed retries: save the output with a `_warning` flag in the metadata and continue the pipeline
5. One agent's validation failure does NOT halt the entire pipeline

## Warning Flag Format

When saving after exhausted retries, add to the output metadata:

```json
{
  "quality_check": {
    "status": "warning",
    "errors": ["list of unresolved validation errors"],
    "retries_attempted": 2
  }
}
```

## What This Skill Does NOT Do

- Does not validate data accuracy (whether numbers are correct)
- Does not validate business logic (whether attribution credits sum correctly — that is each agent's internal check)
- Does not make corrections to the output — it reports errors for the agent to fix on retry
