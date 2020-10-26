# Copyright 2020, Alex Badics, All Rights Reserved
from typing import Tuple, ClassVar, Optional, Type
from abc import ABC, abstractmethod
from pathlib import Path
import argparse

from ajdb.database import Database


class DatabaseCLIAction(ABC):
    SUBCOMMAND_NAME: ClassVar[Optional[str]] = None

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
        subparser = argument_parser.add_parser(cls.SUBCOMMAND_NAME)
        subparser.set_defaults(subparser_action=cls.action)
        cls.add_parameters(subparser)


class AddActAction(DatabaseCLIAction):
    SUBCOMMAND_NAME = 'add_act'

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
            added_path = Database.add_hun_law_act(act_file)
            try:
                added_path = added_path.relative_to(Path.cwd())
            except ValueError:
                pass
            print('Added "{}"'.format(added_path))


class RecomputeAction(DatabaseCLIAction):
    SUBCOMMAND_NAME = 'recompute'

    @classmethod
    def add_parameters(cls, argument_parser: argparse.ArgumentParser) -> None:
        pass

    @classmethod
    def action(cls, params: argparse.Namespace) -> None:
        raise ValueError("Not implemented")


ALL_ACTIONS: Tuple[Type[DatabaseCLIAction], ...] = (AddActAction, RecomputeAction,)


def main() -> None:
    argument_parser = argparse.ArgumentParser(description="Command line interface to the AJDB dabatabse backend")
    subparsers = argument_parser.add_subparsers()
    for action in ALL_ACTIONS:
        action.register_subcommand(subparsers)
    args = argument_parser.parse_args()
    args.subparser_action(args)
