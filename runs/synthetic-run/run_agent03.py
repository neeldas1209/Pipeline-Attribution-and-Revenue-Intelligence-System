import json
import os
from collections import defaultdict

RUN = "/Users/neel/Documents/pipeline-attribution/runs/synthetic-run"
MODELS = ["first_touch", "last_touch", "linear", "time_decay", "w_shaped"]

with open(f"{RUN}/inputs/pipeline-records.json") as f:
    deals = json.load(f)
with open(f"{RUN}/inputs/channel-spend.json") as f:
    spend_records = json.load(f)
with open(f"{RUN}/attribution/attribution-analysis.json") as f:
    attrib = json.load(f)

def r2(v):
    return round(v, 2) if v is not None else None
def r1(v):
    return round(v, 1) if v is not None else None

warnings = []

# Spend aggregation
spend_by_channel = defaultdict(float)
spend_by_campaign = defaultdict(float)
campaign_to_channel = {}
for r in spend_records:
    spend_by_channel[r["channel"]] += r["spend"]
    key = (r["channel"], r["campaign_name"])
    spend_by_campaign[key] += r["spend"]
    campaign_to_channel[r["campaign_name"]] = r["channel"]

total_spend = r2(sum(spend_by_channel.values()))
spend_channels = set(spend_by_channel.keys())
spend_campaigns = set(k[1] for k in spend_by_campaign.keys())

# Pipeline channels/campaigns from touchpoints
pipeline_channels = set()
pipeline_campaigns = set()
for d in deals:
    for tp in d.get("touchpoints", []):
        pipeline_channels.add(tp["channel"])
        pipeline_campaigns.add(tp["campaign_name"])

# Attribution channels/campaigns
attrib_channels = set(attrib["channel_summary"].keys())
attrib_campaigns = set()
for ch_data in attrib["campaign_detail"].values():
    for cp in ch_data:
        attrib_campaigns.add(cp)

all_channels = sorted(spend_channels | pipeline_channels | attrib_channels)
all_campaigns = sorted(spend_campaigns | pipeline_campaigns | attrib_campaigns)

# Check mismatches
channels_unmatched = []
campaigns_unmatched = []
for ch in all_channels:
    if ch not in spend_channels:
        warnings.append(f"Channel '{ch}' in pipeline but not in spend data")
        channels_unmatched.append(ch)
    if ch not in pipeline_channels:
        warnings.append(f"Channel '{ch}' in spend but not in pipeline data")
        channels_unmatched.append(ch)
for cp in all_campaigns:
    if cp not in spend_campaigns:
        warnings.append(f"Campaign '{cp}' in pipeline but not in spend data")
        campaigns_unmatched.append(cp)
    if cp not in pipeline_campaigns and cp in spend_campaigns:
        warnings.append(f"Campaign '{cp}' in spend but not in pipeline data")
        campaigns_unmatched.append(cp)

channels_matched = len(spend_channels & pipeline_channels & attrib_channels)
campaigns_matched = len(spend_campaigns & pipeline_campaigns & attrib_campaigns)

total_pipeline = attrib["metadata"]["total_pipeline_attributed"]
ch_activity = attrib["metadata"]["channel_activity"]

# Volume metrics per channel (model-independent)
def channel_volume(ch):
    sourced = [d for d in deals if any(tp["channel"] == ch for tp in d.get("touchpoints", []))]
    leads = len(sourced)
    mqls = sum(1 for d in sourced if d.get("mql_date"))
    sqls = sum(1 for d in sourced if d.get("sql_date"))
    opps = sum(1 for d in sourced if d.get("opportunity_created_date"))
    won = sum(1 for d in sourced if d.get("deal_outcome") == "won")
    # Pipeline created = sum of deal_size where channel has the first touchpoint
    pipeline_created = 0
    for d in deals:
        tps = sorted(d.get("touchpoints", []), key=lambda t: t["touchpoint_date"])
        if tps and tps[0]["channel"] == ch:
            pipeline_created += d["deal_size"]
    return leads, mqls, sqls, opps, won, r2(pipeline_created)

def campaign_volume(ch, cp):
    sourced = [d for d in deals if any(tp["channel"] == ch and tp["campaign_name"] == cp for tp in d.get("touchpoints", []))]
    leads = len(sourced)
    mqls = sum(1 for d in sourced if d.get("mql_date"))
    sqls = sum(1 for d in sourced if d.get("sql_date"))
    opps = sum(1 for d in sourced if d.get("opportunity_created_date"))
    won = sum(1 for d in sourced if d.get("deal_outcome") == "won")
    pipeline_created = 0
    for d in deals:
        tps = sorted(d.get("touchpoints", []), key=lambda t: t["touchpoint_date"])
        if tps and tps[0]["channel"] == ch and tps[0]["campaign_name"] == cp:
            pipeline_created += d["deal_size"]
    return leads, mqls, sqls, opps, won, r2(pipeline_created)

# Build channel leaderboard
channel_leaderboard = {}
for ch in sorted(spend_channels & pipeline_channels):
    leads, mqls, sqls, opps, won, pipeline_created = channel_volume(ch)
    ch_spend = r2(spend_by_channel[ch])
    budget_pct = r1(ch_spend / total_spend * 100) if total_spend > 0 else 0

    by_model = {}
    for m in MODELS:
        ch_attrib = attrib["channel_summary"].get(ch, {}).get(m, {})
        pi = ch_attrib.get("pipeline_credited", 0)
        dt = ch_attrib.get("deals_touched", 0)
        rank = ch_attrib.get("rank", 6)
        avg_ds = r2(pi / dt) if dt > 0 else None
        roi = r2((pi - ch_spend) / ch_spend) if ch_spend > 0 else None
        ppd = r2(pi / ch_spend) if ch_spend > 0 else None
        by_model[m] = {"pipeline_influenced": r2(pi), "avg_deal_size_attributed": avg_ds,
                       "roi": roi, "pipeline_per_dollar": ppd, "rank": rank}

    # Time-normalized
    act = ch_activity.get(ch, {})
    if act.get("first_touchpoint_date") and act.get("last_touchpoint_date"):
        from datetime import datetime
        d1 = datetime.fromisoformat(act["first_touchpoint_date"])
        d2 = datetime.fromisoformat(act["last_touchpoint_date"])
        active_months = max((d2 - d1).days / 30.44, 0.01)
    else:
        active_months = 1
    low_data = active_months < 1

    ppm = {}
    rpm = {}
    for m in MODELS:
        pi = by_model[m]["pipeline_influenced"]
        roi_val = by_model[m]["roi"]
        ppm[m] = r2(pi / active_months)
        rpm[m] = r2(roi_val / active_months) if roi_val is not None else None
    spm = r2(ch_spend / active_months)

    channel_leaderboard[ch] = {
        "total_spend": ch_spend,
        "budget_pct": budget_pct,
        "leads_generated": leads,
        "mqls": mqls,
        "sqls": sqls,
        "opps": opps,
        "won": won,
        "cost_per_lead": r2(ch_spend / leads) if leads > 0 else None,
        "cost_per_mql": r2(ch_spend / mqls) if mqls > 0 else None,
        "cost_per_sql": r2(ch_spend / sqls) if sqls > 0 else None,
        "cost_per_opp": r2(ch_spend / opps) if opps > 0 else None,
        "cost_per_won": r2(ch_spend / won) if won > 0 else None,
        "conversion_lead_to_won": r1(won / leads * 100) if leads > 0 else None,
        "pipeline_created": pipeline_created,
        "by_model": by_model,
        "time_normalized": {
            "active_months": round(active_months, 1),
            "pipeline_per_month": ppm,
            "roi_per_month": rpm,
            "spend_per_month": spm
        },
        "channel_activity": act
    }

# Build campaign detail
campaign_detail = {}
for ch in sorted(spend_channels & pipeline_channels):
    campaign_detail[ch] = {}
    ch_campaigns = set()
    for key in spend_by_campaign:
        if key[0] == ch:
            ch_campaigns.add(key[1])
    for d in deals:
        for tp in d.get("touchpoints", []):
            if tp["channel"] == ch:
                ch_campaigns.add(tp["campaign_name"])

    for cp in sorted(ch_campaigns):
        leads, mqls, sqls, opps, won, pipeline_created = campaign_volume(ch, cp)
        cp_spend = r2(spend_by_campaign.get((ch, cp), 0))

        by_model = {}
        for m in MODELS:
            cp_attrib = attrib["campaign_detail"].get(ch, {}).get(cp, {}).get(m, {})
            pi = cp_attrib.get("pipeline_credited", 0)
            dt = cp_attrib.get("deals_touched", 0)
            rank = cp_attrib.get("rank", 1)
            avg_ds = r2(pi / dt) if dt > 0 else None
            roi = r2((pi - cp_spend) / cp_spend) if cp_spend > 0 else None
            ppd = r2(pi / cp_spend) if cp_spend > 0 else None
            by_model[m] = {"pipeline_influenced": r2(pi), "avg_deal_size_attributed": avg_ds,
                           "roi": roi, "pipeline_per_dollar": ppd, "rank": rank}

        campaign_detail[ch][cp] = {
            "total_spend": cp_spend,
            "leads_generated": leads,
            "mqls": mqls,
            "sqls": sqls,
            "opps": opps,
            "won": won,
            "cost_per_lead": r2(cp_spend / leads) if leads > 0 else None,
            "cost_per_mql": r2(cp_spend / mqls) if mqls > 0 else None,
            "cost_per_sql": r2(cp_spend / sqls) if sqls > 0 else None,
            "cost_per_opp": r2(cp_spend / opps) if opps > 0 else None,
            "cost_per_won": r2(cp_spend / won) if won > 0 else None,
            "conversion_lead_to_won": r1(won / leads * 100) if leads > 0 else None,
            "pipeline_created": pipeline_created,
            "by_model": by_model
        }

# Diagnostic flags
diagnostic_flags = []
channels_list = sorted(channel_leaderboard.keys())

for m in MODELS:
    rois = [(ch, channel_leaderboard[ch]["by_model"][m]["roi"]) for ch in channels_list]
    rois_valid = [(ch, r) for ch, r in rois if r is not None]
    rois_valid.sort(key=lambda x: -x[1])
    roi_values = [r for _, r in rois_valid]
    median_roi = sorted(roi_values)[len(roi_values) // 2] if roi_values else 0

    budgets = [(ch, channel_leaderboard[ch]["budget_pct"]) for ch in channels_list]
    budgets.sort(key=lambda x: -x[1])
    budget_values = sorted([b for _, b in budgets])
    median_budget = budget_values[len(budget_values) // 2] if budget_values else 0

    leads_list = [(ch, channel_leaderboard[ch]["leads_generated"]) for ch in channels_list]
    leads_values = sorted([l for _, l in leads_list])
    median_leads = leads_values[len(leads_values) // 2] if leads_values else 0

    cpw_list = [(ch, channel_leaderboard[ch]["cost_per_won"]) for ch in channels_list]
    cpw_valid = sorted([c for _, c in cpw_list if c is not None])
    median_cpw = cpw_valid[len(cpw_valid) // 2] if cpw_valid else 0

    conv_list = [(ch, channel_leaderboard[ch]["conversion_lead_to_won"]) for ch in channels_list]
    conv_valid = sorted([c for _, c in conv_list if c is not None])
    median_conv = conv_valid[len(conv_valid) // 2] if conv_valid else 0

    for ch in channels_list:
        ch_data = channel_leaderboard[ch]
        ch_roi = ch_data["by_model"][m]["roi"]
        ch_budget = ch_data["budget_pct"]
        ch_pi = ch_data["by_model"][m]["pipeline_influenced"]
        ch_rank = ch_data["by_model"][m]["rank"]

        # ROI rank
        roi_rank = sorted(channels_list, key=lambda c: -(channel_leaderboard[c]["by_model"][m]["roi"] or -999)).index(ch) + 1
        budget_rank = sorted(channels_list, key=lambda c: -channel_leaderboard[c]["budget_pct"]).index(ch) + 1

        # Underfunded: ROI above median AND budget_pct in bottom 50%
        if ch_roi is not None and ch_roi > median_roi and ch_budget < median_budget:
            diagnostic_flags.append({
                "channel": ch, "model": m, "flag_type": "underfunded",
                "roi": ch_roi, "roi_rank": roi_rank, "budget_pct": ch_budget,
                "budget_rank": budget_rank, "pipeline_influenced": ch_pi
            })

        # High-volume-low-quality: leads above median AND (cpw above median OR conv below median)
        ch_leads = ch_data["leads_generated"]
        ch_cpw = ch_data["cost_per_won"]
        ch_conv = ch_data["conversion_lead_to_won"]
        if ch_leads > median_leads:
            low_qual = False
            if ch_cpw is not None and ch_cpw > median_cpw:
                low_qual = True
            if ch_conv is not None and ch_conv < median_conv:
                low_qual = True
            if low_qual:
                diagnostic_flags.append({
                    "channel": ch, "model": m, "flag_type": "high_volume_low_quality",
                    "leads_generated": ch_leads, "cost_per_won": ch_cpw,
                    "conversion_rate": ch_conv, "pipeline_influenced": ch_pi,
                    "roi": ch_roi, "roi_rank": roi_rank,
                    "budget_pct": ch_budget, "budget_rank": budget_rank
                })

# Persona analysis
persona_analysis = {}
for ch in sorted(spend_channels & pipeline_channels):
    role_counts = defaultdict(int)
    total_tp = 0
    for d in deals:
        for tp in d.get("touchpoints", []):
            if tp["channel"] == ch:
                role_counts[tp.get("contact_role", "unknown")] += 1
                total_tp += 1

    dist = sorted([{"contact_role": role, "count": cnt, "pct": r1(cnt / total_tp * 100) if total_tp > 0 else 0}
                   for role, cnt in role_counts.items()], key=lambda x: -x["count"])
    top = dist[0]["contact_role"] if dist else "unknown"
    breadth = len(role_counts)

    persona_analysis[ch] = {
        "touchpoint_distribution": dist,
        "top_persona": top,
        "persona_reach_breadth": breadth
    }

# Validation
print(f"Total spend: ${total_spend:,.2f}")
print(f"Total pipeline attributed: ${total_pipeline:,.2f}")
print(f"Channels matched: {channels_matched}, unmatched: {channels_unmatched}")
print(f"Campaigns matched: {campaigns_matched}")
print(f"Diagnostic flags: {len(diagnostic_flags)}")
for f in diagnostic_flags:
    print(f"  {f['channel']} ({f['model']}): {f['flag_type']}")

for ch in channels_list:
    for m in MODELS:
        ch_pi = channel_leaderboard[ch]["by_model"][m]["pipeline_influenced"]
        camp_sum = sum(campaign_detail[ch][cp]["by_model"][m]["pipeline_influenced"]
                       for cp in campaign_detail[ch] if m in campaign_detail[ch][cp].get("by_model", {}))
        if abs(camp_sum - ch_pi) > 1:
            print(f"  ROLLUP MISMATCH: {ch} {m}: channel={ch_pi} campaigns={camp_sum}")

for m in MODELS:
    ranks = [channel_leaderboard[ch]["by_model"][m]["rank"] for ch in channels_list]
    if sorted(ranks) != list(range(1, len(channels_list) + 1)):
        print(f"  RANK ERROR {m}: {ranks}")

output = {
    "metadata": {
        "run_id": "synthetic-run",
        "generated_date": "2026-07-14T00:00:00Z",
        "agent": "03-channel-performance",
        "total_spend": total_spend,
        "total_pipeline_attributed": total_pipeline,
        "channels_matched": channels_matched,
        "channels_unmatched": channels_unmatched,
        "campaigns_matched": campaigns_matched,
        "campaigns_unmatched": campaigns_unmatched,
        "data_quality_warnings": warnings
    },
    "channel_leaderboard": channel_leaderboard,
    "campaign_detail": campaign_detail,
    "diagnostic_flags": diagnostic_flags,
    "persona_analysis": persona_analysis
}

os.makedirs(f"{RUN}/performance", exist_ok=True)
with open(f"{RUN}/performance/channel-performance.json", "w") as f:
    json.dump(output, f, indent=2)

fsize = os.path.getsize(f"{RUN}/performance/channel-performance.json")
print(f"\nWritten to channel-performance.json ({fsize:,} bytes)")
