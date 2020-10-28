import pytest
from flask import Flask
from flask.testing import FlaskClient
from ajdb_web.app import create_app, TestConfig


@pytest.fixture
def app() -> Flask:
    return create_app(TestConfig())


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    # That's the point of fixtures, pylint, ugh.
    # pylint: disable=redefined-outer-name
    return app.test_client()
