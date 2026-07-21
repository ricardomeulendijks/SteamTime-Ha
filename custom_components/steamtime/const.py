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

# Services — public API (design §6), breaking changes must be flagged.
SERVICE_START_SESSION = "start_session"
SERVICE_CONFIRM_DISH = "confirm_dish"
SERVICE_CANCEL_SESSION = "cancel_session"
SERVICE_ADD_DISH = "add_dish"
SERVICE_UPDATE_DISH = "update_dish"
SERVICE_REMOVE_DISH = "remove_dish"
SERVICE_GET_DISHES = "get_dishes"
SERVICE_GET_HISTORY = "get_history"
SERVICE_RESTART_SESSION = "restart_session"

# Custom-dish validation bounds (design §6, mirrors the original rules layer).
DISH_CATEGORIES = ("vegetables", "fish", "meat", "other")
DISH_NAME_MIN_LENGTH = 1
DISH_NAME_MAX_LENGTH = 100
DISH_MINUTES_MIN = 1
DISH_MINUTES_MAX = 600
DISH_TEMPERATURE_MIN = 1
DISH_TEMPERATURE_MAX = 250
DISH_DEFAULT_TEMPERATURE = 100
DISH_DEFAULT_CATEGORY = "other"
