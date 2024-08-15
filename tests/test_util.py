"""Tests for the Russound RIO package."""

from contextlib import nullcontext

import pytest

from aiorussound.const import FeatureFlag
from aiorussound.exceptions import UnsupportedFeatureError
from aiorussound.util import (
    controller_device_str,
    get_max_zones,
    is_feature_supported,
    is_fw_version_higher,
    raise_unsupported_feature,
    source_device_str,
    zone_device_str,
)


@pytest.mark.parametrize(
    "version,expectation",
    [("1.05.00", nullcontext()), ("1.03.00", pytest.raises(UnsupportedFeatureError))],
)
def test_raise_unsupported_feature(version: str, expectation: Exception) -> None:
    """Test whether raise_unsupported_feature raises an exception
    under the proper circumstances.
    """
    with expectation:
        raise_unsupported_feature(version, FeatureFlag.PROPERTY_CTRL_TYPE)


@pytest.mark.parametrize("version,result", [("1.05.00", True), ("1.03.00", False)])
def test_is_feature_supported(version: str, result: bool) -> None:
    """Test whether features are being properly detected by version."""
    assert is_feature_supported(version, FeatureFlag.PROPERTY_CTRL_TYPE) == result


@pytest.mark.parametrize(
    "version,result",
    [("1.10.00", True), ("1.03.00", True), ("1.10.01", False), ("1.12.00", False)],
)
def test_is_fw_version_higher(version: str, result: bool) -> None:
    """Test whether firmware versions are being properly compared."""
    assert is_fw_version_higher("1.10.00", version) == result


def test_is_fw_version_higher_wrong_format() -> None:
    """Test if incorrect version formats are being detected."""
    assert is_fw_version_higher("1.234.44", "1.10.00") is False
    assert is_fw_version_higher("abcd", "1.10.00") is False


@pytest.mark.parametrize("controller_id,result", [(1, "C[1]"), (6, "C[6]")])
def test_controller_device_str(controller_id: int, result: str) -> None:
    """Test if the controller device string is correct."""
    assert controller_device_str(controller_id) == result


@pytest.mark.parametrize(
    "controller_id,zone_id,result", [(1, 2, "C[1].Z[2]"), (6, 3, "C[6].Z[3]")]
)
def test_zone_device_str(controller_id: int, zone_id: int, result: str) -> None:
    """Test if the zone device string is correct."""
    assert zone_device_str(controller_id, zone_id) == result


@pytest.mark.parametrize("source_id,result", [(1, "S[1]"), (2, "S[2]")])
def test_source_device_str(source_id: int, result: str) -> None:
    """Test if the source device string is correct."""
    assert source_device_str(source_id) == result


@pytest.mark.parametrize(
    "model,max_zones",
    [
        ("MCA-C5", 8),
        ("MCA-88", 8),
        ("MCA-66", 6),
        ("MCA-C3", 6),
        ("MBX-PRE", 1),
        ("Other", 1),
    ],
)
def test_get_max_zones(model: str, max_zones: int) -> None:
    """Test if the maximum number of zones is correct."""
    assert get_max_zones(model) == max_zones
