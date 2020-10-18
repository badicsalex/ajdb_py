# Copyright 2020, Alex Badics, All Rights Reserved
from typing import Iterable, Any
from pathlib import Path
import difflib
import io
import yaml

import pytest
import attr

from hun_law.structure import Act, Reference, SubArticleElement
from hun_law.utils import Date
from hun_law.output.txt import write_txt
from hun_law import dict2object

from ajdb.database import ActSet

THIS_DIR = Path(__file__).parent


def semantic_remover(_reference: Reference, sae: SubArticleElement) -> SubArticleElement:
    return attr.evolve(
        sae,
        semantic_data=None,
        outgoing_references=None,
        act_id_abbreviations=None,
    )


def semantic_faker(_reference: Reference, sae: SubArticleElement) -> SubArticleElement:
    return attr.evolve(
        sae,
        semantic_data=sae.semantic_data or (),
        outgoing_references=sae.outgoing_references or (),
        act_id_abbreviations=sae.act_id_abbreviations or (),
    )


def act_set_testcase_provider() -> Iterable[Any]:
    data_dir = THIS_DIR / 'data'
    for acts_dir in sorted(data_dir.iterdir()):
        act_set = ActSet()
        for file_path in acts_dir.iterdir():
            if not file_path.is_file():
                continue
            if file_path.name not in ('expected.yaml', 'target_date.yaml'):
                with file_path.open('rt') as f:
                    data = yaml.load(f, Loader=yaml.Loader)
                    act: Act = dict2object.to_object(data, Act)
                    act = act.map_saes(semantic_faker)
                    act_set.add_act(act)

        with (acts_dir / 'expected.yaml').open('r') as f:
            expected_act = dict2object.to_object(yaml.load(f, Loader=yaml.Loader), Act)
        with (acts_dir / 'target_date.yaml').open('r') as f:
            target_date = dict2object.to_object(yaml.load(f, Loader=yaml.Loader), Date)
        yield pytest.param(
            act_set,
            expected_act,
            target_date,
            id=acts_dir.name
        )


def act_as_text(act: Act) -> str:
    iobuf = io.StringIO()
    write_txt(iobuf, act)
    return iobuf.getvalue()


# TODO: Instead of providing full testacases, provide only the paths,
#       because workers=auto may be super slow with huge parameters
@pytest.mark.parametrize("act_set,expected_act,target_date", act_set_testcase_provider())  # type: ignore
def test_amending_exact(act_set: ActSet, expected_act: Act, target_date: Date) -> None:
    for date in act_set.interesting_dates():
        if date > target_date:
            break
        for act in act_set.acts_at_date(date):
            act_set.apply_all_modifications(act)
    resulting_act = act_set.acts[expected_act.identifier].act
    expected_act = expected_act.map_saes(semantic_remover)
    resulting_act = resulting_act.map_saes(semantic_remover)

    print(
        '\n'.join(
            difflib.unified_diff(
                act_as_text(expected_act).split('\n'),
                act_as_text(resulting_act).split('\n'),
            )
        )
    )

    assert expected_act.children == resulting_act.children