import json
import os
from collections import defaultdict

RUN = "/Users/neel/Documents/pipeline-attribution/runs/synthetic-run"
MODELS = ["first_touch", "last_touch", "linear", "time_decay", "w_shaped"]

with open(f"{RUN}/performance/channel-performance.json") as f:
    perf = json.load(f)
with open(f"{RUN}/inputs/channel-spend.json") as f:
    spend_records = json.load(f)
with open(f"{RUN}/inputs/pipeline-records.json") as f:
    deals = json.load(f)

def r2(v):
    return round(v, 2) if v is not None else None
def r1(v):
    return round(v, 1) if v is not None else None

# Baseline metrics
total_budget = perf["metadata"]["total_spend"]
current_pipeline = perf["metadata"]["total_pipeline_attributed"]
won_deals = sum(1 for d in deals if d.get("deal_outcome") == "won")
closed_deals = sum(1 for d in deals if d.get("deal_outcome") in ("won", "lost"))
historical_win_rate = round(won_deals / closed_deals, 4) if closed_deals > 0 else 0
current_revenue = r2(current_pipeline * historical_win_rate)
current_roi = r2(current_pipeline / total_budget) if total_budget > 0 else 0

print(f"Baseline: budget=${total_budget:,.2f}, pipeline=${current_pipeline:,.2f}, win_rate={historical_win_rate}, revenue=${current_revenue:,.2f}, roi={current_roi}")

# Channel data
channels = sorted(perf["channel_leaderboard"].keys())
ch_lb = perf["channel_leaderboard"]

# Current allocation
current_alloc = {ch: ch_lb[ch]["budget_pct"] for ch in channels}
ch_spend = {ch: ch_lb[ch]["total_spend"] for ch in channels}

# Pipeline per dollar from Agent 03
ppd = {}
for ch in channels:
    ppd[ch] = {}
    for m in MODELS:
        pi = ch_lb[ch]["by_model"][m]["pipeline_influenced"]
        sp = ch_lb[ch]["total_spend"]
        ppd[ch][m] = r2(pi / sp) if sp > 0 else 0

# Step 1: Read diagnostic flags
flags = perf["diagnostic_flags"]
underfunded = [f for f in flags if f["flag_type"] == "underfunded"]
low_quality = [f for f in flags if f["flag_type"] == "high_volume_low_quality"]

uf_channels = defaultdict(int)
for f in underfunded:
    uf_channels[f["channel"]] += 1
lq_channels = defaultdict(int)
for f in low_quality:
    lq_channels[f["channel"]] += 1

print(f"Underfunded channels: {dict(uf_channels)}")
print(f"Low-quality channels: {dict(lq_channels)}")

# Step 2: Identify source (reduce) and destination (increase)
# Source: low quality flagged under most models, worst ROI
source_candidates = sorted(lq_channels.keys(), key=lambda c: (-lq_channels[c], ch_lb[c]["by_model"]["w_shaped"]["roi"] or 999))
# Destination: underfunded flagged under most models, best ROI
dest_candidates = sorted(uf_channels.keys(), key=lambda c: (-uf_channels[c], -(ch_lb[c]["by_model"]["w_shaped"]["roi"] or -999)))

source = source_candidates[0] if source_candidates else max(channels, key=lambda c: ch_lb[c]["budget_pct"])
dest_channels = dest_candidates if dest_candidates else [max(channels, key=lambda c: (ch_lb[c]["by_model"]["w_shaped"]["roi"] or -999))]

print(f"Source channel (reduce): {source}")
print(f"Destination channels (increase): {dest_channels}")

# ROI spread
rois_w = {ch: ch_lb[ch]["by_model"]["w_shaped"]["roi"] for ch in channels}
roi_values = [v for v in rois_w.values() if v is not None]
roi_spread = max(roi_values) / min(v for v in roi_values if v > 0) if roi_values and min(v for v in roi_values if v > 0) > 0 else 1

def project_scenario(alloc_pcts, label=""):
    projections = {}
    for m in MODELS:
        projected_pipeline = 0
        for ch in channels:
            new_spend = total_budget * alloc_pcts[ch] / 100
            projected_pipeline += new_spend * ppd[ch][m]
        projected_pipeline = r2(projected_pipeline)
        projected_revenue = r2(projected_pipeline * historical_win_rate)
        projected_roi = r2(projected_pipeline / total_budget) if total_budget > 0 else 0
        pipeline_delta = r2(projected_pipeline - current_pipeline)
        pipeline_delta_pct = r1(pipeline_delta / current_pipeline * 100) if current_pipeline > 0 else 0
        roi_delta = r2(projected_roi - current_roi)

        # Confidence
        shift_pct = sum(abs(alloc_pcts[ch] - current_alloc[ch]) for ch in channels) / 2
        if shift_pct <= 20:
            confidence = "High"
        elif shift_pct <= 40:
            confidence = "Medium"
        else:
            confidence = "Low"

        projections[m] = {
            "projected_pipeline": projected_pipeline,
            "pipeline_delta": pipeline_delta,
            "pipeline_delta_pct": pipeline_delta_pct,
            "projected_revenue": projected_revenue,
            "projected_roi": projected_roi,
            "roi_delta": roi_delta,
            "confidence": confidence
        }
    return projections

scenarios = []

# Scenario 1: Scale underfunded channel
if dest_channels:
    dest = dest_channels[0]
    shift_pct = 15  # 15% of total budget
    new_alloc = dict(current_alloc)
    source_reduction = min(shift_pct, new_alloc[source] - 5)
    new_alloc[source] = r1(new_alloc[source] - source_reduction)
    new_alloc[dest] = r1(new_alloc[dest] + source_reduction)

    changes = []
    unchanged = []
    for ch in channels:
        if abs(new_alloc[ch] - current_alloc[ch]) > 0.05:
            changes.append({"channel": ch, "from_pct": current_alloc[ch], "to_pct": new_alloc[ch],
                            "delta_dollars": r2(total_budget * (new_alloc[ch] - current_alloc[ch]) / 100)})
        else:
            unchanged.append(ch)

    scenarios.append({
        "scenario_id": "S1",
        "name": f"Scale {dest}",
        "description": f"Shift {source_reduction}% of budget from {source} to {dest}, leveraging {dest}'s higher ROI",
        "reallocation": {"changes": changes, "unchanged": unchanged},
        "projections": project_scenario(new_alloc),
        "assumptions": [
            "Linear scaling: pipeline_per_dollar remains constant as spend increases",
            f"{dest} can absorb additional spend without diminishing returns",
            "Market conditions remain stable"
        ],
        "generated_because": f"{dest} flagged as underfunded ({uf_channels.get(dest, 0)} models), {source} flagged as high-volume-low-quality ({lq_channels.get(source, 0)} models)"
    })

# Scenario 2: Redistribute from low-quality
if source_candidates:
    source_ch = source_candidates[0]
    reduce_pct = current_alloc[source_ch] * 0.4  # 40% of source's current allocation
    new_alloc = dict(current_alloc)
    new_alloc[source_ch] = r1(new_alloc[source_ch] - reduce_pct)

    # Redistribute to top 2 by ROI (excluding source)
    top_roi = sorted([ch for ch in channels if ch != source_ch],
                     key=lambda c: -(ch_lb[c]["by_model"]["w_shaped"]["roi"] or -999))[:2]
    per_dest = reduce_pct / len(top_roi)
    for ch in top_roi:
        new_alloc[ch] = r1(new_alloc[ch] + per_dest)

    changes = []
    unchanged = []
    for ch in channels:
        if abs(new_alloc[ch] - current_alloc[ch]) > 0.05:
            changes.append({"channel": ch, "from_pct": current_alloc[ch], "to_pct": new_alloc[ch],
                            "delta_dollars": r2(total_budget * (new_alloc[ch] - current_alloc[ch]) / 100)})
        else:
            unchanged.append(ch)

    scenarios.append({
        "scenario_id": "S2",
        "name": f"Redistribute from {source_ch}",
        "description": f"Reduce {source_ch} by {r1(reduce_pct)}pp, redistribute to {' and '.join(top_roi)}",
        "reallocation": {"changes": changes, "unchanged": unchanged},
        "projections": project_scenario(new_alloc),
        "assumptions": [
            "Linear scaling: pipeline_per_dollar remains constant",
            f"{source_ch} reduction doesn't impact downstream pipeline disproportionately",
            f"{', '.join(top_roi)} can absorb incremental spend efficiently"
        ],
        "generated_because": f"{source_ch} flagged as high-volume-low-quality under {lq_channels[source_ch]} models; {', '.join(top_roi)} are top ROI channels"
    })

# Scenario 3: Aggressive reallocation (if ROI spread > 3x)
if roi_spread > 3 and source_candidates and dest_candidates:
    worst_roi_ch = min(channels, key=lambda c: ch_lb[c]["by_model"]["w_shaped"]["roi"] or 999)
    new_alloc = dict(current_alloc)
    target_pct = 7.5  # Reduce to ~7.5% of budget
    freed = new_alloc[worst_roi_ch] - target_pct
    if freed > 0:
        new_alloc[worst_roi_ch] = target_pct
        top2 = sorted([ch for ch in channels if ch != worst_roi_ch],
                       key=lambda c: -(ch_lb[c]["by_model"]["w_shaped"]["roi"] or -999))[:2]
        per_d = freed / len(top2)
        for ch in top2:
            new_alloc[ch] = r1(new_alloc[ch] + per_d)

        changes = []
        unchanged = []
        for ch in channels:
            if abs(new_alloc[ch] - current_alloc[ch]) > 0.05:
                changes.append({"channel": ch, "from_pct": current_alloc[ch], "to_pct": r1(new_alloc[ch]),
                                "delta_dollars": r2(total_budget * (new_alloc[ch] - current_alloc[ch]) / 100)})
            else:
                unchanged.append(ch)

        scenarios.append({
            "scenario_id": "S3",
            "name": f"Aggressive Reallocation from {worst_roi_ch}",
            "description": f"Reduce {worst_roi_ch} to {target_pct}% of budget, redistribute to top-ROI channels",
            "reallocation": {"changes": changes, "unchanged": unchanged},
            "projections": project_scenario(new_alloc),
            "assumptions": [
                "Linear scaling: pipeline_per_dollar remains constant at higher spend levels",
                f"{worst_roi_ch} at {target_pct}% still maintains minimum viable presence",
                "Large reallocation can be executed without disruption",
                "No channel saturation effects at increased spend levels"
            ],
            "generated_because": f"ROI spread of {r1(roi_spread)}x between best and worst channels; both underfunded and low-quality flags present"
        })

# Status Quo (always included)
# Monthly spend trend for projection
monthly_spend = defaultdict(lambda: defaultdict(float))
for r in spend_records:
    monthly_spend[r["channel"]][r["month"]] += r["spend"]

sq_alloc = dict(current_alloc)
sq_projections = project_scenario(sq_alloc)

scenarios.append({
    "scenario_id": "SQ",
    "name": "Status Quo: Current allocation projected forward",
    "description": "No reallocation. Current budget distribution maintained with existing spend trends.",
    "reallocation": {"changes": [], "unchanged": channels},
    "projections": sq_projections,
    "assumptions": [
        "Current budget allocation continues unchanged",
        "Pipeline_per_dollar rates remain stable",
        "Market conditions and competitive dynamics unchanged"
    ],
    "generated_because": "Mandatory baseline scenario for comparison"
})

# Custom scenario parameters
custom_params = {
    "total_budget": total_budget,
    "win_rate": historical_win_rate,
    "current_pipeline": current_pipeline,
    "current_revenue": current_revenue,
    "current_roi": current_roi,
    "current_allocation": current_alloc,
    "pipeline_per_dollar": ppd
}

# Generation reasoning
reasoning = {
    "flags_found": {
        "underfunded": [f"{f['channel']} ({f['model']})" for f in underfunded],
        "high_volume_low_quality": [f"{f['channel']} ({f['model']})" for f in low_quality]
    },
    "source_channel_selection": f"{source} selected as primary source: flagged high-volume-low-quality under {lq_channels.get(source, 0)} models",
    "destination_channel_selection": f"{', '.join(dest_channels)} selected as destinations: flagged underfunded with highest ROI",
    "reallocation_sizing": "Moderate shifts (15% for scaling, 40% reduction for redistribution) to balance impact vs risk",
    "scenarios_generated": len(scenarios),
    "note": f"ROI spread: {r1(roi_spread)}x. {'Aggressive scenario included.' if roi_spread > 3 else 'ROI spread < 3x, no aggressive scenario.'}"
}

# Validation
for s in scenarios:
    for m in MODELS:
        p = s["projections"][m]
        check_pipe = r2(sum(total_budget * s["reallocation"]["changes"][i]["to_pct"] / 100 * ppd[s["reallocation"]["changes"][i]["channel"]][m]
                           for i in range(len(s["reallocation"]["changes"])))
                       + sum(total_budget * current_alloc[ch] / 100 * ppd[ch][m] for ch in s["reallocation"]["unchanged"]))
    if s["scenario_id"] != "SQ":
        alloc_sum = 0
        for c in s["reallocation"]["changes"]:
            alloc_sum += c["to_pct"]
        for ch in s["reallocation"]["unchanged"]:
            alloc_sum += current_alloc[ch]
        if abs(alloc_sum - 100) > 0.5:
            print(f"  ALLOC ERROR {s['scenario_id']}: sum={alloc_sum}")
        else:
            print(f"  {s['scenario_id']} alloc sum: {r1(alloc_sum)}%")

print(f"Scenarios generated: {len(scenarios)}")
for s in scenarios:
    w = s["projections"]["w_shaped"]
    print(f"  {s['scenario_id']} ({s['name']}): pipeline_delta={w['pipeline_delta_pct']}%, confidence={w['confidence']}")

output = {
    "metadata": {
        "run_id": "synthetic-run",
        "generated_date": "2026-07-14T00:00:00Z",
        "agent": "04-scenario-planning",
        "total_budget": total_budget,
        "current_pipeline": current_pipeline,
        "current_revenue": current_revenue,
        "current_roi": current_roi,
        "historical_win_rate": historical_win_rate,
        "scenarios_generated": len(scenarios),
        "models_computed": MODELS
    },
    "scenarios": scenarios,
    "custom_scenario_parameters": custom_params,
    "generation_reasoning": reasoning
}

os.makedirs(f"{RUN}/scenarios", exist_ok=True)
with open(f"{RUN}/scenarios/scenario-analysis.json", "w") as f:
    json.dump(output, f, indent=2)

fsize = os.path.getsize(f"{RUN}/scenarios/scenario-analysis.json")
print(f"\nWritten to scenario-analysis.json ({fsize:,} bytes)")
