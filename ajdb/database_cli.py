# Copyright 2020, Alex Badics, All Rights Reserved
from typing import Tuple, ClassVar, Optional, Type
from abc import ABC, abstractmethod
from pathlib import Path
import argparse
import sys

from hun_law.utils import Date
from hun_law.output.txt import write_txt

from ajdb.database import Database


class DatabaseCLIAction(ABC):
    SUBCOMMAND_NAME: ClassVar[Optional[str]] = None
    SUBCOMMAND_HELP: ClassVar[Optional[str]] = None

    @classmethod
    @abstractmethod
    def add_parameters(cls, argument_parser: argparse.ArgumentParser) -> None:
        pass

    @classmethod
    @abstractmethod
    def action(cls, params: argparse.Namespace) -> None:
        pass

    @classmethod
    def register_subcommand(cls, argument_parser: 'argparse._SubParsersAction') -> None:
        assert cls.SUBCOMMAND_NAME is not None
        subparser = argument_parser.add_parser(cls.SUBCOMMAND_NAME, help=cls.SUBCOMMAND_HELP)
        subparser.set_defaults(subparser_action=cls.action)
        cls.add_parameters(subparser)


class AddActAction(DatabaseCLIAction):
    SUBCOMMAND_NAME = 'add_act'
    SUBCOMMAND_HELP = 'Add a parsed hun_law file to the database'

    @classmethod
    def add_parameters(cls, argument_parser: argparse.ArgumentParser) -> None:
        argument_parser.add_argument(
            'act_files',
            metavar='act_file',
            nargs='+',
            type=Path,
            help="The file(s) to add"
        )

    @classmethod
    def action(cls, params: argparse.Namespace) -> None:
        for act_file in params.act_files:
            added_path = Database.store_hun_law_act_from_path(act_file)
            try:
                added_path = added_path.relative_to(Path.cwd())
            except ValueError:
                pass
            print('Added "{}"'.format(added_path))


class RecomputeAction(DatabaseCLIAction):
    SUBCOMMAND_NAME = 'recompute'
    SUBCOMMAND_HELP = 'Recompute amendments and other data from only the stored hun_law acts. Recomputation happens between the specified date range.'

    @classmethod
    def add_parameters(cls, argument_parser: argparse.ArgumentParser) -> None:
        argument_parser.add_argument(
            'from_date',
            nargs='?',
            default=Date(2009, 1, 1),
            type=Date.from_simple_string,
            help="Start of the date range"
        )
        argument_parser.add_argument(
            'to_date',
            nargs='?',
            default=Date.today().add_days(365),
            type=Date.from_simple_string,
            help="End of the date range [Inclusive]"
        )

    @classmethod
    def action(cls, params: argparse.Namespace) -> None:
        print("Recomputing database between {} and {}".format(params.from_date, params.to_date))
        Database.recompute_date_range(params.from_date, params.to_date)


class ListAction(DatabaseCLIAction):
    SUBCOMMAND_NAME = 'list'
    SUBCOMMAND_HELP = 'List acts'

    @classmethod
    def add_parameters(cls, argument_parser: argparse.ArgumentParser) -> None:
        argument_parser.add_argument(
            '-d', '--date',
            nargs='?',
            default=Date.today(),
            type=Date.from_simple_string,
            help="The date"
        )

    @classmethod
    def action(cls, params: argparse.Namespace) -> None:
        print("Acts at", params.date)
        act_set = Database.load_act_set(params.date)
        for act_proxy in sorted(act_set.acts, key=lambda a: a.identifier):
            padding = ' ' * (32 - len(act_proxy.identifier))
            print('"{}"{} {}'.format(act_proxy.identifier, padding, act_proxy.subject))


class OutputAction(DatabaseCLIAction):
    SUBCOMMAND_NAME = 'output'
    SUBCOMMAND_HELP = 'Output a specific act at a specific date'

    @classmethod
    def add_parameters(cls, argument_parser: argparse.ArgumentParser) -> None:
        argument_parser.add_argument(
            '-d', '--date',
            nargs='?',
            default=Date.today(),
            type=Date.from_simple_string,
            help="The date"
        )
        argument_parser.add_argument(
            '-n', '--no-wrap',
            action='store_true'
        )
        argument_parser.add_argument(
            'act_id',
            type=str,
            help="The act"
        )

    @classmethod
    def action(cls, params: argparse.Namespace) -> None:
        act = Database.load_act_set(params.date).act(params.act_id)
        text_width = 0 if params.no_wrap else 90
        write_txt(act.to_simple_act(), sys.stdout, width=text_width)


ALL_ACTIONS: Tuple[Type[DatabaseCLIAction], ...] = tuple(DatabaseCLIAction.__subclasses__())


def main() -> None:
    argument_parser = argparse.ArgumentParser(description="Command line interface to the AJDB dabatabse backend")
    subparsers = argument_parser.add_subparsers(dest='action')
    subparsers.required = True
    for action in ALL_ACTIONS:
        action.register_subcommand(subparsers)
    args = argument_parser.parse_args()
    args.subparser_action(args)
