# Copyright 2020, Alex Badics, All Rights Reserved
import json
import gzip
from pathlib import Path

from hun_law.utils import Date
from hun_law import dict2object
from hun_law.structure import Act

from ajdb.config import AJDBConfig
from ajdb.structure import ActSet
from ajdb.utils import LruDict
from ajdb.amender import ActConverter, ActSetAmendmentApplier
from ajdb.indexer import ReferenceReindexer

# TODO: Incremental upgrade:
#       - Find out which acts need to be updated: if any inputs changed, update acts
#           - Put inputs into Act. This is needed anyway (last modified date, and modifying acts)
#       - Collect all input acts (modified or not)
#       - Recompute all acts that need update


class Database:
    CACHE: LruDict[Date, ActSet] = LruDict(16)
    ACT_SET_CONVERTER = dict2object.get_converter(ActSet)

    @classmethod
    def store_hun_law_act_from_path(cls, path: Path) -> Path:
        act_raw = ActConverter.load_hun_law_act(path)
        return cls.store_hun_law_act(act_raw)

    @classmethod
    def store_hun_law_act(cls, act_raw: Act) -> Path:
        save_dir = cls.hun_law_acts_path(act_raw.publication_date)
        save_dir.mkdir(parents=True, exist_ok=True)
        save_path = save_dir / '{}.json.gz'.format(act_raw.identifier)
        ActConverter.save_hun_law_act_json_gz(save_path, act_raw)
        return save_path

    @classmethod
    def add_relevant_hun_law_acts(cls, act_set: ActSet, date: Date) -> ActSet:
        acts_to_add_path = cls.hun_law_acts_path(date)
        if not acts_to_add_path.is_dir():
            return act_set
        acts_to_add = []

        for act_path in cls.hun_law_acts_path(date).iterdir():
            act_raw = ActConverter.load_hun_law_act(act_path)
            act = ActConverter.convert_hun_law_act(act_raw)
            print("Adding {} to the act set".format(act.identifier))
            acts_to_add.append(act)
        if not acts_to_add:
            return act_set
        return act_set.add_acts(acts_to_add)

    @classmethod
    def recompute_date_range(cls, from_date: Date, to_date: Date) -> None:
        date = from_date
        while date <= to_date:
            cls.recompute_at_date(date)
            date = date.add_days(1)

    @classmethod
    def recompute_at_date(cls, date: Date) -> None:
        act_set = cls.load_act_set(date.add_days(-1))

        act_set = cls.add_relevant_hun_law_acts(act_set, date)
        act_set = ActSetAmendmentApplier.apply_all_amendments(act_set, date)
        if act_set.has_unsaved():
            act_set = ReferenceReindexer.reindex_act_set(act_set)
        act_set = act_set.save_all_acts()
        cls.save_act_set(act_set, date)

    @classmethod
    def load_act_set(cls, date: Date) -> ActSet:
        if date in cls.CACHE:
            return cls.CACHE[date]

        path = cls.states_path(date)
        if not path.is_file():
            return ActSet()

        with gzip.open(path, 'rt') as f:
            result: ActSet = cls.ACT_SET_CONVERTER.to_object(json.load(f))

        cls.CACHE[date] = result
        return result

    @classmethod
    def save_act_set(cls, act_set: ActSet, date: Date) -> None:
        cls.CACHE[date] = act_set
        path = cls.states_path(date)
        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, 'wt') as f:
            act_set_dict = cls.ACT_SET_CONVERTER.to_dict(act_set)
            json.dump(act_set_dict, f, indent='  ', sort_keys=True, ensure_ascii=False)

    @classmethod
    def hun_law_acts_path(cls, date: Date) -> Path:
        return AJDBConfig.STORAGE_PATH / 'hun_law_acts/{}/{:02}/{:02}'.format(date.year, date.month, date.day)

    @classmethod
    def states_path(cls, date: Date) -> Path:
        return AJDBConfig.STORAGE_PATH / 'states/{}/{:02}/{:02}.json.gz'.format(date.year, date.month, date.day)
