# Copyright 2020, Alex Badics, All Rights Reserved
from typing import Tuple, Optional, Dict, Iterable, Set, List, Type, ClassVar, Union
from pathlib import Path
from abc import ABC, abstractmethod
import gzip
import json
from collections import defaultdict

import attr

from hun_law.structure import \
    Act, Article, Paragraph, SubArticleElement, BlockAmendmentContainer, \
    StructuralElement, Subtitle, Book,\
    Reference, StructuralReference, SubtitleArticleComboType, \
    EnforcementDate, DaysAfterPublication, DayInMonthAfterPublication, EnforcementDateTypes, \
    SemanticData, Repeal, TextAmendment, ArticleTitleAmendment, BlockAmendment, \
    SubArticleChildType

from hun_law.utils import Date, identifier_less
from hun_law.parsers.semantic_parser import ActSemanticsParser
from hun_law import dict2object

from ajdb.utils import iterate_all_saes_of_act, first_matching_index
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
        assert default is not None, act.identifier
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

        def article_modifier(_reference: Reference, article: Article) -> Article:
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
    source_sae: SubArticleElement = attr.ib()
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
    position: Reference = attr.ib(init=False)
    original_text: str = attr.ib(init=False)
    replacement_text: str = attr.ib(init=False)

    @position.default
    def _position_default(self) -> Reference:
        if isinstance(self.modification, TextAmendment):
            return self.modification.position
        assert isinstance(self.modification, Repeal) and isinstance(self.modification.position, Reference)
        return self.modification.position

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
        return act.map_saes(self.text_replacer, self.position)

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
class ArticleTitleAmendmentApplier(ModificationApplier):
    @classmethod
    def can_apply(cls, modification: SemanticData) -> bool:
        return isinstance(modification, ArticleTitleAmendment)

    def modifier(self, _reference: Reference, article: Article) -> Article:
        assert isinstance(self.modification, ArticleTitleAmendment)
        assert article.title is not None
        self.applied = self.modification.original_text in article.title
        new_title = article.title.replace(self.modification.original_text, self.modification.replacement_text)
        return attr.evolve(
            article,
            title=new_title,
        )

    def apply(self, act: Act) -> Act:
        assert isinstance(self.modification, ArticleTitleAmendment)
        _, reference_type = self.modification.position.last_component_with_type()
        assert reference_type is Article
        return act.map_articles(self.modifier, self.modification.position)


def get_cut_points_for_structural_reference(position: StructuralReference, children: Tuple[SubArticleChildType, ...]) -> Tuple[int, int]:
    structural_id, structural_type_nc = position.last_component_with_type()
    assert structural_id is not None
    assert structural_type_nc is not None
    assert issubclass(structural_type_nc, StructuralElement)
    # Pypy does not properly infer the type of structural_type without this explicit assignment
    structural_type: Type[StructuralElement] = structural_type_nc

    start_cut = 0
    if position.book is not None:
        book_id = position.book
        start_cut = first_matching_index(children, lambda c: bool(isinstance(c, Book) and book_id == c.identifier))
        assert start_cut < len(children)

    start_cut = first_matching_index(
        children,
        lambda c: isinstance(c, structural_type) and structural_id in (c.identifier, c.title),
        start=start_cut
    )
    # TODO: Insertions are should be legal though, but this is most likely a mistake, so
    # keep an error until I find an actual insertion. It will need to be handled separately.
    assert start_cut < len(children), ("Only replacements are supported for structural amendments or repeals", position)

    end_cut = first_matching_index(
        children,
        lambda c: isinstance(c, (structural_type, * structural_type.PARENT_TYPES)),
        start=start_cut + 1
    )
    return start_cut, end_cut


@attr.s(slots=True, auto_attribs=True)
class RepealApplier(ModificationApplier):
    @classmethod
    def can_apply(cls, modification: SemanticData) -> bool:
        return isinstance(modification, Repeal) and modification.text is None

    def sae_repealer(self, _reference: Reference, sae: SubArticleElement) -> SubArticleElement:
        self.applied = True
        return sae.__class__(
            identifier=sae.identifier,
            text=NOT_ENFORCED_TEXT,
            semantic_data=(),
            outgoing_references=(),
            act_id_abbreviations=(),
        )

    def article_repealer(self, _reference: Reference, article: Article) -> Article:
        self.applied = True
        return Article(
            identifier=article.identifier,
            children=(
                Paragraph(
                    text=NOT_ENFORCED_TEXT,
                    semantic_data=(),
                    outgoing_references=(),
                    act_id_abbreviations=(),
                ),
            ),
        )

    def apply_to_act(self, act: Act) -> Act:
        assert isinstance(self.modification, Repeal)
        assert isinstance(self.modification.position, StructuralReference)
        position: StructuralReference = self.modification.position

        if position.special is None:
            start_cut, end_cut = get_cut_points_for_structural_reference(position, act.children)
        else:
            assert position.special.position == SubtitleArticleComboType.BEFORE_WITHOUT_ARTICLE, \
                "Only BEFORE_WITHOUT_ARTICLE is supported for special subtitle repeals for now"
            article_id = position.special.article_id
            end_cut = first_matching_index(act.children, lambda c: isinstance(c, Article) and c.identifier == article_id)
            if end_cut >= len(act.children):
                # Not found: probably an error. Calling code will Warn probably.
                return act
            start_cut = end_cut - 1

        self.applied = True
        # TODO: Repeal articles instead of deleting them.
        return attr.evolve(act, children=act.children[:start_cut] + act.children[end_cut:])

    def apply(self, act: Act) -> Act:
        assert isinstance(self.modification, Repeal)
        if isinstance(self.modification.position, Reference):
            _, reference_type = self.modification.position.last_component_with_type()
            if reference_type is Article:
                return act.map_articles(self.article_repealer, self.modification.position)
            return act.map_saes(self.sae_repealer, self.modification.position)
        return self.apply_to_act(act)


@attr.s(slots=True, auto_attribs=True)
class BlockAmendmentApplier(ModificationApplier):
    new_children: Tuple[SubArticleChildType, ...] = attr.ib(init=False)
    position: Union[Reference, StructuralReference] = attr.ib(init=False)
    pure_insertion: bool = attr.ib(init=False)

    @new_children.default
    def _new_children_default(self) -> Tuple[SubArticleChildType, ...]:
        assert self.source_sae.children is not None
        assert len(self.source_sae.children) == 1
        block_amendment_container = self.source_sae.children[0]
        assert isinstance(block_amendment_container, BlockAmendmentContainer)
        assert block_amendment_container.children is not None
        return block_amendment_container.children

    @position.default
    def _position_default(self) -> Union[Reference, StructuralReference]:
        assert isinstance(self.modification, BlockAmendment)
        return self.modification.position

    @pure_insertion.default
    def _pure_insertion_default(self) -> bool:
        assert isinstance(self.modification, BlockAmendment)
        return self.modification.pure_insertion

    @classmethod
    def can_apply(cls, modification: SemanticData) -> bool:
        return isinstance(modification, BlockAmendment)

    def get_cut_points_for_reference(self, parent_reference: Reference, children: Tuple[SubArticleChildType, ...]) -> Tuple[int, int]:
        assert isinstance(self.position, Reference)
        start_ref = self.position.first_in_range()
        end_ref = self.position.last_in_range()
        start_cut = first_matching_index(
            children,
            lambda c: bool(hasattr(c, 'relative_reference') and start_ref <= c.relative_reference.relative_to(parent_reference))
        )
        end_cut = first_matching_index(
            children,
            lambda c: bool(not hasattr(c, 'relative_reference') or end_ref < c.relative_reference.relative_to(parent_reference)),
            start=start_cut
        )
        # TODO: assert between start_cut == end_cut and pure_insertion
        # However if there is an act that marked an amendment an insertion
        # or vica-versa, that will need to be fixed.
        if start_cut == end_cut:
            # This is a quick hack and should be handled way better
            # Insertions should come before all structural elements.
            while start_cut > 0 and isinstance(children[start_cut-1], StructuralElement):
                start_cut -= 1
                end_cut -= 1
        return start_cut, end_cut

    def get_cut_points_for_special_reference(self, children: Tuple[SubArticleChildType, ...]) -> Tuple[int, int]:
        assert isinstance(self.position, StructuralReference)
        assert self.position.special is not None
        article_id = self.position.special.article_id
        start_cut = first_matching_index(
            children,
            lambda c: isinstance(c, Article) and not identifier_less(c.identifier, article_id)
        )
        if start_cut < len(children) and children[start_cut].identifier == article_id:
            article_found = True
            end_cut = start_cut + 1
        else:
            article_found = False
            # This is a quick hack and should be handled way better
            # Insertions should come before all structural elements.
            while start_cut > 0 and isinstance(children[start_cut-1], StructuralElement):
                start_cut -= 1
            end_cut = start_cut

        if self.position.special.position == SubtitleArticleComboType.BEFORE_WITH_ARTICLE:
            # TODO: assert between article_found and pure_insertion
            if article_found:
                start_cut -= 1
                assert isinstance(children[start_cut], Subtitle), self.position
        elif self.position.special.position == SubtitleArticleComboType.BEFORE_WITHOUT_ARTICLE:
            assert article_found, "BEFORE_WITHOUT_ARTICLE needs an existing article"
            if self.pure_insertion:
                # Move the end cut above the article
                end_cut -= 1
            else:
                assert isinstance(children[start_cut-1], Subtitle), self.position
                # Move the cutting frame to the Subtitle itself
                start_cut -= 1
                end_cut -= 1
        elif self.position.special.position == SubtitleArticleComboType.AFTER:
            assert article_found, "AFTER needs an existing article"
            if self.pure_insertion:
                # Move the end cut below the article
                start_cut += 1
            else:
                assert isinstance(children[start_cut + 1], Subtitle)
                # Move the cutting frame to the Subtitle itself
                start_cut += 1
                end_cut += 1
        else:
            raise ValueError("Unhandled SubtitleArticleComboType", self.position.special.position)
        return start_cut, end_cut

    def compute_new_children(self, parent_reference: Reference, children: Tuple[SubArticleChildType, ...]) -> Tuple[SubArticleChildType, ...]:
        if isinstance(self.position, Reference):
            start_cut_point, end_cut_point = self.get_cut_points_for_reference(parent_reference, children)
        elif isinstance(self.position, StructuralReference) and self.position.special is not None:
            start_cut_point, end_cut_point = self.get_cut_points_for_special_reference(children)
        elif isinstance(self.position, StructuralReference):
            start_cut_point, end_cut_point = get_cut_points_for_structural_reference(self.position, children)
        else:
            raise ValueError("Unknown amendment position type", self.position)

        assert start_cut_point <= end_cut_point
        self.applied = True
        return children[:start_cut_point] + self.new_children + children[end_cut_point:]

    def apply_to_sae(self, reference: Reference, sae: SubArticleElement) -> SubArticleElement:
        assert isinstance(self.position, Reference)
        if reference != self.position.parent():
            return sae
        assert sae.children is not None
        return attr.evolve(sae, children=self.compute_new_children(reference, sae.children))

    def apply_to_article(self, reference: Reference, article: Article) -> Article:
        new_children = []
        for child in self.compute_new_children(reference, article.children):
            assert isinstance(child, Paragraph)
            new_children.append(child)
        return attr.evolve(article, children=tuple(new_children))

    def apply_to_act(self, act: Act) -> Act:
        new_children = []
        for child in self.compute_new_children(Reference(act.identifier), act.children):
            assert isinstance(child, (Article, StructuralElement))
            new_children.append(child)
        return attr.evolve(act, children=tuple(new_children))

    def apply(self, act: Act) -> Act:
        if isinstance(self.position, Reference):
            expected_type = self.position.last_component_with_type()[1]
            assert expected_type is not None
            if expected_type is Article:
                return self.apply_to_act(act)
            if expected_type is Paragraph:
                article_ref = Reference(act.identifier, self.position.article)
                return act.map_articles(self.apply_to_article, article_ref)
            if issubclass(expected_type, SubArticleElement):
                return act.map_saes(self.apply_to_sae, self.position.parent())
            raise ValueError("Unknown reference type", self.position)
        return self.apply_to_act(act)


@ attr.s(slots=True, frozen=True, auto_attribs=True)
class ModificationSet:
    APPLIER_CLASSES: ClassVar[Tuple[Type[ModificationApplier], ...]] = (
        TextReplacementApplier,
        ArticleTitleAmendmentApplier,
        RepealApplier,
        BlockAmendmentApplier,
    )

    modifications: Tuple[Tuple[SubArticleElement, SemanticData], ...]

    def apply_all(self, act: Act) -> Act:
        appliers: List[ModificationApplier] = []
        for applier_class in self.APPLIER_CLASSES:
            appliers.extend(applier_class(m, sae) for sae, m in self.modifications if applier_class.can_apply(m))

        appliers.sort(key=lambda x: x.priority, reverse=True)

        for applier in appliers:
            act = applier.apply(act)
            if not applier.applied:
                print("WARN: Could not apply ", applier.modification)
        return act


@ attr.s(slots=True, frozen=True, auto_attribs=True)
class ActWithCachedData:
    act: Act
    enforcement_dates: EnforcementDateSet = attr.ib(init=False)

    @ enforcement_dates.default
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

    def is_interesting_date_for(self, act_id: str, date: Date) -> bool:
        return date in self.acts[act_id].interesting_dates()

    def acts_at_date(self, date: Date) -> Iterable[Act]:
        for act in self.acts.values():
            try:
                yield act.state_at_date(date)
            except ActNotInForce:
                pass

    @ staticmethod
    def _get_amendments_and_repeals(act: Act) -> Dict[str, List[Tuple[SubArticleElement, SemanticData]]]:
        modifications_per_act: Dict[str, List[Tuple[SubArticleElement, SemanticData]]] = defaultdict(list)

        def sae_walker(reference: Reference, sae: SubArticleElement) -> SubArticleElement:
            if sae.semantic_data is None:
                return sae
            for semantic_data_element in sae.semantic_data:
                if isinstance(semantic_data_element, EnforcementDate):
                    continue
                # Type is ignored here, since all subclasses except for EnforcementDate
                # have a position field. Maybe this should be solved by introducing a class
                # in the middle with a position, but it isn't worth it TBH.
                # This will fail very fast and very loudly if there is a problem.
                modified_ref = semantic_data_element.position  # type: ignore
                assert modified_ref.act is not None
                modifications_per_act[modified_ref.act].append((sae, semantic_data_element))
                modifications_per_act[act.identifier].append((sae, Repeal(position=reference)))
            return sae
        act.map_saes(sae_walker)
        return modifications_per_act

    def apply_all_modifications(self, amending_act: Act) -> Tuple[str, ...]:
        modified_acts = []
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
            modified_acts.append(act_id)
        return tuple(modified_acts)
