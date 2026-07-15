# Pipeline Attribution & Revenue Intelligence System

An agentic system built in Claude Code that ingests multi-touch B2B pipeline data and channel spend data, applies five attribution models simultaneously, identifies funnel bottlenecks, ranks channels by true ROI, models budget reallocation scenarios, and produces an interactive HTML dashboard for CMO presentation.

## The Problem

Most B2B marketing teams have attribution data sitting in their CRM, but it rarely drives decisions. Reports are backward-looking. Multi-touch attribution is theoretically understood but practically ignored because building the model, interrogating it, and translating it into budget decisions takes too long. The CMO asks "which channels drove revenue and where should we shift budget next quarter?" and the team scrambles to produce a static spreadsheet that arrives two weeks late.

## What This System Does

**[View the live dashboard](https://neeldas1209.github.io/Pipeline-Attribution-and-Revenue-Intelligence-System/runs/synthetic-run/dashboard/dashboard.html)**

This system takes two standard CRM exports — pipeline deals with touchpoints and channel spend data — and runs them through a six-agent pipeline that:

1. **Attributes pipeline credit** across five models (first-touch, last-touch, linear, time-decay, W-shaped) for every closed deal
2. **Identifies funnel bottlenecks** — where deals stall, which segments underperform, which reps are struggling
3. **Ranks channels by true ROI** — not just volume, but cost-per-closed-won, pipeline per dollar, and efficiency under every attribution lens
4. **Models budget scenarios** — data-driven reallocation recommendations with projected pipeline impact under each model
5. **Writes a CMO-ready narrative** — a 5-minute executive summary with quantified findings and recommendations
6. **Generates an interactive dashboard** — standalone HTML file with five views, model selector, drill-downs, and live budget sliders

## Architecture

Six agents execute in a linear pipeline, coordinated by an orchestrator:

```
CSV Inputs → [Preprocessing] → Agent 01: Attribution Modeling
                                Agent 02: Funnel Velocity
                                Agent 03: Channel Performance
                                    ↓
                              [Human Review Gate]
                                    ↓
                                Agent 04: Scenario Planning
                                Agent 05: Narrative Report
                                Agent 06: Interactive Dashboard → dashboard.html
```

All agents are pure reasoning — no web search, no external APIs. The system operates entirely on structured data.

### Agent Pipeline

| Agent | Purpose | Output |
|-------|---------|--------|
| 01 — Attribution Modeling | Apply 5 attribution models to ~140 closed deals | attribution-analysis.json |
| 02 — Funnel Velocity | Identify bottlenecks by stage, segment, and rep | funnel-velocity.json |
| 03 — Channel Performance | Rank channels by efficiency using attribution + spend | channel-performance.json |
| 04 — Scenario Planning | Model budget reallocation with projected impact | scenario-analysis.json |
| 05 — Narrative Report | Synthesize into CMO-ready executive summary | executive-narrative.json |
| 06 — Interactive Dashboard | Generate standalone HTML with 5 interactive views | dashboard.html |

### Design Principles

- **All 5 models flow through all agents.** No model is locked at any step. The CMO selects the model in the dashboard
- **Scenarios are data-driven, not precoded.** Agent 04 reasons about which scenarios to generate based on Agent 03's diagnostic flags
- **Computed vs interpretive separation.** Agents 01–04 are computation only. Agent 05 is the interpretation layer. Agent 06 is a rendering engine
- **Single human review gate** after Agent 03 validates the analytical foundation before scenarios are built on it

## Five Attribution Models

| Model | Logic | What It Reveals |
|-------|-------|-----------------|
| First-Touch | 100% credit to first touchpoint | Which channels generate awareness |
| Last-Touch | 100% credit to last touch before opportunity creation | Which channels drive deals |
| Linear | Equal credit across all touchpoints | Balanced full-journey view |
| Time-Decay | Exponential decay toward close (7-day half-life) | Which recent touches mattered |
| W-Shaped | 30/30/30/10 across first touch, lead creation, opp creation | Critical conversion moments |

## Dashboard Views

The final output is a standalone HTML file that opens in any browser — no server, no build tools, no dependencies.

1. **Attribution** — bar chart of pipeline credit by channel with progressive drill-down: channel → campaign → deal audit trail
2. **Funnel Velocity** — funnel diagram with click-to-expand segment breakdowns, drop-off analysis, and sales rep table
3. **Channel Performance** — sortable leaderboard with 11 metrics, column picker, diagnostic flag badges, and campaign drill-down
4. **Scenario Planning** — data-driven scenario cards plus custom budget sliders with live projection recalculation
5. **Narrative** — the executive summary as a clean reading view with copy-to-clipboard

## Inputs

Three CSV files (standard CRM exports):

| File | Rows | Content |
|------|------|---------|
| pipeline-deals.csv | 50 | One row per deal — company, stage, outcome, timestamps |
| pipeline-touchpoints.csv | ~300 | One row per marketing touchpoint, linked by deal_id |
| channel-spend.csv | 216 | Monthly spend per campaign (12 months × 18 campaigns) |

The orchestrator merges deals + touchpoints into the JSON format agents process.

## How to Run

```bash
cd ~/Documents/pipeline-attribution
claude --agent pipeline-orchestrator --dangerously-skip-permissions
```

The orchestrator will preprocess CSVs, run Agents 01–03, pause for human review, then run Agents 04–06 and generate the dashboard.

## Tech Stack

- **Claude Code** — agentic orchestration and reasoning
- **Chart.js** — data visualization (CDN, no install)
- **Vanilla HTML/CSS/JS** — standalone dashboard, no React, no build step
- **Python** — CSV preprocessing only

---

Built by [Neel Das](https://neeldas.ca) • July 2026
