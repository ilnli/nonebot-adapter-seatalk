import os
from zipfile import ZipFile

import pytest


def test_wheel_contains_only_adapter_and_metadata():
    wheel = os.environ.get("SEATALK_TEST_WHEEL")
    if not wheel:
        pytest.skip("Set SEATALK_TEST_WHEEL for the built-artifact check")
    with ZipFile(wheel) as archive:
        names = archive.namelist()
        assert "nonebot/adapters/seatalk/py.typed" in names
        assert "nonebot/adapters/seatalk/adapter.py" in names
        assert "nonebot/__init__.py" not in names
        assert all(
            name.startswith("nonebot/adapters/seatalk/") or ".dist-info/" in name for name in names
        )
        assert not any("seatalk_oapi_sdk" in name or name.endswith(".env") for name in names)
