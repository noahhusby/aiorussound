import re

from aiorussound.const import FeatureFlag
from aiorussound.rio import UnsupportedFeature

_fw_pattern = re.compile(r"^(?P<major>\d{1,2})\.(?P<minor>\d{2})\.(?P<patch>\d{2})$")


def check_feature_flag(firmware_ver: str, flag: FeatureFlag) -> None:
    if not is_fw_version_higher(firmware_ver, flag.value):
        raise UnsupportedFeature(f"Russound feature {flag} not supported in firmware {firmware_ver}")


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
