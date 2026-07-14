# Pipeline Attribution & Revenue Intelligence

## Purpose

Project 4 is an agentic system that ingests multi-touch B2B pipeline data and channel spend data, applies five attribution models simultaneously, identifies funnel bottlenecks, ranks channels by true ROI, models budget reallocation scenarios, and produces both a narrative executive report and an interactive HTML dashboard for CMO presentation.

This is the bottom-of-funnel system in a four-project AI marketing portfolio. It closes the loop: measuring what actually worked and recommending where to invest next.

## Architecture

Six agents execute in a linear pipeline, coordinated by an orchestrator. All agents are pure reasoning — no web search required. Every agent operates on structured JSON inputs and produces structured JSON outputs, except Agent 6 which generates a standalone HTML dashboard.

### Agent Pipeline

| Step | Agent | Purpose |
|------|-------|---------|
| 1 | 01-attribution-modeling | Apply 5 attribution models to closed deals |
| 2 | 02-funnel-velocity | Identify where deals stall by stage and segment |
| 3 | 03-channel-performance | Rank channels by efficiency using attribution + spend data |
| — | HUMAN REVIEW GATE | Validate analytical foundation before scenarios |
| 4 | 04-scenario-planning | Model budget reallocation with projected impact |
| 5 | 05-narrative-report | Synthesize findings into CMO-ready executive summary |
| 6 | 06-interactive-dashboard | Generate standalone HTML dashboard with 5 views |

### Dependencies

- Agents 1 and 2 are independent — both read raw input data only
- Agent 3 depends on Agent 1 (requires attribution data for Pipeline Influenced metric)
- Agent 4 depends on Agent 3 (requires diagnostic flags and channel metrics for scenario generation)
- Agent 5 depends on Agents 1–4 (synthesizes all upstream outputs into narrative)
- Agent 6 depends on Agents 1–5 (renders all data into interactive dashboard)

## File Structure

```
pipeline-attribution/
├── CLAUDE.md
├── .claude/
│   ├── agents/
│   │   ├── 00-pipeline-orchestrator.md
│   │   ├── 01-attribution-modeling.md
│   │   ├── 02-funnel-velocity.md
│   │   ├── 03-channel-performance.md
│   │   ├── 04-scenario-planning.md
│   │   ├── 05-narrative-report.md
│   │   └── 06-interactive-dashboard.md
│   └── skills/
│       ├── quality-check.md
│       ├── output-format.md
│       └── human-review.md
├── schemas/
│   ├── attribution-analysis.schema.json
│   ├── funnel-velocity.schema.json
│   ├── channel-performance.schema.json
│   ├── scenario-analysis.schema.json
│   ├── executive-narrative.schema.json
│   └── dashboard-input.schema.json
└── runs/
    └── <run-name>/
        ├── inputs/
        │   ├── pipeline-records.json
        │   └── channel-spend.json
        ├── attribution/
        │   └── attribution-analysis.json
        ├── velocity/
        │   └── funnel-velocity.json
        ├── performance/
        │   └── channel-performance.json
        ├── scenarios/
        │   └── scenario-analysis.json
        ├── narrative/
        │   └── executive-narrative.json
        ├── dashboard/
        │   └── dashboard.html
        └── review/
```

## Input Specification

Two input files are required. Both live in `runs/<run-name>/inputs/`.

### Pipeline Records (pipeline-records.json)

200 B2B SaaS deals spanning 12 months (July 2025 – June 2026), 6 channels, 18 campaigns.

**Deal-level fields:**
- deal_id, company_name, industry, company_size, employee_count, annual_revenue
- geography, deal_size, deal_type, deal_stage, deal_outcome (won/lost/open)
- lost_reason (null if not lost), sales_rep, product_line, lead_source, buyer_persona

**Stage transition timestamps (ISO 8601):**
- lead_created_date, mql_date, sql_date, opportunity_created_date, closed_date
- Null timestamps indicate the deal did not reach that stage

**Touchpoints array (2–12 per deal):**
- touchpoint_date, channel, campaign_name, content_asset
- touchpoint_type, funnel_stage_at_touch, contact_role

### Channel Spend Data (channel-spend.json)

12 months of marketing spend at campaign level. Each record contains: channel, campaign_name, month (YYYY-MM format), spend (USD).

## Channels and Campaigns

| Channel | Campaigns |
|---------|-----------|
| Google Ads | Brand Search, Non-Brand Search, Retargeting |
| LinkedIn | Sponsored Content, InMail, Conversation Ads |
| Content Marketing | Blog/SEO, Webinars, Ebooks/Guides |
| Events | Conferences, Hosted Roundtables, Partner Events |
| Outbound BDR | Cold Outbound, Warm Follow-up, Inbound Response |
| Email Campaigns | Nurture Sequences, Product Updates, Re-engagement |

## Five Attribution Models

All five models are computed by Agent 1 and flow through all downstream agents. No model is locked at any intermediate step. Model selection happens in the dashboard by the end user (CMO).

| Model | Logic |
|-------|-------|
| First-Touch | 100% credit to the first touchpoint in the deal timeline |
| Last-Touch | 100% credit to the last touchpoint before opportunity creation |
| Linear | Credit split equally across all touchpoints |
| Time-Decay | Exponential decay toward close date. Half-life: 7 days |
| W-Shaped | 30/30/30/10: first touch, lead creation, opp creation, remainder split linearly |

## Conventions

### Data Formats

- All monetary values in USD, rounded to 2 decimal places
- All dates in ISO 8601 format
- All percentages rounded to 1 decimal place
- All velocity metrics in days, rounded to 1 decimal place

### Quality Checks

- Every agent output validated against its JSON schema in `schemas/` by the quality-check skill
- Maximum 2 retries on validation failure, then save with warning flag and continue
- One agent failure does not halt the pipeline — downstream agents handle missing data gracefully

### Human Review

- Single mandatory review gate after Agent 3 (Channel Performance)
- Three options: approve, revise with feedback, partial approval with manual edits
- Purpose: validate analytical foundation before scenarios are built on it
- No model selection at the review gate — all 5 models continue through the pipeline

### Computed vs Interpretive Separation

- Agents 1–4 are computation only: calculate, count, rank, flag. No insights, no "this suggests," no recommendations
- Agent 5 is the interpretation agent: draws conclusions, identifies patterns, makes recommendations — but every claim must be grounded in upstream agent data
- Agent 6 is a rendering engine: takes structured data and makes it visual. Performs no analysis

### Agent Output Paths

Each agent writes to its designated subdirectory within the active run:
- Agent 1 → `runs/<run>/attribution/attribution-analysis.json`
- Agent 2 → `runs/<run>/velocity/funnel-velocity.json`
- Agent 3 → `runs/<run>/performance/channel-performance.json`
- Agent 4 → `runs/<run>/scenarios/scenario-analysis.json`
- Agent 5 → `runs/<run>/narrative/executive-narrative.json`
- Agent 6 → `runs/<run>/dashboard/dashboard.html`

### Dashboard

- Standalone HTML file with Chart.js via CDN
- All data embedded as JavaScript objects — no external data files, no API calls
- Opens in any browser by double-clicking. No server, no build step, no React
