from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.signal import Signal
from app.schemas.signal import SignalOut

router = APIRouter(tags=["signals"])


@router.get("/signals", response_model=list[SignalOut])
def get_signals(db: Session = Depends(get_db), limit: int = Query(50, ge=1, le=500)) -> list[SignalOut]:
    signals = db.execute(select(Signal).order_by(Signal.timestamp.desc()).limit(limit)).scalars().all()
    return [SignalOut.model_validate(s) for s in signals]
