#!/usr/bin/env python3
# Copyright 2020, Alex Badics, All Rights Reserved
from typing import Iterable, Optional, Any, TextIO
from pathlib import Path
import argparse
import attr
import yaml

from hun_law.structure import SubArticleElement, Article, \
    EnforcementDate, TextAmendment, ArticleTitleAmendment, BlockAmendment, Repeal,\
    Reference
from hun_law.utils import Date
from hun_law.output.txt import write_txt
from hun_law import dict2object

from ajdb.structure import ActWM, SaeWMType
from ajdb.amender import ActSet


def serialize_to_yaml(obj: Any, f: TextIO) -> None:
    yaml.dump(dict2object.to_dict(obj, type(obj)), f, allow_unicode=True)


def load_acts(acts: Iterable[Path]) -> ActSet:
    act_set = ActSet()
    for file_path in acts:
        act_set.load_from_file(file_path)
    return act_set


def parse_args() -> argparse.Namespace:
    argparser = argparse.ArgumentParser(description="Create test sets from known good parse results")
    argparser.add_argument(
        'target_act',
        type=str,
        help="The act ID that will be focused on in the test set"
    )
    argparser.add_argument(
        'target_date',
        type=lambda s: Date(*(int(part) for part in s.split('/'))),
        help="The date until which amendments shall be applied. Format: 2020/1/1"
    )
    argparser.add_argument(
        'source_acts',
        nargs='+',
        type=Path,
        help="The optionally gzipped yaml input acts that will be used as input"
    )
    argparser.add_argument(
        'destination_dir',
        type=Path,
        help="The directory that will contain the test set"
    )
    return argparser.parse_args()


def do_amendments(act_set: ActSet, target_date: Date) -> None:
    for date in act_set.interesting_dates():
        if date > target_date:
            break
        print("Processing date", date)
        for act in act_set.acts.values():
            act_set.apply_all_modifications(act, date)


def filter_interesting_articles(act: ActWM, target_act_id: str) -> Optional[ActWM]:
    has_interesting: bool
    has_amendment = False

    def has_interesting_fn(_reference: Reference, sae: SubArticleElement) -> SubArticleElement:
        nonlocal has_interesting, has_amendment
        if sae.semantic_data is not None:
            for semantic_element in sae.semantic_data:
                if isinstance(semantic_element, EnforcementDate):
                    has_interesting = True
                    break
                assert isinstance(semantic_element, (TextAmendment, ArticleTitleAmendment, BlockAmendment, Repeal))
                if semantic_element.position.act == target_act_id:
                    has_interesting = True
                    has_amendment = True
                    break
        return sae

    new_children = []
    for c in act.children:
        if isinstance(c, Article):
            has_interesting = False
            c.map_recursive(Reference(), has_interesting_fn)
            if has_interesting:
                new_children.append(c)

    if not has_amendment:
        return None
    return attr.evolve(act, children=tuple(new_children))


def sae_trimmer(_reference: Reference, sae: SaeWMType) -> SaeWMType:
    return attr.evolve(
        sae,
        semantic_data=sae.semantic_data or None,
        outgoing_references=None,
        act_id_abbreviations=sae.act_id_abbreviations or None,
    )


def save_act(act: ActWM, path: Path) -> None:
    act = act.map_saes_wm(sae_trimmer)
    with path.open('w') as f:
        serialize_to_yaml(act.to_simple_act(), f)


def main() -> None:
    args = parse_args()
    act_set = load_acts(args.source_acts)
    dest_dir: Path = args.destination_dir
    dest_dir.mkdir(exist_ok=True)
    print("Saving original")
    original = act_set.acts[args.target_act]
    save_act(original, dest_dir / 'original.yaml')
    print("Saving amendments")
    for act in act_set.acts.values():
        if act.identifier != args.target_act:
            filtered_act = filter_interesting_articles(act, args.target_act)
            if filtered_act is not None:
                save_act(filtered_act, dest_dir / (act.identifier + '.yaml'))
    do_amendments(act_set, args.target_date)
    print("Saving expected")
    expected = act_set.acts[args.target_act]
    save_act(expected, dest_dir / 'expected.yaml')
    with (dest_dir / 'target_date.yaml').open('w') as f:
        serialize_to_yaml(args.target_date, f)
    with (dest_dir / 'expected.txt').open('w') as f:
        write_txt(f, expected)


if __name__ == "__main__":
    main()
