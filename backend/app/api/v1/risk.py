from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.risk_decision import RiskDecision
from app.models.signal import Signal
from app.schemas.risk import RiskDecisionOut

router = APIRouter(tags=["risk"])


@router.get("/risk/decisions", response_model=list[RiskDecisionOut])
def get_risk_decisions(
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=500),
    strategy_name: str | None = Query(
        None, description="Filter to decisions on one strategy's signals — e.g. SMA_CROSSOVER or INTRADAY_VWAP_MOMENTUM."
    ),
) -> list[RiskDecisionOut]:
    # RiskDecision has no strategy_name of its own (or a portfolio_id) —
    # it only points at the Signal it was decided for — so filtering by
    # strategy requires joining through Signal, same reasoning as /signals.
    query = select(RiskDecision).order_by(RiskDecision.timestamp.desc()).limit(limit)
    if strategy_name is not None:
        query = (
            select(RiskDecision)
            .join(Signal, RiskDecision.signal_id == Signal.id)
            .where(Signal.strategy_name == strategy_name)
            .order_by(RiskDecision.timestamp.desc())
            .limit(limit)
        )
    decisions = db.execute(query).scalars().all()
    return [RiskDecisionOut.model_validate(d) for d in decisions]
