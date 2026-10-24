"""Constants for the Rixens integration."""

DOMAIN = "rixens"

# Configuration keys
CONF_HOST = "host"
CONF_PORT = "port"

# Defaults
DEFAULT_PORT = 80

# Fan speed constants
FAN_SPEED_MIN = 10  # Docs allow 0-100; meaning of 0 unconfirmed, see #72
FAN_SPEED_MAX = 100
FAN_SPEED_STEP = 10
FAN_SPEED_AUTO = 999  # act=2 value and documented <fanspeed> value for Auto

# Fan mode values reported by the device XML (<fanspeed> element).
# Firmware 1.205 reports "Auto"; a documented 999 is normalized to it by the API.
# "Off" is not in the docs but is kept in case older firmware sends it, see #72.
DEVICE_FAN_OFF = "Off"
DEVICE_FAN_AUTO = "Auto"

# Fan mode values used in the HA climate entity
FAN_MODE_OFF = "off"
FAN_MODE_AUTO = "auto"

# Temperature constants (Celsius)
TEMP_MIN = 5
TEMP_MAX = 35
TEMP_STEP = 0.5

# Fuel consumption constants
CONF_FUEL_DOSE = "fuel_dose"
DEFAULT_FUEL_DOSE = 0.0297979798  # ml per dose (improved accuracy)
