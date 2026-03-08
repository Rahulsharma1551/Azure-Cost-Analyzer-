from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlmodel.ext.asyncio.session import AsyncSession

from config import settings
from db.database import get_session
from db.operations import (
    get_daily_costs_by_range,
    get_monthly_costs_by_range,
    save_daily_costs,
    save_service_costs,
)
from models.cost_models import CostRecordRead
from services.cache_service import cost_cache, make_cache_key, ttl_for
from services.cost_preprocessor import (
    normalize_cost_response,
    preprocess_daily_costs,
    preprocess_service_costs,
)
from services.cost_service import (
    fetch_last_7_days_cost,
    fetch_month_to_date_cost_by_service,
)
from services.cost_tasks import fetch_process_save

router = APIRouter(prefix="/cost", tags=["cost"])


@router.get("/last-7-days")
async def get_last_7_days_cost():
    """Fetch daily cost for last 7 days from Azure, preprocess, and persist."""
    processed_records, billing_period_id, saved_count = await fetch_process_save(
        fetch_last_7_days_cost, preprocess_daily_costs, save_daily_costs
    )
    return {
        "status": "success",
        "billing_period_id": billing_period_id,
        "count": len(processed_records),
        "saved_to_db": saved_count,
        "data": [record.model_dump() for record in processed_records],
    }


@router.get("/month-to-date")
async def get_month_to_date_cost_by_service():
    """Fetch month-to-date costs by service from Azure, preprocess, and persist."""
    processed_records, billing_period_id, saved_count = await fetch_process_save(
        fetch_month_to_date_cost_by_service,
        preprocess_service_costs,
        save_service_costs,
    )
    return {
        "status": "success",
        "billing_period_id": billing_period_id,
        "count": len(processed_records),
        "saved_to_db": saved_count,
        "data": [record.model_dump() for record in processed_records],
    }


@router.get("/month-to-date/raw")
async def get_month_to_date_cost_raw():
    """Raw month-to-date costs without preprocessing (debug)."""
    raw_result = await fetch_month_to_date_cost_by_service()
    data = normalize_cost_response(raw_result)
    return {"status": "success", "data": data}


@router.get("/db")
async def get_cost_from_db(
    granularity: str = Query(
        default="daily",
        pattern="^(daily|monthly)$",
        description="'daily' reads daily_cost table; 'monthly' reads service_cost.",
    ),
    start_date: date | None = Query(
        default=None,
        description="Inclusive start date YYYY-MM-DD. Omit to use default window.",
    ),
    end_date: date | None = Query(
        default=None,
        description="Inclusive end date YYYY-MM-DD. Omit to use today.",
    ),
    session: AsyncSession = Depends(get_session),
):
    """
    Read cost data from the local database with optional date filtering.

    Date resolution
    ---------------
    granularity=daily,   no dates  -> last ALERT_HISTORY_DAYS days (default 30)
    granularity=monthly, no dates  -> last ALERT_HISTORY_MONTHS * 30 days (default 90)
    any custom dates               -> used exactly as provided

    Response includes cache_hit: true when served from the in-process TTL cache.
    """
    from loguru import logger

    today = date.today()

    resolved_end = end_date or today
    if start_date is None:
        if granularity == "daily":
            resolved_start = today - timedelta(days=settings.ALERT_HISTORY_DAYS)
        else:
            resolved_start = today - timedelta(days=settings.ALERT_HISTORY_MONTHS * 30)
    else:
        resolved_start = start_date

    cache_key = make_cache_key(
        granularity,
        resolved_start.isoformat(),
        resolved_end.isoformat(),
    )

    # Cache lookup — return immediately on hit
    cached = cost_cache.get(cache_key)
    if cached is not None:
        return cached

    # DB query
    if granularity == "daily":
        records: list[CostRecordRead] = await get_daily_costs_by_range(
            session, resolved_start, resolved_end
        )
    else:
        records = await get_monthly_costs_by_range(
            session, resolved_start, resolved_end
        )

    total_cost = round(sum(r.cost for r in records), 2)
    currency = records[0].currency if records else "INR"

    response = {
        "status": "success",
        "granularity": granularity,
        "start_date": resolved_start.isoformat(),
        "end_date": resolved_end.isoformat(),
        "count": len(records),
        "total_cost": total_cost,
        "currency": currency,
        "cache_hit": False,
        "data": [r.model_dump() for r in records],
    }

    # Store a version with cache_hit=True for subsequent requests
    cost_cache.set(cache_key, {**response, "cache_hit": True}, ttl=ttl_for(granularity))

    if settings.show_debug_info:
        logger.debug(
            f"DB query: granularity={granularity} "
            f"range={resolved_start}->{resolved_end} "
            f"rows={len(records)}"
        )

    return response
