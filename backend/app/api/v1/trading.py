from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.database.session import get_db
from app.models.enums import PositionStatus
from app.models.position import Position
from app.scheduler.runners import run_guarded_entry_cycle
from app.scheduler.trading_scheduler import scheduler
from app.schemas.autonomous import AutonomousStatusOut
from app.schemas.market_session import MarketSessionOut
from app.schemas.portfolio import PortfolioOut
from app.schemas.trading import ExitConfigOut, RunCycleResult, TradingStatusOut
from app.services import autonomous_control_service
from app.services.market_session_service import MarketSessionService
from app.services.portfolio_service import get_or_create_portfolio

router = APIRouter(tags=["trading"])


def _open_position_count(db: Session, portfolio_id: int) -> int:
    return db.execute(
        select(func.count(Position.id)).where(
            Position.portfolio_id == portfolio_id, Position.status == PositionStatus.OPEN
        )
    ).scalar_one()


def _autonomous_status(db: Session, settings: Settings, portfolio_id: int) -> AutonomousStatusOut:
    state = autonomous_control_service.get_or_create_state(db, settings)
    db.commit()
    return AutonomousStatusOut(
        state=state.state,
        reason=state.reason,
        updated_at=state.updated_at,
        emergency_stop=settings.emergency_stop,
        scheduler_running=scheduler.is_running,
        trading_cycle_interval_seconds=settings.trading_cycle_interval_seconds,
        position_monitor_interval_seconds=settings.position_monitor_interval_seconds,
        last_successful_cycle_at=scheduler.last_successful_cycle_at,
        last_failed_cycle_at=scheduler.last_failed_cycle_at,
        last_error=scheduler.last_error,
        last_skip_reason=scheduler.last_skip_reason,
        last_monitor_run_at=scheduler.last_monitor_run_at,
        last_monitor_error=scheduler.last_monitor_error,
        open_position_count=_open_position_count(db, portfolio_id),
    )


@router.get("/trading/status", response_model=TradingStatusOut)
def get_trading_status(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> TradingStatusOut:
    portfolio = get_or_create_portfolio(db, settings)
    db.commit()

    market_session = MarketSessionService(settings).describe()

    return TradingStatusOut(
        trading_mode=settings.trading_mode,
        emergency_stop=settings.emergency_stop,
        strategy_names=["SMA_CROSSOVER"],
        market_data_provider=settings.market_data_provider,
        symbols=settings.market_data_symbols,
        portfolio=PortfolioOut.model_validate(portfolio),
        open_position_count=_open_position_count(db, portfolio.id),
        autonomous=_autonomous_status(db, settings, portfolio.id),
        market_session=MarketSessionOut(**market_session),
        exit_config=ExitConfigOut(
            stop_loss_percent=settings.stop_loss_percent,
            target_percent=settings.target_percent,
            trailing_stop_enabled=settings.trailing_stop_enabled,
            trailing_stop_percent=settings.trailing_stop_percent,
            force_close_at_session_end=settings.force_close_at_session_end,
        ),
    )


@router.post("/trading/run-cycle", response_model=RunCycleResult)
def run_trading_cycle(db: Session = Depends(get_db)) -> RunCycleResult:
    outcome = run_guarded_entry_cycle(db)
    if not outcome.ran:
        raise HTTPException(status_code=409, detail=outcome.skipped_reason)
    return outcome.result


@router.get("/trading/autonomous/status", response_model=AutonomousStatusOut)
def get_autonomous_status(
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings)
) -> AutonomousStatusOut:
    portfolio = get_or_create_portfolio(db, settings)
    db.commit()
    return _autonomous_status(db, settings, portfolio.id)


@router.post("/trading/autonomous/start", response_model=AutonomousStatusOut)
def start_autonomous_trading(
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings)
) -> AutonomousStatusOut:
    autonomous_control_service.start(db, settings)
    portfolio = get_or_create_portfolio(db, settings)
    db.commit()
    return _autonomous_status(db, settings, portfolio.id)


@router.post("/trading/autonomous/pause", response_model=AutonomousStatusOut)
def pause_autonomous_trading(
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings)
) -> AutonomousStatusOut:
    autonomous_control_service.pause(db)
    portfolio = get_or_create_portfolio(db, settings)
    db.commit()
    return _autonomous_status(db, settings, portfolio.id)


@router.post("/trading/autonomous/stop", response_model=AutonomousStatusOut)
def stop_autonomous_trading(
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings)
) -> AutonomousStatusOut:
    autonomous_control_service.stop(db)
    portfolio = get_or_create_portfolio(db, settings)
    db.commit()
    return _autonomous_status(db, settings, portfolio.id)
