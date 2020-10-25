# Copyright 2020, Alex Badics, All Rights Reserved
from pathlib import Path

_THIS_DIR = Path(__file__).parent


class AJDBConfig:
    STORAGE_PATH = _THIS_DIR.parent / 'cache'
