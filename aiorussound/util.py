"""Asynchronous Python client for Russound RIO."""

import re

from aiorussound.const import VERSIONS_BY_FLAGS, FeatureFlag
from aiorussound.exceptions import UnsupportedFeatureError

_fw_pattern = re.compile(r"^(?P<major>\d{1,2})\.(?P<minor>\d{2})\.(?P<patch>\d{2})$")


def raise_unsupported_feature(api_ver: str, flag: FeatureFlag) -> None:
    """Raise an UnsupportedFeature exception if the specified feature is not supported
    in the provided version.
    """
    if not is_feature_supported(api_ver, flag):
        err = f"Russound feature {flag} not supported in api v{api_ver}"
        raise UnsupportedFeatureError(err)


def is_feature_supported(api_ver: str, flag: FeatureFlag) -> bool:
    """Return true if the feature is supported in the provided version,
    false otherwise.
    """
    return is_fw_version_higher(api_ver, VERSIONS_BY_FLAGS[flag])


def is_fw_version_higher(fw_a: str, fw_b: str) -> bool:
    """Return true if fw_a is greater than or equal to fw_b."""
    a_match = _fw_pattern.match(fw_a)
    b_match = _fw_pattern.match(fw_b)

    if not (a_match and b_match):
        return False

    a_major = int(a_match.group("major"))
    a_minor = int(a_match.group("minor"))
    a_patch = int(a_match.group("patch"))

    b_major = int(b_match.group("major"))
    b_minor = int(b_match.group("minor"))
    b_patch = int(b_match.group("patch"))

    return (
        (a_major > b_major)
        or (a_major == b_major and a_minor > b_minor)
        or (a_major == b_major and a_minor == b_minor and a_patch >= b_patch)
    )


def controller_device_str(controller_id: int) -> str:
    """Return a string representation of the specified controller device."""
    return f"C[{controller_id}]"


def zone_device_str(controller_id: int, zone_id: int) -> str:
    """Return a string representation of the specified zone device."""
    return f"C[{controller_id}].Z[{zone_id}]"


def source_device_str(source_id: int) -> str:
    """Return a string representation of the specified source device."""
    return f"S[{source_id}]"


def get_max_zones(model: str) -> int:
    """Return a maximum number of zones supported by a specific controller."""
    if model in ("MCA-88", "MCA-88X", "MCA-C5"):
        return 8
    if model in ("MCA-66", "MCA-C3"):
        return 6
    return 1


def is_rnet_capable(model: str) -> bool:
    """Return whether a controller is rnet capable."""
    return model in ("MCA-88X", "MCA-88", "MCA-66", "MCA-C5", "MCA-C3")


def map_rio_to_dict(state: dict, branch: str, leaf: str, value: str) -> None:
    """Maps a RIO variable to a python dictionary."""
    path = re.findall(r"\w+\[?\d*]?", branch)
    current = state
    for part in path:
        match = re.match(r"(\w+)\[(\d+)]", part)
        if match:
            key, index = match.groups()
            index = int(index)
            if key not in current:
                current[key] = {}
            if index not in current[key]:
                current[key][index] = {}
            current = current[key][index]
        else:
            if part not in current:
                current[part] = {}
            current = current[part]

    # Set the leaf and value in the final dictionary location
    current[leaf] = value
