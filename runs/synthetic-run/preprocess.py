import csv
import json
import sys
from collections import defaultdict

RUN_DIR = "/Users/neel/Documents/pipeline-attribution/runs/synthetic-run"
INPUT_DIR = f"{RUN_DIR}/inputs"

# --- Merge pipeline-deals.csv + pipeline-touchpoints.csv → pipeline-records.json ---

deals = []
with open(f"{INPUT_DIR}/pipeline-deals.csv", newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        row["deal_size"] = float(row["deal_size"])
        row["employee_count"] = int(row["employee_count"])
        ts_fields = ["lead_created_date", "mql_date", "sql_date", "opportunity_created_date", "closed_date"]
        for field in ts_fields:
            if row[field] == "" or row[field] is None:
                row[field] = None
        if row["lost_reason"] == "":
            row["lost_reason"] = None
        row["touchpoints"] = []
        deals.append(row)

deal_map = {d["deal_id"]: d for d in deals}

touchpoint_count = 0
orphaned = []
with open(f"{INPUT_DIR}/pipeline-touchpoints.csv", newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        touchpoint_count += 1
        did = row["deal_id"]
        if did not in deal_map:
            orphaned.append(did)
            continue
        deal_map[did]["touchpoints"].append({
            "touchpoint_date": row["touchpoint_date"],
            "channel": row["channel"],
            "campaign_name": row["campaign_name"],
            "content_asset": row["content_asset"],
            "touchpoint_type": row["touchpoint_type"],
            "funnel_stage_at_touch": row["funnel_stage_at_touch"],
            "contact_role": row["contact_role"],
        })

# Sort touchpoints by date within each deal
for d in deals:
    d["touchpoints"].sort(key=lambda t: t["touchpoint_date"])

# Validate
deals_with_zero = [d["deal_id"] for d in deals if len(d["touchpoints"]) == 0]
if deals_with_zero:
    print(f"WARNING: {len(deals_with_zero)} deals with 0 touchpoints: {deals_with_zero}")
if orphaned:
    print(f"WARNING: {len(orphaned)} orphaned touchpoints (deal_id not found)")

with open(f"{INPUT_DIR}/pipeline-records.json", "w", encoding="utf-8") as f:
    json.dump(deals, f, indent=2)

total_touchpoints = sum(len(d["touchpoints"]) for d in deals)
print(f"pipeline-records.json: {len(deals)} deals, {total_touchpoints} touchpoints")

# --- channel-spend.csv → channel-spend.json ---

spend_records = []
with open(f"{INPUT_DIR}/channel-spend.csv", newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        row["spend"] = float(row["spend"])
        spend_records.append(row)

with open(f"{INPUT_DIR}/channel-spend.json", "w", encoding="utf-8") as f:
    json.dump(spend_records, f, indent=2)

print(f"channel-spend.json: {len(spend_records)} spend records")

if len(spend_records) != 216:
    print(f"WARNING: Expected 216 spend records (12 months x 18 campaigns), got {len(spend_records)}")

print(f"\nPreprocessing complete. {len(deals)} deals with {total_touchpoints} total touchpoints. {len(spend_records)} spend records.")
