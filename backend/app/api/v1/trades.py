from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.trade import Trade
from app.schemas.trade import TradeOut
from app.services.portfolio_service import get_or_create_portfolio

router = APIRouter(tags=["trades"])


@router.get("/trades", response_model=list[TradeOut])
def get_trades(db: Session = Depends(get_db), limit: int = Query(50, ge=1, le=500)) -> list[TradeOut]:
    # Scoped to the daily portfolio (this endpoint's historical behavior,
    # from before the intraday portfolio existed). Intraday trades are
    # listed separately at GET /intraday/trades.
    portfolio = get_or_create_portfolio(db)
    db.commit()
    trades = db.execute(
        select(Trade).where(Trade.portfolio_id == portfolio.id).order_by(Trade.timestamp.desc()).limit(limit)
    ).scalars().all()
    return [TradeOut.model_validate(t) for t in trades]
