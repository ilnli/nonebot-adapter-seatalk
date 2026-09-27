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

        entry = next(name for name in names if name.endswith("/entry_points.txt"))
        assert "n-p-alc.uniseg.adapters" in archive.read(entry).decode()
        assert (
            "nonebot.adapters.seatalk.integrations.alconna:Loader" in archive.read(entry).decode()
        )
        metadata = archive.read(next(name for name in names if name.endswith("/METADATA"))).decode()
        assert "file://" not in metadata
        assert "portal_session" not in metadata


def test_base_and_loader_import_without_alconna():
    import subprocess
    import sys

    script = """
import importlib.abc
import sys
class NoAlconna(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith('nonebot_plugin_alconna'):
            raise AssertionError('base import must not load Alconna')
sys.meta_path.insert(0, NoAlconna())
import nonebot.adapters
"""
    if not os.environ.get("SEATALK_TEST_INSTALLED"):
        from pathlib import Path

        source = str(Path(__file__).resolve().parents[1] / "nonebot" / "adapters")
        script += f"nonebot.adapters.__path__.append({source!r})\n"
    script += "from nonebot.adapters.seatalk import Adapter\n"
    script += "from nonebot.adapters.seatalk.integrations.alconna import Loader\n"
    script += "assert Loader().get_adapter().value == 'SeaTalk'\n"
    subprocess.run([sys.executable, "-c", script], check=True)
