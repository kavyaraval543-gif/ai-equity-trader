"""Intraday research API. Entirely separate router/prefix from the daily
`/trading` and `/backtests` endpoints — mirrors their shape so the frontend
pattern is familiar, but every read/write here is scoped to the INTRADAY
portfolio and the intraday-specific settings/services built in Phase 5.

Nothing in this file ever touches the daily portfolio, the daily
`AutonomousTradingState`, or the daily `TradingScheduler`.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.backtesting.intraday_engine import IntradayBacktestEngine
from app.backtesting.intraday_results import IntradayBacktestResult
from app.core.config import Settings, get_settings
from app.database.session import get_db
from app.market_data.base import MarketDataError
from app.models.backtest import BacktestRun, BacktestTrade
from app.models.enums import PortfolioKind, PositionStatus
from app.models.position import Position
from app.risk.intraday_rules import is_in_cooldown, is_max_consecutive_losses_reached
from app.scheduler.intraday_scheduler import intraday_scheduler
from app.scheduler.runners import run_guarded_intraday_cycle
from app.schemas.intraday import (
    IntradayAutonomousStatusOut,
    IntradayBacktestCreate,
    IntradayBacktestRunOut,
    IntradayExitConfigOut,
    IntradayRiskConfigOut,
    IntradayRunCycleResult,
    IntradayScanResultOut,
    IntradayTradingStatusOut,
)
from app.schemas.market_session import MarketSessionOut
from app.schemas.portfolio import PortfolioOut, PositionOut
from app.schemas.trade import TradeOut
from app.services import intraday_control_service
from app.services.intraday_scanner import IntradayScanner
from app.services.intraday_stats import get_daily_stats
from app.services.market_session_service import MarketSessionService
from app.services.portfolio_service import get_or_create_portfolio
from app.models.trade import Trade

router = APIRouter(prefix="/intraday", tags=["intraday"])


def _open_position_count(db: Session, portfolio_id: int) -> int:
    return db.execute(
        select(func.count(Position.id)).where(
            Position.portfolio_id == portfolio_id, Position.status == PositionStatus.OPEN
        )
    ).scalar_one()


def _autonomous_status(db: Session, settings: Settings) -> IntradayAutonomousStatusOut:
    portfolio = get_or_create_portfolio(db, settings, kind=PortfolioKind.INTRADAY)
    state = intraday_control_service.get_or_create_state(db, settings)
    stats = get_daily_stats(db, portfolio, settings)
    db.commit()

    now_ist = MarketSessionService(settings).now()
    return IntradayAutonomousStatusOut(
        state=state.state,
        reason=state.reason,
        updated_at=state.updated_at,
        emergency_stop=settings.emergency_stop,
        scheduler_running=intraday_scheduler.is_running,
        cycle_interval_seconds=settings.intraday_cycle_interval_seconds,
        position_monitor_interval_seconds=settings.intraday_position_monitor_interval_seconds,
        last_successful_cycle_at=intraday_scheduler.last_successful_cycle_at,
        last_failed_cycle_at=intraday_scheduler.last_failed_cycle_at,
        last_error=intraday_scheduler.last_error,
        last_skip_reason=intraday_scheduler.last_skip_reason,
        last_monitor_run_at=intraday_scheduler.last_monitor_run_at,
        last_monitor_error=intraday_scheduler.last_monitor_error,
        open_position_count=_open_position_count(db, portfolio.id),
        trades_today=stats.trades_today,
        max_trades_per_day=settings.intraday_risk_max_trades_per_day,
        realized_pnl_today=stats.realized_pnl_today,
        max_daily_loss_pct=settings.intraday_risk_max_daily_loss_pct,
        consecutive_losses=stats.consecutive_losses,
        max_consecutive_losses=settings.intraday_risk_max_consecutive_losses,
        in_cooldown=(
            is_max_consecutive_losses_reached(stats.consecutive_losses, settings.intraday_risk_max_consecutive_losses)
            or is_in_cooldown(now_ist, stats.last_loss_at, settings.intraday_risk_cooldown_minutes)
        ),
    )


# --- scanner (read-only, never executes) ---


@router.get("/scan", response_model=list[IntradayScanResultOut])
def scan_intraday_universe(settings: Settings = Depends(get_settings)) -> list[IntradayScanResultOut]:
    scanner = IntradayScanner(settings)
    results = []
    for scan in scanner.scan_all():
        if scan.signal is not None:
            results.append(
                IntradayScanResultOut(
                    symbol=scan.symbol,
                    signal_type=scan.signal.signal_type,
                    confidence=scan.signal.confidence,
                    reason=scan.signal.reason,
                    indicator_data=scan.signal.indicator_data,
                    market_price=scan.latest_price,
                    latest_bar_time=scan.latest_bar_time,
                    is_stale=scan.is_stale,
                )
            )
        else:
            results.append(IntradayScanResultOut(symbol=scan.symbol, is_stale=scan.is_stale, error=scan.error))
    return results


# --- status / positions / trades ---


@router.get("/status", response_model=IntradayTradingStatusOut)
def get_intraday_status(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> IntradayTradingStatusOut:
    portfolio = get_or_create_portfolio(db, settings, kind=PortfolioKind.INTRADAY)
    db.commit()

    market_session = MarketSessionService(settings).describe()

    return IntradayTradingStatusOut(
        trading_mode=settings.trading_mode,
        emergency_stop=settings.emergency_stop,
        strategy_names=["INTRADAY_VWAP_MOMENTUM"],
        market_data_provider=settings.market_data_provider,
        symbols=settings.intraday_symbols,
        interval=settings.intraday_timeframe,
        portfolio=PortfolioOut.model_validate(portfolio),
        open_position_count=_open_position_count(db, portfolio.id),
        autonomous=_autonomous_status(db, settings),
        market_session=MarketSessionOut(**market_session),
        exit_config=IntradayExitConfigOut(
            stop_loss_percent=settings.intraday_stop_loss_percent,
            target_percent=settings.intraday_target_percent,
            trailing_stop_enabled=settings.intraday_trailing_stop_enabled,
            trailing_stop_percent=settings.intraday_trailing_stop_percent,
            max_holding_minutes=settings.intraday_max_holding_minutes,
            force_close_at_session_end=settings.intraday_force_close_at_session_end,
        ),
        risk_config=IntradayRiskConfigOut(
            max_trades_per_day=settings.intraday_risk_max_trades_per_day,
            max_simultaneous_positions=settings.intraday_risk_max_simultaneous_positions,
            max_capital_per_trade_pct=settings.intraday_risk_max_capital_per_trade_pct,
            max_daily_loss_pct=settings.intraday_risk_max_daily_loss_pct,
            max_consecutive_losses=settings.intraday_risk_max_consecutive_losses,
            cooldown_minutes=settings.intraday_risk_cooldown_minutes,
            no_entry_minutes_before_close=settings.intraday_no_entry_minutes_before_close,
        ),
    )


@router.get("/positions", response_model=list[PositionOut])
def get_intraday_positions(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> list[PositionOut]:
    portfolio = get_or_create_portfolio(db, settings, kind=PortfolioKind.INTRADAY)
    db.commit()
    positions = db.execute(
        select(Position)
        .where(Position.portfolio_id == portfolio.id, Position.status == PositionStatus.OPEN)
        .order_by(Position.opened_at.desc())
    ).scalars().all()
    return [PositionOut.model_validate(p) for p in positions]


@router.get("/trades", response_model=list[TradeOut])
def get_intraday_trades(
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings), limit: int = Query(50, ge=1, le=500)
) -> list[TradeOut]:
    portfolio = get_or_create_portfolio(db, settings, kind=PortfolioKind.INTRADAY)
    db.commit()
    trades = db.execute(
        select(Trade).where(Trade.portfolio_id == portfolio.id).order_by(Trade.timestamp.desc()).limit(limit)
    ).scalars().all()
    return [TradeOut.model_validate(t) for t in trades]


# --- manual cycle + autonomous control ---


@router.post("/run-cycle", response_model=IntradayRunCycleResult)
def run_intraday_cycle(db: Session = Depends(get_db)) -> IntradayRunCycleResult:
    outcome = run_guarded_intraday_cycle(db)
    if not outcome.ran:
        raise HTTPException(status_code=409, detail=outcome.skipped_reason)
    return outcome.result


@router.get("/autonomous/status", response_model=IntradayAutonomousStatusOut)
def get_intraday_autonomous_status(
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings)
) -> IntradayAutonomousStatusOut:
    return _autonomous_status(db, settings)


@router.post("/autonomous/start", response_model=IntradayAutonomousStatusOut)
def start_intraday_autonomous_trading(
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings)
) -> IntradayAutonomousStatusOut:
    intraday_control_service.start(db, settings)
    return _autonomous_status(db, settings)


@router.post("/autonomous/pause", response_model=IntradayAutonomousStatusOut)
def pause_intraday_autonomous_trading(
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings)
) -> IntradayAutonomousStatusOut:
    intraday_control_service.pause(db)
    return _autonomous_status(db, settings)


@router.post("/autonomous/stop", response_model=IntradayAutonomousStatusOut)
def stop_intraday_autonomous_trading(
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings)
) -> IntradayAutonomousStatusOut:
    intraday_control_service.stop(db)
    return _autonomous_status(db, settings)


# --- backtesting ---


def _persist_intraday_backtest(
    db: Session, symbol: str, interval: str, start_date: date, end_date: date, result: IntradayBacktestResult
) -> BacktestRun:
    run = BacktestRun(
        symbol=result.symbol,
        interval=interval,
        start_date=start_date,
        end_date=end_date,
        starting_capital=result.starting_capital,
        ending_capital=result.ending_capital,
        total_return_pct=result.total_return_pct,
        total_trades=result.total_trades,
        winning_trades=result.winning_trades,
        losing_trades=result.losing_trades,
        win_rate=result.win_rate,
        max_drawdown_pct=result.max_drawdown_pct,
        buy_hold_return_pct=0.0,  # no buy & hold comparison for intraday research
        transaction_cost_percent=result.transaction_cost_percent,
        slippage_percent=result.slippage_percent,
        strategy_name=result.strategy_name,
        strategy_params=result.strategy_params,
    )
    db.add(run)
    db.flush()
    for t in result.trades:
        db.add(
            BacktestTrade(
                backtest_run_id=run.id,
                symbol=result.symbol,
                side=t.side,
                quantity=t.quantity,
                price=t.price,
                transaction_cost=t.transaction_cost,
                realized_pnl=t.realized_pnl,
                exit_reason=t.exit_reason,
                timestamp=t.timestamp,
            )
        )
    return run


@router.post("/backtests", response_model=IntradayBacktestRunOut, status_code=201)
def create_intraday_backtest(payload: IntradayBacktestCreate, db: Session = Depends(get_db)) -> IntradayBacktestRunOut:
    try:
        engine = IntradayBacktestEngine()
        result = engine.run(
            symbol=payload.symbol,
            interval=payload.interval,
            start_date=payload.start_date,
            end_date=payload.end_date,
            starting_capital=payload.starting_capital,
            transaction_cost_percent=payload.transaction_cost_percent,
            slippage_percent=payload.slippage_percent,
        )
    except MarketDataError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    run = _persist_intraday_backtest(db, payload.symbol, payload.interval, payload.start_date, payload.end_date, result)
    db.commit()
    db.refresh(run)

    return IntradayBacktestRunOut(
        id=run.id,
        symbol=result.symbol,
        interval=result.interval,
        start_date=payload.start_date,
        end_date=payload.end_date,
        starting_capital=result.starting_capital,
        ending_capital=result.ending_capital,
        total_pnl=result.total_pnl,
        total_return_pct=result.total_return_pct,
        total_trades=result.total_trades,
        winning_trades=result.winning_trades,
        losing_trades=result.losing_trades,
        win_rate=result.win_rate,
        avg_win=result.avg_win,
        avg_loss=result.avg_loss,
        profit_factor=result.profit_factor,
        max_drawdown_pct=result.max_drawdown_pct,
        longest_losing_streak=result.longest_losing_streak,
        trading_days=result.trading_days,
        trades_per_day=result.trades_per_day,
        transaction_cost_percent=result.transaction_cost_percent,
        slippage_percent=result.slippage_percent,
        strategy_name=result.strategy_name,
        strategy_params=result.strategy_params,
        created_at=run.created_at,
        trades=result.trades,
    )
