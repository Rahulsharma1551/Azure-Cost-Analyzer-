"""Alert evaluation engine — incident-based with cooldown-controlled notifications."""

import asyncio
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from math import isfinite, sqrt

from loguru import logger
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from config import settings
from db.alert_operations import (
    create_anomaly_log,
    get_anomaly_settings,
    get_daily_cost_history,
    get_monthly_cost_history,
    get_open_incident,
    is_cooldown_elapsed,
    open_incident,
    record_notification,
    resolve_incident,
    update_incident_cost,
    get_thresholds,
)
from db.models import (
    AlertEvent,
    AzureService,
    BillingPeriod,
    DailyCost,
    PeriodType,
    ServiceCost,
)
from exceptions.cost_exceptions import AlertError
from models.alert_models import AlertEvaluationSummary, AlertEventRead
from services.email_service import _email_executor, _send_alert_email_sync


#  Statistical helpers


def _mean(values: list[Decimal]) -> float:
    if not values:
        return 0.0
    return float(sum(values)) / len(values)


def _std(values: list[Decimal], mean: float) -> float:
    if len(values) < 2:
        return 0.0
    variance = sum((float(v) - mean) ** 2 for v in values) / len(values)
    return sqrt(variance) if isfinite(variance) else 0.0


def _to_decimal2(value: float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


#  Cost fetching helpers


async def _get_current_billing_period_id(session: AsyncSession) -> int | None:
    try:
        result = await session.exec(
            select(BillingPeriod)
            .where(col(BillingPeriod.is_current).is_(True))
            .limit(1)
        )
        bp = result.first()
        return bp.id if bp else None
    except Exception as exc:
        msg = f"Failed to query current billing period: {exc}"
        logger.error(
            msg
            if settings.show_debug_info
            else "Failed to query current billing period."
        )
        raise AlertError(
            msg
            if not settings.is_production
            else "Failed to query current billing period."
        ) from exc


async def _get_latest_daily_cost(
    session: AsyncSession, service_id: int
) -> tuple[date, Decimal] | None:
    try:
        result = await session.exec(
            select(DailyCost)
            .where(
                DailyCost.service_id == service_id,
                DailyCost.usage_date < date.today(),
            )
            .order_by(col(DailyCost.usage_date).desc())
            .limit(1)
        )
        row = result.first()
        return (row.usage_date, row.cost_amount) if row else None
    except Exception as exc:
        msg = f"Failed to query latest daily cost for service_id={service_id}: {exc}"
        logger.error(
            msg
            if settings.show_debug_info
            else f"Failed to query daily cost for service_id={service_id}."
        )
        raise AlertError(
            msg if not settings.is_production else "Failed to query daily cost data."
        ) from exc


async def _get_current_monthly_cost(
    session: AsyncSession, service_id: int, billing_period_id: int
) -> Decimal | None:
    try:
        result = await session.exec(
            select(ServiceCost).where(
                ServiceCost.service_id == service_id,
                ServiceCost.billing_period_id == billing_period_id,
            )
        )
        row = result.first()
        return row.cost_amount if row else None
    except Exception as exc:
        msg = f"Failed to query monthly cost for service_id={service_id}: {exc}"
        logger.error(
            msg
            if settings.show_debug_info
            else f"Failed to query monthly cost for service_id={service_id}."
        )
        raise AlertError(
            msg if not settings.is_production else "Failed to query monthly cost data."
        ) from exc


# Threshold computation


def _compute_components(
    history: list[Decimal],
    absolute_threshold: Decimal | None,
    k: float,
    pct_buffer: float,
) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
    absolute_component = absolute_threshold
    if len(history) < 2:
        return absolute_component, None, None
    mu = _mean(history)
    sigma = _std(history, mu)
    statistical_component = _to_decimal2(mu + k * sigma)
    percentage_component = _to_decimal2(mu * pct_buffer)
    return absolute_component, statistical_component, percentage_component


def _effective_threshold(
    absolute_component: Decimal | None,
    statistical_component: Decimal | None,
    percentage_component: Decimal | None,
) -> tuple[Decimal, str] | None:
    candidates: dict[str, Decimal] = {}
    if absolute_component is not None:
        candidates["absolute"] = absolute_component
    if statistical_component is not None:
        candidates["statistical"] = statistical_component
    if percentage_component is not None:
        candidates["percentage"] = percentage_component
    if not candidates:
        return None
    winner = max(candidates, key=lambda k: candidates[k])
    return candidates[winner], winner


async def evaluate_thresholds(
    session: AsyncSession,
    period_type: PeriodType,
) -> AlertEvaluationSummary:
    """Evaluate all active thresholds for the given period type.

    For each threshold:
      1. Fetch current cost.
      2. Compute effective threshold from history.
      3a. No breach + open incident → resolve incident.
      3b. Breach + no open incident → open new incident + send email.
      3c. Breach + open incident → update cost fields on incident.
              If cooldown elapsed → send reminder email.
              If cooldown not elapsed → skip email silently.
      4. Write anomaly_log entry for every evaluation.

    Returns AlertEvaluationSummary.
    """
    anomaly_cfg = await get_anomaly_settings(session)
    k = anomaly_cfg.k_value
    pct_buffer = anomaly_cfg.percentage_buffer
    global_cooldown = anomaly_cfg.cooldown_minutes

    thresholds = await get_thresholds(
        session, period_type=period_type, active_only=True
    )

    evaluated = 0
    new_incidents = 0
    ongoing_incidents = 0
    resolved_incidents = 0
    notifications_sent = 0
    skipped_no_cost = 0
    skipped_cooldown = 0
    newly_opened: list[AlertEvent] = []
    reminder_events: list[AlertEvent] = []

    current_bp_id: int | None = None
    if period_type == PeriodType.MONTHLY:
        current_bp_id = await _get_current_billing_period_id(session)
        if current_bp_id is None:
            logger.warning(
                "evaluate_thresholds(MONTHLY): no current billing period found, skipping."
            )
            return AlertEvaluationSummary(
                evaluated=0,
                new_incidents=0,
                ongoing_incidents=0,
                resolved_incidents=0,
                notifications_sent=0,
                skipped_no_cost=len(thresholds),
                skipped_cooldown=0,
                new_alerts=[],
            )

    for threshold in thresholds:
        evaluated += 1
        service_id = threshold.service_id

        try:
            # 1. Fetch current cost
            if period_type == PeriodType.DAILY:
                daily_result = await _get_latest_daily_cost(session, service_id)
                if daily_result is None:
                    logger.debug(
                        f"No daily cost data for service_id={service_id}, skipping."
                    )
                    skipped_no_cost += 1
                    continue
                ref_date, current_cost = daily_result
            else:
                assert current_bp_id is not None
                current_cost = await _get_current_monthly_cost(
                    session, service_id, current_bp_id
                )
                if current_cost is None:
                    logger.debug(
                        f"No monthly cost data for service_id={service_id}, skipping."
                    )
                    skipped_no_cost += 1
                    continue
                bp_result = await session.get(BillingPeriod, current_bp_id)
                ref_date = (
                    bp_result.start_date.date()
                    if bp_result
                    else date.today().replace(day=1)
                )

            # 2. Fetch history and compute threshold
            if period_type == PeriodType.DAILY:
                since_date = date.today() - timedelta(
                    days=anomaly_cfg.alert_history_days
                )
                history = await get_daily_cost_history(session, service_id, since_date)
            else:
                assert current_bp_id is not None
                history = await get_monthly_cost_history(
                    session,
                    service_id,
                    exclude_billing_period_id=current_bp_id,
                    limit=anomaly_cfg.alert_history_months,
                )

            absolute_component, statistical_component, percentage_component = (
                _compute_components(
                    history, threshold.absolute_threshold, k, pct_buffer
                )
            )
            effective = _effective_threshold(
                absolute_component, statistical_component, percentage_component
            )
            if effective is None:
                logger.debug(
                    f"service_id={service_id}: no computable threshold, skipping."
                )
                skipped_no_cost += 1
                continue

            computed_threshold, winning_component = effective

            # 3. Resolve service name
            service_obj = await session.get(AzureService, service_id)
            service_name = (
                service_obj.name if service_obj else f"service_id={service_id}"
            )

            # 4. Existing open incident?
            existing = await get_open_incident(session, service_id, period_type)

            if current_cost <= computed_threshold:
                # No breach
                if existing is not None:
                    # Cost came back down — auto-resolve
                    await resolve_incident(session, existing)
                    resolved_incidents += 1
                    logger.info(
                        f"RESOLVED — service_id={service_id} incident_id={existing.id} "
                        f"cost={current_cost} is now <= threshold={computed_threshold}"
                    )

                await create_anomaly_log(
                    session,
                    service_id=service_id,
                    service_name=service_name,
                    period_type=period_type,
                    reference_date=ref_date,
                    current_cost=current_cost,
                    absolute_component=absolute_component,
                    statistical_component=statistical_component,
                    percentage_component=percentage_component,
                    computed_threshold=computed_threshold,
                    winning_component=winning_component,
                    is_alert_fired=False,
                    alert_event_id=existing.id if existing else None,
                )
                continue

            # Breach
            if existing is None:
                # Fresh breach — open new incident
                effective_cooldown = global_cooldown
                logger.warning(
                    f"NEW BREACH — service_id={service_id} period={period_type.value} "
                    f"cost={current_cost} > threshold={computed_threshold} "
                    f"(rule={winning_component}) cooldown={effective_cooldown}m"
                )
                incident = await open_incident(
                    session,
                    threshold_id=threshold.id,  # type: ignore[arg-type]
                    service_id=service_id,
                    period_type=period_type,
                    reference_date=ref_date,
                    current_cost=current_cost,
                    computed_threshold=computed_threshold,
                    absolute_component=absolute_component,
                    statistical_component=statistical_component,
                    percentage_component=percentage_component,
                    winning_component=winning_component,
                    cooldown_minutes=effective_cooldown,
                )
                new_incidents += 1
                notifications_sent += 1
                newly_opened.append(incident)

            else:
                # Ongoing breach — update cost fields on existing incident
                ongoing_incidents += 1
                incident = await update_incident_cost(
                    session,
                    existing,
                    current_cost=current_cost,
                    computed_threshold=computed_threshold,
                    absolute_component=absolute_component,
                    statistical_component=statistical_component,
                    percentage_component=percentage_component,
                    winning_component=winning_component,
                    reference_date=ref_date,
                )

                if is_cooldown_elapsed(incident):
                    # Cooldown elapsed — send reminder
                    incident = await record_notification(session, incident)
                    notifications_sent += 1
                    reminder_events.append(incident)
                    logger.info(
                        f"REMINDER — service_id={service_id} incident_id={incident.id} "
                        f"notification #{incident.notification_count} "
                        f"cost={current_cost} threshold={computed_threshold}"
                    )
                else:
                    skipped_cooldown += 1
                    logger.debug(
                        f"COOLDOWN — service_id={service_id} incident_id={incident.id} "
                        f"skipping email, cooldown not elapsed."
                    )

            await create_anomaly_log(
                session,
                service_id=service_id,
                service_name=service_name,
                period_type=period_type,
                reference_date=ref_date,
                current_cost=current_cost,
                absolute_component=absolute_component,
                statistical_component=statistical_component,
                percentage_component=percentage_component,
                computed_threshold=computed_threshold,
                winning_component=winning_component,
                is_alert_fired=True,
                alert_event_id=incident.id,
            )

        except AlertError:
            logger.warning(
                f"Skipping threshold_id={threshold.id} service_id={service_id} "
                "due to alert query error."
            )
            skipped_no_cost += 1
        except Exception as exc:
            err_detail = f": {exc}" if settings.show_debug_info else "."
            logger.error(
                f"Unexpected error evaluating threshold_id={threshold.id} "
                f"service_id={service_id}{err_detail}"
            )
            skipped_no_cost += 1

    # Email dispatch
    receiver = anomaly_cfg.receiver_email
    email_ok = settings.ALERT_EMAIL_ENABLED and anomaly_cfg.email_enabled and receiver

    all_to_notify = newly_opened + reminder_events
    if all_to_notify and email_ok:
        try:
            await asyncio.get_running_loop().run_in_executor(
                _email_executor,
                _send_alert_email_sync,
                all_to_notify,
                receiver,
            )
        except Exception as exc:
            err_detail = f": {exc}" if settings.show_debug_info else "."
            logger.error(f"Failed to send alert email{err_detail}")

    logger.info(
        f"Evaluation complete — period={period_type.value} evaluated={evaluated} "
        f"new={new_incidents} ongoing={ongoing_incidents} resolved={resolved_incidents} "
        f"notifications={notifications_sent} cooldown_skipped={skipped_cooldown}"
    )

    return AlertEvaluationSummary(
        evaluated=evaluated,
        new_incidents=new_incidents,
        ongoing_incidents=ongoing_incidents,
        resolved_incidents=resolved_incidents,
        notifications_sent=notifications_sent,
        skipped_no_cost=skipped_no_cost,
        skipped_cooldown=skipped_cooldown,
        new_alerts=[_event_to_read(e) for e in newly_opened],
    )


def _event_to_read(event: AlertEvent) -> AlertEventRead:
    assert event.id is not None
    try:
        service_name = event.service.name
    except Exception:
        service_name = f"service_id={event.service_id}"

    return AlertEventRead(
        id=event.id,
        threshold_id=event.threshold_id,
        service_id=event.service_id,
        service_name=service_name,
        period_type=event.period_type,
        reference_date=event.reference_date,
        current_cost=event.current_cost,
        computed_threshold=event.computed_threshold,
        absolute_component=event.absolute_component,
        statistical_component=event.statistical_component,
        percentage_component=event.percentage_component,
        winning_component=event.winning_component,
        status=event.status,
        breach_started_at=event.breach_started_at,
        breach_resolved_at=event.breach_resolved_at,
        acknowledged_at=event.acknowledged_at,
        last_notified_at=event.last_notified_at,
        notification_count=event.notification_count,
        cooldown_minutes=event.cooldown_minutes,
    )
