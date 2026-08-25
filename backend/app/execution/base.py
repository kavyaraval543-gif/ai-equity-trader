"""Execution provider abstraction.

The ONLY way to create a trade in this system is through
`execute_approved_signal`, and its signature requires a `RiskDecisionResult`
— not a bare signal. There is no alternate method that accepts just a
signal, so no code path can execute a trade without having gone through
`RiskEngine.evaluate` first.
"""
from abc import ABC, abstractmethod

from sqlalchemy.orm import Session

from app.models.portfolio import Portfolio
from app.models.trade import Trade
from app.risk.schemas import RiskDecisionResult


class ExecutionProvider(ABC):
    @abstractmethod
    def execute_approved_signal(
        self,
        db: Session,
        risk_decision: RiskDecisionResult,
        portfolio: Portfolio,
    ) -> Trade:
        """Execute a trade for an APPROVED risk decision.

        Must raise (never silently no-op or approve-itself) if
        `risk_decision.decision` is not APPROVED.
        """

    @abstractmethod
    def update_position_prices(self, db: Session, price_lookup: dict[str, float], portfolio_id: int | None = None) -> None:
        """Mark open positions to the latest real market prices.

        `portfolio_id=None` marks to market across every portfolio holding
        that symbol (used only where no single portfolio is in scope);
        callers that already have a specific portfolio in hand should pass
        its id so a price fetched for one portfolio's cycle never touches
        another portfolio's position in the same symbol.
        """
