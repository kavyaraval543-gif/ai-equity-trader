from app.core.config import Settings
from app.models.enums import AutonomousTradingState
from app.services import autonomous_control_service


def _settings(**overrides) -> Settings:
    defaults = dict(emergency_stop=False, autonomous_trading_enabled=False)
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


def test_fresh_install_defaults_to_stopped(db_session):
    state = autonomous_control_service.get_or_create_state(db_session, _settings())

    assert state.state == AutonomousTradingState.STOPPED


def test_seeds_running_when_enabled_by_config(db_session):
    state = autonomous_control_service.get_or_create_state(db_session, _settings(autonomous_trading_enabled=True))

    assert state.state == AutonomousTradingState.RUNNING


def test_start_transitions_to_running(db_session):
    state = autonomous_control_service.start(db_session, _settings())

    assert state.state == AutonomousTradingState.RUNNING


def test_pause_transitions_to_paused(db_session):
    autonomous_control_service.start(db_session, _settings())

    state = autonomous_control_service.pause(db_session)

    assert state.state == AutonomousTradingState.PAUSED


def test_stop_transitions_to_stopped(db_session):
    autonomous_control_service.start(db_session, _settings())
    autonomous_control_service.pause(db_session)

    state = autonomous_control_service.stop(db_session)

    assert state.state == AutonomousTradingState.STOPPED


def test_emergency_stop_overrides_start(db_session):
    """Starting while the emergency stop is active must not enable autonomous
    trading — the emergency stop overrides all autonomous controls."""
    state = autonomous_control_service.start(db_session, _settings(emergency_stop=True))

    assert state.state == AutonomousTradingState.STOPPED


def test_mark_error_sets_error_state(db_session):
    state = autonomous_control_service.mark_error(db_session, "scheduler crashed")

    assert state.state == AutonomousTradingState.ERROR
    assert state.reason == "scheduler crashed"
