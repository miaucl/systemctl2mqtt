#!/usr/bin/env python3
"""Listens to systemctl events and stats for services and sends it to mqtt and supports discovery for home assistant."""

import argparse
import datetime
import json
import logging
import platform
from queue import Empty, Queue
import re
import signal
import socket
import subprocess
import sys
from threading import Thread
from time import sleep, time
from typing import Any

import paho.mqtt.client

from . import __version__
from .const import (
    ANSI_ESCAPE,
    DESTROYED_SERVICE_TTL_DEFAULT,
    HOMEASSISTANT_PREFIX_DEFAULT,
    HOMEASSISTANT_SINGLE_DEVICE_DEFAULT,
    INVALID_HA_TOPIC_CHARS,
    MAX_QUEUE_SIZE,
    MQTT_CLIENT_ID_DEFAULT,
    MQTT_PORT_DEFAULT,
    MQTT_QOS_DEFAULT,
    MQTT_TIMEOUT_DEFAULT,
    MQTT_TOPIC_PREFIX_DEFAULT,
    STATS_RECORD_SECONDS_DEFAULT,
    STATS_REGISTRATION_ENTRIES,
    SYSTEMCTL_CHILD_PID_POST_CMD,
    SYSTEMCTL_CHILD_PID_PRE_CMD,
    SYSTEMCTL_EVENTS_CMD,
    SYSTEMCTL_LIST_CMD,
    SYSTEMCTL_PID_PRE_CMD,
    SYSTEMCTL_STATS_CMD,
    SYSTEMCTL_VERSION_CMD,
)
from .exceptions import (
    Systemctl2MqttConfigException,
    Systemctl2MqttConnectionException,
    Systemctl2MqttEventsException,
    Systemctl2MqttException,
    Systemctl2MqttStatsException,
)
from .helpers import clean_for_discovery
from .type_definitions import (
    PIDStats,
    ServiceDeviceEntry,
    ServiceEntry,
    ServiceEvent,
    ServiceEventStateType,
    ServiceEventStatusType,
    ServiceStats,
    ServiceStatsRef,
    Systemctl2MqttConfig,
    SystemctlService,
)

# Configure logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

# Loggers
main_logger = logging.getLogger("main")
events_logger = logging.getLogger("events")
stats_logger = logging.getLogger("stats")


class Systemctl2Mqtt:
    """systemctl2mqtt class.

    Attributes
    ----------
    version
        The version of systemctl2mqtt
    cfg
        The config for systemctl2mqtt
    b_stats
        Activate the stats
    b_events
        Activate the events
    systemctl_events
        Queue with systemctl events
    systemctl_stats
        Queue with systemctl stats

    known_event_services
        The dict with the known service events
    known_stat_services
        The dict with the known service stats references
    last_stat_services
        The dict with the last service stats
    mqtt
        The mqtt client
    systemctl_events_t
        The thread to collect events from systemctl
    systemctl_stats_t
        The thread to collect stats from systemctl
    systemctl_version
        The systemctl version
    discovery_binary_sensor_topic
        Topic template for a binary sensor
    discovery_sensor_topic
        Topic template for a nary sensor
    status_topic
        Topic template for a status value
    version_topic
        Topic template for a version value
    stats_topic
        Topic template for stats
    events_topic
        Topic template for an events
    do_not_exit
        Prevent exit from within Systemctl2mqtt, when handled outside

    """

    # Version
    version: str = __version__

    cfg: Systemctl2MqttConfig

    b_stats: bool = False
    b_events: bool = False

    systemctl_events: Queue[dict[str, str]] = Queue(maxsize=MAX_QUEUE_SIZE)
    systemctl_stats: Queue[list[str]] = Queue(maxsize=MAX_QUEUE_SIZE)
    known_event_services: dict[str, ServiceEvent] = {}
    known_stat_services: dict[str, dict[int, ServiceStatsRef]] = {}
    last_stat_services: dict[str, ServiceStats | dict[str, Any]] = {}
    pending_destroy_operations: dict[str, float] = {}

    mqtt: paho.mqtt.client.Client

    systemctl_events_t: Thread
    systemctl_stats_t: Thread

    systemctl_version: str

    discovery_binary_sensor_topic: str
    discovery_sensor_topic: str
    status_topic: str
    version_topic: str
    stats_topic: str
    events_topic: str

    do_not_exit: bool

    def __init__(self, cfg: Systemctl2MqttConfig, do_not_exit: bool = False):
        """Initialize the Systemctl2mqtt.

        Parameters
        ----------
        cfg
            The configuration object for Systemctl2mqtt
        do_not_exit
            Prevent exit from within Systemctl2mqtt, when handled outside

        """

        self.cfg = cfg
        self.do_not_exit = do_not_exit

        self.discovery_binary_sensor_topic = f"{cfg['homeassistant_prefix']}/binary_sensor/{cfg['mqtt_topic_prefix']}/{cfg['systemctl2mqtt_hostname']}_{{}}/config"
        self.discovery_sensor_topic = f"{cfg['homeassistant_prefix']}/sensor/{cfg['mqtt_topic_prefix']}/{cfg['systemctl2mqtt_hostname']}_{{}}/config"
        self.status_topic = (
            f"{cfg['mqtt_topic_prefix']}/{cfg['systemctl2mqtt_hostname']}/status"
        )
        self.version_topic = (
            f"{cfg['mqtt_topic_prefix']}/{cfg['systemctl2mqtt_hostname']}/version"
        )
        self.stats_topic = (
            f"{cfg['mqtt_topic_prefix']}/{cfg['systemctl2mqtt_hostname']}/{{}}/stats"
        )
        self.events_topic = (
            f"{cfg['mqtt_topic_prefix']}/{cfg['systemctl2mqtt_hostname']}/{{}}/events"
        )

        if self.cfg["enable_events"]:
            self.b_events = True
        if self.cfg["enable_stats"]:
            self.b_stats = True

        main_logger.setLevel(self.cfg["log_level"].upper())
        events_logger.setLevel(self.cfg["log_level"].upper())
        stats_logger.setLevel(self.cfg["log_level"].upper())

        try:
            self.systemctl_version = self._get_systemctl_version()
        except FileNotFoundError as ex:
            raise Systemctl2MqttConfigException(
                "Could not get systemctl version"
            ) from ex

        if not self.do_not_exit:
            main_logger.info("Register signal handlers for SIGINT and SIGTERM")
            signal.signal(signal.SIGTERM, self._signal_handler)
            signal.signal(signal.SIGINT, self._signal_handler)

        main_logger.info("Events enabled: %d", self.b_events)
        main_logger.info("Stats enabled: %d", self.b_stats)

        try:
            # Setup MQTT
            self.mqtt = paho.mqtt.client.Client(
                callback_api_version=paho.mqtt.client.CallbackAPIVersion.VERSION2,  # type: ignore[attr-defined, call-arg]
                client_id=self.cfg["mqtt_client_id"],
            )
            self.mqtt.username_pw_set(
                username=self.cfg["mqtt_user"], password=self.cfg["mqtt_password"]
            )
            self.mqtt.will_set(
                self.status_topic,
                "offline",
                qos=self.cfg["mqtt_qos"],
                retain=True,
            )
            self.mqtt.connect(
                self.cfg["mqtt_host"], self.cfg["mqtt_port"], self.cfg["mqtt_timeout"]
            )
            self.mqtt.loop_start()
            self._mqtt_send(self.status_topic, "online", retain=True)
            self._mqtt_send(self.version_topic, self.version, retain=True)

        except paho.mqtt.client.WebsocketConnectionError as ex:
            main_logger.exception("Error while trying to connect to MQTT broker.")
            main_logger.debug(ex)
            raise Systemctl2MqttConnectionException from ex

        # Register services
        self._reload_services()

        started = False
        try:
            if self.b_events:
                logging.info("Starting Events thread")
                self._start_readline_events_thread()
                started = True
        except Exception as ex:
            main_logger.exception("Error while trying to start events thread.")
            main_logger.debug(ex)
            raise Systemctl2MqttConfigException from ex

        try:
            if self.b_stats:
                started = True
                logging.info("Starting Stats thread")
                self._start_readline_stats_thread()
        except Exception as ex:
            main_logger.exception("Error while trying to start stats thread.")
            main_logger.debug(ex)
            raise Systemctl2MqttConfigException from ex

        if started is False:
            logging.critical("Nothing started, check your config!")
            sys.exit(1)

    def __del__(self) -> None:
        """Destroy the class."""
        self._cleanup()

    def _signal_handler(self, _signum: Any, _frame: Any) -> None:
        """Handle a signal for SIGINT or SIGTERM on the process.

        Parameters
        ----------
        _signum : Any
            (Unused)

        _frame : Any
            (Unused)

        """
        self._cleanup()
        sys.exit(0)

    def _cleanup(self) -> None:
        """Cleanup the Systemctl2mqtt."""
        main_logger.warning("Shutting down gracefully.")
        try:
            self._mqtt_disconnect()
        except Systemctl2MqttConnectionException as ex:
            main_logger.exception("MQTT Cleanup Failed")
            main_logger.debug(ex)
            main_logger.info("Ignoring cleanup error and exiting...")

    def loop(self) -> None:
        """Start the loop.

        Raises
        ------
        Systemctl2MqttEventsException
            If anything goes wrong in the processing of the events
        Systemctl2MqttStatsException
            If anything goes wrong in the processing of the stats
        Systemctl2MqttException
            If anything goes wrong outside of the known exceptions

        """

        self._remove_destroyed_services()

        self._handle_events_queue()

        self._handle_stats_queue()

        try:
            if self.b_events and not self.systemctl_events_t.is_alive():
                main_logger.warning("Restarting events thread")
                self._start_readline_events_thread()
        except Exception as e:
            main_logger.exception("Error while trying to restart events thread.")
            main_logger.debug(e)
            raise Systemctl2MqttConfigException from e

        try:
            if self.b_stats and not self.systemctl_stats_t.is_alive():
                main_logger.warning("Restarting stats thread")
                self._start_readline_stats_thread()
        except Exception as e:
            main_logger.exception("Error while trying to restart stats thread.")
            main_logger.debug(e)
            raise Systemctl2MqttConfigException from e

    def loop_busy(self, raise_known_exceptions: bool = False) -> None:
        """Start the loop (blocking).

        Parameters
        ----------
        raise_known_exceptions
            Should any known processing exception be raised or ignored

        Raises
        ------
        Systemctl2MqttEventsException
            If anything goes wrong in the processing of the events
        Systemctl2MqttStatsException
            If anything goes wrong in the processing of the stats
        Systemctl2MqttException
            If anything goes wrong outside of the known exceptions

        """

        while True:
            try:
                self.loop()
            except Systemctl2MqttEventsException as ex:
                if raise_known_exceptions:
                    raise ex  # noqa: TRY201
                else:
                    main_logger.warning(
                        "Do not raise due to raise_known_exceptions=False: %s", str(ex)
                    )
            except Systemctl2MqttStatsException as ex:
                if raise_known_exceptions:
                    raise ex  # noqa: TRY201
                else:
                    main_logger.warning(
                        "Do not raise due to raise_known_exceptions=False: %s", str(ex)
                    )

            # Calculate next iteration between (~0.2s and 0.001s)
            sleep_time = 0.001 + 0.2 / MAX_QUEUE_SIZE * (
                MAX_QUEUE_SIZE
                - max(self.systemctl_events.qsize(), self.systemctl_stats.qsize())
            )
            main_logger.debug("Sleep for %.5fs until next iteration", sleep_time)
            sleep(sleep_time)

    def _get_systemctl_version(self) -> str:
        """Get the systemctl version and save it to a global value.

        Returns
        -------
        str
            The systemctl version as string

        Raises
        ------
        FileNotFoundError
            If systemctl binary is not accessible.

        """
        try:
            # Run the `systemctl --version` command
            result = subprocess.run(
                SYSTEMCTL_VERSION_CMD,
                capture_output=True,
                text=True,
                check=False,
            )

            # Check if the command was successful
            if result.returncode == 0:
                # Extract the version information from the output
                return result.stdout.strip()
            else:
                raise Systemctl2MqttException(f"Error: {result.stderr.strip()}")
        except FileNotFoundError:
            return "Systemctl is not installed or not found in PATH."

    def _mqtt_send(self, topic: str, payload: str, retain: bool = False) -> None:
        """Send a mqtt payload to for a topic.

        Parameters
        ----------
        topic
            The topic to send a payload to
        payload
            The payload to send to the topic
        retain
            Whether the payload should be retained by the mqtt server

        Raises
        ------
        Systemctl2MqttConnectionError
            If the mqtt client could not send the data

        """
        try:
            main_logger.debug("Sending to MQTT: %s: %s", topic, payload)
            self.mqtt.publish(
                topic, payload=payload, qos=self.cfg["mqtt_qos"], retain=retain
            )

        except paho.mqtt.client.WebsocketConnectionError as ex:
            main_logger.exception("MQTT Publish Failed: %s")
            main_logger.debug(ex)
            raise Systemctl2MqttConnectionException() from ex

    def _mqtt_disconnect(self) -> None:
        """Make sure we send our last_will message.

        Raises
        ------
        Systemctl2MqttConnectionError
            If the mqtt client could not send the data

        """
        try:
            self.mqtt.publish(
                self.status_topic,
                "offline",
                qos=self.cfg["mqtt_qos"],
                retain=True,
            )
            self.mqtt.publish(
                self.version_topic,
                self.version,
                qos=self.cfg["mqtt_qos"],
                retain=True,
            )
            self.mqtt.disconnect()
            sleep(1)
            self.mqtt.loop_stop()
        except paho.mqtt.client.WebsocketConnectionError as ex:
            main_logger.exception("MQTT Disconnect")
            main_logger.debug(ex)
            raise Systemctl2MqttConnectionException() from ex

    def _start_readline_events_thread(self) -> None:
        """Start the events thread."""
        self.systemctl_events_t = Thread(
            target=self._run_readline_events_thread, daemon=True, name="Events"
        )
        self.systemctl_events_t.start()

    def _run_readline_events_thread(self) -> None:
        """Run journal events and continually read lines from it."""
        thread_logger = logging.getLogger("event-thread")
        thread_logger.setLevel(self.cfg["log_level"].upper())
        try:
            thread_logger.info("Starting events thread")
            thread_logger.debug("Command: %s", SYSTEMCTL_EVENTS_CMD)
            with subprocess.Popen(
                SYSTEMCTL_EVENTS_CMD, stdout=subprocess.PIPE, text=True
            ) as process:
                while True:
                    assert process.stdout
                    line = ANSI_ESCAPE.sub("", process.stdout.readline())
                    if line == "" and process.poll() is not None:
                        break
                    if line:
                        line_obj = json.loads(line)
                        if self._filter_service(line_obj["UNIT"]):
                            thread_logger.debug("Read journalctl event line: %s", line)
                            self.systemctl_events.put(line_obj)
                    _rc = process.poll()
        except Exception as ex:
            thread_logger.exception("Error Running Events thread")
            thread_logger.debug(ex)
            thread_logger.debug("Waiting for main thread to restart this thread")

    def _start_readline_stats_thread(self) -> None:
        """Start the stats thread."""
        self.systemctl_stats_t = Thread(
            target=self._run_readline_stats_thread, daemon=True, name="Stats"
        )
        self.systemctl_stats_t.start()

    def _run_readline_stats_thread(self) -> None:
        """Run top stats and continually read lines from it."""
        thread_logger = logging.getLogger("stats-thread")
        thread_logger.setLevel(self.cfg["log_level"].upper())
        try:
            thread_logger.info("Starting stats thread")
            thread_logger.debug("Command: %s", SYSTEMCTL_STATS_CMD)
            with subprocess.Popen(
                SYSTEMCTL_STATS_CMD, stdout=subprocess.PIPE, text=True
            ) as process:
                while True:
                    assert process.stdout
                    line = ANSI_ESCAPE.sub("", process.stdout.readline())
                    if line == "" and process.poll() is not None:
                        break
                    if line:
                        stat = line.strip().split()
                        if len(stat) > 0 and stat[0].isdigit():
                            pid = int(stat[0])
                            service = next(
                                (
                                    s["name"]
                                    for s in self.known_event_services.values()
                                    if s["pid"] == pid or pid in s["cpids"]
                                ),
                                None,
                            )
                            if service:
                                thread_logger.debug("Read top stat line: %s", line)
                                self.systemctl_stats.put(
                                    stat
                                    + [service]
                                    + [str(self.known_event_services[service]["pid"])]
                                )
                    _rc = process.poll()
        except Exception as ex:
            thread_logger.exception("Error Running Stats thread")
            thread_logger.debug(ex)
            thread_logger.debug("Waiting for main thread to restart this thread")

    def _device_definition(self, service_entry: ServiceEvent) -> ServiceDeviceEntry:
        """Create device definition of a service for each entity for home assistant.

        Parameters
        ----------
        service_entry : ServiceEvent
            The service event with the data to build a device entry config

        Returns
        -------
        ServiceDeviceEntry
            The device entry config

        """
        service = service_entry["name"]
        if not self.cfg["homeassistant_single_device"]:
            return {
                "identifiers": f"{self.cfg['systemctl2mqtt_hostname']}_{self.cfg['mqtt_topic_prefix']}_{service}",
                "name": f"{self.cfg['systemctl2mqtt_hostname']} {self.cfg['mqtt_topic_prefix'].title()} {service}",
                "model": f"{platform.system()} {platform.machine()} {self.systemctl_version}",
            }
        return {
            "identifiers": f"{self.cfg['systemctl2mqtt_hostname']}_{self.cfg['mqtt_topic_prefix']}",
            "name": f"{self.cfg['systemctl2mqtt_hostname']} {self.cfg['mqtt_topic_prefix'].title()}",
            "model": f"{platform.system()} {platform.machine()} {self.systemctl_version}",
        }

    def _reload_services(self) -> None:
        """Reload the service and update all enabled/disabled services."""
        registered_services = []
        for service_status in self._get_services():
            status_str: ServiceEventStatusType
            state_str: ServiceEventStateType

            service = service_status["unit"]
            if self._filter_service(service) and "load" in service_status["load"]:
                if "active" in service_status["active"]:
                    status_str = service_status["sub"]
                    state_str = "on"
                elif "inactive" in service_status["active"]:
                    status_str = service_status["sub"]
                    state_str = "off"
                elif "failed" in service_status["active"]:
                    status_str = service_status["sub"]
                    state_str = "off"
                else:
                    status_str = service_status["sub"]
                    state_str = "off"

                if self.b_events:
                    registered_services.append(service)
                    self._register_service(
                        {
                            "name": service,
                            "description": service_status["description"],
                            "pid": self._pid_for_service(service),
                            "cpids": self._child_pids_for_service(service),
                            "status": status_str,
                            "state": state_str,
                        }
                    )
                    if service in self.pending_destroy_operations:
                        del self.pending_destroy_operations[service]
                        events_logger.debug("Removing pending delete for %s.", service)

        for service in self.known_event_services:
            if (
                service not in self.pending_destroy_operations
                and service not in registered_services
            ):
                events_logger.debug("Mark as pending to delete for %s.", service)
                del self.pending_destroy_operations[service]
                self.pending_destroy_operations[service] = time()

    def _get_services(self) -> list[SystemctlService]:
        """Get services from systemctl.

        Returns
        -------
        list[SystemctlService]
            The services

        """
        systemctl_list = subprocess.run(
            SYSTEMCTL_LIST_CMD, capture_output=True, text=True, check=False
        )
        return [
            service
            for line in systemctl_list.stdout.splitlines()
            for service in json.loads(line)
        ]

    def _pid_for_service(self, service: str) -> int:
        """Get PID for service.

        Parameters
        ----------
        service
            The service

        Returns
        -------
        int
            The PID of the service

        """
        service_pid = subprocess.run(
            SYSTEMCTL_PID_PRE_CMD + [service],
            capture_output=True,
            text=True,
            check=False,
        )
        pid = int(service_pid.stdout.strip())
        return pid

    def _child_pids_for_service(self, service: str) -> list[int]:
        """Get PID for service.

        Parameters
        ----------
        service
            The service

        Returns
        -------
        list[int]
            The child PIDs of the service

        """
        pid = self._pid_for_service(service)

        service_pid = subprocess.run(
            SYSTEMCTL_CHILD_PID_PRE_CMD + [str(pid)] + SYSTEMCTL_CHILD_PID_POST_CMD,
            capture_output=True,
            text=True,
            check=False,
        )
        pids = list(map(int, service_pid.stdout.strip().split()))
        return pids

    def _register_service(self, service_entry: ServiceEvent) -> None:
        """Create discovery topics of service for all entities for home assistant.

        Parameters
        ----------
        service_entry : ServiceEvent
            The service event with the data to register a service

        Raises
        ------
        Systemctl2MqttConnectionError
            If the mqtt client could not send the data

        """
        service = service_entry["name"]
        self.known_event_services[service] = service_entry

        # Events
        registration_topic = self.discovery_binary_sensor_topic.format(
            INVALID_HA_TOPIC_CHARS.sub("_", f"{service}_events")
        )
        events_topic = self.events_topic.format(service)
        registration_packet = ServiceEntry(
            {
                "name": "Events",
                "unique_id": f"{self.cfg['mqtt_topic_prefix']}_{self.cfg['systemctl2mqtt_hostname']}_{registration_topic}",
                "availability_topic": f"{self.cfg['mqtt_topic_prefix']}/{self.cfg['systemctl2mqtt_hostname']}/status",
                "payload_available": "online",
                "payload_not_available": "offline",
                "state_topic": events_topic,
                "value_template": '{{ value_json.state if value_json is not undefined and value_json.state is not undefined else "off" }}',
                "payload_on": "on",
                "payload_off": "off",
                "icon": "mdi:console",
                "unit_of_measurement": None,
                "device": self._device_definition(service_entry),
                "device_class": "running",
                "json_attributes_topic": events_topic,
                "qos": self.cfg["mqtt_qos"],
            }
        )
        self._mqtt_send(
            registration_topic,
            json.dumps(clean_for_discovery(registration_packet)),
            retain=True,
        )
        self._mqtt_send(
            events_topic,
            json.dumps(service_entry),
            retain=True,
        )

        # Stats
        for label, field, device_class, unit, icon in STATS_REGISTRATION_ENTRIES:
            registration_topic = self.discovery_sensor_topic.format(
                INVALID_HA_TOPIC_CHARS.sub("_", f"{service}_{field}_stats")
            )
            stats_topic = self.stats_topic.format(service)
            registration_packet = ServiceEntry(
                {
                    "name": label,
                    "unique_id": f"{self.cfg['mqtt_topic_prefix']}_{self.cfg['systemctl2mqtt_hostname']}_{registration_topic}",
                    "availability_topic": f"{self.cfg['mqtt_topic_prefix']}/{self.cfg['systemctl2mqtt_hostname']}/status",
                    "payload_available": "online",
                    "payload_not_available": "offline",
                    "state_topic": stats_topic,
                    "value_template": f"{{{{ value_json.{ field } if value_json is not undefined and value_json.{ field } is not undefined else None }}}}",
                    "unit_of_measurement": unit,
                    "icon": icon,
                    "payload_on": None,
                    "payload_off": None,
                    "json_attributes_topic": stats_topic,
                    "device_class": device_class,
                    "device": self._device_definition(service_entry),
                    "qos": self.cfg["mqtt_qos"],
                }
            )
            self._mqtt_send(
                registration_topic,
                json.dumps(clean_for_discovery(registration_packet)),
                retain=True,
            )
            self._mqtt_send(
                stats_topic,
                json.dumps({}),
                retain=True,
            )

    def _unregister_service(self, service: str) -> None:
        """Remove all discovery topics of service from home assistant.

        Parameters
        ----------
        service
            The container name unregister a service

        Raises
        ------
        Systemctl2MqttConnectionError
            If the mqtt client could not send the data

        """
        # Events
        self._mqtt_send(
            self.discovery_binary_sensor_topic.format(
                INVALID_HA_TOPIC_CHARS.sub("_", f"{service}_events")
            ),
            "",
            retain=True,
        )
        self._mqtt_send(
            self.events_topic.format(service),
            "",
            retain=True,
        )

        # Stats
        for _, field, _, _, _ in STATS_REGISTRATION_ENTRIES:
            self._mqtt_send(
                self.discovery_sensor_topic.format(
                    INVALID_HA_TOPIC_CHARS.sub("_", f"{service}_{field}_stats")
                ),
                "",
                retain=True,
            )
        self._mqtt_send(
            self.stats_topic.format(service),
            "",
            retain=True,
        )

    def _match_service(self, service: str, to_check: str) -> bool:
        """Match a service to a value.

        Parameters
        ----------
        service
            The service to match
        to_check
            The string to check it with

        Returns
        -------
        bool
            Whether the service matches the string

        """
        return (
            service in (to_check, f"{to_check}.service")
            or re.compile(to_check).match(service) is not None
        )

    def _filter_service(self, service: str) -> bool:
        """Filter a service to whitelist and blacklist.

        Parameters
        ----------
        service
            The service to match

        Returns
        -------
        bool
            Whether the service should be considered

        """
        if len(self.cfg["service_whitelist"]) > 0:
            for to_check in self.cfg["service_whitelist"]:
                if self._match_service(service, to_check):
                    events_logger.debug(
                        "Match service '%s' with whitelist entry: %s", service, to_check
                    )
                    break
            else:
                return False
        for to_check in self.cfg["service_blacklist"]:
            if self._match_service(service, to_check):
                return False
        return True

    def _remove_destroyed_services(self) -> None:
        """Remove any destroyed services that have passed the TTL.

        Raises
        ------
        Systemctl2MqttEventsException
            If anything goes wrong in the processing of the events

        """
        try:
            for (
                service,
                destroyed_at,
            ) in self.pending_destroy_operations.copy().items():
                if time() - destroyed_at > self.cfg["destroyed_service_ttl"]:
                    main_logger.info("Removing service %s from MQTT.", service)
                    self._unregister_service(service)
                    del self.pending_destroy_operations[service]
        except Exception as e:
            raise Systemctl2MqttEventsException(
                "Could not remove destroyed services"
            ) from e

    def _handle_events_queue(self) -> None:
        """Check if any event is present in the queue and process it.

        Raises
        ------
        Systemctl2MqttEventsException
            If anything goes wrong in the processing of the events

        """
        event = {}

        systemctl_events_qsize = self.systemctl_events.qsize()
        try:
            if self.b_events:
                event = self.systemctl_events.get(block=False)
            events_logger.debug("Events queue length: %s", systemctl_events_qsize)
        except Empty:
            # No data right now, just move along.
            pass

        if self.b_events and systemctl_events_qsize > 0:
            if event:
                try:
                    service: str = event["UNIT"]
                    events_logger.debug(
                        "Have an event to process for Service: %s", service
                    )

                    if event["MESSAGE"] == "Reloading.":
                        self._reload_services()

                    if "JOB_TYPE" in event:
                        if "JOB_RESULT" not in event:
                            events_logger.debug(
                                "Skip pending event for service %s",
                                service,
                            )

                        if event["JOB_TYPE"] == "start" and "JOB_RESULT" in event:
                            events_logger.info("Service %s has been started.", service)
                            self.known_event_services[service]["status"] = (
                                "running" if event["JOB_RESULT"] == "done" else "failed"
                            )
                            self.known_event_services[service]["state"] = "on"
                            self.known_event_services[service]["pid"] = (
                                self._pid_for_service(service)
                            )

                        elif event["JOB_TYPE"] == "stop" and "JOB_RESULT" in event:
                            # Add this service to pending_destroy_operations.
                            events_logger.info("Service %s has been stopped.", service)
                            self.known_event_services[service]["status"] = (
                                "exited" if event["JOB_RESULT"] == "done" else "failed"
                            )
                            self.known_event_services[service]["state"] = "off"

                        elif event["JOB_TYPE"] == "restart" and "JOB_RESULT" in event:
                            events_logger.info("Service %s has restarted.", service)
                            self.known_event_services[service]["status"] = (
                                "exited" if event["JOB_RESULT"] == "done" else "failed"
                            )
                            self.known_event_services[service]["state"] = "off"

                        else:
                            events_logger.debug(
                                "Unknown event: %s",
                                event.get("JOB_TYPE", "--event not found--"),
                            )

                    else:
                        events_logger.debug(
                            "Skip line: %s", event.get("MESSAGE", str(event))
                        )

                except Exception as ex:
                    events_logger.exception("Error parsing line: %s", event)
                    events_logger.exception("Error of parsed line:")
                    events_logger.debug(ex)
                    raise Systemctl2MqttEventsException(
                        f"Error parsing line: {event}"
                    ) from ex

                events_logger.debug("Sending mqtt payload")
                self._mqtt_send(
                    self.events_topic.format(service),
                    json.dumps(self.known_event_services[service]),
                    retain=True,
                )

    def _handle_stats_queue(self) -> None:
        """Check if any stat is present in the queue and process it.

        Raises
        ------
        Systemctl2MqttStatsException
            If anything goes wrong in the processing of the stats

        """
        stat = []
        send_mqtt = False

        systemctl_stats_qsize = self.systemctl_stats.qsize()
        try:
            if self.b_stats:
                stat = self.systemctl_stats.get(block=False)
            stats_logger.debug("Stats queue length: %s", systemctl_stats_qsize)
        except Empty:
            # No data right now, just move along.
            return

            #################################
            # Examples:
            #    PID USER      PR  NI    VIRT    RES    SHR S  %CPU  %MEM     TIME+ COMMAND
            # 506213 root      20   0  365920  65232  35840 S  16.8   1.6 151:22.70 ffmpeg
            # 506212 root      20   0  772704  64000  45056 S   4.0   1.5  32:58.94 rpicam-vid
            #    736 root      20   0  259264  19456   5120 S   2.0   0.5      7,30 python
            #
            #      0    1       2   3       4      5      6 7     8     9        10 11
            #
            # Index -2: service name
            # Index -1: parent pid of the service
            #################################

        if self.b_stats and systemctl_stats_qsize > 0:
            if stat and len(stat) > 0:
                try:
                    pid = int(stat[0])
                    ppid = int(stat[-1])
                    service: str = stat[-2]
                    stats_logger.debug(
                        "Have a Stat to process for service: %s (%s)", service, pid
                    )

                    if service not in self.known_stat_services:
                        self.known_stat_services[service] = {}
                        self.last_stat_services[service] = {}
                    if pid not in self.known_stat_services[service]:
                        self.known_stat_services[service][pid] = ServiceStatsRef(
                            {"last": datetime.datetime(2020, 1, 1)}
                        )

                    check_date = datetime.datetime.now() - datetime.timedelta(
                        seconds=self.cfg["stats_record_seconds"]
                    )
                    pid_date = self.known_stat_services[service][pid]["last"]
                    stats_logger.debug("Compare dates %s %s", check_date, pid_date)

                    if pid_date <= check_date:
                        # To reduce traffic, only send for the parent pid
                        send_mqtt = ppid == pid

                        stats_logger.info("Processing %s (%d) stats", service, pid)
                        self.known_stat_services[service][pid]["last"] = (
                            datetime.datetime.now()
                        )
                        # delta_seconds = (
                        #     self.known_stat_services[service][pid]["last"] - container_date
                        # ).total_seconds()

                        pid_stats = PIDStats(
                            {
                                "pid": pid,
                                "cpu": float(stat[8]),
                                "memory": float(stat[5]) / 1024,  # KB --> MB
                            }
                        )
                        stats_logger.debug("Printing pid stats: %s", pid_stats)

                        service_stats = ServiceStats(
                            {
                                "name": service,
                                "host": self.cfg["systemctl2mqtt_hostname"],
                                "cpu": 0,
                                "memory": 0,
                                "pid_stats": self.last_stat_services[service][
                                    "pid_stats"
                                ]
                                if self.last_stat_services[service]
                                else {},
                            }
                        )
                        service_stats["pid_stats"][pid] = pid_stats

                        for pid_stat in service_stats["pid_stats"].values():
                            service_stats["memory"] += pid_stat["memory"]
                            service_stats["cpu"] += pid_stat["cpu"]

                        self.last_stat_services[service] = service_stats
                    else:
                        stats_logger.debug(
                            "Not processing record as duplicate record or too young: %s ",
                            service,
                        )

                except Exception as ex:
                    stats_logger.exception("Error parsing line: %s", str(stat))
                    stats_logger.exception("Error of parsed line:")
                    stats_logger.debug(ex)
                    raise Systemctl2MqttStatsException(
                        f"Error parsing line: {str(stat)}"
                    ) from ex

                if send_mqtt:
                    stats_logger.debug(
                        "Printing service stats: %s", self.last_stat_services[service]
                    )

                    child_pids = self._child_pids_for_service(service)
                    self.known_event_services[service]["cpids"] = child_pids
                    # Need to iterate keys beforehand to avoid "RuntimeError: dictionary changed size during iteration"
                    pids = list(self.last_stat_services[service]["pid_stats"].keys())
                    if len(pids) > 0:
                        stats_logger.debug(
                            "Checking for child pids of exited threads to clean up for service: %s",
                            service,
                        )
                        for pid in pids:
                            if int(pid) != ppid and pid not in child_pids:
                                stats_logger.info(
                                    "Cleanup child pid (%d) of service: %s",
                                    pid,
                                    service,
                                )
                                del self.last_stat_services[service]["pid_stats"][pid]

                    stats_logger.debug("Sending mqtt payload")
                    self._mqtt_send(
                        self.stats_topic.format(service),
                        json.dumps(self.last_stat_services[service]),
                        retain=False,
                    )


def main() -> None:
    """Run main entry for the Systemctl2mqtt executable.

    Raises
    ------
    Systemctl2MqttConfigException
        Bad config
    Systemctl2MqttConnectionException
        If anything with the mqtt connection goes wrong

    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "--name",
        default=socket.gethostname(),
        help="A descriptive name for the docker being monitored (default: hostname)",
    )
    parser.add_argument(
        "--host",
        default="localhost",
        help="Hostname or IP address of the MQTT broker (default: localhost)",
    )
    parser.add_argument(
        "--port",
        default=MQTT_PORT_DEFAULT,
        type=int,
        help="Port or IP address of the MQTT broker (default: 1883)",
    )
    parser.add_argument(
        "--client",
        default=f"{socket.gethostname()}_{MQTT_CLIENT_ID_DEFAULT}",
        help=f"Client Id for MQTT broker client (default: <hostname>_{MQTT_CLIENT_ID_DEFAULT})",
    )
    parser.add_argument(
        "--username",
        default=None,
        help="Username for MQTT broker authentication (default: None)",
    )
    parser.add_argument(
        "--password",
        default=None,
        help="Password for MQTT broker authentication (default: None)",
    )
    parser.add_argument(
        "--qos",
        default=MQTT_QOS_DEFAULT,
        type=int,
        help="QOS for MQTT broker authentication (default: 1)",
        choices=range(0, 3),
    )
    parser.add_argument(
        "--timeout",
        default=MQTT_TIMEOUT_DEFAULT,
        type=int,
        help=f"The timeout for the MQTT connection. (default: {MQTT_TIMEOUT_DEFAULT}s)",
    )
    parser.add_argument(
        "--ttl",
        default=DESTROYED_SERVICE_TTL_DEFAULT,
        type=int,
        help=f"How long, in seconds, before destroyed services are removed from Home Assistant. Services won't be removed if the service is restarted before the TTL expires. (default: {DESTROYED_SERVICE_TTL_DEFAULT}s)",
    )
    parser.add_argument(
        "--homeassistant-prefix",
        default=HOMEASSISTANT_PREFIX_DEFAULT,
        help=f"MQTT discovery topic prefix (default: {HOMEASSISTANT_PREFIX_DEFAULT})",
    )
    parser.add_argument(
        "--homeassistant-single-device",
        action="store_true",
        help=f"Group all entities by a single device in Home Assistant instead of one device per entity (default: {HOMEASSISTANT_SINGLE_DEVICE_DEFAULT})",
    )
    parser.add_argument(
        "--topic-prefix",
        default=MQTT_TOPIC_PREFIX_DEFAULT,
        help=f"MQTT topic prefix (default: {MQTT_TOPIC_PREFIX_DEFAULT})",
    )
    parser.add_argument(
        "--whitelist",
        help="Service whitelist",
        type=str,
        action="append",
        nargs="?",
        const="",
        default=None,
        metavar="SERVICE",
    )
    parser.add_argument(
        "--blacklist",
        help="Service blacklist",
        type=str,
        action="append",
        nargs="?",
        const="",
        default=None,
        metavar="SERVICE",
    )
    parser.add_argument(
        "-v",
        "--verbosity",
        action="count",
        default=0,
        help="Log verbosity (default: 0 (log output disabled))",
    )
    parser.add_argument(
        "--events",
        help="Publish Events",
        action="store_true",
    )
    parser.add_argument(
        "--stats",
        help="Publish Stats",
        action="store_true",
    )
    parser.add_argument(
        "--interval",
        help=f"The number of seconds to record state and make an average (default: {STATS_RECORD_SECONDS_DEFAULT})",
        type=int,
        default=STATS_RECORD_SECONDS_DEFAULT,
    )

    try:
        args = parser.parse_args()
    except argparse.ArgumentError as e:
        raise Systemctl2MqttConfigException("Cannot start due to bad config") from e
    except argparse.ArgumentTypeError as e:
        raise Systemctl2MqttConfigException(
            "Cannot start due to bad config data type"
        ) from e
    log_level = ["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "DEBUG"][
        args.verbosity
    ]
    cfg = Systemctl2MqttConfig(
        {
            "log_level": log_level,
            "destroyed_service_ttl": args.ttl,
            "homeassistant_prefix": args.homeassistant_prefix,
            "homeassistant_single_device": args.homeassistant_single_device,
            "systemctl2mqtt_hostname": args.name,
            "mqtt_client_id": args.client,
            "mqtt_user": args.username,
            "mqtt_password": args.password,
            "mqtt_host": args.host,
            "mqtt_port": args.port,
            "mqtt_timeout": args.timeout,
            "mqtt_topic_prefix": args.topic_prefix,
            "service_whitelist": args.whitelist or [],
            "service_blacklist": args.blacklist or [],
            "mqtt_qos": args.qos,
            "enable_events": args.events,
            "enable_stats": args.stats,
            "stats_record_seconds": args.interval,
        }
    )

    Systemctl2mqtt = Systemctl2Mqtt(
        cfg,
        do_not_exit=False,
    )

    Systemctl2mqtt.loop_busy()
