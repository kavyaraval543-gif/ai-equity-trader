from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.signal import Signal
from app.schemas.signal import SignalOut

router = APIRouter(tags=["signals"])


@router.get("/signals", response_model=list[SignalOut])
def get_signals(
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=500),
    strategy_name: str | None = Query(
        None, description="Filter to one strategy — e.g. SMA_CROSSOVER (daily) or INTRADAY_VWAP_MOMENTUM (intraday)."
    ),
) -> list[SignalOut]:
    # Signal rows aren't portfolio-scoped (the daily and intraday traders
    # write into the same shared table), so this filter is what keeps the
    # daily dashboard's feed showing only its own strategy's signals now
    # that a second, independent strategy also generates them.
    conditions = [Signal.strategy_name == strategy_name] if strategy_name is not None else []
    signals = db.execute(
        select(Signal).where(*conditions).order_by(Signal.timestamp.desc()).limit(limit)
    ).scalars().all()
    return [SignalOut.model_validate(s) for s in signals]
