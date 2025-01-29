"""Systemctl2mqtt type definitions."""

from datetime import datetime
from typing import Literal, TypedDict

ServiceEventStateType = Literal["on", "off"]
"""Service event state"""

ServiceEventStatusType = Literal["running", "exited", "failed"]
"""Service event Systemctl status"""

ServiceLoadType = Literal["loaded", "not-found", "error"]
"""Systemctl service load status"""

ServiceActiveType = Literal["active", "inactive", "failed"]
"""Systemctl service active status"""

"""Systemctl service sub status"""


class Systemctl2MqttConfig(TypedDict):
    """A config object.

    Attributes
    ----------
    log_level
        Log verbosity
    homeassistant_prefix
        MQTT discovery topic prefix
    homeassistant_single_device
        Group all entities by a single device in Home Assistant instead of one device per entity
    systemctl2mqtt_hostname
        A descriptive name for the Systemctl being monitored
    mqtt_client_id
        Client Id for MQTT broker client
    mqtt_user
        Username for MQTT broker authentication
    mqtt_password
        Password for MQTT broker authentication
    mqtt_host
        Hostname or IP address of the MQTT broker
    mqtt_port
        Port or IP address of the MQTT broker
    mqtt_timeout
        Timeout for MQTT messages
    mqtt_topic_prefix
        MQTT topic prefix
    mqtt_qos
        QOS for standard MQTT messages
    destroyed_service_ttl
        How long, in seconds, before destroyed services are removed from Home Assistant. Services won't be removed if the service is restarted before the TTL expires.
    service_whitelist
        Whitelist the services to monitor, if empty, everything is monitored. The entries are either match as literal strings or as regex.
    service_blacklist
        Blacklist the services to monitor, takes priority over whitelist. The entries are either match as literal strings or as regex.
    enable_events
        Flag to enable event monitoring
    enable_stats
        Flag to enable stat monitoring
    stats_record_seconds
        Interval every how many seconds the stats are published via MQTT

    """

    log_level: str
    homeassistant_prefix: str
    homeassistant_single_device: bool
    systemctl2mqtt_hostname: str
    mqtt_client_id: str
    mqtt_user: str
    mqtt_password: str
    mqtt_host: str
    mqtt_port: int
    mqtt_timeout: int
    mqtt_topic_prefix: str
    mqtt_qos: int
    destroyed_service_ttl: int
    service_whitelist: list[str]
    service_blacklist: list[str]
    enable_events: bool
    enable_stats: bool
    stats_record_seconds: int


class SystemctlService(TypedDict):
    """A systemctl service definition.

    Attributes
    ----------
    unit
        The name of the service
    load
        Is the service loaded
    active
        High level status of the service
    sub
        Detailed state of the service
    description
        Description of the service

    """

    unit: str
    load: ServiceLoadType
    active: ServiceActiveType
    sub: ServiceEventStatusType
    description: str


class ServiceEvent(TypedDict):
    """A Service event object to send to an mqtt topic.

    Attributes
    ----------
    name
        The name of the Service
    description
        The description of the Service
    pid
        The pid of the Service
    cpids
        The child pids of the Service
    status
        The Systemctl status the Service is in
    state
        The state of the Service

    """

    name: str
    description: str
    pid: int
    cpids: list[int]
    status: ServiceEventStatusType
    state: ServiceEventStateType


class ServiceStatsRef(TypedDict):
    """A Service stats ref object compare between current and past stats.

    Attributes
    ----------
    last
        When the last stat rotation happened

    """

    last: datetime


class PIDStats(TypedDict):
    """A PID stats object which is part of the services stats.

    Attributes
    ----------
    pid
        The pid of the Service
    memory
        Used memory in MB
    cpu
        The cpu usage by the Service in cpu-% (ex.: a Systemctl with 4 cores has 400% cpu available)

    """

    pid: int
    cpu: float
    memory: float


class ServiceStats(TypedDict):
    """A Service stats object to send to an mqtt topic.

    Attributes
    ----------
    name
        The name of the Service
    host
        The Systemctl host
    memory
        Used memory in MB
    cpu
        The cpu usage by the Service in cpu-% (ex.: a Systemctl with 4 cores has 400% cpu available)
    pid_stats
        The stats for all pids

    """

    name: str
    host: str
    memory: float
    cpu: float
    pid_stats: dict[int, PIDStats]


class ServiceDeviceEntry(TypedDict):
    """A Service device entry object for discovery in home assistant.

    Attributes
    ----------
    identifiers
        A unique str to identify the device in home assistant
    name
        The name of the device to display in home assistant
    model
        The model of the device as additional info

    """

    identifiers: str
    name: str
    model: str


class ServiceEntry(TypedDict):
    """A Service entry object for discovery in home assistant.

    Attributes
    ----------
    name
        The name of the sensor to display in home assistant
    unique_id
        The unique id of the sensor in home assistant
    icon
        The icon of the sensor to display
    availability_topic
        The topic to check the availability of the sensor
    payload_available
        The payload of availability_topic of the sensor when available
    payload_unavailable
        The payload of availability_topic of the sensor when unavailable
    state_topic
        The topic containing all information for the state of the sensor
    value_template
        The jinja2 template to extract the state value from the state_topic for the sensor
    unit_of_measurement
        The unit of measurement of the sensor
    payload_on
        When a binary sensor: The value of extracted state of the sensor to be considered 'on'
    payload_off
        When a binary sensor: The value of extracted state of the sensor to be considered 'off'
    device
        The device the sensor is attributed to
    device_class
        The device class of the sensor
    state_topic
        The topic containing all information for the attributes of the sensor
    qos
        The QOS of the discovery message

    """

    name: str
    unique_id: str
    icon: str | None
    availability_topic: str
    payload_available: str
    payload_not_available: str
    state_topic: str
    value_template: str
    unit_of_measurement: str | None
    payload_on: str | None
    payload_off: str | None
    device: ServiceDeviceEntry
    device_class: str | None
    json_attributes_topic: str | None
    qos: int
