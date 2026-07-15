import json
import math
import os
from datetime import datetime

RUN = "/Users/neel/Documents/pipeline-attribution/runs/synthetic-run"

with open(f"{RUN}/inputs/pipeline-records.json") as f:
    deals = json.load(f)

closed = [d for d in deals if d["deal_outcome"] in ("won", "lost")]
skipped = []
processable = []
for d in closed:
    if not d.get("touchpoints") or len(d["touchpoints"]) == 0:
        skipped.append(d["deal_id"])
    elif not d.get("closed_date"):
        skipped.append(d["deal_id"])
    else:
        processable.append(d)

print(f"Total deals: {len(deals)}, Closed: {len(closed)}, Processable: {len(processable)}, Skipped: {len(skipped)}")

def parse_date(s):
    return datetime.fromisoformat(s).timestamp() / 86400.0

def days_between(a, b):
    return (datetime.fromisoformat(b) - datetime.fromisoformat(a)).days

def r2(n):
    return round(n, 2)

MODELS = ["first_touch", "last_touch", "linear", "time_decay", "w_shaped"]

deal_audits = []
ch_agg = {}
cp_agg = {}
ch_activity = {}

for deal in processable:
    tps = sorted(deal["touchpoints"], key=lambda t: t["touchpoint_date"])
    n = len(tps)
    ds = deal["deal_size"]

    # Key moments
    ft_idx = 0

    # Lead creation touch
    if not deal.get("lead_created_date"):
        lc_idx = 0
    else:
        lc_idx = None
        for i in range(n):
            if tps[i]["touchpoint_date"] <= deal["lead_created_date"]:
                lc_idx = i
        if lc_idx is None:
            for i in range(n):
                if tps[i]["touchpoint_date"] > deal["lead_created_date"]:
                    lc_idx = i
                    break
            if lc_idx is None:
                lc_idx = 0

    # Opp creation touch
    if not deal.get("opportunity_created_date"):
        oc_idx = n - 1
    else:
        oc_idx = None
        for i in range(n):
            if tps[i]["touchpoint_date"] <= deal["opportunity_created_date"]:
                oc_idx = i
        if oc_idx is None:
            for i in range(n):
                if tps[i]["touchpoint_date"] > deal["opportunity_created_date"]:
                    oc_idx = i
                    break
            if oc_idx is None:
                oc_idx = n - 1

    credits = {m: [0.0] * n for m in MODELS}

    # First-Touch
    credits["first_touch"][0] = ds

    # Last-Touch
    if not deal.get("opportunity_created_date"):
        lt_idx = n - 1
    else:
        lt_idx = None
        for i in range(n):
            if tps[i]["touchpoint_date"] <= deal["opportunity_created_date"]:
                lt_idx = i
        if lt_idx is None:
            lt_idx = n - 1
    credits["last_touch"][lt_idx] = ds

    # Linear
    each = ds / n
    for i in range(n):
        credits["linear"][i] = r2(each)
    lin_sum = sum(credits["linear"])
    credits["linear"][n - 1] = r2(credits["linear"][n - 1] + ds - r2(lin_sum))

    # Time-Decay
    raw_weights = []
    for i in range(n):
        dbc = days_between(tps[i]["touchpoint_date"], deal["closed_date"])
        raw_weights.append(2 ** (-dbc / 7.0))
    w_sum = sum(raw_weights)
    for i in range(n):
        credits["time_decay"][i] = r2(ds * raw_weights[i] / w_sum)
    td_sum = sum(credits["time_decay"])
    credits["time_decay"][n - 1] = r2(credits["time_decay"][n - 1] + ds - r2(td_sum))

    # W-Shaped
    if n == 1:
        credits["w_shaped"][0] = ds
    else:
        key_set = set([ft_idx, lc_idx, oc_idx])
        if len(key_set) == 1:
            credits["w_shaped"][ft_idx] = ds
        else:
            kp = {}
            kp[ft_idx] = kp.get(ft_idx, 0) + 0.30
            kp[lc_idx] = kp.get(lc_idx, 0) + 0.30
            kp[oc_idx] = kp.get(oc_idx, 0) + 0.30
            remainder_indices = [i for i in range(n) if i not in key_set]
            if len(remainder_indices) == 0:
                total_kp = sum(kp.values())
                for idx in kp:
                    kp[idx] = kp[idx] + 0.10 * (kp[idx] / total_kp)
            for idx in kp:
                credits["w_shaped"][idx] = r2(ds * kp[idx])
            if len(remainder_indices) > 0:
                each_rem = r2(ds * 0.10 / len(remainder_indices))
                for i in remainder_indices:
                    credits["w_shaped"][i] = each_rem
            w_sum = sum(credits["w_shaped"])
            credits["w_shaped"][n - 1] = r2(credits["w_shaped"][n - 1] + ds - r2(w_sum))

    # Validate per-deal sums
    for m in MODELS:
        s = r2(sum(credits[m]))
        if abs(s - ds) > 0.01:
            print(f"SUM ERROR: {deal['deal_id']} {m} sum={s} size={ds}")
        for i in range(n):
            if credits[m][i] < 0:
                print(f"NEG ERROR: {deal['deal_id']} {m} idx={i} val={credits[m][i]}")

    deal_audits.append({
        "deal_id": deal["deal_id"],
        "company_name": deal["company_name"],
        "deal_size": ds,
        "deal_outcome": deal["deal_outcome"],
        "touchpoint_count": n,
        "key_moments": {
            "first_touch_index": ft_idx,
            "lead_creation_index": lc_idx,
            "opp_creation_index": oc_idx
        },
        "touchpoints": [{
            "touchpoint_date": tps[i]["touchpoint_date"],
            "channel": tps[i]["channel"],
            "campaign_name": tps[i]["campaign_name"],
            "content_asset": tps[i].get("content_asset", ""),
            "touchpoint_type": tps[i]["touchpoint_type"],
            "funnel_stage_at_touch": tps[i].get("funnel_stage_at_touch", ""),
            "contact_role": tps[i]["contact_role"],
            "credits": {m: credits[m][i] for m in MODELS}
        } for i in range(n)]
    })

    # Aggregate to channels and campaigns
    for i, tp in enumerate(tps):
        ch = tp["channel"]
        cp = tp["campaign_name"]

        if ch not in ch_agg:
            ch_agg[ch] = {"deals": set(), "tc": 0, "cr": {m: 0.0 for m in MODELS}}
        ch_agg[ch]["deals"].add(deal["deal_id"])
        ch_agg[ch]["tc"] += 1
        for m in MODELS:
            ch_agg[ch]["cr"][m] += credits[m][i]

        if ch not in cp_agg:
            cp_agg[ch] = {}
        if cp not in cp_agg[ch]:
            cp_agg[ch][cp] = {"deals": set(), "tc": 0, "cr": {m: 0.0 for m in MODELS}}
        cp_agg[ch][cp]["deals"].add(deal["deal_id"])
        cp_agg[ch][cp]["tc"] += 1
        for m in MODELS:
            cp_agg[ch][cp]["cr"][m] += credits[m][i]

        if ch not in ch_activity:
            ch_activity[ch] = {"first_touchpoint_date": tp["touchpoint_date"], "last_touchpoint_date": tp["touchpoint_date"], "total_touchpoint_count": 0}
        if tp["touchpoint_date"] < ch_activity[ch]["first_touchpoint_date"]:
            ch_activity[ch]["first_touchpoint_date"] = tp["touchpoint_date"]
        if tp["touchpoint_date"] > ch_activity[ch]["last_touchpoint_date"]:
            ch_activity[ch]["last_touchpoint_date"] = tp["touchpoint_date"]
        ch_activity[ch]["total_touchpoint_count"] += 1

# Round aggregated credits
for ch in ch_agg:
    for m in MODELS:
        ch_agg[ch]["cr"][m] = r2(ch_agg[ch]["cr"][m])
for ch in cp_agg:
    for cp in cp_agg[ch]:
        for m in MODELS:
            cp_agg[ch][cp]["cr"][m] = r2(cp_agg[ch][cp]["cr"][m])

total_pipeline = r2(sum(d["deal_size"] for d in processable))
channels = sorted(ch_agg.keys())

# Rank channels per model
ch_ranks = {ch: {} for ch in channels}
for m in MODELS:
    sorted_chs = sorted(channels, key=lambda c: (-ch_agg[c]["cr"][m], -len(ch_agg[c]["deals"]), c))
    for rank, ch in enumerate(sorted_chs, 1):
        ch_ranks[ch][m] = rank

# Rank campaigns within channel per model
cp_ranks = {}
for ch in cp_agg:
    cp_ranks[ch] = {}
    cps = sorted(cp_agg[ch].keys())
    for cp in cps:
        cp_ranks[ch][cp] = {}
    for m in MODELS:
        sorted_cps = sorted(cps, key=lambda c: (-cp_agg[ch][c]["cr"][m], -len(cp_agg[ch][c]["deals"]), c))
        for rank, cp in enumerate(sorted_cps, 1):
            cp_ranks[ch][cp][m] = rank

# Build channel_summary — schema expects channel -> model -> fields
channel_summary = {}
for ch in channels:
    channel_summary[ch] = {}
    for m in MODELS:
        credited = ch_agg[ch]["cr"][m]
        dt = len(ch_agg[ch]["deals"])
        channel_summary[ch][m] = {
            "pipeline_credited": credited,
            "rank": ch_ranks[ch][m],
            "deals_touched": dt,
            "touchpoint_count": ch_agg[ch]["tc"],
            "avg_credit_per_deal": r2(credited / dt) if dt > 0 else 0,
            "pct_of_total": round(credited / total_pipeline * 100, 1) if total_pipeline > 0 else 0
        }

# Build campaign_detail — schema expects channel -> campaign -> model -> fields
campaign_detail = {}
for ch in channels:
    campaign_detail[ch] = {}
    for cp in sorted(cp_agg[ch].keys()):
        campaign_detail[ch][cp] = {}
        for m in MODELS:
            credited = cp_agg[ch][cp]["cr"][m]
            dt = len(cp_agg[ch][cp]["deals"])
            campaign_detail[ch][cp][m] = {
                "pipeline_credited": credited,
                "rank": cp_ranks[ch][cp][m],
                "deals_touched": dt,
                "touchpoint_count": cp_agg[ch][cp]["tc"],
                "avg_credit_per_deal": r2(credited / dt) if dt > 0 else 0,
                "pct_of_total": round(credited / total_pipeline * 100, 1) if total_pipeline > 0 else 0
            }

# Validation
print(f"\nTotal pipeline: ${total_pipeline:,.2f}")
for m in MODELS:
    ch_sum = r2(sum(ch_agg[ch]["cr"][m] for ch in channels))
    print(f"  {m} channel sum: ${ch_sum:,.2f} (diff: ${ch_sum - total_pipeline:,.2f})")
    ranks = sorted(ch_ranks[ch][m] for ch in channels)
    print(f"  {m} ranks: {ranks}")

for ch in channels:
    for m in MODELS:
        camp_sum = r2(sum(cp_agg[ch][cp]["cr"][m] for cp in cp_agg[ch]))
        ch_credit = ch_agg[ch]["cr"][m]
        if abs(camp_sum - ch_credit) > 0.05:
            print(f"  ROLLUP MISMATCH: {ch} {m} camps={camp_sum} ch={ch_credit}")

# Print rankings
for m in MODELS:
    ranked = sorted(channels, key=lambda c: ch_ranks[c][m])
    line = " | ".join(f"{ch_ranks[c][m]}.{c}=${ch_agg[c]['cr'][m]:,.0f}" for c in ranked)
    print(f"  {m}: {line}")

output = {
    "metadata": {
        "run_id": "synthetic-run",
        "generated_date": "2026-07-14T00:00:00Z",
        "agent": "01-attribution-modeling",
        "total_deals_processed": len(processable),
        "deals_skipped": {"count": len(skipped), "deal_ids": skipped},
        "total_pipeline_attributed": total_pipeline,
        "models_computed": MODELS,
        "half_life_days": 7,
        "channel_activity": ch_activity
    },
    "channel_summary": channel_summary,
    "campaign_detail": campaign_detail,
    "deal_attribution": deal_audits
}

os.makedirs(f"{RUN}/attribution", exist_ok=True)
with open(f"{RUN}/attribution/attribution-analysis.json", "w") as f:
    json.dump(output, f, indent=2, default=list)

fsize = os.path.getsize(f"{RUN}/attribution/attribution-analysis.json")
print(f"\nWritten to attribution-analysis.json ({fsize:,} bytes)")
