import json
import os
from pathlib import Path

import pytest
from nonebot.log import logger
from nonebug import NONEBOT_INIT_KWARGS

import nonebot.adapters

# NoneBot is a regular package. Like official adapters, source tests add only
# the adapter search path; clean-wheel tests explicitly disable this hook.
if not os.environ.get("SEATALK_TEST_INSTALLED"):
    nonebot.adapters.__path__.append(
        str(Path(__file__).resolve().parents[1] / "nonebot" / "adapters")
    )


def pytest_configure(config):
    config.stash[NONEBOT_INIT_KWARGS] = {"driver": "~none", "nickname": {"bot"}}


@pytest.fixture
def case():
    def load(name):
        return json.loads((Path(__file__).parent / "fixtures" / f"{name}.json").read_text())

    return load


@pytest.fixture
def seatalk_logs():
    records = []
    sink = logger.add(records.append, format="{message}", level="DEBUG", colorize=True)
    try:
        yield records
    finally:
        logger.remove(sink)
