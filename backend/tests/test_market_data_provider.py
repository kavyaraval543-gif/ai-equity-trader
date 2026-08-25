"""Tests the market data provider layer. The last two tests hit the real
Yahoo Finance API by design — this system has no mock provider to fall back
to, so "does the real provider work" has to be verified against the real
thing, not a stub."""
import pytest

from app.market_data.symbols import to_yahoo_ticker
from app.market_data.yahoo_provider import YahooFinanceProvider


def test_to_yahoo_ticker_maps_known_symbol():
    assert to_yahoo_ticker("reliance") == "RELIANCE.NS"
    assert to_yahoo_ticker("TCS") == "TCS.NS"


def test_to_yahoo_ticker_rejects_unknown_symbol():
    with pytest.raises(ValueError):
        to_yahoo_ticker("NOT_A_REAL_SYMBOL")


@pytest.mark.network
def test_yahoo_provider_fetches_real_latest_price():
    provider = YahooFinanceProvider()
    quote = provider.get_latest_price("RELIANCE")

    assert quote.symbol == "RELIANCE"
    assert quote.provider == "yahoo"
    assert quote.price > 0


@pytest.mark.network
def test_yahoo_provider_fetches_real_historical_data():
    provider = YahooFinanceProvider()
    candles = provider.get_historical_data("TCS", interval="1d")

    assert len(candles) > 0
    latest = candles[-1]
    assert latest.close > 0
    assert latest.high >= latest.low


@pytest.mark.network
def test_yahoo_provider_raises_market_data_error_for_unknown_symbol():
    provider = YahooFinanceProvider()
    with pytest.raises(ValueError):
        provider.get_latest_price("NOT_A_REAL_SYMBOL")
