from sqlalchemy.orm import Session

from app.models.enums import SystemEventLevel
from app.models.system_event import SystemEvent


def log_event(
    db: Session,
    level: SystemEventLevel,
    category: str,
    message: str,
    details: dict | None = None,
) -> SystemEvent:
    event = SystemEvent(level=level, category=category, message=message, details=details)
    db.add(event)
    return event
