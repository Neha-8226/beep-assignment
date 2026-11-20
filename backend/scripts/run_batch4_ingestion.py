"""Batch 4 Ingestion Script for Milestone 8 Phase 2.

Executes targeted ingestion across 28 newly verified employers:
- 24 Greenhouse ATS employers
- 4 Lever ATS employers
"""
import sys
import json
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.database import SessionLocal, init_db
from app.ingestion.pipeline import run_ingestion_pipeline
from app.ingestion.sources.company_registry import get_verified_companies
from app.ingestion.sources.greenhouse import GreenhouseAdapter
from app.ingestion.sources.lever import LeverAdapter

# Define Batch 4 slug list
BATCH4_GH_SLUGS = [
    "canonical", "fivetran", "cloudsek", "twinhealth", "prodigal", "zetaglobal",
    "worldquant", "imc", "squarepointcapital", "exoduspoint", "towerresearchcapital",
    "starburst", "anydesk", "binance", "bitgo", "nice", "aqr", "akunacapital",
    "adyen", "deliveroo", "dialpad", "five9", "anthropic", "scaleai"
]

BATCH4_LEVER_SLUGS = [
    "cyderes", "collabora", "crypto", "outreach"
]


def main():
    print("=" * 80)
    print("STARTING MILESTONE 8 PHASE 2 - BATCH 4 INGESTION RUN")
    print("=" * 80)

    init_db()
    db = SessionLocal()

    all_gh = get_verified_companies(provider="greenhouse", active_only=True)
    all_lever = get_verified_companies(provider="lever", active_only=True)

    batch4_gh = [c for c in all_gh if c.token_or_slug in BATCH4_GH_SLUGS]
    batch4_lever = [c for c in all_lever if c.token_or_slug in BATCH4_LEVER_SLUGS]

    print(f"Executing Batch 4 across {len(batch4_gh)} Greenhouse and {len(batch4_lever)} Lever employers...")

    gh_adapter = GreenhouseAdapter(companies=batch4_gh)
    lever_adapter = LeverAdapter(companies=batch4_lever)

    try:
        summary = run_ingestion_pipeline(
            db=db,
            adapters=[gh_adapter, lever_adapter],
            batch_run_id="m8_phase2_batch4"
        )

        print("\nBATCH 4 EXECUTION REPORT:")
        print(f"Master Run ID: {summary['run_id']}")
        print("-" * 80)
        print(f"{'Source':<12} | {'Req':<4} | {'Fetched':<8} | {'Rejected':<8} | {'Unique':<7} | {'Conf Dup':<8} | {'Pot Dup':<7} | {'Time(s)':<7} | {'Status':<7}")
        print("-" * 80)

        for src, data in summary["sources"].items():
            print(
                f"{src:<12} | "
                f"{data['requests_made']:<4} | "
                f"{data['fetched_count']:<8} | "
                f"{data['rejected_count']:<8} | "
                f"{data['unique_inserted']:<7} | "
                f"{data['confirmed_duplicates']:<8} | "
                f"{data['potential_duplicates']:<7} | "
                f"{data['duration_seconds']:<7.2f} | "
                f"{data['status']:<7}"
            )
            if data.get("error"):
                print(f"   Error: {data['error']}")

        print("-" * 80)
        t = summary["totals"]
        print("TOTALS:")
        print(f"  Requests Made:        {t['requests_made']}")
        print(f"  Records Fetched:      {t['records_fetched']}")
        print(f"  Records Rejected:     {t['records_rejected']}")
        print(f"  Canonical Inserted:   {t['unique_inserted']}")
        print(f"  Confirmed Duplicates: {t['confirmed_duplicates']}")
        print(f"  Potential Duplicates: {t['potential_duplicates']}")
        print(f"  Errors Encountered:   {t['errors_count']}")
        print("=" * 80)

        with open("m8_p2_batch4_summary.json", "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        print("\nSummary written to m8_p2_batch4_summary.json")

    finally:
        db.close()


if __name__ == "__main__":
    main()
