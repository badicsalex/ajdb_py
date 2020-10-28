# Copyright 2020, Alex Badics, All Rights Reserved
import os
from flask import Flask
from .index import INDEX_BLUEPRINT


class Config:
    SECRET_KEY = os.urandom(24)


class DevelopmentConfig(Config):
    ENV = 'development'
    DEBUG = 1


class TestConfig(Config):
    TESTING = 1


def create_app(config: Config) -> Flask:
    # create and configure the app
    app = Flask(__name__)
    app.config.from_object(config)
    app.register_blueprint(INDEX_BLUEPRINT)
    return app
