# Copyright 2020, Alex Badics, All Rights Reserved

from pathlib import Path

from hun_law.utils import Date
from hun_law import dict2object

from ajdb.structure import ActSet, ActWM
from ajdb.utils import LruDict
from ajdb.object_storage import ObjectStorage
from ajdb.amender import ActConverter, ActSetAmendmentApplier

# TODO: Incremental upgrade:
#       - Find out which acts need to be updated: if any inputs changed, update acts
#           - Put inputs into Act. This is needed anyway (last modified date, and modifying acts)
#       - Collect all input acts (modified or not)
#       - Recompute all acts that need update


class Database:
    CACHE: LruDict[Date, ActSet] = LruDict(16)
    ACT_SET_CONVERTER = dict2object.get_converter(ActSet)

    @classmethod
    def load_hun_law_act(cls, path: Path) -> ActWM:
        act_raw = ActConverter.load_hun_law_act(path)
        act = ActConverter.convert_hun_law_act(act_raw)
        return act

    @classmethod
    def recompute_at_date(cls, date: Date) -> None:
        act_set = cls.load_act_set(date.add_days(-1))

        acts_to_add = ()  # TODO. Also TODO: command to put hun_law jsons into the proper dir
        if acts_to_add:
            act_set = ActSet(acts=act_set.acts + acts_to_add)
        act_set = ActSetAmendmentApplier.apply_all_amendments(act_set, date)

        cls.save_act_set(act_set, date)

    @classmethod
    def load_act_set(cls, date: Date) -> ActSet:
        # Load state, return it.
        if date in cls.CACHE:
            return cls.CACHE[date]

        key = cls._date_to_key(date)
        result: ActSet
        try:
            result = ObjectStorage('states').load(key)
        except KeyError:
            result = ActSet()
        cls.CACHE[date] = result
        return result

    @classmethod
    def save_act_set(cls, act_set: ActSet, date: Date) -> None:
        cls.CACHE[date] = act_set
        key = cls._date_to_key(date)
        ObjectStorage('states').save(cls.ACT_SET_CONVERTER.to_dict(act_set), key=key)

    @classmethod
    def _date_to_key(cls, date: Date) -> str:
        return '{}.{:02}.{:02}'.format(date.year, date.month, date.day)
