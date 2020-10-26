# Copyright 2020, Alex Badics, All Rights Reserved
from typing import Tuple, ClassVar, Optional, Type
from abc import ABC, abstractmethod
from pathlib import Path
import argparse

from hun_law.utils import Date

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


ALL_ACTIONS: Tuple[Type[DatabaseCLIAction], ...] = (AddActAction, RecomputeAction,)


def main() -> None:
    argument_parser = argparse.ArgumentParser(description="Command line interface to the AJDB dabatabse backend")
    subparsers = argument_parser.add_subparsers(dest='action')
    subparsers.required = True
    for action in ALL_ACTIONS:
        action.register_subcommand(subparsers)
    args = argument_parser.parse_args()
    args.subparser_action(args)
