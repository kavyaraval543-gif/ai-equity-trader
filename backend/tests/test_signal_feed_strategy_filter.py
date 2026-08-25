"""Regression test for a display-layer bug introduced by Phase 5: `Signal`
and `RiskDecision` rows aren't portfolio-scoped (the daily and intraday
traders write into the same shared tables), so once the intraday strategy
started generating its own signals, GET /signals and GET /risk/decisions
(used by the daily dashboard) began returning a feed mixed with intraday
activity — a real, user-visible regression to the existing daily trader's
dashboard even though the daily trading LOGIC itself was untouched.

Fixed with an optional `strategy_name` filter on both endpoints; the
frontend's daily dashboard now always passes strategy_name=SMA_CROSSOVER
and the intraday dashboard passes strategy_name=INTRADAY_VWAP_MOMENTUM.
"""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.database.session import get_db
from app.main import app
from app.models.risk_decision import RiskDecision
from app.models.signal import Signal
from app.models.enums import RiskDecisionType, SignalType

NOW = datetime.now(timezone.utc)


@pytest.fixture()
def client(db_session):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


def _seed_signals_and_decisions(db):
    daily_signal = Signal(
        symbol="RELIANCE", signal_type=SignalType.BUY, confidence=0.8, strategy_name="SMA_CROSSOVER",
        reason="daily", indicator_data={}, market_price=1000.0, timestamp=NOW,
    )
    intraday_signal = Signal(
        symbol="RELIANCE", signal_type=SignalType.BUY, confidence=0.8, strategy_name="INTRADAY_VWAP_MOMENTUM",
        reason="intraday", indicator_data={}, market_price=1000.0, timestamp=NOW,
    )
    db.add_all([daily_signal, intraday_signal])
    db.flush()
    db.add_all([
        RiskDecision(signal_id=daily_signal.id, decision=RiskDecisionType.APPROVED, reason="daily approved"),
        RiskDecision(signal_id=intraday_signal.id, decision=RiskDecisionType.APPROVED, reason="intraday approved"),
    ])
    db.commit()
    return daily_signal, intraday_signal


def test_signals_endpoint_without_filter_returns_both_strategies(client, db_session):
    _seed_signals_and_decisions(db_session)

    resp = client.get("/api/v1/signals")

    assert resp.status_code == 200
    strategy_names = {s["strategy_name"] for s in resp.json()}
    assert strategy_names == {"SMA_CROSSOVER", "INTRADAY_VWAP_MOMENTUM"}


def test_signals_endpoint_filters_to_daily_strategy_only(client, db_session):
    _seed_signals_and_decisions(db_session)

    resp = client.get("/api/v1/signals?strategy_name=SMA_CROSSOVER")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["strategy_name"] == "SMA_CROSSOVER"
    assert body[0]["reason"] == "daily"


def test_signals_endpoint_filters_to_intraday_strategy_only(client, db_session):
    _seed_signals_and_decisions(db_session)

    resp = client.get("/api/v1/signals?strategy_name=INTRADAY_VWAP_MOMENTUM")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["strategy_name"] == "INTRADAY_VWAP_MOMENTUM"


def test_risk_decisions_endpoint_filters_by_strategy_via_signal_join(client, db_session):
    _seed_signals_and_decisions(db_session)

    resp = client.get("/api/v1/risk/decisions?strategy_name=SMA_CROSSOVER")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["reason"] == "daily approved"


def test_risk_decisions_endpoint_without_filter_returns_both(client, db_session):
    _seed_signals_and_decisions(db_session)

    resp = client.get("/api/v1/risk/decisions")

    assert resp.status_code == 200
    assert len(resp.json()) == 2
