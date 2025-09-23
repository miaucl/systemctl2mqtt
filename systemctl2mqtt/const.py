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
    # label,                   field,                       device_class,    unit,   icon,                    catetogy
    ('CPU',                    'cpu',                       None,            '%',    'mdi:chip',              None),         # CPU utilization percentage
    ('Memory (Virtual)',       'memory',                    'data_size',     'MB',   'mdi:memory',            None),         # Total virtual memory usage
    ('Memory (Real)',          'memory_real',               'data_size',     'MB',   'mdi:memory',            None),         # Real memory (calculated from smaps)
    ('Memory (Real PSS)',      'memory_real_pss',           'data_size',     'MB',   'mdi:memory',            None),         # Real memory (calculated from smaps), based on PSS
    ('PSS Memory',             'memory_pss',                'data_size',     'MB',   'mdi:memory',            "diagnostic"), # Proportional Set Size (shared pages divided among processes)
    ('PSS Anon',               'memory_pss_anon',           'data_size',     'MB',   'mdi:memory',            "diagnostic"), # Anonymous memory part of PSS
    ('PSS File',               'memory_pss_file',           'data_size',     'MB',   'mdi:memory',            "diagnostic"), # File-backed memory part of PSS
    ('PSS Dirty',              'memory_pss_dirty',          'data_size',     'MB',   'mdi:memory',            "diagnostic"), # Modified (dirty) memory part of PSS
    ('PSS Shmem',              'memory_pss_shmem',          'data_size',     'MB',   'mdi:memory',            "diagnostic"), # Shared memory part of PSS
    ('RSS',                    'memory_rss',                'data_size',     'MB',   'mdi:memory',            "diagnostic"), # Resident Set Size (non-swapped physical memory)
    ('Shared Clean',           'memory_shared_clean',       'data_size',     'MB',   'mdi:memory',            "diagnostic"), # Shared pages not modified (clean)
    ('Shared Dirty',           'memory_shared_dirty',       'data_size',     'MB',   'mdi:memory',            "diagnostic"), # Shared pages modified (dirty)
    ('Private Clean',          'memory_private_clean',      'data_size',     'MB',   'mdi:memory',            "diagnostic"), # Private pages that are clean
    ('Private Dirty',          'memory_private_dirty',      'data_size',     'MB',   'mdi:memory',            "diagnostic"), # Private pages that are dirty
    ('Referenced',             'memory_referenced',         'data_size',     'MB',   'mdi:memory',            "diagnostic"), # Recently accessed pages
    ('Anonymous',              'memory_anonymous',          'data_size',     'MB',   'mdi:memory',            "diagnostic"), # Anonymous memory (not file-backed)
    ('LazyFree',               'memory_lazyfree',           'data_size',     'MB',   'mdi:memory',            "diagnostic"), # Pages marked as free-on-demand (MADV_FREE)
    ('Anon HugePages',         'memory_anon_hugepages',     'data_size',     'MB',   'mdi:memory',            "diagnostic"), # Anonymous memory using HugePages
    ('Shmem PMD Mapped',       'memory_shmem_pmd_mapped',   'data_size',     'MB',   'mdi:memory',            "diagnostic"), # Shared memory mapped with hugepages (PMD)
    ('File PMD Mapped',        'memory_file_pmd_mapped',    'data_size',     'MB',   'mdi:memory',            "diagnostic"), # File-backed memory mapped with hugepages
    ('Shared HugeTLB',         'memory_shared_hugetlb',     'data_size',     'MB',   'mdi:memory',            "diagnostic"), # Shared HugeTLB memory usage
    ('Private HugeTLB',        'memory_private_hugetlb',    'data_size',     'MB',   'mdi:memory',            "diagnostic"), # Private HugeTLB memory usage
    ('Swap',                   'memory_swap',               'data_size',     'MB',   'mdi:swap-horizontal',   "diagnostic"), # Memory swapped out
    ('Swap PSS',               'memory_swappss',            'data_size',     'MB',   'mdi:swap-horizontal',   "diagnostic"), # Proportional swap usage
    ('Locked',                 'memory_locked',             'data_size',     'MB',   'mdi:lock',              "diagnostic"), # Locked pages (mlock)
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
        "enable_smaps": STATS_DEFAULT,
        "stats_record_seconds": STATS_RECORD_SECONDS_DEFAULT,
    }
)
