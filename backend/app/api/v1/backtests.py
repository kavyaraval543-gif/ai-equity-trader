"""Backtesting API. Runs synchronously and persists results only into the
isolated backtest_runs/backtest_trades tables — never touches the live
portfolio/positions/trades. The comparison endpoints reuse the exact same
BacktestEngine trade-simulation logic as a single backtest; they do not
duplicate or bypass it.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.backtesting.comparison import run_comparison, run_multi_stock_comparison
from app.backtesting.engine import BacktestEngine
from app.backtesting.results import BacktestResult
from app.database.session import get_db
from app.market_data.base import MarketDataError
from app.market_data.symbols import DEFAULT_SYMBOLS
from app.models.backtest import BacktestRun, BacktestTrade
from app.schemas.backtest import (
    BacktestCreate,
    BacktestRunOut,
    BacktestTradeOut,
    CompareRequest,
    CompareResponse,
    MultiStockCompareRequest,
    MultiStockCompareResponse,
    MultiStockStrategyAverageOut,
    StrategyComparisonResultOut,
)
from app.strategies.factory import build_strategy

router = APIRouter(tags=["backtests"])


def _persist(db: Session, symbol: str, start_date: date, end_date: date, result: BacktestResult) -> BacktestRun:
    run = BacktestRun(
        symbol=result.symbol,
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
        buy_hold_return_pct=result.buy_hold_return_pct,
        transaction_cost_percent=result.transaction_cost_percent,
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
                timestamp=t.timestamp,
            )
        )
    return run


def _to_comparison_row(run: BacktestRun) -> StrategyComparisonResultOut:
    return StrategyComparisonResultOut(
        backtest_run_id=run.id,
        symbol=run.symbol,
        strategy_name=run.strategy_name,
        strategy_params=run.strategy_params,
        total_return_pct=run.total_return_pct,
        ending_capital=run.ending_capital,
        total_trades=run.total_trades,
        win_rate=run.win_rate,
        max_drawdown_pct=run.max_drawdown_pct,
        buy_hold_return_pct=run.buy_hold_return_pct,
    )


@router.post("/backtests", response_model=BacktestRunOut, status_code=201)
def create_backtest(payload: BacktestCreate, db: Session = Depends(get_db)) -> BacktestRunOut:
    try:
        strategy = build_strategy(payload.strategy, payload.strategy_params)
        engine = BacktestEngine(strategy=strategy)
        result = engine.run(
            symbol=payload.symbol,
            start_date=payload.start_date,
            end_date=payload.end_date,
            starting_capital=payload.starting_capital,
            transaction_cost_percent=payload.transaction_cost_percent,
        )
    except MarketDataError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    run = _persist(db, payload.symbol, payload.start_date, payload.end_date, result)
    db.commit()
    db.refresh(run)
    return BacktestRunOut.model_validate(run)


@router.get("/backtests", response_model=list[BacktestRunOut])
def list_backtests(db: Session = Depends(get_db), limit: int = Query(50, ge=1, le=500)) -> list[BacktestRunOut]:
    runs = db.execute(select(BacktestRun).order_by(BacktestRun.created_at.desc()).limit(limit)).scalars().all()
    return [BacktestRunOut.model_validate(r) for r in runs]


@router.get("/backtests/{backtest_id}", response_model=BacktestRunOut)
def get_backtest(backtest_id: int, db: Session = Depends(get_db)) -> BacktestRunOut:
    run = db.get(BacktestRun, backtest_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Backtest not found")
    return BacktestRunOut.model_validate(run)


@router.get("/backtests/{backtest_id}/trades", response_model=list[BacktestTradeOut])
def get_backtest_trades(backtest_id: int, db: Session = Depends(get_db)) -> list[BacktestTradeOut]:
    run = db.get(BacktestRun, backtest_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Backtest not found")
    trades = db.execute(
        select(BacktestTrade).where(BacktestTrade.backtest_run_id == backtest_id).order_by(BacktestTrade.timestamp.asc())
    ).scalars().all()
    return [BacktestTradeOut.model_validate(t) for t in trades]


@router.post("/backtests/compare", response_model=CompareResponse)
def compare_strategies(payload: CompareRequest, db: Session = Depends(get_db)) -> CompareResponse:
    try:
        results = run_comparison(
            symbol=payload.symbol,
            start_date=payload.start_date,
            end_date=payload.end_date,
            starting_capital=payload.starting_capital,
            transaction_cost_percent=payload.transaction_cost_percent,
        )
    except MarketDataError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    rows = []
    for result in results:
        run = _persist(db, payload.symbol, payload.start_date, payload.end_date, result)
        db.flush()
        rows.append(_to_comparison_row(run))

    # Buy & Hold is identical across every strategy run in this set (same
    # stock/range/capital/cost) — add it once as its own comparison row
    # rather than persisting it as a fake "strategy" backtest.
    rows.append(
        StrategyComparisonResultOut(
            backtest_run_id=None,
            symbol=payload.symbol.upper(),
            strategy_name="BUY_AND_HOLD",
            strategy_params={},
            total_return_pct=results[0].buy_hold_return_pct,
            ending_capital=payload.starting_capital * (1 + results[0].buy_hold_return_pct / 100),
            total_trades=1,
            win_rate=100.0 if results[0].buy_hold_return_pct > 0 else 0.0,
            max_drawdown_pct=0.0,  # not tracked for the buy & hold baseline
            buy_hold_return_pct=results[0].buy_hold_return_pct,
        )
    )
    rows.sort(key=lambda r: r.total_return_pct, reverse=True)

    db.commit()
    return CompareResponse(
        symbol=payload.symbol.upper(),
        start_date=payload.start_date,
        end_date=payload.end_date,
        starting_capital=payload.starting_capital,
        transaction_cost_percent=payload.transaction_cost_percent,
        results=rows,
    )


@router.post("/backtests/compare-multi-stock", response_model=MultiStockCompareResponse)
def compare_strategies_multi_stock(
    payload: MultiStockCompareRequest, db: Session = Depends(get_db)
) -> MultiStockCompareResponse:
    """Runs the standard comparison independently for all five configured
    stocks (each with its own fresh starting_capital — never pooled), then
    averages return% and max drawdown% per strategy across stocks."""
    try:
        per_symbol = run_multi_stock_comparison(
            start_date=payload.start_date,
            end_date=payload.end_date,
            starting_capital=payload.starting_capital,
            transaction_cost_percent=payload.transaction_cost_percent,
        )
    except MarketDataError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Persist every individual run, keyed by (strategy_name, params) so
    # results for the same configuration across different stocks group together.
    by_strategy: dict[str, list[StrategyComparisonResultOut]] = {}
    strategy_params_by_key: dict[str, dict] = {}
    strategy_name_by_key: dict[str, str] = {}

    for symbol, results in per_symbol.items():
        for result in results:
            run = _persist(db, symbol, payload.start_date, payload.end_date, result)
            db.flush()
            row = _to_comparison_row(run)
            key = f"{result.strategy_name}:{result.strategy_params}"
            by_strategy.setdefault(key, []).append(row)
            strategy_params_by_key[key] = result.strategy_params
            strategy_name_by_key[key] = result.strategy_name

    averages = []
    for key, rows in by_strategy.items():
        avg_return = sum(r.total_return_pct for r in rows) / len(rows)
        avg_drawdown = sum(r.max_drawdown_pct for r in rows) / len(rows)
        avg_buy_hold = sum(r.buy_hold_return_pct for r in rows) / len(rows)
        averages.append(
            MultiStockStrategyAverageOut(
                strategy_name=strategy_name_by_key[key],
                strategy_params=strategy_params_by_key[key],
                avg_return_pct=avg_return,
                avg_max_drawdown_pct=avg_drawdown,
                avg_buy_hold_return_pct=avg_buy_hold,
                per_stock=rows,
            )
        )
    averages.sort(key=lambda a: a.avg_return_pct, reverse=True)

    db.commit()
    return MultiStockCompareResponse(
        start_date=payload.start_date,
        end_date=payload.end_date,
        starting_capital=payload.starting_capital,
        transaction_cost_percent=payload.transaction_cost_percent,
        symbols=list(DEFAULT_SYMBOLS),
        averages=averages,
    )
