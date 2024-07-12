import json

MAX_ZONES_KEY = "max_zones"
RNET_SUPPORT_KEY = "rnet_support"

# Each controller is separated to support future differences in features
with open('aiorussound/devices.json') as json_file:
    CONTROLLER_ATTR = json.load(json_file)