"""Constants for the AjaxSecurFlow integration."""
from typing import Final

DOMAIN: Final = "ajaxsecurflow"
VERSION: Final = "0.1.0"
USER_AGENT: Final = f"ajaxsecurflow-hass/{VERSION}"
API_PREFIX: Final = "/api/v1"

CONF_BASE_URL: Final = "base_url"
CONF_TOKEN: Final = "token"
CONF_SCAN_INTERVAL: Final = "scan_interval"

DEFAULT_BASE_URL: Final = "https://api.ajaxsecurflow.com"
DEFAULT_SCAN_INTERVAL: Final = 60
MIN_SCAN_INTERVAL: Final = 30
MAX_SCAN_INTERVAL: Final = 600

REQUEST_TIMEOUT: Final = 15
STREAM_READ_TIMEOUT: Final = 90  # backend pings every 15 s
SSE_BACKOFF_MIN: Final = 5
SSE_BACKOFF_MAX: Final = 300

EVENT_NAME: Final = "ajaxsecurflow_event"

PLANS_WITH_DEVICES: Final = frozenset({"basic", "pro", "premium"})
PLANS_WITH_CONTROL: Final = frozenset({"pro", "premium"})

ARM_STATE_DISARM: Final = 0
ARM_STATE_ARM: Final = 1
ARM_STATE_NIGHT: Final = 2

SIGNAL_LEVELS: Final = ["NO_SIGNAL", "WEAK", "NORMAL", "STRONG"]

# Event tags (Ajax `eventTag`, matched case-insensitively) → which device flag they drive.
ARM_TAGS: Final = frozenset({"arm", "armed"})
DISARM_TAGS: Final = frozenset({"disarm", "disarmed"})
NIGHT_ON_TAGS: Final = frozenset({"nightmodeon", "nightmode", "night_mode_on"})
NIGHT_OFF_TAGS: Final = frozenset({"nightmodeoff", "night_mode_off"})
OPENING_TAGS: Final = frozenset({"opened", "reedopened", "contactopened", "dooropened"})
EXT_CONTACT_TAGS: Final = frozenset({"extcontactopened"})
MOTION_TAGS: Final = frozenset({"motiondetected", "motion"})
GLASS_TAGS: Final = frozenset({"glassbreak", "glassbreakdetected"})
LEAK_TAGS: Final = frozenset({"leak", "leakdetected", "leakagedetected"})
SMOKE_TAGS: Final = frozenset({"smoke", "smokedetected", "smokealarm", "firealarm"})
OFFLINE_TAGS: Final = frozenset({"offline", "devicelost", "lostconnection", "connectionlost"})
