import re

from aiorussound.const import FeatureFlag, VERSIONS_BY_FLAGS
from aiorussound.exceptions import UnsupportedFeature

_fw_pattern = re.compile(r"^(?P<major>\d{1,2})\.(?P<minor>\d{2})\.(?P<patch>\d{2})$")


def raise_unsupported_feature(api_ver: str, flag: FeatureFlag) -> None:
    if not is_feature_supported(api_ver, flag):
        raise UnsupportedFeature(f"Russound feature {flag} not supported in api v{api_ver}")


def is_feature_supported(api_ver: str, flag: FeatureFlag) -> bool:
    return is_fw_version_higher(api_ver, VERSIONS_BY_FLAGS[flag])


def is_fw_version_higher(fw_a: str, fw_b: str) -> bool:
    """Returns true if fw_a is greater than or equal to fw_b"""
    a_match = _fw_pattern.match(fw_a)
    b_match = _fw_pattern.match(fw_b)

    if not (a_match and b_match):
        return False

    a_major = int(a_match.group('major'))
    a_minor = int(a_match.group('minor'))
    a_patch = int(a_match.group('patch'))

    b_major = int(b_match.group('major'))
    b_minor = int(b_match.group('minor'))
    b_patch = int(b_match.group('patch'))

    return (a_major > b_major) or (a_major == b_major and a_minor > b_minor) or (
            a_major == b_major and a_minor == b_minor and a_patch >= b_patch)


def form_zone_device_str(controller_id: int, zone_id: int) -> str:
    return f"C[{controller_id}].Z[{zone_id}]"


def form_source_device_str(controller_id: int, source_id: int) -> str:
    return f"C[{controller_id}].S[{source_id}]"
