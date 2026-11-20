"""Controlled Ingestion Script for Milestone 8 Phase 1.

Executes controlled ingestion across all 4 proven integrations:
- Hasjob (Atom feed)
- Remotive (Remote tech JSON API)
- Greenhouse ATS (7 verified companies)
- Lever ATS (7 verified companies)
"""
import sys
import json
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.database import SessionLocal, init_db
from app.ingestion.pipeline import run_ingestion_pipeline
from app.ingestion.sources.hasjob import HasjobAdapter
from app.ingestion.sources.remotive import RemotiveAdapter
from app.ingestion.sources.greenhouse import GreenhouseAdapter
from app.ingestion.sources.lever import LeverAdapter


def main():
    print("=" * 80)
    print("STARTING CONTROLLED INGESTION RUN (Milestone 8 Phase 1)")
    print("=" * 80)

    init_db()
    db = SessionLocal()

    adapters = [
        HasjobAdapter(),
        RemotiveAdapter(),
        GreenhouseAdapter(),
        LeverAdapter()
    ]

    try:
        summary = run_ingestion_pipeline(
            db=db,
            adapters=adapters,
            batch_run_id="m8_phase1_run"
        )

        print("\nINGESTION EXECUTION REPORT:")
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
            if data.get("rejection_reasons"):
                print(f"   Rejection categories for {src}:")
                for reason, count in sorted(data["rejection_reasons"].items(), key=lambda x: x[1], reverse=True):
                    print(f"     - {reason}: {count}")
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

        # Output JSON summary for automated reporting
        with open("m8_p1_ingestion_summary.json", "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        print("\nSummary written to m8_p1_ingestion_summary.json")

    finally:
        db.close()


if __name__ == "__main__":
    main()
