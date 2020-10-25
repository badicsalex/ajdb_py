# Copyright 2020, Alex Badics, All Rights Reserved
from typing import Iterable, Any, Tuple, Dict, List
from pathlib import Path
from collections import defaultdict
import difflib
import io
import yaml

import pytest

from hun_law.structure import Act
from hun_law.utils import Date
from hun_law.output.txt import write_txt
from hun_law import dict2object

from tests.utils import add_fake_semantic_data, remove_semantic_data

from ajdb.structure import ActSet, ActWM
from ajdb.amender import ActSetAmendmentApplier, ActConverter

THIS_DIR = Path(__file__).parent


def act_set_testcase_provider() -> Iterable[Any]:
    data_dir = THIS_DIR / 'data'
    for acts_dir in sorted(data_dir.iterdir()):
        yield pytest.param(
            acts_dir,
            id=acts_dir.name,
        )


def load_test_data(acts_dir: Path) -> Tuple[Act, Date, Dict[Date, List[ActWM]]]:
    acts_to_apply = defaultdict(list)
    for file_path in acts_dir.iterdir():
        if not file_path.is_file():
            continue
        if file_path.name not in ('expected.yaml', 'target_date.yaml'):
            act_raw = ActConverter.load_hun_law_act(file_path)
            act_raw = add_fake_semantic_data(act_raw)
            act = ActConverter.convert_hun_law_act(act_raw)
            acts_to_apply[act.publication_date].append(act)

    expected_act = ActConverter.load_hun_law_act(acts_dir / 'expected.yaml')
    with (acts_dir / 'target_date.yaml').open('r') as f:
        target_date = dict2object.to_object(yaml.load(f, Loader=yaml.Loader), Date)
    return expected_act, target_date, acts_to_apply


def act_as_text(act: Act) -> str:
    iobuf = io.StringIO()
    write_txt(iobuf, act)
    return iobuf.getvalue()


@pytest.mark.parametrize("acts_dir", act_set_testcase_provider())
def test_amending_exact(acts_dir: Path) -> None:
    expected_act, target_date, acts_to_apply = load_test_data(acts_dir)
    act_set = ActSet(acts=())
    date = min(acts_to_apply.keys())
    while date <= target_date:
        if date in acts_to_apply:
            act_set = ActSet(acts=act_set.acts + tuple(acts_to_apply[date]))
        act_set = ActSetAmendmentApplier.apply_all_amendments(act_set, date)
        date = date.add_days(1)

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
