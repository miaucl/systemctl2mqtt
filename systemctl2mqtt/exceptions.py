"""systemctl2mqtt exceptions."""


class Systemctl2MqttException(Exception):
    """General processing exception occurred."""


class Systemctl2MqttConfigException(Systemctl2MqttException):
    """Config exception occurred."""


class Systemctl2MqttConnectionException(Systemctl2MqttException):
    """Connection exception occurred."""


class Systemctl2MqttEventsException(Systemctl2MqttException):
    """Events processing exception occurred."""


class Systemctl2MqttStatsException(Systemctl2MqttException):
    """Stats processing exception occurred."""
