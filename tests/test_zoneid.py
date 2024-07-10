from aiorussound import ZoneID


def test_device_str():
    assert ZoneID(1).device_str() == "C[1].Z[1]"
    assert ZoneID(7).device_str() == "C[1].Z[7]"
    assert ZoneID(1, 2).device_str() == "C[2].Z[1]"
    assert ZoneID(7, 4).device_str() == "C[4].Z[7]"
