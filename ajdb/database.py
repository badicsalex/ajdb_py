# Copyright 2020, Alex Badics, All Rights Reserved
from typing import Tuple, Optional, Dict, Iterable, Set, List, Type
from pathlib import Path
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
    def _get_amendments_and_repeals(act: Act) -> Dict[str, Dict[Type, List[SemanticData]]]:
        modifications_per_act: Dict[str, Dict[Type, List[SemanticData]]] = defaultdict(lambda: defaultdict(list))

        def sae_walker(reference: Reference, sae: SubArticleElement) -> SubArticleElement:
            if sae.semantic_data is None:
                return sae
            for semantic_data_element in sae.semantic_data:
                if not isinstance(semantic_data_element, (Repeal, TextAmendment, BlockAmendment)):
                    continue
                modified_ref = semantic_data_element.position
                assert modified_ref.act is not None
                modifications_per_act[modified_ref.act][type(semantic_data_element)].append(semantic_data_element)
                modifications_per_act[act.identifier][Repeal].append(Repeal(position=reference))
            return sae
        act.map_saes(sae_walker)
        return modifications_per_act

    @classmethod
    def apply_text_replacement_to_act(cls, act: Act, replace_at: Reference, old_str: str, new_str: str) -> Act:
        applied = False

        def text_replacer(_reference: Reference, sae: SubArticleElement) -> SubArticleElement:
            nonlocal applied
            new_text = sae.text.replace(old_str, new_str) if sae.text is not None else None
            new_intro = sae.intro.replace(old_str, new_str) if sae.intro is not None else None
            new_wrap_up = sae.wrap_up.replace(old_str, new_str) if sae.wrap_up is not None else None
            if sae.text == new_text and sae.intro == new_intro and sae.wrap_up == new_wrap_up:
                return sae
            applied = True
            return attr.evolve(
                sae,
                text=new_text,
                intro=new_intro,
                wrap_up=new_wrap_up,
                semantic_data=None,
                outgoing_references=None,
                act_id_abbreviations=None,
            )
        result = act.map_saes(text_replacer, replace_at)
        if not applied:
            print("WARN: Could not apply replacement '{}'=>'{}' at {}".format(old_str, new_str, replace_at))
        return result

    @classmethod
    def apply_text_amendment_to_act(cls, act: Act, text_amendment: TextAmendment) -> Act:
        return cls.apply_text_replacement_to_act(act, text_amendment.position, text_amendment.original_text, text_amendment.replacement_text)

    @classmethod
    def apply_repeal_to_act(cls, act: Act, repeal: Repeal) -> Act:
        if repeal.text is not None:
            return cls.apply_text_replacement_to_act(act, repeal.position, repeal.text, '')
        repeal_at = repeal.position

        def repealer(_reference: Reference, sae: SubArticleElement) -> SubArticleElement:
            return sae.__class__(
                identifier=sae.identifier,
                text=NOT_ENFORCED_TEXT,
                semantic_data=(),
                outgoing_references=(),
                act_id_abbreviations=(),
            )
        return act.map_saes(repealer, repeal_at)

    def apply_all_modifications(self, amending_act: Act) -> None:
        for act_id, modifications in self._get_amendments_and_repeals(amending_act).items():
            if act_id not in self.acts:
                continue
            act: Act = self.acts[act_id].act
            if act.identifier != amending_act.identifier:
                print("AMENDING ", act.identifier, "WITH", amending_act.identifier)

            modifications[TextAmendment].sort(key=lambda ta: -len(ta.original_text))  # type: ignore
            for text_amendment in modifications[TextAmendment]:
                assert isinstance(text_amendment, TextAmendment)
                act = self.apply_text_amendment_to_act(act, text_amendment)

            for repeal in modifications[Repeal]:
                assert isinstance(repeal, Repeal)
                act = self.apply_repeal_to_act(act, repeal)

            act = ActSemanticsParser.add_semantics_to_act(act)
            self.acts[act_id] = ActWithCachedData(act)
