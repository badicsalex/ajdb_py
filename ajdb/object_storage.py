# Copyright 2020, Alex Badics, All Rights Reserved
from pathlib import Path
from typing import Any, Optional
from hashlib import md5
import json
import gzip

import attr

from ajdb.config import AJDBConfig


@attr.s(slots=True, frozen=True, auto_attribs=True)
class ObjectStorage:
    prefix: str

    def save(self, data: Any, *, key: Optional[str] = None) -> str:
        data_as_json_bytes = json.dumps(data, ensure_ascii=False, sort_keys=True).encode('utf-8')
        if key is None:
            # MD5 is used instead of a "fast" hash, because MD5 is actually
            # quite fast, and on pypy pure python hash functions are pretty slow.
            key = md5(data_as_json_bytes).hexdigest()
        object_path = self.get_object_path(key)
        object_path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(object_path, 'wb') as f:
            f.write(data_as_json_bytes)
        return key

    def load(self, key: str) -> Any:
        object_path = self.get_object_path(key)
        if not object_path.is_file():
            raise KeyError("Object {}/{} does not exist".format(self.prefix, key))
        with gzip.open(self.get_object_path(key), 'r') as f:
            return json.load(f)

    def get_object_path(self, key: str) -> Path:
        return AJDBConfig.STORAGE_PATH / self.prefix / key[0] / key[1] / (key[2:] + '.json.gz')
