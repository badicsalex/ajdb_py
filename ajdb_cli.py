#!/usr/bin/env python3
from pathlib import Path
from typing import Sequence
import argparse
import shutil
import subprocess
import textwrap
import os

from ajdb.database import ActSet
from hun_law.structure import Act
from hun_law.utils import Date
from hun_law.output.html import generate_html_for_act
from hun_law.output.json import serialize_to_json_file
from hun_law.output.txt import write_txt

ACTS_DESCRIPTORS = (
    ('Btk.', '2012. évi C. törvény'),
    ('Ptk.', '2013. évi V. törvény'),
)
ALLOWED_ACTS = set(a[1] for a in ACTS_DESCRIPTORS)

THIS_DIR = Path(__file__).parent


def load_parsed_acts(acts_dir: Path) -> ActSet:
    act_set = ActSet()
    for file_path in acts_dir.iterdir():
        if not file_path.is_file():
            continue
        act_set.load_from_file(file_path)
    return act_set


def set_up_dir_structure(destination_dir: Path) -> None:
    if destination_dir.exists():
        shutil.rmtree(destination_dir)
    shutil.copytree(THIS_DIR / 'generated_repo_skeleton', destination_dir)
    (destination_dir / 'html').mkdir(exist_ok=True)
    (destination_dir / 'json').mkdir(exist_ok=True)
    (destination_dir / 'txt').mkdir(exist_ok=True)
    subprocess.run(
        ['git', 'init'],
        cwd=destination_dir,
        check=True,
    )
    subprocess.run(
        ['git', 'add', '.'],
        cwd=destination_dir,
        check=True,
    )
    subprocess.run(
        ['git', 'commit', '-m', "Initial commit"],
        cwd=destination_dir,
        check=True
    )


def save_in_all_formats(acts: Sequence[Act], destination_dir: Path) -> None:
    # TODO: check for changes
    for act in acts:
        if not act.identifier in ALLOWED_ACTS:
            continue
        with (destination_dir / 'html' / (act.identifier + '.html')).open('w') as f:
            generate_html_for_act(act, f)
        with (destination_dir / 'json' / (act.identifier + '.json')).open('w') as f:
            serialize_to_json_file(act, f)
        with (destination_dir / 'txt' / (act.identifier + '.txt')).open('w') as f:
            write_txt(f, act)


def create_named_act_symlinks(destination_dir: Path) -> None:
    for inner_dir_name in ('html', 'json', 'txt'):
        inner_dir = destination_dir / inner_dir_name
        for name, identifier in ACTS_DESCRIPTORS:
            act_file_name = '{}.{}'.format(identifier, inner_dir_name)
            symlink_source = inner_dir / act_file_name
            symlink_destination = inner_dir / '{}.{}'.format(name, inner_dir_name)
            if symlink_source.exists() and not symlink_destination.exists():
                symlink_destination.symlink_to(act_file_name)


def git_commit(amending_act: Act, date: Date, destination_dir: Path) -> None:
    commit_message = "{}\n\n{}".format(
        amending_act.identifier,
        textwrap.fill(amending_act.subject, width=80)
    )
    subprocess.run(
        ['git', 'add', '.'],
        cwd=destination_dir,
        check=True,
    )
    date_str = '{}.{:02}.{:02}T08:00:00+00:00'.format(date.year, date.month, date.day)
    commit_result = subprocess.run(  # pylint: disable=subprocess-run-check
        [
            'git', 'commit',
            '-m', commit_message,
        ],
        env={
            **os.environ,
            'GIT_AUTHOR_DATE': date_str,
            'GIT_COMMITTER_DATE': date_str,
        },
        cwd=destination_dir,
    )
    if commit_result.returncode != 0:
        print("WARN: Commit not successful. Probably empty.")


def generate_repository(act_set: ActSet, destination_dir: Path) -> None:
    set_up_dir_structure(destination_dir)

    for date in act_set.interesting_dates():
        print("Processing date", date)

        for act in act_set.acts_at_date(date):
            modified_act_ids = set(act_set.apply_all_modifications(act))
            modified_acts = tuple(
                a for a in act_set.acts_at_date(date) if
                a.identifier in modified_act_ids and
                a.identifier in ALLOWED_ACTS
            )
            if act.identifier in ALLOWED_ACTS and act_set.is_interesting_date_for(act.identifier, date):
                modified_acts = (act, ) + modified_acts
            if not modified_acts:
                continue
            save_in_all_formats(modified_acts, destination_dir)
            create_named_act_symlinks(destination_dir)
            git_commit(act, date, destination_dir)


def parse_args() -> argparse.Namespace:
    argparser = argparse.ArgumentParser(description="Generate git repo from acts")
    argparser.add_argument(
        'source_dir',
        type=Path,
        help="The directory that contains the gzipped, json-parsed acts"
    )
    argparser.add_argument(
        'destination_dir',
        type=Path,
        help="The directory that contains the gzipped, json-parsed acts"
    )
    return argparser.parse_args()


def main() -> None:
    args = parse_args()
    act_set = load_parsed_acts(args.source_dir)
    generate_repository(act_set, args.destination_dir)


if __name__ == '__main__':
    main()
