"""CLI Script to Execute Ground-Truth Evaluation.

Usage:
    python backend/scripts/run_evaluation.py
"""
import sys
import json
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.database import SessionLocal
from app.models import Job, GroundTruthEval
from app.ai.evaluator import evaluate_classifications, print_evaluation_report


def main():
    benchmark_file = backend_dir / "data" / "ground_truth_benchmark.json"
    if not benchmark_file.exists():
        print(f"[ERROR] Benchmark file not found at: {benchmark_file}")
        sys.exit(1)

    with open(benchmark_file, "r", encoding="utf-8") as f:
        ground_truth = json.load(f)

    db = SessionLocal()
    try:
        # Fetch current database records for the benchmark job IDs
        gt_ids = [item["job_id"] for item in ground_truth]
        jobs_in_db = db.query(Job).filter(Job.id.in_(gt_ids)).all()
        jobs_map = {j.id: j for j in jobs_in_db}

        model_predictions = []
        for item in ground_truth:
            jid = item["job_id"]
            if jid in jobs_map:
                j = jobs_map[jid]
                model_predictions.append({
                    "job_id": jid,
                    "model_role": j.role_category,
                    "model_city": j.standardized_city,
                    "model_fresher_status": j.fresher_eligibility_status or (
                        "fresher_friendly" if j.is_fresher_friendly is True else (
                            "not_fresher_friendly" if j.is_fresher_friendly is False else "uncertain"
                        )
                    )
                })
            else:
                model_predictions.append({
                    "job_id": jid,
                    "model_role": None,
                    "model_city": None,
                    "model_fresher_status": "uncertain"
                })

        metrics = evaluate_classifications(
            ground_truth_records=ground_truth,
            model_predictions=model_predictions
        )

        print_evaluation_report(metrics)

        # Seed or update ground_truth_evals table in database
        for item in ground_truth:
            jid = item["job_id"]
            existing = db.query(GroundTruthEval).filter(GroundTruthEval.job_id == jid).first()
            pred = next((p for p in model_predictions if p["job_id"] == jid), {})

            role_match = (item["human_role"].lower() == (pred.get("model_role") or "").lower())
            city_match = ((item.get("human_city") or "unknown").lower() == (pred.get("model_city") or "unknown").lower())
            fresher_match = (item.get("human_fresher_status") == pred.get("model_fresher_status"))

            if existing:
                existing.human_role_category = item["human_role"]
                existing.human_city = item.get("human_city")
                existing.human_fresher_status = item.get("human_fresher_status", "uncertain")
                existing.role_match = role_match
                existing.city_match = city_match
                existing.fresher_match = fresher_match
                existing.notes = item.get("notes")
            else:
                eval_row = GroundTruthEval(
                    job_id=jid,
                    human_role_category=item["human_role"],
                    human_city=item.get("human_city"),
                    human_fresher_status=item.get("human_fresher_status", "uncertain"),
                    role_match=role_match,
                    city_match=city_match,
                    fresher_match=fresher_match,
                    notes=item.get("notes")
                )
                db.add(eval_row)

        db.commit()
        print(f"\nPersisted {len(ground_truth)} benchmark evaluations to 'ground_truth_evals' table.")

    finally:
        db.close()


if __name__ == "__main__":
    main()
