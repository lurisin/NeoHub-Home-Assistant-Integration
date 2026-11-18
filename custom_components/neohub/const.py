"""Constants for the DSC Neo (via NeoHub) integration."""

DOMAIN = "neohub"

CONF_SSL = "ssl"
CONF_ACCESS_TOKEN = "access_token"

DEFAULT_PORT = 8080
DEFAULT_SSL = False

SIGNAL_STATE_UPDATED = f"{DOMAIN}_state_updated"
SIGNAL_CONNECTION_STATE = f"{DOMAIN}_connection_state"

# Panel response code that NeoHub reports when an arm command is rejected
# because the partition is not ready to arm (for example a zone is open).
PANEL_RESPONSE_NOT_READY = 1
