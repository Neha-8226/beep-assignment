"""Token Accounting & Cost Tracking Telemetry.

Clearly separates:
1. Actual cost incurred (e.g. $0.00 for free tier).
2. Nominal commercial baseline cost calculated from published input/output rates.
"""
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.config import settings
from app.models import LLMAuditLog


def calculate_batch_costs(
    prompt_tokens: int,
    completion_tokens: int,
    pricing_tier: Optional[str] = None,
    input_price_per_1m: Optional[float] = None,
    output_price_per_1m: Optional[float] = None
) -> Dict[str, float]:
    """Calculate actual and nominal costs from token counts.

    Returns:
        Dict with:
        - nominal_cost_usd: calculated standard commercial cost
        - actual_cost_usd: $0.00 if tier is 'free', else nominal_cost_usd
    """
    tier = (pricing_tier or settings.GEMINI_PRICING_TIER).lower().strip()
    p_in = input_price_per_1m if input_price_per_1m is not None else settings.GEMINI_INPUT_PRICE_PER_1M
    p_out = output_price_per_1m if output_price_per_1m is not None else settings.GEMINI_OUTPUT_PRICE_PER_1M

    nominal_cost = ((prompt_tokens / 1_000_000.0) * p_in) + ((completion_tokens / 1_000_000.0) * p_out)
    nominal_cost = round(nominal_cost, 6)

    if tier == "free":
        actual_cost = 0.0
    else:
        actual_cost = nominal_cost

    return {
        "nominal_cost_usd": nominal_cost,
        "actual_cost_usd": actual_cost,
        "input_price_per_1m": p_in,
        "output_price_per_1m": p_out,
        "pricing_tier": tier
    }


def record_llm_audit_log(
    db: Session,
    batch_id: str,
    model_name: str,
    jobs_count: int,
    prompt_tokens: int,
    completion_tokens: int,
    latency_seconds: float,
    status: str = "success",
    error_message: Optional[str] = None
) -> LLMAuditLog:
    """Record LLM execution telemetry into llm_audit_logs table."""
    costs = calculate_batch_costs(prompt_tokens, completion_tokens)
    total_tokens = prompt_tokens + completion_tokens

    audit_entry = LLMAuditLog(
        batch_id=batch_id,
        jobs_count=jobs_count,
        status=status,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        model_name=model_name,
        latency_seconds=round(latency_seconds, 2),
        pricing_tier=costs["pricing_tier"],
        input_price_per_1m=costs["input_price_per_1m"],
        output_price_per_1m=costs["output_price_per_1m"],
        actual_cost_usd=costs["actual_cost_usd"],
        nominal_cost_usd=costs["nominal_cost_usd"],
        error_message=error_message
    )
    db.add(audit_entry)
    db.commit()
    db.refresh(audit_entry)
    return audit_entry


def get_cost_summary(db: Session) -> Dict[str, Any]:
    """Compute aggregate token consumption, actual expenditure, and nominal cost per 1k posts."""
    total_logs = db.query(LLMAuditLog).count()
    if total_logs == 0:
        return {
            "total_batches": 0,
            "total_jobs_processed": 0,
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
            "total_tokens": 0,
            "total_actual_cost_usd": 0.0,
            "total_nominal_cost_usd": 0.0,
            "nominal_cost_per_1000_posts_usd": None,
            "pricing_tier": settings.GEMINI_PRICING_TIER
        }

    agg = db.query(
        func.sum(LLMAuditLog.jobs_count),
        func.sum(LLMAuditLog.prompt_tokens),
        func.sum(LLMAuditLog.completion_tokens),
        func.sum(LLMAuditLog.total_tokens),
        func.sum(LLMAuditLog.actual_cost_usd),
        func.sum(LLMAuditLog.nominal_cost_usd)
    ).filter(LLMAuditLog.status == "success").first()

    jobs_cnt = agg[0] or 0
    prompt_tokens = agg[1] or 0
    comp_tokens = agg[2] or 0
    total_tokens = agg[3] or 0
    actual_cost = float(agg[4] or 0.0)
    nominal_cost = float(agg[5] or 0.0)

    nominal_per_1k = None
    if jobs_cnt > 0 and (prompt_tokens > 0 or comp_tokens > 0):
        nominal_per_1k = round((nominal_cost / jobs_cnt) * 1000.0, 4)

    return {
        "total_batches": total_logs,
        "total_jobs_processed": jobs_cnt,
        "total_prompt_tokens": prompt_tokens,
        "total_completion_tokens": comp_tokens,
        "total_tokens": total_tokens,
        "total_actual_cost_usd": round(actual_cost, 4),
        "total_nominal_cost_usd": round(nominal_cost, 4),
        "nominal_cost_per_1000_posts_usd": nominal_per_1k,
        "pricing_tier": settings.GEMINI_PRICING_TIER
    }
