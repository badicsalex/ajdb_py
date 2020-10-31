# Copyright 2020, Alex Badics, All Rights Reserved
from pathlib import Path
from typing import Any, Optional, TypeVar, Generic, Type
from hashlib import md5
import json
import gzip

import attr

from hun_law import dict2object
from ajdb.config import AJDBConfig
from ajdb.utils import LruDict


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


_T = TypeVar('_T')


class CachedTypedObjectStorage(Generic[_T]):
    converter: 'dict2object.Converter[_T]'

    def __init__(self, stored_type: Type[_T], prefix: str, cache_size: int) -> None:
        self.object_storage = ObjectStorage(prefix)
        self.converter = dict2object.get_converter(stored_type)
        self.cache: LruDict[str, _T] = LruDict(cache_size)

    def load(self, key: str) -> _T:
        if key in self.cache:
            return self.cache[key]
        result = self.converter.to_object(self.object_storage.load(key))
        self.cache[key] = result
        return result

    def save(self, data: _T) -> str:
        data_as_dict = self.converter.to_dict(data)
        key = self.object_storage.save(data_as_dict)
        self.cache[key] = data
        return key
