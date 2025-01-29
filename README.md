# systemctl2mqtt - Deliver systemctl status information over MQTT

[![Mypy](https://github.com/miaucl/systemctl2mqtt/actions/workflows/mypy.yaml/badge.svg)](https://github.com/miaucl/systemctl2mqtt/actions/workflows/mypy.yaml)
[![Ruff](https://github.com/miaucl/systemctl2mqtt/actions/workflows/ruff.yml/badge.svg)](https://github.com/miaucl/systemctl2mqtt/actions/workflows/ruff.yml)
[![Markdownlint](https://github.com/miaucl/systemctl2mqtt/actions/workflows/markdownlint.yml/badge.svg)](https://github.com/miaucl/systemctl2mqtt/actions/workflows/markdownlint.yml)
[![Publish](https://github.com/miaucl/systemctl2mqtt/actions/workflows/publish.yml/badge.svg)](https://github.com/miaucl/systemctl2mqtt/actions/workflows/publish.yml)

This program uses `journalctl` and `systemctl` to watch for changes in your services, and `top` for metrics about those services, and delivers current status to MQTT. It will also publish Home Assistant MQTT Discovery messages so that (binary) sensors automatically show up in Home Assistant.

The focus lies on long-running services with continuous uptime, instead of single or one-shot services, as the stats being reported as well as the child PIDs being refreshed every `stats_record_seconds`. For services with a lifespan comparable to this interval, the reported stats will not be accurate. Further, as the library uses `top` and matches the services with their respective PIDs, including child PIDs from subprocesses, it is also not suited for monitoring services which spawn regularly new threads.

_This is part of a family of similar tools:_

* [miaucl/linux2mqtt](https://github.com/miaucl/linux2mqtt)
* [miaucl/docker2mqtt](https://github.com/miaucl/docker2mqtt)
* [miaucl/systemctl2mqtt](https://github.com/miaucl/systemctl2mqtt)

## Installation and Deployment

It is available as python package on [pypi/systemctl2mqtt](https://pypi.org/p/systemctl2mqtt).

### Pypi package

[![PyPI version](https://badge.fury.io/py/systemctl2mqtt.svg)](https://pypi.org/p/systemctl2mqtt)

```bash
pip install systemctl2mqtt
systemctl2mqtt --name MySystemName --events -vvvvv
```

Usage

```python
from systemctl2mqtt import systemctl2Mqtt, DEFAULT_CONFIG

cfg = Systemctl2MqttConfig({ 
  **DEFAULT_CONFIG,
  "host": "mosquitto",
  "enable_events": True
})

try:
  systemctl2mqtt = Systemctl2Mqtt(cfg)
  systemctl2mqtt.loop_busy()

except Exception as ex:
  # Do something
```

## Default Configuration

You can use environment variables to control the behavior.

| Config | Default | Description |
|--------|---------|-------------|
| `log_level` | `INFO` | Set to `DEBUG,INFO,WARN,ERROR,CRITICAL` to enable different levels of verbosity. |
| `systemctl2mqtt_hostname` | systemctl2mqtt Hostname | The hostname of your host, if you want to overwrite it.  |
| `homeassistant_prefix` | `homeassistant` | The prefix for Home Assistant discovery. Must be the same as `discovery_prefix` in your Home Assistant configuration. |
| `homeassistant_single_device` | `false` | Group all entities by a single device in Home Assistant instead of one device per entity. |
| `mqtt_client_id` | `mqtt2discord` | The client id to send to the MQTT broker. |
| `mqtt_host` | `localhost` | The MQTT broker to connect to. |
| `mqtt_port` | `1883` | The port on the broker to connect to. |
| `mqtt_user` | | The user to send to the MQTT broker. Leave unset to disable authentication. |
| `mqtt_password` | | The password to send to the MQTT broker. Leave unset to disable authentication. |
| `mqtt_timeout` | `30` | The timeout for the MQTT connection. |
| `mqtt_topic_prefix` | `systemctl` | The MQTT topic prefix. With the default data will be published to `systemctl/<hostname>`. |
| `mqtt_qos` | `1` | The MQTT QOS level |
| `service_whitelist` | | Define a whitelist for services to consider, if empty, everything is monitored. The entries are either match as literal strings or as regex. |
| `service_blacklist` | | Define a blacklist for services to consider, takes priority over whitelist. The entries are either match as literal strings or as regex. |
| `destroyed_service_ttl` | `86400` | How long, in seconds, before destroyed services are removed from Home Assistant. Services won't be removed if the service is restarted before the TTL expires. |
| `stats_record_seconds` | `30` | The number of seconds to record state and make an average |
| `enable_events` | `0` | 1 Or 0 for processing events |
| `enable_stats` | `0` | 1 Or 0 for processing statistics |

## Consuming The Data

Data is published to the topic `systemctl/<hostname>/events` using JSON serialization. It will arrive whenever a change happens and its type can be inspected in [type_definitions.py](https://github.com/miaucl/systemctl2mqtt/blob/master/systemctl2mqtt/type_definitions.py) or the documentation.

Data is also published to the topic `systemctl/<hostname>/stats` using JSON serialization. It will arrive every `STATS_RECORD_SECONDS` seconds or so can be inspected in [type_definitions.py](https://github.com/miaucl/systemctl2mqtt/blob/master/systemctl2mqtt/type_definitions.py) or the documentation.

## Home Assistant

Once `systemctl2mqtt` is collecting data and publishing it to MQTT, it's rather trivial to use the data in Home Assistant.

A few assumptions:

* **Home Assistant is already configured to use a MQTT broker.** Setting up MQTT and HA is beyond the scope of this documentation. However, there are a lot of great tutorials on YouTube. An external broker (or as add-on) like [Mosquitto](https://mosquitto.org/) will need to be installed and the HA MQTT integration configured.
* **The HA MQTT integration is configured to use `homeassistant` as the MQTT autodiscovery prefix.** This is the default for the integration and also the default for `systemctl2mqtt`. If you have changed this from the default, use the `--prefix` parameter to specify the correct one.
* **You're not using TLS to connect to the MQTT broker.** Currently `systemctl2mqtt` only works with unencrypted connections. Username / password authentication can be specified with the `--username` and `--password` parameters, but TLS encryption is not yet supported.

After you start the service (binary) sensors should show up in Home Assistant immediately. Look for sensors that start with `(binary_)sensor.systemctl`. Metadata about the container will be available as attributes for events, which you can then expose using template sensors if you wish.

![Screenshot of Home Assistant sensor showing status and attributes.](https://raw.githubusercontent.com/miaucl/systemctl2mqtt/master/media/ha_screenshot.png)

## Documentation

Using `mkdocs`, the documentation and reference is generated and available on [github pages](https://miaucl.github.io/systemctl2mqtt/).

## Dev

Setup the dev environment using VSCode, it is highly recommended.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements_dev.txt
```

Install [pre-commit](https://pre-commit.com)

```bash
pre-commit install

# Run the commit hooks manually
pre-commit run --all-files
```

Following VSCode integrations may be helpful:

* [ruff](https://marketplace.visualstudio.com/items?itemName=charliermarsh.ruff)
* [mypy](https://marketplace.visualstudio.com/items?itemName=matangover.mypy)
* [markdownlint](https://marketplace.visualstudio.com/items?itemName=DavidAnson.vscode-markdownlint)

### Releasing

It is only possible to release a _final version_ on the `master` branch. For it to pass the gates of the `publish` workflow, it must have the same version in the `tag`, the `setup.cfg`, the `bring_api/__init__.py` and an entry in the `CHANGELOG.md` file.

To release a prerelease version, no changelog entry is required, but it can only happen on a feature branch (**not** `master` branch). Also, prerelease versions are marked as such in the github release page.

## Credits

This is inspired from my other repo [docker2mqtt](https://github.com/miaucl/docker2mqtt).
