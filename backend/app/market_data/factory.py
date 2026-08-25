"""Provider selection. Fails loudly on misconfiguration rather than
silently falling back to a different (or fake) provider."""
from functools import lru_cache

from app.core.config import get_settings
from app.market_data.base import MarketDataProvider
from app.market_data.yahoo_provider import YahooFinanceProvider

_PROVIDERS: dict[str, type[MarketDataProvider]] = {
    "yahoo": YahooFinanceProvider,
}


@lru_cache
def get_market_data_provider() -> MarketDataProvider:
    settings = get_settings()
    provider_cls = _PROVIDERS.get(settings.market_data_provider)
    if provider_cls is None:
        raise RuntimeError(
            f"Unknown MARKET_DATA_PROVIDER '{settings.market_data_provider}'. "
            f"Configured providers: {list(_PROVIDERS)}. Refusing to silently fall back."
        )
    return provider_cls()
