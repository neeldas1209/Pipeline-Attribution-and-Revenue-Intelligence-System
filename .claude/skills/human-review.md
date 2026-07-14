# Skill: Human Review

## Purpose

Present agent outputs for human review at designated review gates. The reviewer validates the analytical foundation before downstream agents build on it.

## Review Gate Placement

Project 4 has a single mandatory review gate:

**After Agent 3 (Channel Performance), before Agent 4 (Scenario Planning)**

At this gate, the reviewer sees outputs from Agents 1, 2, and 3 — the complete analytical foundation. If attribution weights are wrong, velocity calculations are off, or channel rankings are misleading, every downstream output (scenarios, narrative, dashboard) would propagate those errors.

## What the Reviewer Checks

- **Attribution results (Agent 1):** Do channel rankings make intuitive sense across models? Are credit allocations reasonable?
- **Funnel velocity (Agent 2):** Are there velocity anomalies that need investigation? Do bottleneck flags align with expectations?
- **Channel performance (Agent 3):** Do channel rankings and ROI calculations align with domain knowledge? Are diagnostic flags reasonable?

## What the Reviewer Does NOT Do

- **No model selection.** All 5 attribution models continue through Agents 4–6. The CMO selects the model in the dashboard, not the operator at the review gate.
- **No data correction.** The reviewer validates the analytical approach, not individual data points.

## Presenting the Review

When the orchestrator reaches the review gate, present a summary of each agent's key outputs:

1. **Agent 1 summary:** Channel rankings under W-shaped (default) and any notable rank shifts across models. Total pipeline attributed. Deals processed vs skipped.
2. **Agent 2 summary:** Bottleneck flags with specific metrics. Top 2–3 segment findings. Any sales rep flags.
3. **Agent 3 summary:** Top 3 channels by ROI. Diagnostic flags triggered (underfunded, high-volume-low-quality). Any data quality warnings.

Then prompt the reviewer with three options.

## Three Response Options

### Option 1: Approve

Proceed to Agent 4. No changes needed. The analytical foundation is validated.

```
[APPROVED] — Proceeding to scenario planning.
```

### Option 2: Revise with Feedback

Re-run one or more agents with specific feedback. The orchestrator re-spawns the flagged agent(s) with the reviewer's notes appended to the prompt.

```
[REVISE] Agent X — [reviewer's specific feedback]
```

The re-run counts toward the agent's retry limit (max 2 retries total including quality-check retries).

### Option 3: Partial Approval

Approve some outputs, flag others for revision. The orchestrator re-runs only the flagged agents, then re-presents for review.

```
[PARTIAL]
- Agent 1: Approved
- Agent 2: Approved
- Agent 3: Revise — [specific feedback]
```

## After Review

Once all three agent outputs are approved (or approved with warnings after retry exhaustion), the orchestrator proceeds to Agent 4 (Scenario Planning). The review gate is not revisited — downstream agents build on the validated foundation.
