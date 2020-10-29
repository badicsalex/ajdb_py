from typing import Iterable
from pathlib import Path

import pytest
# For typing only
from _pytest.monkeypatch import MonkeyPatch

from flask import Flask
from flask.testing import FlaskClient

from hun_law.utils import Date
from ajdb_web.app import create_app, TestConfig
from ajdb.structure import ActSet
from ajdb.database import Database
from ajdb.config import AJDBConfig

from .data import TEST_ACT1, TEST_ACT2


@pytest.fixture
def app() -> Flask:
    return create_app(TestConfig())


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    # That's the point of fixtures, pylint, ugh.
    # pylint: disable=redefined-outer-name
    return app.test_client()


@pytest.fixture
def fake_db(tmp_path: Path, monkeypatch: MonkeyPatch) -> Iterable[ActSet]:
    monkeypatch.setattr(AJDBConfig, "STORAGE_PATH", tmp_path)
    act_set = ActSet(acts=(TEST_ACT1, TEST_ACT2))
    Database.save_act_set(act_set, Date.today())
    yield act_set
