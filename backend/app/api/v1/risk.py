from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.risk_decision import RiskDecision
from app.schemas.risk import RiskDecisionOut

router = APIRouter(tags=["risk"])


@router.get("/risk/decisions", response_model=list[RiskDecisionOut])
def get_risk_decisions(db: Session = Depends(get_db), limit: int = Query(50, ge=1, le=500)) -> list[RiskDecisionOut]:
    decisions = db.execute(
        select(RiskDecision).order_by(RiskDecision.timestamp.desc()).limit(limit)
    ).scalars().all()
    return [RiskDecisionOut.model_validate(d) for d in decisions]
