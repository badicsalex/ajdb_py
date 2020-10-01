# Copyright 2020, Alex Badics, All Rights Reserved
from typing import Tuple, Optional, Dict, Iterable, Set, List, Type, ClassVar
from pathlib import Path
from abc import ABC, abstractmethod
import gzip
import json
from collections import defaultdict

import attr

from hun_law.structure import \
    Act, Article, Paragraph, SubArticleElement, Reference, SemanticData,\
    EnforcementDate, DaysAfterPublication, DayInMonthAfterPublication, EnforcementDateTypes, \
    Repeal, TextAmendment, BlockAmendment

from hun_law.utils import Date
from hun_law.parsers.semantic_parser import ActSemanticsParser
from hun_law import dict2object

from ajdb.utils import iterate_all_saes_of_act
from ajdb.fixups import apply_fixups

NOT_ENFORCED_TEXT = ' '

act_converter = dict2object.get_converter(Act)


@attr.s(slots=True, frozen=True, auto_attribs=True, kw_only=True)
class ActualizedEnforcementDate:
    position: Optional[Reference]
    from_date: Date
    to_date: Optional[Date] = None

    @staticmethod
    def _actualize_single_date(date: EnforcementDateTypes, publication_date: Date) -> Date:
        if isinstance(date, Date):
            return date
        if isinstance(date, DaysAfterPublication):
            return publication_date.add_days(date.days)
        if isinstance(date, DayInMonthAfterPublication):
            year = publication_date.year
            month = publication_date.month + date.months
            if month > 12:
                month = month - 12
                year = year + 1
            return Date(year, month, date.day)
        raise ValueError("Unsupported EnforcementDate: {}".format(date))

    @classmethod
    def from_enforcement_date(cls, enforcement_date: EnforcementDate, publication_date: Date) -> 'ActualizedEnforcementDate':
        return cls(
            position=enforcement_date.position,
            from_date=cls._actualize_single_date(enforcement_date.date, publication_date),
            to_date=enforcement_date.repeal_date
        )

    def is_in_force_at_date(self, date: Date) -> bool:
        if date < self.from_date:
            return False
        if self.to_date is not None and date > self.to_date:
            return False
        return True

    def is_applicable_to(self, reference: Reference) -> bool:
        assert self.position is not None
        return self.position.contains(reference)


class ActNotInForce(Exception):
    pass


@attr.s(slots=True, frozen=True, auto_attribs=True)
class EnforcementDateSet:
    default: ActualizedEnforcementDate
    specials: Tuple[ActualizedEnforcementDate, ...]

    @classmethod
    def from_act(cls, act: Act) -> 'EnforcementDateSet':
        default = None
        specials = []
        for sae in iterate_all_saes_of_act(act):
            assert sae.semantic_data is not None
            for semantic_data_element in sae.semantic_data:
                if isinstance(semantic_data_element, EnforcementDate):
                    aed = ActualizedEnforcementDate.from_enforcement_date(semantic_data_element, act.publication_date)
                    if aed.position is None:
                        assert default is None
                        default = aed
                    else:
                        specials.append(aed)
        assert default is not None
        assert all(default.from_date <= special.from_date for special in specials)
        assert all(special.to_date is None for special in specials)
        return cls(
            default,
            tuple(specials)
        )

    def filter_act(self, act: Act, date: Date) -> Act:
        if not self.default.is_in_force_at_date(date):
            raise ActNotInForce(
                "Act is not in force at {}. (from: {}, to: {})"
                .format(date, self.default.from_date, self.default.to_date)
            )
        not_yet_in_force = tuple(aed for aed in self.specials if not aed.is_in_force_at_date(date))
        if not not_yet_in_force:
            return act

        def sae_modifier(reference: Reference, sae: SubArticleElement) -> SubArticleElement:
            reference = attr.evolve(reference, act=None)
            for aed in not_yet_in_force:
                if aed.is_applicable_to(reference):
                    return sae.__class__(
                        identifier=sae.identifier,
                        text=NOT_ENFORCED_TEXT,
                        semantic_data=(),
                        outgoing_references=(),
                        act_id_abbreviations=(),
                    )
            return sae

        def article_modifier(article: Article) -> Article:
            for aed in not_yet_in_force:
                if aed.is_applicable_to(Reference(None, article.identifier)):
                    return Article(
                        identifier=article.identifier,
                        children=(
                            Paragraph(
                                identifier=None,
                                text=NOT_ENFORCED_TEXT,
                                semantic_data=(),
                                outgoing_references=(),
                                act_id_abbreviations=(),
                            ),
                        )
                    )
            return article

        act = act.map_articles(article_modifier)
        return act.map_saes(sae_modifier)


@attr.s(slots=True, auto_attribs=True)
class ModificationApplier(ABC):
    modification: SemanticData = attr.ib()
    applied: bool = attr.ib(init=False, default=False)

    @classmethod
    @abstractmethod
    def can_apply(cls, modification: SemanticData) -> bool:
        pass

    @abstractmethod
    def apply(self, act: Act) -> Act:
        pass

    @property
    def priority(self) -> int:
        # Mostly meaningful in TextReplacementApplier
        # Higher means it has to be applied sooner
        return 0


@attr.s(slots=True, auto_attribs=True)
class TextReplacementApplier(ModificationApplier):
    original_text: str = attr.ib(init=False)
    replacement_text: str = attr.ib(init=False)

    @original_text.default
    def _original_text_default(self) -> str:
        if isinstance(self.modification, TextAmendment):
            return self.modification.original_text
        if isinstance(self.modification, Repeal):
            assert self.modification.text is not None
            return self.modification.text
        raise TypeError("Unknown SemanticData type in TextReplacementApplier")

    @replacement_text.default
    def _replacement_text_default(self) -> str:
        if isinstance(self.modification, TextAmendment):
            return self.modification.replacement_text
        if isinstance(self.modification, Repeal):
            return NOT_ENFORCED_TEXT
        raise TypeError("Unknown SemanticData type in TextReplacementApplier")

    @classmethod
    def can_apply(cls, modification: SemanticData) -> bool:
        return isinstance(modification, TextAmendment) or (isinstance(modification, Repeal) and modification.text is not None)

    def text_replacer(self, _reference: Reference, sae: SubArticleElement) -> SubArticleElement:
        new_text = sae.text.replace(self.original_text, self.replacement_text) if sae.text is not None else None
        new_intro = sae.intro.replace(self.original_text, self.replacement_text) if sae.intro is not None else None
        new_wrap_up = sae.wrap_up.replace(self.original_text, self.replacement_text) if sae.wrap_up is not None else None
        if sae.text == new_text and sae.intro == new_intro and sae.wrap_up == new_wrap_up:
            return sae
        self.applied = True
        return attr.evolve(
            sae,
            text=new_text,
            intro=new_intro,
            wrap_up=new_wrap_up,
            semantic_data=None,
            outgoing_references=None,
            act_id_abbreviations=None,
        )

    def apply(self, act: Act) -> Act:
        assert isinstance(self.modification, (TextAmendment, Repeal))
        return act.map_saes(self.text_replacer, self.modification.position)

    @property
    def priority(self) -> int:
        # Sorting these modifications is needed because of cases like:
        # Original text: "This is ABC, and also ABC is important for ABCD reasons"
        # Replacement 1: ABC => DEF
        # Replacement 2: ABCD => DEFG
        # In the wrong order, this produces "This is DEF, and also DEF is important for DEFD reasons"

        # Higher means it has to be applied sooner
        return len(self.original_text)


@attr.s(slots=True, auto_attribs=True)
class RepealApplier(ModificationApplier):
    @classmethod
    def can_apply(cls, modification: SemanticData) -> bool:
        return isinstance(modification, Repeal) and modification.text is None

    def repealer(self, _reference: Reference, sae: SubArticleElement) -> SubArticleElement:
        self.applied = True
        return sae.__class__(
            identifier=sae.identifier,
            text=NOT_ENFORCED_TEXT,
            semantic_data=(),
            outgoing_references=(),
            act_id_abbreviations=(),
        )

    def apply(self, act: Act) -> Act:
        assert isinstance(self.modification, Repeal)
        return act.map_saes(self.repealer, self.modification.position)



@attr.s(slots=True, frozen=True, auto_attribs=True)
class ModificationSet:
    APPLIER_CLASSES: ClassVar[Tuple[Type[ModificationApplier], ...]] = (
        TextReplacementApplier,
        RepealApplier,
    )

    modifications: Tuple[SemanticData, ...]

    def apply_all(self, act: Act) -> Act:
        appliers: List[ModificationApplier] = []
        for applier_class in self.APPLIER_CLASSES:
            appliers.extend(applier_class(m) for m in self.modifications if applier_class.can_apply(m))

        appliers.sort(key=lambda x: x.priority, reverse=True)

        for applier in appliers:
            act = applier.apply(act)
            if not applier.applied:
                print("WARN: Could not apply ", applier.modification)
        return act


@attr.s(slots=True, frozen=True, auto_attribs=True)
class ActWithCachedData:
    act: Act
    enforcement_dates: EnforcementDateSet = attr.ib(init=False)

    @enforcement_dates.default
    def _enforcement_dates_default(self) -> EnforcementDateSet:
        return EnforcementDateSet.from_act(self.act)

    def interesting_dates(self) -> Tuple[Date, ...]:
        result = set()
        result.add(self.enforcement_dates.default.from_date)
        if self.enforcement_dates.default.to_date is not None:
            result.add(self.enforcement_dates.default.to_date)

        result.update(aed.from_date for aed in self.enforcement_dates.specials)
        return tuple(result)

    def state_at_date(self, date: Date) -> Act:
        return self.enforcement_dates.filter_act(self.act, date)


class ActSet:
    acts: Dict[str, ActWithCachedData]

    def __init__(self) -> None:
        self.acts = {}

    def load_from_file(self, path: Path) -> None:
        if path.suffix == '.gz':
            with gzip.open(path, 'rt') as f:
                the_dict = json.load(f)
        else:
            with open(path, 'rt') as f:
                the_dict = json.load(f)
        act = act_converter.to_object(the_dict)
        act = apply_fixups(act)
        self.acts[act.identifier] = ActWithCachedData(act)

    def interesting_dates(self) -> Tuple[Date, ...]:
        result: Set[Date] = set()
        for act in self.acts.values():
            result.update(act.interesting_dates())
        return tuple(sorted(result))

    def acts_at_date(self, date: Date) -> Iterable[Act]:
        for act in self.acts.values():
            try:
                yield act.state_at_date(date)
            except ActNotInForce:
                pass

    @staticmethod
    def _get_amendments_and_repeals(act: Act) -> Dict[str, List[SemanticData]]:
        modifications_per_act: Dict[str, List[SemanticData]] = defaultdict(list)

        def sae_walker(reference: Reference, sae: SubArticleElement) -> SubArticleElement:
            if sae.semantic_data is None:
                return sae
            for semantic_data_element in sae.semantic_data:
                if not isinstance(semantic_data_element, (Repeal, TextAmendment, BlockAmendment)):
                    continue
                modified_ref = semantic_data_element.position
                assert modified_ref.act is not None
                modifications_per_act[modified_ref.act].append(semantic_data_element)
                modifications_per_act[act.identifier].append(Repeal(position=reference))
            return sae
        act.map_saes(sae_walker)
        return modifications_per_act

    def apply_all_modifications(self, amending_act: Act) -> None:
        for act_id, modifications in self._get_amendments_and_repeals(amending_act).items():
            if act_id not in self.acts:
                continue
            act: Act = self.acts[act_id].act
            if act.identifier != amending_act.identifier:
                print("AMENDING ", act.identifier, "WITH", amending_act.identifier)

            modification_set = ModificationSet(tuple(modifications))
            act = modification_set.apply_all(act)

            act = ActSemanticsParser.add_semantics_to_act(act)
            self.acts[act_id] = ActWithCachedData(act)
