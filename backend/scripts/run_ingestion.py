"""CLI Script to Execute Data Ingestion Pipeline.

Usage:
    python backend/scripts/run_ingestion.py
"""
import sys
import json
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.database import SessionLocal, init_db
from app.ingestion.pipeline import run_ingestion_pipeline


def main():
    print("=" * 70)
    print("STARTING DATA INGESTION PIPELINE (Milestone 2)")
    print("=" * 70)

    # Initialize tables if not already existing
    init_db()
    db = SessionLocal()

    try:
        summary = run_ingestion_pipeline(db=db)

        print("\nINGESTION EXECUTION REPORT:")
        print(f"Master Run ID: {summary['run_id']}")
        print("-" * 70)
        print(f"{'Source':<12} | {'Req':<4} | {'Fetched':<8} | {'Rejected':<8} | {'Unique':<7} | {'Conf Dup':<8} | {'Pot Dup':<7} | {'Time(s)':<7} | {'Status':<7}")
        print("-" * 70)

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
            if data["rejection_reasons"]:
                print(f"   Rejections for {src}:")
                for reason, count in data["rejection_reasons"].items():
                    print(f"     - {reason}: {count}")
            if data["error"]:
                print(f"   Error: {data['error']}")

        print("-" * 70)
        t = summary["totals"]
        print("TOTALS:")
        print(f"  Requests Made:        {t['requests_made']}")
        print(f"  Records Fetched:      {t['records_fetched']}")
        print(f"  Records Rejected:     {t['records_rejected']}")
        print(f"  Canonical Inserted:   {t['unique_inserted']}")
        print(f"  Confirmed Duplicates: {t['confirmed_duplicates']}")
        print(f"  Potential Duplicates: {t['potential_duplicates']}")
        print(f"  Errors Encountered:   {t['errors_count']}")
        print("=" * 70)

    finally:
        db.close()


if __name__ == "__main__":
    main()
