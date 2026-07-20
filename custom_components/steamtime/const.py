"""Constants for SteamTime."""

from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

DOMAIN = "steamtime"

# HA bus events — public API (design §6), breaking changes must be flagged.
EVENT_ADD_DISH = "steamtime_add_dish"
EVENT_DISH_DONE = "steamtime_dish_done"
EVENT_SESSION_COMPLETED = "steamtime_session_completed"
EVENT_SESSION_CANCELLED = "steamtime_session_cancelled"

# Dispatcher signal for entities to refresh from SessionManager.state.
SIGNAL_SESSION_UPDATED = f"{DOMAIN}_session_updated"
