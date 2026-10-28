"""Constants for the Rixens integration."""

DOMAIN = "rixens"

# Configuration keys
CONF_HOST = "host"
CONF_PORT = "port"

# Defaults
DEFAULT_PORT = 80

# Fan speed constants
# act=2 accepts 0-100, but 0 sets a 0% speed rather than turning the fan off
# (Rixen's, #72); the fan is turned off with act=8 instead
FAN_SPEED_MIN = 10
FAN_SPEED_MAX = 100
FAN_SPEED_STEP = 10
FAN_SPEED_AUTO = 999  # act=2 value for Auto (also documented for <fanspeed>)

# Fan mode values reported by the device XML (<fanspeed> element). Rixen's
# confirmed current firmware sends "Off", a percentage or "Auto" (#72); a
# documented 999 is still normalized to "Auto" by the API.
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
DEFAULT_FUEL_DOSE = 0.02952  # ml per dose
