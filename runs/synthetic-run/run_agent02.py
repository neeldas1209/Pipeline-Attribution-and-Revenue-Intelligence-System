import json
import math
import os
from datetime import datetime
from collections import defaultdict

RUN = "/Users/neel/Documents/pipeline-attribution/runs/synthetic-run"
ANALYSIS_DATE = "2026-07-14"
analysis_dt = datetime.fromisoformat(ANALYSIS_DATE)

with open(f"{RUN}/inputs/pipeline-records.json") as f:
    deals = json.load(f)

total_deals = len(deals)

def parse_date(s):
    if s is None:
        return None
    return datetime.fromisoformat(s.split("T")[0])

def days_between(start, end):
    if start is None or end is None:
        return None
    return (parse_date(end) - parse_date(start)).days

def compute_stats(values):
    if not values:
        return {"avg": 0, "median": 0, "p90": 0, "min": 0, "max": 0, "deal_count": 0}
    vals = sorted(values)
    n = len(vals)
    avg_val = round(sum(vals) / n, 1)
    if n % 2 == 0:
        median_val = round((vals[n // 2 - 1] + vals[n // 2]) / 2, 1)
    else:
        median_val = round(vals[n // 2], 1)
    p90_idx = (n - 1) * 0.9
    lo = int(math.floor(p90_idx))
    hi = min(int(math.ceil(p90_idx)), n - 1)
    p90_val = round(vals[lo] + (vals[hi] - vals[lo]) * (p90_idx - lo), 1) if lo != hi else round(vals[lo], 1)
    return {"avg": avg_val, "median": median_val, "p90": p90_val,
            "min": round(min(vals), 1), "max": round(max(vals), 1), "deal_count": n}

def r1(v):
    return round(v, 1) if v is not None else None

TRANSITIONS = [
    {"name": "lead_to_mql", "start": "lead_created_date", "end": "mql_date"},
    {"name": "mql_to_sql", "start": "mql_date", "end": "sql_date"},
    {"name": "sql_to_opp", "start": "sql_date", "end": "opportunity_created_date"},
    {"name": "opp_to_closed", "start": "opportunity_created_date", "end": "closed_date"},
]

# Segment dimension name mapping: internal key -> schema prefix, deal field
SEG_DEFS = [
    ("by_industry", "industry"),
    ("by_company_size", "company_size"),
    ("by_lead_source", "lead_source"),
    ("by_deal_type", "deal_type"),
    ("by_geography", "geography"),
]

def get_seg(deal, field):
    return deal.get(field)

def seg_deals(field, val):
    return [d for d in deals if get_seg(d, field) == val]

def all_seg_values(field):
    return sorted(set(get_seg(d, field) for d in deals if get_seg(d, field) is not None))

# Data quality
warnings = []
no_lead = []
skipped_mql = []
skipped_sql = []

for d in deals:
    did = d["deal_id"]
    if d.get("lead_created_date") is None:
        no_lead.append(did)
        warnings.append(f"{did}: missing lead_created_date, excluded from velocity calculations")
    if d.get("mql_date") is None and d.get("sql_date") is not None:
        skipped_mql.append(did)
        warnings.append(f"{did}: skipped MQL stage")
    if d.get("sql_date") is None and d.get("opportunity_created_date") is not None:
        skipped_sql.append(did)
        warnings.append(f"{did}: skipped SQL stage")
    ts_order = ["lead_created_date", "mql_date", "sql_date", "opportunity_created_date", "closed_date"]
    prev_val, prev_name = None, None
    for ts_name in ts_order:
        curr = d.get(ts_name)
        if curr is not None:
            if prev_val is not None:
                dd = days_between(prev_val, curr)
                if dd is not None and dd < 0:
                    warnings.append(f"{did}: out-of-order timestamps ({prev_name} > {ts_name})")
            prev_val, prev_name = curr, ts_name

# Stalled deals
stalled = []
for d in deals:
    if d.get("deal_outcome") == "open":
        for ts_name, stage in [("closed_date", "Closed"), ("opportunity_created_date", "Opportunity"),
                                ("sql_date", "SQL"), ("mql_date", "MQL"), ("lead_created_date", "Lead")]:
            if d.get(ts_name) is not None:
                days_in = (analysis_dt - parse_date(d[ts_name])).days
                if days_in > 90:
                    stalled.append({"deal_id": d["deal_id"], "current_stage": stage, "days_stalled": days_in})
                break

stage_counts = {
    "lead": sum(1 for d in deals if d.get("lead_created_date")),
    "mql": sum(1 for d in deals if d.get("mql_date")),
    "sql": sum(1 for d in deals if d.get("sql_date")),
    "opportunity": sum(1 for d in deals if d.get("opportunity_created_date")),
    "closed": sum(1 for d in deals if d.get("closed_date")),
    "closed_won": sum(1 for d in deals if d.get("deal_outcome") == "won"),
    "closed_lost": sum(1 for d in deals if d.get("deal_outcome") == "lost"),
    "open": sum(1 for d in deals if d.get("deal_outcome") == "open"),
}

def get_velocities(subset, start_f, end_f):
    return [days_between(d.get(start_f), d.get(end_f)) for d in subset
            if d.get(start_f) is not None and d.get(end_f) is not None]

def get_conversion(subset, start_f, end_f):
    denom = sum(1 for d in subset if d.get(start_f) is not None)
    numer = sum(1 for d in subset if d.get(start_f) is not None and d.get(end_f) is not None)
    return {"rate": r1(numer / denom * 100) if denom > 0 else 0.0, "numerator": numer, "denominator": denom}

def get_dropoff(subset, start_f, end_f):
    at_start = [d for d in subset if d.get(start_f) is not None]
    dropped = [d for d in at_start if d.get(end_f) is None and d.get("deal_outcome") == "lost"]
    still_open = [d for d in at_start if d.get(end_f) is None and d.get("deal_outcome") == "open"]
    reason_counts = defaultdict(int)
    for d in dropped:
        reason_counts[d.get("lost_reason") or "unspecified"] += 1
    total_dropped = len(dropped)
    reasons = [{"reason": r, "count": c, "pct": r1(c / total_dropped * 100) if total_dropped > 0 else 0.0}
               for r, c in sorted(reason_counts.items(), key=lambda x: -x[1])]
    return {"deals_dropped": total_dropped,
            "drop_rate": r1(total_dropped / len(at_start) * 100) if at_start else 0.0,
            "still_open_count": len(still_open), "lost_reason_breakdown": reasons}

# ==================== BUILD stage_velocity ====================
stage_vel_out = {}
for t in TRANSITIONS:
    entry = {"overall": compute_stats(get_velocities(deals, t["start"], t["end"]))}
    for seg_key, field in SEG_DEFS:
        seg_data = {}
        for val in all_seg_values(field):
            sd = seg_deals(field, val)
            stats = compute_stats(get_velocities(sd, t["start"], t["end"]))
            if len(sd) < 5:
                stats["low_confidence"] = True
            seg_data[val] = stats
        entry[seg_key] = seg_data
    stage_vel_out[t["name"]] = entry

fc_vals = [days_between(d["lead_created_date"], d["closed_date"])
           for d in deals if d.get("lead_created_date") and d.get("closed_date")]
stage_vel_out["full_cycle"] = {"overall": compute_stats(fc_vals)}

# ==================== BUILD conversion_rates ====================
conv_out = {}
for t in TRANSITIONS:
    entry = {"overall": get_conversion(deals, t["start"], t["end"])}
    for seg_key, field in SEG_DEFS:
        seg_data = {}
        for val in all_seg_values(field):
            sd = seg_deals(field, val)
            seg_data[val] = get_conversion(sd, t["start"], t["end"])
        entry[seg_key] = seg_data
    conv_out[t["name"]] = entry

won_count = stage_counts["closed_won"]
total_leads = stage_counts["lead"]
conv_out["cumulative"] = {"lead_to_won": r1(won_count / total_leads * 100) if total_leads > 0 else 0.0}

# ==================== BUILD drop_off_analysis ====================
drop_out = {}
for t in TRANSITIONS:
    drop_out[t["name"]] = get_dropoff(deals, t["start"], t["end"])

# ==================== BOTTLENECK DETECTION ====================
all_medians = [stage_vel_out[t["name"]]["overall"]["median"] for t in TRANSITIONS
               if stage_vel_out[t["name"]]["overall"]["median"] is not None]
all_convs = [conv_out[t["name"]]["overall"]["rate"] for t in TRANSITIONS]
median_of_medians = sum(all_medians) / len(all_medians) if all_medians else 0
avg_conv = sum(all_convs) / len(all_convs) if all_convs else 0
vel_thresh = r1(median_of_medians * 1.5)
conv_thresh = r1(avg_conv * 0.5)

bottlenecks = []
for t in TRANSITIONS:
    v = stage_vel_out[t["name"]]["overall"]
    c = conv_out[t["name"]]["overall"]
    if v["median"] is not None and v["median"] > vel_thresh:
        affected = []
        for seg_key, field in SEG_DEFS:
            for val in all_seg_values(field):
                sm = stage_vel_out[t["name"]].get(seg_key, {}).get(val, {}).get("median")
                if sm is not None and v["median"] > 0:
                    affected.append({"dimension": seg_key.replace("by_", ""), "segment": val,
                                     "value": sm, "vs_overall": r1(sm / v["median"])})
        affected.sort(key=lambda x: -(x["value"] or 0))
        bottlenecks.append({"transition": t["name"], "type": "velocity", "value": v["median"],
                            "threshold": vel_thresh, "ratio": r1(v["median"] / median_of_medians) if median_of_medians > 0 else 0,
                            "segments_most_affected": affected[:10]})
    if c["rate"] < conv_thresh:
        affected = []
        for seg_key, field in SEG_DEFS:
            for val in all_seg_values(field):
                sc = conv_out[t["name"]].get(seg_key, {}).get(val, {}).get("rate", 0)
                affected.append({"dimension": seg_key.replace("by_", ""), "segment": val,
                                 "value": sc, "vs_overall": r1(sc / c["rate"]) if c["rate"] > 0 else 0})
        affected.sort(key=lambda x: x["value"] if x["value"] is not None else 999)
        bottlenecks.append({"transition": t["name"], "type": "conversion", "value": c["rate"],
                            "threshold": conv_thresh, "ratio": r1(c["rate"] / avg_conv) if avg_conv > 0 else 0,
                            "segments_most_affected": affected[:10]})

# ==================== SEGMENT COMPARISONS ====================
seg_comps = {}
for seg_key, field in SEG_DEFS:
    dim_name = seg_key.replace("by_", "")
    seg_comps[dim_name] = {}
    for val in all_seg_values(field):
        sd = seg_deals(field, val)
        low_conf = len(sd) < 5
        vel = {}
        for t in TRANSITIONS:
            vel[t["name"]] = compute_stats(get_velocities(sd, t["start"], t["end"]))
        conv = {}
        for t in TRANSITIONS:
            conv[t["name"]] = get_conversion(sd, t["start"], t["end"])
        drop = {}
        for t in TRANSITIONS:
            drop[t["name"]] = get_dropoff(sd, t["start"], t["end"])
        sl = sum(1 for d in sd if d.get("lead_created_date"))
        sw = sum(1 for d in sd if d.get("deal_outcome") == "won")
        seg_comps[dim_name][val] = {
            "deal_count": len(sd), "low_confidence": low_conf,
            "velocity": vel, "conversion": conv,
            "cumulative_conversion": r1(sw / sl * 100) if sl > 0 else 0.0,
            "drop_off": drop
        }
# Add sales_rep dimension
seg_comps["sales_rep"] = {}
reps = sorted(set(d.get("sales_rep") for d in deals if d.get("sales_rep")))
for rep in reps:
    sd = [d for d in deals if d.get("sales_rep") == rep]
    low_conf = len(sd) < 5
    vel = {}
    for t in TRANSITIONS:
        vel[t["name"]] = compute_stats(get_velocities(sd, t["start"], t["end"]))
    conv = {}
    for t in TRANSITIONS:
        conv[t["name"]] = get_conversion(sd, t["start"], t["end"])
    drop = {}
    for t in TRANSITIONS:
        drop[t["name"]] = get_dropoff(sd, t["start"], t["end"])
    sl = sum(1 for d in sd if d.get("lead_created_date"))
    sw = sum(1 for d in sd if d.get("deal_outcome") == "won")
    seg_comps["sales_rep"][rep] = {
        "deal_count": len(sd), "low_confidence": low_conf,
        "velocity": vel, "conversion": conv,
        "cumulative_conversion": r1(sw / sl * 100) if sl > 0 else 0.0,
        "drop_off": drop
    }

# ==================== SALES REP ANALYSIS ====================
team_won = [d for d in deals if d.get("deal_outcome") == "won"]
team_decided = len(team_won) + len([d for d in deals if d.get("deal_outcome") == "lost"])
team_wr = r1(len(team_won) / team_decided * 100) if team_decided > 0 else 0.0
team_cycles = [days_between(d["lead_created_date"], d["closed_date"])
               for d in team_won if d.get("lead_created_date") and d.get("closed_date")]
team_avg_cycle = r1(sum(team_cycles) / len(team_cycles)) if team_cycles else None

rep_analysis = []
for rep in reps:
    rd = [d for d in deals if d.get("sales_rep") == rep]
    rw = [d for d in rd if d.get("deal_outcome") == "won"]
    rl = [d for d in rd if d.get("deal_outcome") == "lost"]
    ro = [d for d in rd if d.get("deal_outcome") == "open"]
    decided = len(rw) + len(rl)
    wr = r1(len(rw) / decided * 100) if decided > 0 else 0.0
    cycles = [days_between(d["lead_created_date"], d["closed_date"])
              for d in rw if d.get("lead_created_date") and d.get("closed_date")]
    avg_c = r1(sum(cycles) / len(cycles)) if cycles else None
    vel = {}
    for t in TRANSITIONS:
        vel[t["name"]] = compute_stats(get_velocities(rd, t["start"], t["end"]))
    conv = {}
    for t in TRANSITIONS:
        conv[t["name"]] = get_conversion(rd, t["start"], t["end"])

    bf_obj = None
    if team_wr > 0 and wr < team_wr * 0.5:
        bf_obj = {"type": "low_win_rate", "value": wr, "team_avg": team_wr, "ratio": r1(wr / team_wr)}
    elif team_avg_cycle is not None and avg_c is not None and avg_c > team_avg_cycle * 1.5:
        bf_obj = {"type": "slow_cycle", "value": avg_c, "team_avg": team_avg_cycle, "ratio": r1(avg_c / team_avg_cycle)}
    elif decided > 0 and len(rw) == 0:
        bf_obj = {"type": "zero_wins", "value": 0, "team_avg": team_wr, "ratio": 0}

    rep_analysis.append({"rep_name": rep, "total_deals": len(rd), "won": len(rw), "lost": len(rl),
                         "open": len(ro), "win_rate": wr, "avg_cycle_won": avg_c,
                         "velocity_by_transition": vel, "conversion_by_transition": conv,
                         "bottleneck_flag": bf_obj})

# ==================== WRITE OUTPUT ====================
output = {
    "metadata": {
        "run_id": "synthetic-run",
        "generated_date": "2026-07-14T00:00:00Z",
        "agent": "02-funnel-velocity",
        "total_deals": total_deals,
        "deals_included": total_deals - len(no_lead),
        "deals_excluded": {"count": len(no_lead), "deal_ids": no_lead},
        "deal_counts_by_outcome": {"won": stage_counts["closed_won"], "lost": stage_counts["closed_lost"], "open": stage_counts["open"]},
        "deal_counts_by_stage": {"lead": stage_counts["lead"], "mql": stage_counts["mql"], "sql": stage_counts["sql"],
                                  "opportunity": stage_counts["opportunity"], "closed": stage_counts["closed"]},
        "stage_skipping_deals": {"count": len(skipped_mql) + len(skipped_sql), "deal_ids": skipped_mql + skipped_sql},
        "stalled_deals": stalled,
        "data_quality_warnings": warnings,
        "analysis_date": ANALYSIS_DATE
    },
    "stage_velocity": stage_vel_out,
    "conversion_rates": conv_out,
    "drop_off_analysis": drop_out,
    "bottleneck_flags": bottlenecks,
    "segment_comparisons": seg_comps,
    "sales_rep_analysis": rep_analysis
}

os.makedirs(f"{RUN}/velocity", exist_ok=True)
with open(f"{RUN}/velocity/funnel-velocity.json", "w") as f:
    json.dump(output, f, indent=2)

fsize = os.path.getsize(f"{RUN}/velocity/funnel-velocity.json")
print(f"Written to funnel-velocity.json ({fsize:,} bytes)")
print(f"Deals: {total_deals}, Won={stage_counts['closed_won']}, Lost={stage_counts['closed_lost']}, Open={stage_counts['open']}")
print(f"Stalled: {len(stalled)}, Bottlenecks: {len(bottlenecks)}, Reps flagged: {sum(1 for r in rep_analysis if r['bottleneck_flag'])}")
for b in bottlenecks:
    print(f"  {b['transition']} ({b['type']}): value={b['value']}, threshold={b['threshold']}")
