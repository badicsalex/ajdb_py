# Copyright 2020, Alex Badics, All Rights Reserved
from typing import Tuple, Dict,  Set, List, Type, ClassVar, Union
from pathlib import Path
from abc import ABC, abstractmethod
import gzip
import json
from collections import defaultdict

import yaml
import attr

from hun_law.structure import \
    Act, Article, Paragraph, SubArticleElement, BlockAmendmentContainer, \
    StructuralElement, Subtitle, Book,\
    Reference, StructuralReference, SubtitleArticleComboType, \
    EnforcementDate, \
    SemanticData, Repeal, TextAmendment, ArticleTitleAmendment, BlockAmendment, \
    SubArticleChildType

from hun_law.utils import Date, identifier_less
from hun_law.parsers.semantic_parser import ActSemanticsParser
from hun_law import dict2object

from ajdb.structure import ConcreteEnforcementDate, \
    ArticleWM, ActWM, ParagraphWM,\
    SaeWMType, SaeMetadata, add_metadata, WM_ABLE_SAE_CLASSES, SAE_WM_CLASSES

from ajdb.utils import iterate_all_saes_of_act, first_matching_index, evolve_into
from ajdb.fixups import apply_fixups

NOT_ENFORCED_TEXT = ' '

act_converter = dict2object.get_converter(Act)


@attr.s(slots=True, frozen=True, auto_attribs=True)
class EnforcementDateSet:
    default: ConcreteEnforcementDate
    specials: Tuple[Tuple[Reference, ConcreteEnforcementDate], ...]

    @classmethod
    def from_act(cls, act: Act) -> 'EnforcementDateSet':
        default = None
        specials = []
        for sae in iterate_all_saes_of_act(act):
            assert sae.semantic_data is not None
            for semantic_data_element in sae.semantic_data:
                if isinstance(semantic_data_element, EnforcementDate):
                    concrete_ed = ConcreteEnforcementDate.from_enforcement_date(semantic_data_element, act.publication_date)
                    if semantic_data_element.position is None:
                        assert default is None
                        default = concrete_ed
                    else:
                        ref = attr.evolve(semantic_data_element.position, act=act.identifier)
                        specials.append((ref, concrete_ed))
        assert default is not None, act.identifier
        assert all(default.from_date <= special.from_date for _, special in specials)
        assert all(special.to_date is None for _, special in specials)
        return EnforcementDateSet(default, tuple(specials))

    def sae_modifier(self, reference: Reference, sae: SubArticleElement) -> SubArticleElement:
        if not isinstance(sae, WM_ABLE_SAE_CLASSES):
            return sae
        applicable_ced = self.default
        for ced_reference, ced in self.specials:
            if ced_reference.contains(reference):
                applicable_ced = ced
        if isinstance(sae, SAE_WM_CLASSES):
            return attr.evolve(
                sae,
                metadata=attr.evolve(
                    sae.metadata,
                    enforcement_date=applicable_ced
                )
            )

        return add_metadata(sae, metadata=SaeMetadata(enforcement_date=applicable_ced))

    def article_modifier(self, reference: Reference, article: Article) -> ArticleWM:
        article = article.map_recursive(reference, self.sae_modifier, children_first=True)
        if isinstance(article, ArticleWM):
            return article
        article_wm: ArticleWM = evolve_into(article, ArticleWM)
        return article_wm

    def interesting_dates(self) -> Tuple[Date, ...]:
        result = set()
        result.add(self.default.from_date)
        if self.default.to_date is not None:
            result.add(self.default.to_date)

        result.update(special.from_date for _, special in self.specials)
        return tuple(result)

    @classmethod
    def convert_act(cls, act: Act) -> ActWM:
        enforcement_set = cls.from_act(act)
        act = act.map_articles(enforcement_set.article_modifier)
        if isinstance(act, ActWM):
            return act
        act_wm: ActWM = evolve_into(act, ActWM, interesting_dates=enforcement_set.interesting_dates())
        return act_wm


@attr.s(slots=True, auto_attribs=True)
class ModificationApplier(ABC):
    modification: SemanticData = attr.ib()
    source_sae: SaeWMType = attr.ib()
    current_date: Date = attr.ib()
    applied: bool = attr.ib(init=False, default=False)

    @classmethod
    @abstractmethod
    def can_apply(cls, modification: SemanticData) -> bool:
        pass

    @abstractmethod
    def apply(self, act: ActWM) -> ActWM:
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

    def text_replacer(self, _reference: Reference, sae: SaeWMType) -> SaeWMType:
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

    def apply(self, act: ActWM) -> ActWM:
        return act.map_saes_wm(self.text_replacer, self.position)

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

    def modifier(self, _reference: Reference, article: ArticleWM) -> ArticleWM:
        assert isinstance(self.modification, ArticleTitleAmendment)
        assert article.title is not None
        self.applied = self.modification.original_text in article.title
        new_title = article.title.replace(self.modification.original_text, self.modification.replacement_text)
        return attr.evolve(
            article,
            title=new_title,
        )

    def apply(self, act: ActWM) -> ActWM:
        assert isinstance(self.modification, ArticleTitleAmendment)
        _, reference_type = self.modification.position.last_component_with_type()
        assert reference_type is Article
        return act.map_articles_wm(self.modifier, self.modification.position)


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

    def create_new_metadata(self, sae: SaeWMType) -> SaeMetadata:
        return SaeMetadata(
            enforcement_date=ConcreteEnforcementDate(
                from_date=sae.metadata.enforcement_date.from_date,
                to_date=self.current_date,
            )
        )

    def sae_repealer(self, _reference: Reference, sae: SaeWMType) -> SaeWMType:
        self.applied = True
        return sae.__class__(
            identifier=sae.identifier,
            text=NOT_ENFORCED_TEXT,
            semantic_data=(),
            outgoing_references=(),
            act_id_abbreviations=(),
            metadata=self.create_new_metadata(sae),
        )

    def article_repealer(self, _reference: Reference, article: ArticleWM) -> ArticleWM:
        first_paragraph = article.children[0]
        assert isinstance(first_paragraph, ParagraphWM)
        self.applied = True
        return ArticleWM(
            identifier=article.identifier,
            children=(
                ParagraphWM(
                    text=NOT_ENFORCED_TEXT,
                    semantic_data=(),
                    outgoing_references=(),
                    act_id_abbreviations=(),
                    metadata=self.create_new_metadata(first_paragraph),
                ),
            ),
        )

    def apply_to_act(self, act: ActWM) -> ActWM:
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

    def apply(self, act: ActWM) -> ActWM:
        assert isinstance(self.modification, Repeal)
        if isinstance(self.modification.position, Reference):
            _, reference_type = self.modification.position.last_component_with_type()
            if reference_type is Article:
                return act.map_articles_wm(self.article_repealer, self.modification.position)
            return act.map_saes_wm(self.sae_repealer, self.modification.position)
        return self.apply_to_act(act)


@attr.s(slots=True, auto_attribs=True)
class BlockAmendmentApplier(ModificationApplier):
    new_children: Tuple[SubArticleChildType, ...] = attr.ib(init=False)
    position: Union[Reference, StructuralReference] = attr.ib(init=False)
    pure_insertion: bool = attr.ib(init=False)

    def sae_metadata_adder(self, _reference: Reference, sae: SubArticleElement) -> SubArticleElement:
        if not isinstance(sae, WM_ABLE_SAE_CLASSES):
            return sae
        assert not isinstance(sae, SAE_WM_CLASSES)
        children_metadata = SaeMetadata(
            enforcement_date=ConcreteEnforcementDate(from_date=self.current_date)
        )
        return add_metadata(sae, metadata=children_metadata)

    @new_children.default
    def _new_children_default(self) -> Tuple[SubArticleChildType, ...]:
        assert self.source_sae.children is not None
        assert len(self.source_sae.children) == 1
        block_amendment_container = self.source_sae.children[0]
        assert isinstance(block_amendment_container, BlockAmendmentContainer)
        assert block_amendment_container.children is not None
        result = []
        for child in block_amendment_container.children:
            if isinstance(child, WM_ABLE_SAE_CLASSES):
                child = child.map_recursive(Reference(), self.sae_metadata_adder, children_first=True)
            if isinstance(child, Article):
                child = child.map_recursive(Reference(), self.sae_metadata_adder, children_first=True)
                child = evolve_into(child, ArticleWM)
            result.append(child)
        return tuple(result)

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

    def apply_to_sae(self, reference: Reference, sae: SaeWMType) -> SaeWMType:
        assert isinstance(self.position, Reference)
        if reference != self.position.parent():
            return sae
        assert sae.children is not None
        return attr.evolve(sae, children=self.compute_new_children(reference, sae.children))

    def apply_to_article(self, reference: Reference, article: ArticleWM) -> ArticleWM:
        new_children = []
        for child in self.compute_new_children(reference, article.children):
            assert isinstance(child, ParagraphWM)
            new_children.append(child)
        return attr.evolve(article, children=tuple(new_children))

    def apply_to_act(self, act: ActWM) -> ActWM:
        new_children = []
        for child in self.compute_new_children(Reference(act.identifier), act.children):
            assert isinstance(child, (ArticleWM, StructuralElement))
            new_children.append(child)
        return attr.evolve(act, children=tuple(new_children))

    def apply(self, act: ActWM) -> ActWM:
        if isinstance(self.position, Reference):
            expected_type = self.position.last_component_with_type()[1]
            assert expected_type is not None
            if expected_type is Article:
                return self.apply_to_act(act)
            if expected_type is Paragraph:
                article_ref = Reference(act.identifier, self.position.article)
                return act.map_articles_wm(self.apply_to_article, article_ref)
            if issubclass(expected_type, SubArticleElement):
                return act.map_saes_wm(self.apply_to_sae, self.position.parent())
            raise ValueError("Unknown reference type", self.position)
        return self.apply_to_act(act)


@attr.s(slots=True, frozen=True, auto_attribs=True)
class ModificationSet:
    APPLIER_CLASSES: ClassVar[Tuple[Type[ModificationApplier], ...]] = (
        TextReplacementApplier,
        ArticleTitleAmendmentApplier,
        RepealApplier,
        BlockAmendmentApplier,
    )

    modifications: Tuple[Tuple[SaeWMType, SemanticData], ...]

    def apply_all(self, act: ActWM, current_date: Date) -> ActWM:
        appliers: List[ModificationApplier] = []
        for applier_class in self.APPLIER_CLASSES:
            appliers.extend(applier_class(m, sae, current_date) for sae, m in self.modifications if applier_class.can_apply(m))

        appliers.sort(key=lambda x: x.priority, reverse=True)

        for applier in appliers:
            act = applier.apply(act)
            if not applier.applied:
                print("WARN: Could not apply ", applier.modification)
        return act


@attr.s(slots=True, auto_attribs=True)
class AmendmentAndRepealExtractor:
    at_date: Date
    act_identifier: str
    modifications_per_act: Dict[str, List[Tuple[SaeWMType, SemanticData]]] = \
        attr.ib(init=False, factory=lambda: defaultdict(list))

    def sae_walker(self, reference: Reference, sae: SaeWMType) -> SaeWMType:
        if sae.semantic_data is None:
            return sae
        if not sae.metadata.enforcement_date.is_in_force_at_date(self.at_date):
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
            self.modifications_per_act[modified_ref.act].append((sae, semantic_data_element))
            self.modifications_per_act[self.act_identifier].append((sae, Repeal(position=reference)))
        return sae

    @classmethod
    def get_amendments_and_repeals(cls, act: ActWM, at_date: Date) -> Dict[str, List[Tuple[SaeWMType, SemanticData]]]:
        instance = cls(at_date, act.identifier)
        act.map_saes_wm(instance.sae_walker)
        return instance.modifications_per_act


class ActSet:
    acts: Dict[str, ActWM]

    def __init__(self) -> None:
        self.acts = {}

    def load_from_file(self, path: Path) -> None:
        if path.suffix == '.gz':
            with gzip.open(path, 'rt') as f:
                the_dict = json.load(f)
        elif path.suffix == '.yaml':
            with open(path, 'rt') as f:
                the_dict = yaml.load(f, Loader=yaml.Loader)
        else:
            with open(path, 'rt') as f:
                the_dict = json.load(f)
        self.add_act(act_converter.to_object(the_dict))

    def add_act(self, act: Act) -> None:
        act = apply_fixups(act)
        self.acts[act.identifier] = EnforcementDateSet.convert_act(act)

    def interesting_dates(self) -> Tuple[Date, ...]:
        result: Set[Date] = set()
        for act in self.acts.values():
            result.update(act.interesting_dates)
        return tuple(sorted(result))

    def is_interesting_date_for(self, act_id: str, date: Date) -> bool:
        return date in self.acts[act_id].interesting_dates

    def apply_all_modifications(self, amending_act: ActWM, at_date: Date) -> Tuple[str, ...]:
        modified_acts = []
        extracted_modifications = AmendmentAndRepealExtractor.get_amendments_and_repeals(amending_act, at_date)
        for act_id, modifications in extracted_modifications.items():
            if act_id not in self.acts:
                continue
            act: ActWM = self.acts[act_id]
            if act.identifier != amending_act.identifier:
                print("AMENDING ", act.identifier, "WITH", amending_act.identifier)

            modification_set = ModificationSet(tuple(modifications))
            act = modification_set.apply_all(act, at_date)

            reparsed_act = ActSemanticsParser.add_semantics_to_act(act)
            assert isinstance(reparsed_act, ActWM)
            self.acts[act_id] = reparsed_act
            modified_acts.append(act_id)
        return tuple(modified_acts)
