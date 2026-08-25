# Import every model so Base.metadata is fully populated for Alembic
# autogenerate and for anything that touches Base.metadata.create_all.
from app.models.autonomous_state import AutonomousState  # noqa: F401
from app.models.backtest import BacktestRun, BacktestTrade  # noqa: F401
from app.models.intraday_state import IntradayAutonomousState  # noqa: F401
from app.models.market_data_cache import MarketDataCache, PriceCandle  # noqa: F401
from app.models.portfolio import Portfolio  # noqa: F401
from app.models.position import Position  # noqa: F401
from app.models.risk_decision import RiskDecision  # noqa: F401
from app.models.signal import Signal  # noqa: F401
from app.models.system_event import SystemEvent  # noqa: F401
from app.models.trade import Trade  # noqa: F401
