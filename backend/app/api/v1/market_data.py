from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.database.session import get_db
from app.market_data.factory import get_market_data_provider
from app.schemas.market_data import MarketDataStatusOut
from app.services.market_data_service import MarketDataService

router = APIRouter(tags=["market-data"])


@router.get("/market-data/status", response_model=MarketDataStatusOut)
def get_market_data_status(
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings)
) -> MarketDataStatusOut:
    provider = get_market_data_provider()
    service = MarketDataService(provider, db, settings)
    status_list = service.get_status(settings.market_data_symbols, settings.market_data_timeframe)
    return MarketDataStatusOut(provider=provider.name, symbols=status_list)
