# Copyright 2020, Alex Badics, All Rights Reserved
from typing import Iterable, Any
from pathlib import Path
import difflib
import io
import yaml

# For typing only
from _pytest.monkeypatch import MonkeyPatch
import pytest

from hun_law.structure import Act
from hun_law.utils import Date
from hun_law.output.txt import write_txt
from hun_law import dict2object

from tests.utils import add_fake_semantic_data, remove_semantic_data

from ajdb.config import AJDBConfig
from ajdb.amender import ActConverter
from ajdb.database import Database

THIS_DIR = Path(__file__).parent


def act_set_testcase_provider() -> Iterable[Any]:
    data_dir = THIS_DIR / 'data'
    for acts_dir in sorted(data_dir.iterdir()):
        yield pytest.param(
            acts_dir,
            id=acts_dir.name,
        )


def act_as_text(act: Act) -> str:
    iobuf = io.StringIO()
    write_txt(iobuf, act)
    return iobuf.getvalue()


@pytest.mark.parametrize("acts_dir", act_set_testcase_provider())
def test_amending_exact(acts_dir: Path, tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    Database.CACHE.clear()
    monkeypatch.setattr(AJDBConfig, "STORAGE_PATH", tmp_path)

    for file_path in acts_dir.iterdir():
        if file_path.name not in ('expected.yaml', 'target_date.yaml'):
            act_raw = ActConverter.load_hun_law_act(file_path)
            act_raw = add_fake_semantic_data(act_raw)
            Database.store_hun_law_act(act_raw)

    expected_act = ActConverter.load_hun_law_act(acts_dir / 'expected.yaml')
    with (acts_dir / 'target_date.yaml').open('r') as f:
        target_date = dict2object.to_object(yaml.load(f, Loader=yaml.Loader), Date)

    Database.recompute_date_range(Date(2009, 1, 1), target_date)
    act_set = Database.load_act_set(target_date)

    resulting_act = act_set.act(expected_act.identifier).to_simple_act()
    expected_act = remove_semantic_data(expected_act)
    resulting_act = remove_semantic_data(resulting_act)

    print(
        '\n'.join(
            difflib.unified_diff(
                act_as_text(expected_act).split('\n'),
                act_as_text(resulting_act).split('\n'),
            )
        )
    )

    assert expected_act.children == resulting_act.children
