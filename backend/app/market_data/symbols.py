"""Mapping between the system's internal symbols and provider-specific tickers.

The strategy/risk/execution layers only ever see the internal symbol
(e.g. "RELIANCE"); provider-specific identifiers are an implementation
detail of each MarketDataProvider.
"""

# NSE-listed symbol -> Yahoo Finance ticker (NSE suffix).
YAHOO_TICKER_MAP: dict[str, str] = {
    "RELIANCE": "RELIANCE.NS",
    "TCS": "TCS.NS",
    "INFY": "INFY.NS",
    "HDFCBANK": "HDFCBANK.NS",
    "ICICIBANK": "ICICIBANK.NS",
}

DEFAULT_SYMBOLS: list[str] = list(YAHOO_TICKER_MAP.keys())


def to_yahoo_ticker(symbol: str) -> str:
    try:
        return YAHOO_TICKER_MAP[symbol.upper()]
    except KeyError:
        raise ValueError(f"Unknown symbol '{symbol}' — not in the configured universe {DEFAULT_SYMBOLS}") from None
