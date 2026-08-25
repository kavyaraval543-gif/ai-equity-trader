from pydantic import BaseModel

from app.models.enums import ExitReason, RiskDecisionType
from app.strategies.base import StrategySignal


class RiskDecisionResult(BaseModel):
    """The risk engine's verdict on a single signal.

    `signal` is embedded so the execution provider can verify the decision
    it was handed actually corresponds to the signal it's about to execute,
    rather than trusting a bare APPROVED/REJECTED string.
    """

    signal: StrategySignal
    decision: RiskDecisionType
    reason: str
    approved_quantity: int | None = None
    # Set for SELL signals originating from the position monitor (stop-loss,
    # target, trailing stop, session-end) so the resulting Trade can record why.
    exit_reason: ExitReason | None = None
