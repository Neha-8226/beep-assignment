"""CLI Script to Execute LLM Classification over Unclassified Jobs.

Enforces strict safety guardrails:
1. Requires explicit `--limit`, `--job-ids`, or `--dry-run` to prevent accidental unbounded classification.
2. Supports explicit comma-separated `--job-ids` with validation against missing, duplicate, or already-classified jobs.
3. Enforces a maximum pilot limit of 15 jobs unless `--override-pilot-limit` is explicitly provided.
4. Includes a full `--dry-run` mode that generates prompts, previews payloads, and estimates tokens
   with ZERO Gemini API calls and ZERO database writes.

Usage:
    # Dry-run preview of approved 15-job pilot sample
    python backend/scripts/run_classification.py --job-ids 113,91,3,112,136,132,94,90,121,137,126,128,98,111,114 --dry-run

    # Dry-run preview of first 15 pending jobs
    python backend/scripts/run_classification.py --dry-run

    # Live classification pilot (capped at 15 jobs)
    python backend/scripts/run_classification.py --limit 15

    # Authorized override for larger batches (> 15 jobs)
    python backend/scripts/run_classification.py --limit 30 --override-pilot-limit
"""
import sys
import os
import argparse
from collections import Counter
from pathlib import Path
from typing import List, Optional

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.config import settings
from app.database import SessionLocal
from app.models import Job
from app.ai.classifier import classify_pending_jobs
from app.ai.prompts import format_batch_prompt, SYSTEM_INSTRUCTIONS
from app.ai.cost_tracker import get_cost_summary, calculate_batch_costs


def estimate_tokens_from_text(text: str) -> int:
    """Heuristic token estimation: ~1 token per 3.8 characters for English tech text."""
    if not text:
        return 0
    return max(1, int(len(text) / 3.8))


def main():
    parser = argparse.ArgumentParser(
        description="Run LLM classification over pending jobs with strict safety guardrails.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
SAFETY SAFEGUARDS:
  - An explicit --limit (e.g. '--limit 15'), --job-ids, or '--dry-run' is REQUIRED.
  - Live execution is capped at 15 jobs max. To process more, supply '--override-pilot-limit'.
  - Dry-run mode previews prompts and estimates token costs with ZERO API calls and ZERO DB writes.
        """
    )
    parser.add_argument(
        "--job-ids",
        type=str,
        default=None,
        help="Comma-separated list of explicit job IDs to classify (e.g. '113,91,3,112,...')."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Explicit number of jobs to classify (max 15 unless --override-pilot-limit is passed)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview prompt payload and estimated token exposure without making API calls or DB writes."
    )
    parser.add_argument(
        "--override-pilot-limit",
        action="store_true",
        help="Explicit authorization override permitting --limit or --job-ids > 15 jobs."
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=15,
        help="Number of jobs per LLM batch (default: 15)."
    )
    parser.add_argument(
        "--desc-limit",
        type=int,
        default=None,
        help=f"Override description truncation character limit (default: {settings.CLASSIFIER_DESCRIPTION_MAX_CHARS})."
    )
    args = parser.parse_args()

    desc_limit = args.desc_limit if args.desc_limit is not None else settings.CLASSIFIER_DESCRIPTION_MAX_CHARS

    print("=" * 75)
    print("LLM CLASSIFICATION ENGINE — SAFETY CONTROLLER (Milestone 7)")
    print("=" * 75)
    print(f"Configured Model:        {settings.GEMINI_MODEL}")
    print(f"Pricing Tier:            {settings.GEMINI_PRICING_TIER}")
    print(f"Input Price / 1M:        ${settings.GEMINI_INPUT_PRICE_PER_1M:.2f}")
    print(f"Output Price / 1M:       ${settings.GEMINI_OUTPUT_PRICE_PER_1M:.2f}")
    print(f"Batch Size:              {args.batch_size}")
    print(f"Request Pacing Delay:    {settings.GEMINI_REQUEST_DELAY_SECONDS}s")
    print(f"Description Limit:       {desc_limit} chars")
    print("-" * 75)

    # -------------------------------------------------------------------------
    # Parse and Validate --job-ids if provided
    # -------------------------------------------------------------------------
    parsed_job_ids: Optional[List[int]] = None
    if args.job_ids:
        raw_parts = [p.strip() for p in args.job_ids.split(",") if p.strip()]
        if not raw_parts:
            print("\n[SAFETY ERROR] Empty --job-ids argument provided.")
            sys.exit(1)

        parsed_job_ids = []
        for part in raw_parts:
            try:
                parsed_job_ids.append(int(part))
            except ValueError:
                print(f"\n[SAFETY ERROR] Invalid job ID format in --job-ids: '{part}'. Expected comma-separated integers.")
                sys.exit(1)

        # Duplicate ID check
        id_counts = Counter(parsed_job_ids)
        duplicate_ids = [jid for jid, count in id_counts.items() if count > 1]
        if duplicate_ids:
            print(f"\n[SAFETY ERROR] Duplicate job IDs detected in --job-ids: {duplicate_ids}. Each job ID must be unique.")
            sys.exit(1)

    # -------------------------------------------------------------------------
    # Safety Check 1: Prevent unbounded classification
    # -------------------------------------------------------------------------
    if args.limit is None and parsed_job_ids is None and not args.dry_run:
        print("\n[SAFETY ERROR] Execution halted by safety controller.")
        print("Reason: An explicit job selection is required (e.g., '--job-ids 113,91,...', '--limit 15', or '--dry-run').")
        print("Unbounded execution over the entire database is strictly blocked to prevent accidental quota exhaustion.")
        print("\nSupported safe invocations:")
        print("  1. Dry-run preview:               python backend/scripts/run_classification.py --dry-run")
        print("  2. Explicit pilot sample dry-run: python backend/scripts/run_classification.py --job-ids 113,91,3,... --dry-run")
        print("  3. Controlled pilot (<= 15 jobs): python backend/scripts/run_classification.py --limit 15")
        print("  4. Authorized override:          python backend/scripts/run_classification.py --limit 30 --override-pilot-limit")
        sys.exit(1)

    effective_limit = len(parsed_job_ids) if parsed_job_ids is not None else (args.limit if args.limit is not None else 15)

    # -------------------------------------------------------------------------
    # Safety Check 2: Pilot limit cap enforcement (max 15 unless overridden)
    # -------------------------------------------------------------------------
    if effective_limit > 15 and not args.override_pilot_limit:
        print(f"\n[SAFETY ERROR] Execution halted: requested job count ({effective_limit}) exceeds pilot cap of 15 jobs.")
        print("To process more than 15 jobs, you must explicitly pass '--override-pilot-limit'.")
        sys.exit(1)

    db = SessionLocal()

    # -------------------------------------------------------------------------
    # Target Job Retrieval & Validation
    # -------------------------------------------------------------------------
    if parsed_job_ids is not None:
        jobs_in_db = db.query(Job).filter(Job.id.in_(parsed_job_ids)).all()
        found_map = {j.id: j for j in jobs_in_db}
        missing_ids = [jid for jid in parsed_job_ids if jid not in found_map]
        if missing_ids:
            print(f"\n[SAFETY ERROR] Specified job IDs not found in database: {missing_ids}.")
            db.close()
            sys.exit(1)

        already_classified = [j.id for j in jobs_in_db if j.role_category is not None]
        if already_classified:
            print(f"\n[SAFETY ERROR] Specified job IDs have already been classified: {already_classified}. Only pending unclassified jobs may be targeted.")
            db.close()
            sys.exit(1)

        target_jobs = [found_map[jid] for jid in parsed_job_ids]
    else:
        query = db.query(Job).filter(Job.role_category.is_(None)).order_by(Job.id.asc())
        target_jobs = query.limit(effective_limit).all()

    # -------------------------------------------------------------------------
    # DRY RUN MODE (Zero API calls, Zero DB writes)
    # -------------------------------------------------------------------------
    if args.dry_run:
        print("\n>>> EXECUTING DRY-RUN MODE (ZERO API CALLS, ZERO DB WRITES) <<<")
        total_pending = db.query(Job).filter(Job.role_category.is_(None)).count()

        print(f"\nTarget Selection Summary:")
        print(f"  Total pending unclassified jobs in DB: {total_pending}")
        print(f"  Dry-run sample selected for preview:   {len(target_jobs)}")

        if not target_jobs:
            print("[INFO] No pending jobs to classify in the database.")
            db.close()
            return

        print("\nSelected Jobs Preview:")
        print(f"{'ID':<6} | {'Source':<12} | {'Company':<25} | {'Title':<42} | {'Location'}")
        print("-" * 115)
        jobs_data = []
        for j in target_jobs:
            comp = (j.company or "N/A")[:24]
            title = (j.title or "N/A")[:41]
            loc = (j.raw_location or "N/A")[:25]
            print(f"{j.id:<6} | {j.source:<12} | {comp:<25} | {title:<42} | {loc}")
            jobs_data.append({
                "id": j.id,
                "title": j.title,
                "company": j.company,
                "raw_location": j.raw_location,
                "description": j.description
            })

        # Generate sample batch prompt
        sample_prompt = format_batch_prompt(jobs_data[:args.batch_size], max_desc_chars=desc_limit)

        # Estimate token exposure
        est_prompt_tokens = estimate_tokens_from_text(SYSTEM_INSTRUCTIONS + sample_prompt)
        est_completion_tokens = len(jobs_data[:args.batch_size]) * 95  # ~95 tokens per structured classification
        est_costs = calculate_batch_costs(est_prompt_tokens, est_completion_tokens)

        print("\n" + "=" * 75)
        print("TOKEN & COST EXPOSURE ESTIMATE (HEURISTIC):")
        print("=" * 75)
        print(f"  Sample Batch Jobs:               {len(jobs_data[:args.batch_size])}")
        print(f"  Estimated Prompt Tokens:         ~{est_prompt_tokens:,} tokens")
        print(f"  Estimated Completion Tokens:     ~{est_completion_tokens:,} tokens")
        print(f"  Estimated Total Tokens:          ~{est_prompt_tokens + est_completion_tokens:,} tokens")
        print(f"  Estimated Nominal Cost (Batch):  ${est_costs['nominal_cost_usd']:.5f}")
        est_per_1k = round((est_costs['nominal_cost_usd'] / len(jobs_data[:args.batch_size])) * 1000.0, 4)
        print(f"  Projected Nominal Cost / 1k:     ${est_per_1k:.4f}")

        print("\n" + "=" * 75)
        print("PROMPT PAYLOAD PREVIEW (FIRST BATCH):")
        print("=" * 75)
        lines = sample_prompt.split("\n")
        preview_lines = lines[:45]
        print("\n".join(preview_lines))
        if len(lines) > 45:
            print(f"\n... [{len(lines) - 45} more lines omitted for brevity] ...")
        print("\n" + "=" * 75)
        print("[DRY RUN COMPLETE] Verified: 0 Gemini API calls made. 0 database records modified.")
        print("=" * 75)
        db.close()
        return

    # -------------------------------------------------------------------------
    # LIVE CLASSIFICATION EXECUTION (PILOT)
    # -------------------------------------------------------------------------
    api_key = settings.GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[WARNING] GEMINI_API_KEY is not configured in .env or environment.")
        print("To run live classification, set GEMINI_API_KEY in your .env file.")
        print(f"Current unclassified jobs in database: {db.query(Job).filter(Job.role_category.is_(None)).count()}")
        db.close()
        return

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
    except Exception as e:
        print(f"[ERROR] Failed to initialize Google GenAI Client: {e}")
        db.close()
        return

    try:
        res = classify_pending_jobs(
            db=db,
            client=client,
            batch_size=args.batch_size,
            max_jobs=effective_limit if parsed_job_ids is None else None,
            job_ids=parsed_job_ids
        )

        print("\nCLASSIFICATION EXECUTION SUMMARY:")
        print(f"  Total Jobs Target:    {res['total_jobs']}")
        print(f"  Batches Executed:     {res['batches']}")
        print(f"  Successfully Updated: {res['success']}")
        print(f"  Errors Encountered:   {res['errors']}")
        print("-" * 75)

        # Collect detailed classification output including model reasoning
        classification_details = {}
        for b_rep in res.get("batch_reports", []):
            for c_item in b_rep.get("classifications", []):
                classification_details[c_item["job_id"]] = c_item

        target_id_list = parsed_job_ids if parsed_job_ids else [j.id for j in target_jobs]
        updated_jobs = db.query(Job).filter(Job.id.in_(target_id_list)).all()
        updated_map = {j.id: j for j in updated_jobs}

        print("\nRECORD-LEVEL CLASSIFICATION RESULTS:")
        print("=" * 120)
        for jid in target_id_list:
            job = updated_map.get(jid)
            c_info = classification_details.get(jid, {})
            reasoning = c_info.get("reasoning", "N/A")
            if job:
                print(f"Job ID:                      {job.id}")
                print(f"Title:                       {job.title}")
                print(f"Company:                     {job.company or 'N/A'}")
                print(f"Source:                      {job.source}")
                print(f"Raw Location:                {job.raw_location or 'N/A'}")
                print(f"Predicted Role Category:     {job.role_category}")
                print(f"Predicted Standardized City: {job.standardized_city}")
                print(f"Predicted Job Type:          {job.job_type}")
                print(f"Predicted Fresher Status:    {job.fresher_eligibility_status}")
                print(f"Model Confidence:            {job.model_confidence}")
                print(f"Model Reasoning:             {reasoning}")
                print(f"Classification Error:        {job.classification_error or 'None'}")
                print("-" * 120)

        print("\nBATCH EXECUTION METRICS:")
        print("=" * 75)
        for idx, b_rep in enumerate(res.get("batch_reports", []), start=1):
            p_tok = b_rep.get("prompt_tokens", 0)
            c_tok = b_rep.get("completion_tokens", 0)
            t_tok = p_tok + c_tok
            lat = b_rep.get("latency_seconds", 0.0)
            status = b_rep.get("status", "unknown")
            batch_costs = calculate_batch_costs(p_tok, c_tok)
            print(f"Batch {idx} ID:               {b_rep.get('batch_id')}")
            print(f"Model Used:                 {settings.GEMINI_MODEL}")
            print(f"Status:                     {status}")
            print(f"Processed / Success / Err:  {b_rep.get('processed')} / {b_rep.get('success')} / {b_rep.get('errors')}")
            print(f"Latency:                    {lat:.2f}s")
            print(f"Input (Prompt) Tokens:      {p_tok:,}")
            print(f"Output (Completion) Tokens: {c_tok:,}")
            print(f"Total Billed Tokens:        {t_tok:,}")
            print(f"Actual Incurred Cost:       ${batch_costs['actual_cost_usd']:.5f} (Tier: {settings.GEMINI_PRICING_TIER})")
            print(f"Nominal Commercial Cost:    ${batch_costs['nominal_cost_usd']:.5f}")
            if b_rep.get('success', 0) > 0:
                cost_per_1k = round((batch_costs['nominal_cost_usd'] / b_rep['success']) * 1000.0, 4)
                print(f"Nominal Cost / 1,000 Jobs:  ${cost_per_1k:.4f}")
        print("=" * 75)

        # Print cost telemetry
        cost_stats = get_cost_summary(db)
        print("CUMULATIVE TELEMETRY & COST METRICS:")
        print(f"  Total Prompt Tokens:       {cost_stats['total_prompt_tokens']:,}")
        print(f"  Total Completion Tokens:   {cost_stats['total_completion_tokens']:,}")
        print(f"  Total Tokens Billed:       {cost_stats['total_tokens']:,}")
        print(f"  Actual Incurred Cost (USD):${cost_stats['total_actual_cost_usd']:.4f} (Tier: {cost_stats['pricing_tier']})")
        print(f"  Nominal Baseline Cost (USD):${cost_stats['total_nominal_cost_usd']:.4f}")
        if cost_stats['nominal_cost_per_1000_posts_usd'] is not None:
            print(f"  Nominal Cost / 1,000 Posts:${cost_stats['nominal_cost_per_1000_posts_usd']:.4f}")
        print("=" * 75)

    finally:
        db.close()


if __name__ == "__main__":
    main()
