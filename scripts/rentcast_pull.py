#!/usr/bin/env python3
"""
RentCast rental-listing puller with a write-once disk cache.

The free plan allows 50 API requests per month, so every call is treated as
expensive and irreversible: responses are cached to data/raw/ BEFORE parsing,
and a cached request is never re-issued. Do all downstream development against
the cache -- never re-call the API just to re-parse.

Usage:
    python3 scripts/rentcast_pull.py --probe      # 1 request: count + first 500
    python3 scripts/rentcast_pull.py --pull       # paginate to completion
    python3 scripts/rentcast_pull.py --status     # cache + quota report, 0 requests
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
QUOTA_LOG = ROOT / "data" / "quota_log.jsonl"

API = "https://api.rentcast.io/v1/listings/rental/long-term"
PAGE = 500          # API maximum per request
RATE_SLEEP = 0.2    # well under the 20 req/sec hard limit

# Circle covering Santa Cruz + Monterey + San Benito counties, plus the
# southern Santa Clara fringe (Gilroy / Morgan Hill). County is returned on
# every record, so the tier-2 fringe gets tagged and kept or dropped later
# rather than being excluded at collection time.
CENTER_LAT, CENTER_LON, RADIUS_MI = 36.75, -121.75, 40

# Named search circles. The wide "tricounty" circle is sorted by lastSeenDate,
# so paginating it is dominated by high-churn large complexes in Salinas /
# Monterey / south San Jose and reaches Santa Cruz County barely or not at all.
# Targeted circles are the only reliable way to cover the area we actually care
# about on a constrained request budget.
CIRCLES = {
    "tricounty":  (36.75, -121.75, 40),   # SC + Monterey + San Benito + S. Santa Clara
    "santacruz":  (37.00, -121.97, 15),   # ~all of Santa Cruz County
    # Peninsula + Seaside/Marina + Salinas + Castroville in one circle. Reaches
    # ~11mi to Carmel and ~6mi to Salinas; stops short of Watsonville (~19mi).
    # Small overlap with "santacruz" near Pajaro/Moss Landing -- dedup on id.
    "montereyco": (36.64, -121.76, 14),
}


def load_env():
    env = {}
    for line in (ROOT / ".env").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    key = env.get("RENTCAST_API_KEY")
    if not key:
        sys.exit("RENTCAST_API_KEY is empty in .env")
    return key


def log_quota(tag, n):
    QUOTA_LOG.parent.mkdir(parents=True, exist_ok=True)
    with QUOTA_LOG.open("a") as f:
        f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                            "tag": tag, "requests": n}) + "\n")


def spent_this_month():
    if not QUOTA_LOG.exists():
        return 0
    prefix = time.strftime("%Y-%m")
    return sum(json.loads(l)["requests"] for l in QUOTA_LOG.read_text().splitlines()
               if l.strip() and json.loads(l)["ts"].startswith(prefix))


def fetch(key, offset, snapshot, circle, total_count=False):
    """One API request. Returns (records, total_or_None, was_cached)."""
    lat, lon, rad = CIRCLES[circle]
    params = {
        "latitude": lat, "longitude": lon, "radius": rad,
        "limit": PAGE, "offset": offset,
    }
    if total_count:
        params["includeTotalCount"] = "true"

    out = RAW / snapshot / circle / f"rental_offset{offset:05d}.json"
    if out.exists():
        blob = json.loads(out.read_text())
        return blob["records"], blob.get("totalCount"), True

    url = f"{API}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Accept": "application/json",
                                               "X-Api-Key": key})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            records = json.loads(r.read().decode())
            total = r.headers.get("X-Total-Count")
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code} at offset {offset}: {e.read().decode()[:400]}")

    total = int(total) if total else None
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "_meta": {"pulled": time.strftime("%Y-%m-%dT%H:%M:%S"), "params": params,
                  "endpoint": API},
        "totalCount": total,
        "records": records,
    }, indent=2))
    log_quota(f"offset{offset}", 1)
    return records, total, False


def summarize(records):
    """Field-population report -- the point of the D0 probe."""
    n = len(records)
    fields, counties, ptypes, beds = {}, {}, {}, {}
    for r in records:
        for k, v in r.items():
            if v not in (None, "", [], {}):
                fields[k] = fields.get(k, 0) + 1
        counties[r.get("county")] = counties.get(r.get("county"), 0) + 1
        ptypes[r.get("propertyType")] = ptypes.get(r.get("propertyType"), 0) + 1
        b = r.get("bedrooms")
        beds[b] = beds.get(b, 0) + 1

    print(f"\n{'='*62}\nFIELD POPULATION  (n={n})\n{'='*62}")
    for k, c in sorted(fields.items(), key=lambda x: -x[1]):
        bar = "#" * int(28 * c / n)
        print(f"  {k:<22} {c:>4}/{n}  {100*c/n:5.1f}%  {bar}")

    print(f"\n{'='*62}\nCOUNTY\n{'='*62}")
    for k, c in sorted(counties.items(), key=lambda x: -x[1]):
        print(f"  {str(k):<22} {c:>4}  {100*c/n:5.1f}%")

    print(f"\n{'='*62}\nPROPERTY TYPE\n{'='*62}")
    for k, c in sorted(ptypes.items(), key=lambda x: -x[1]):
        print(f"  {str(k):<22} {c:>4}  {100*c/n:5.1f}%")

    print(f"\n{'='*62}\nBEDROOMS  (0 = studio)\n{'='*62}")
    for k, c in sorted(beds.items(), key=lambda x: (x[0] is None, x[0])):
        star = "   <-- target" if k in (0, 1) else ""
        print(f"  {str(k):<22} {c:>4}  {100*c/n:5.1f}%{star}")
    stat = {}
    for r in records:
        stat[r.get("status")] = stat.get(r.get("status"), 0) + 1
    print(f"\n{'='*62}\nLISTING STATUS\n{'='*62}")
    for k, c in sorted(stat.items(), key=lambda x: -x[1]):
        print(f"  {str(k):<22} {c:>4}  {100*c/n:5.1f}%")

    tgt = sum(c for k, c in beds.items() if k in (0, 1))
    print(f"\n  studio+1br subtotal: {tgt} of {n}  ({100*tgt/n:.1f}%)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--pull", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--snapshot", default=date.today().isoformat())
    ap.add_argument("--circle", default="santacruz", choices=sorted(CIRCLES))
    ap.add_argument("--max-requests", type=int, default=12,
                    help="hard ceiling on API calls this run")
    a = ap.parse_args()

    used = spent_this_month()
    print(f"quota used this calendar month: {used}/50")

    if a.status:
        for d in sorted(p for p in RAW.glob("*/*") if p.is_dir()):
            files = sorted(d.glob("rental_offset*.json"))
            recs = sum(len(json.loads(f.read_text())["records"]) for f in files)
            print(f"  {d.parent.name}/{d.name}: {len(files)} pages, {recs} records")
        return

    key = load_env()

    if a.probe:
        recs, total, cached = fetch(key, 0, a.snapshot, a.circle, total_count=True)
        print(f"{'cache hit' if cached else 'API call'} -> {len(recs)} records")
        print(f"X-Total-Count for this query: {total}")
        if total:
            print(f"pages needed to pull all: {-(-total // PAGE)} "
                  f"({-(-total // PAGE) - 1} more beyond this one)")
        summarize(recs)
        (RAW / a.snapshot / a.circle / "_sample_record.json").write_text(
            json.dumps(recs[0], indent=2))
        print(f"\nfull example record -> data/raw/{a.snapshot}/{a.circle}/_sample_record.json")
        return

    if a.pull:
        all_recs, offset, calls = [], 0, 0
        while True:
            recs, total, cached = fetch(key, offset, a.snapshot, a.circle,
                                        total_count=(offset == 0))
            if not cached:
                calls += 1
                time.sleep(RATE_SLEEP)
            all_recs += recs
            print(f"  offset {offset:>5}: {len(recs):>3} records"
                  f"{' (cached)' if cached else ''}")
            if len(recs) < PAGE:
                break
            offset += PAGE
            if calls >= a.max_requests:
                print(f"stopping: hit --max-requests ceiling of {a.max_requests}")
                break
        print(f"\ntotal records: {len(all_recs)}   API calls this run: {calls}")
        summarize(all_recs)


if __name__ == "__main__":
    main()
