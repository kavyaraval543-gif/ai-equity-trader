from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.enums import PositionStatus
from app.models.position import Position
from app.schemas.portfolio import PortfolioOut, PositionOut
from app.services.portfolio_service import get_or_create_portfolio

router = APIRouter(tags=["portfolio"])


@router.get("/portfolio", response_model=PortfolioOut)
def get_portfolio(db: Session = Depends(get_db)) -> PortfolioOut:
    portfolio = get_or_create_portfolio(db)
    db.commit()
    return PortfolioOut.model_validate(portfolio)


@router.get("/portfolio/positions", response_model=list[PositionOut])
def get_positions(db: Session = Depends(get_db)) -> list[PositionOut]:
    portfolio = get_or_create_portfolio(db)
    db.commit()
    positions = db.execute(
        select(Position)
        .where(Position.portfolio_id == portfolio.id, Position.status == PositionStatus.OPEN)
        .order_by(Position.opened_at.desc())
    ).scalars().all()
    return [PositionOut.model_validate(p) for p in positions]
