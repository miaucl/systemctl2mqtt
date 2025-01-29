"""systemctl2mqtt const."""

# Env config
import re
import socket

from .type_definitions import Systemctl2MqttConfig

LOG_LEVEL_DEFAULT = "INFO"
HOMEASSISTANT_PREFIX_DEFAULT = "homeassistant"
HOMEASSISTANT_SINGLE_DEVICE_DEFAULT = False
MQTT_CLIENT_ID_DEFAULT = "systemctl2mqtt"
MQTT_PORT_DEFAULT = 1883
MQTT_TIMEOUT_DEFAULT = 30  # s
MQTT_TOPIC_PREFIX_DEFAULT = "systemctl"
MQTT_QOS_DEFAULT = 1
DESTROYED_SERVICE_TTL_DEFAULT = 24 * 60 * 60  # s
SERVICE_WHITELIST: list[str] = []
SERVICE_BLACKLIST: list[str] = []
EVENTS_DEFAULT = False
STATS_DEFAULT = False
STATS_RECORD_SECONDS_DEFAULT = 30  # s

# Const
WATCHED_EVENTS = (
    "restart",
    "start",
    "stop",
    "reload",
)
MAX_QUEUE_SIZE = 100
SYSTEMCTL_EVENTS_CMD = ["journalctl", "_COMM=systemd", "--output=json", "-f", "-n", "0"]
SYSTEMCTL_LIST_CMD = ["systemctl", "--type=service", "--output=json", "--no-pager"]
SYSTEMCTL_PID_PRE_CMD = ["systemctl", "show", "--property=MainPID", "--value"]
SYSTEMCTL_CHILD_PID_PRE_CMD = ["ps", "--ppid"]
SYSTEMCTL_CHILD_PID_POST_CMD = ["-o", "pid="]
SYSTEMCTL_STATS_CMD = ["top", "-b", "-d", "1"]
SYSTEMCTL_VERSION_CMD = ["systemctl", "--version", "|", "grep", "systemd"]
INVALID_HA_TOPIC_CHARS = re.compile(r"[^a-zA-Z0-9_-]")
ANSI_ESCAPE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
# fmt: off
STATS_REGISTRATION_ENTRIES = [
    # label,field,device_class,unit,icon
    ('CPU',                     'cpu',              None,           '%',    'mdi:chip'),
    ('Memory',                  'memory',           'data_size',    'MB',   'mdi:memory'),
]
# fmt: on

DEFAULT_CONFIG = Systemctl2MqttConfig(
    {
        "log_level": LOG_LEVEL_DEFAULT,
        "homeassistant_prefix": HOMEASSISTANT_PREFIX_DEFAULT,
        "homeassistant_single_device": HOMEASSISTANT_SINGLE_DEVICE_DEFAULT,
        "systemctl2mqtt_hostname": socket.gethostname(),
        "mqtt_client_id": MQTT_CLIENT_ID_DEFAULT,
        "mqtt_user": "",
        "mqtt_password": "",
        "mqtt_host": "",
        "mqtt_port": MQTT_PORT_DEFAULT,
        "mqtt_timeout": MQTT_TIMEOUT_DEFAULT,
        "mqtt_topic_prefix": MQTT_TOPIC_PREFIX_DEFAULT,
        "mqtt_qos": MQTT_QOS_DEFAULT,
        "destroyed_service_ttl": DESTROYED_SERVICE_TTL_DEFAULT,
        "service_whitelist": SERVICE_WHITELIST,
        "service_blacklist": SERVICE_BLACKLIST,
        "enable_events": EVENTS_DEFAULT,
        "enable_stats": STATS_DEFAULT,
        "stats_record_seconds": STATS_RECORD_SECONDS_DEFAULT,
    }
)
