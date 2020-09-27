# Copyright 2020, Alex Badics, All Rights Reserved
from typing import Tuple, Optional, Dict, Iterable, Set, List
from pathlib import Path
import gzip
import json
import attr
from collections import defaultdict

from hun_law.structure import \
    Act, Article, Paragraph, SubArticleElement, Reference, SemanticData,\
    EnforcementDate, DaysAfterPublication, DayInMonthAfterPublication, EnforcementDateTypes, \
    Repeal, TextAmendment

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
        if self.position.is_range():
            return self.position.is_in_range(reference)
        return self.position == reference


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
                        text=NOT_ENFORCED_TEXT
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
                                text=NOT_ENFORCED_TEXT
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
    def _get_amendments_and_repeals(act: Act) -> Dict[str, List[SemanticData]]:
        modifications_per_act: Dict[str, List[SemanticData]] = defaultdict(list)

        def sae_walker(reference: Reference, sae: SubArticleElement) -> SubArticleElement:
            if sae.semantic_data is None:
                return sae
            for semantic_data_element in sae.semantic_data:
                if not isinstance(semantic_data_element, (Repeal, TextAmendment)):
                    continue
                modified_ref = semantic_data_element.position
                assert modified_ref.act is not None
                modifications_per_act[modified_ref.act].append(semantic_data_element)
                modifications_per_act[act.identifier].append(Repeal(position=reference))
            return sae
        act.map_saes(sae_walker)
        return modifications_per_act

    @classmethod
    def _replace_all(cls, text: Optional[str], replacements: List[Tuple[str, str]]) -> Optional[str]:
        if text is None:
            return text
        for old, new in replacements:
            text = text.replace(old, new)
        return text

    @classmethod
    def _apply_modifications_to_sae(cls, reference: Reference, sae: SubArticleElement, modifications: List[SemanticData]) -> SubArticleElement:
        text_replacements: List[Tuple[str, str]] = []
        for modification in modifications:
            assert isinstance(modification, (Repeal, TextAmendment))

            if not isinstance(modification.position, Reference):
                # TODO
                continue
            if modification.position != reference and (not modification.position.is_range() or not modification.position.is_in_range(reference)):
                continue
            if isinstance(modification, Repeal):
                if modification.text is None:
                    return sae.__class__(
                        identifier=sae.identifier,
                        text=NOT_ENFORCED_TEXT
                    )
                text_replacements.append((modification.text, ''))
            if isinstance(modification, TextAmendment):
                text_replacements.append((modification.original_text, modification.replacement_text))
        if not text_replacements:
            return sae
        text_replacements.sort(key=lambda e: -len(e[0]))
        new_text = cls._replace_all(sae.text, text_replacements)
        new_intro = cls._replace_all(sae.intro, text_replacements)
        new_wrap_up = cls._replace_all(sae.wrap_up, text_replacements)
        if sae.text == new_text and sae.intro == new_intro and sae.wrap_up == new_wrap_up:
            # TODO: more intelligent reporting. We need all actual replacements to apply at least once
            print("WARN: could not apply", text_replacements, "to", reference, sae)
            return sae
        return attr.evolve(sae, text=new_text, intro=new_intro, wrap_up=new_wrap_up)

    def apply_modifications(self, amending_act: Act) -> None:
        for act_id, modifications in self._get_amendments_and_repeals(amending_act).items():
            if act_id not in self.acts:
                continue
            act: Act = self.acts[act_id].act
            print("AMENDING ", act.identifier, "WITH", amending_act.identifier)
            modified_act = act.map_saes(lambda r, sae: self._apply_modifications_to_sae(r, sae, modifications))
            modified_act = ActSemanticsParser.add_semantics_to_act(modified_act)
            self.acts[act_id] = ActWithCachedData(modified_act)
