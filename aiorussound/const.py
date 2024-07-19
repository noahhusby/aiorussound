import json
from enum import Enum

MAX_ZONES_KEY = "max_zones"
RNET_SUPPORT_KEY = "rnet_support"

MINIMUM_API_SUPPORT = "1.03.00"


# TODO: Add features 1.06.00 and up
class FeatureFlag(Enum):
    DMS_3_1 = 1
    KEY_CODE_EVENT = 2
    PROPERTY_IP_ADDRESS = 3
    SUPPORT_SHUFFLE = 4
    COMMAND_MM_CLOSE = 5
    SUPPORT_PAGE_ZONE = 6
    SUPPORT_REPEAT = 7
    PROPERTY_CTRL_TYPE = 8
    PROPERTY_SYS_LANG = 9


# Each controller is separated to support future differences in features
with open('aiorussound/devices.json') as json_file:
    CONTROLLER_ATTR = json.load(json_file)
