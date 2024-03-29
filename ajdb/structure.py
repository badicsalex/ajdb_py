# Copyright 2020, Alex Badics, All Rights Reserved

import sys
import inspect
import gc
from typing import Tuple, Union, Optional, Callable, Dict, Iterable, Any, Sequence, List, ClassVar
from collections import defaultdict

import attr

from hun_law.utils import Date, cut_by_identifier
from hun_law.structure import Act, Article, \
    SubArticleElement, Paragraph, NumericPoint, AlphabeticPoint, NumericSubpoint, AlphabeticSubpoint, \
    QuotedBlock, BlockAmendmentContainer, \
    Reference, \
    StructuralElement, \
    EnforcementDate, EnforcementDateTypes, DaysAfterPublication, DayInMonthAfterPublication

from ajdb.utils import evolve_into
from ajdb.object_storage import CachedTypedObjectStorage


@attr.s(slots=True, frozen=True, auto_attribs=True, kw_only=True)
class ConcreteEnforcementDate:
    from_date: Date
    to_date: Optional[Date] = None

    @staticmethod
    def _concretize_single_date(date: EnforcementDateTypes, publication_date: Date) -> Date:
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
    def from_enforcement_date(cls, enforcement_date: EnforcementDate, publication_date: Date) -> 'ConcreteEnforcementDate':
        return cls(
            from_date=cls._concretize_single_date(enforcement_date.date, publication_date),
            to_date=enforcement_date.repeal_date
        )

    def is_in_force_at_date(self, date: Date) -> bool:
        if date < self.from_date:
            return False
        if self.to_date is not None and date > self.to_date:
            return False
        return True


@attr.s(slots=True, frozen=True, auto_attribs=True)
class LastModified:
    date: Date
    modified_by: Reference


@attr.s(slots=True, frozen=True, auto_attribs=True, kw_only=True)
class SaeMetadata:
    enforcement_date: Optional[ConcreteEnforcementDate] = None
    last_modified: Optional[LastModified] = None


@attr.s(slots=True, frozen=True, auto_attribs=True, kw_only=True)
class AlphabeticSubpointWM(AlphabeticSubpoint):
    metadata: SaeMetadata


@attr.s(slots=True, frozen=True, auto_attribs=True, kw_only=True)
class NumericSubpointWM(NumericSubpoint):
    metadata: SaeMetadata


@attr.s(slots=True, frozen=True, auto_attribs=True, kw_only=True)
class AlphabeticPointWM(AlphabeticPoint):
    ALLOWED_CHILDREN_TYPE = (AlphabeticSubpointWM, NumericSubpointWM, )
    metadata: SaeMetadata


@attr.s(slots=True, frozen=True, auto_attribs=True, kw_only=True)
class NumericPointWM(NumericPoint):
    ALLOWED_CHILDREN_TYPE = (AlphabeticSubpointWM, )
    metadata: SaeMetadata


@attr.s(slots=True, frozen=True, auto_attribs=True, kw_only=True)
class ParagraphWM(Paragraph):
    ALLOWED_CHILDREN_TYPE = (AlphabeticPointWM, NumericPointWM, QuotedBlock, BlockAmendmentContainer)
    metadata: SaeMetadata


SaeWMType = Union[ParagraphWM, NumericPointWM, AlphabeticPointWM, NumericSubpointWM, AlphabeticSubpointWM]

WM_ABLE_SAE_CLASSES = (Paragraph, NumericPoint, AlphabeticPoint, NumericSubpoint, AlphabeticSubpoint)
SAE_WM_CLASSES = (ParagraphWM, NumericPointWM, AlphabeticPointWM, NumericSubpointWM, AlphabeticSubpointWM)
SAE_SIMPLE_TO_WM_MAP = {c.__base__: c for c in SAE_WM_CLASSES}


def add_metadata(
    sae: Union[Paragraph, NumericPoint, AlphabeticPoint, NumericSubpoint, AlphabeticSubpoint],
    metadata: SaeMetadata = SaeMetadata(),
) -> SaeWMType:
    sae_type = type(sae)
    wm_type = SAE_SIMPLE_TO_WM_MAP[sae_type]
    result: SaeWMType = evolve_into(sae, wm_type, metadata=metadata)
    return result


@attr.s(slots=True, frozen=True)
class ArticleWM(Article):
    def __attrs_post_init__(self) -> None:
        for p in self.children:
            assert isinstance(p, ParagraphWM), "All paragraphs shall have metadata (paragraph Id:{})".format(p.identifier)

    @staticmethod
    def sae_metadata_remover(_reference: Reference, sae: SubArticleElement) -> SubArticleElement:
        return evolve_into(  # type:ignore
            sae,
            sae.__class__.__base__,
        )

    def to_simple_article(self) -> Article:
        result: Article = evolve_into(self, Article)
        # TODO: Do more than remove metadata: mark not in force SAEs
        return result.map_recursive(Reference(), self.sae_metadata_remover)

    def map_recursive_wm(
        self,
        parent_reference: Reference,
        modifier: Callable[[Reference, SaeWMType], SaeWMType],
        filter_for_reference: Optional[Reference] = None,
        children_first: bool = False,
    ) -> 'ArticleWM':
        def asserting_modifier(reference: Reference, sae: SubArticleElement) -> SubArticleElement:
            assert isinstance(sae, SAE_WM_CLASSES)
            return modifier(reference, sae)
        result = super().map_recursive(parent_reference, asserting_modifier, filter_for_reference, children_first)
        assert isinstance(result, ArticleWM)
        return result

    def at_reference(self, reference: Reference) -> Tuple[SaeWMType, ...]:
        result: List[SaeWMType] = []
        for element in super().at_reference(reference):
            assert isinstance(element, SAE_WM_CLASSES)
            result.append(element)
        return tuple(result)


# Needed for attr.s(slots=True), and __subclasses__ to work correctly.
# it is used in the converter of CachedTypedObjectStorage(ArticleWM)
gc.collect()


@attr.s(slots=True, frozen=True, auto_attribs=True)
class ArticleWMProxy:
    OBJECT_STORAGE: ClassVar[CachedTypedObjectStorage[ArticleWM]] = \
        CachedTypedObjectStorage(ArticleWM, 'articles', 10000)

    key: str
    identifier: str

    @classmethod
    def save_article(cls, article: ArticleWM) -> 'ArticleWMProxy':
        key = cls.OBJECT_STORAGE.save(article)
        return ArticleWMProxy(key, article.identifier)

    @property
    def article(self) -> ArticleWM:
        return self.OBJECT_STORAGE.load(self.key)

    @property
    def children(self) -> Tuple[Paragraph, ...]:
        return self.article.children

    def to_simple_article(self) -> Article:
        return self.article.to_simple_article()

    @property
    def relative_reference(self) -> 'Reference':
        return Reference(article=self.identifier)


@attr.s(slots=True, frozen=True, auto_attribs=True, kw_only=True)
class ActWM:
    identifier: str
    publication_date: Date
    subject: str
    preamble: str
    children: Tuple[Union[StructuralElement, ArticleWM, ArticleWMProxy], ...] = attr.ib()
    interesting_dates: Tuple[Date, ...]

    articles: Tuple[Union[ArticleWM, ArticleWMProxy], ...] = attr.ib(init=False)
    articles_map: Dict[str, Union[ArticleWM, ArticleWMProxy]] = attr.ib(init=False)

    @children.validator
    def _children_validator(self, _attribute: Any, children: Tuple[Paragraph, ...]) -> None:
        # Attrs validators as decorators are what they are, it cannot be a function.
        # pylint: disable=no-self-use
        # Delete me when attr.evolve does proper type checking with mypy
        assert all(isinstance(c, (StructuralElement, ArticleWM, ArticleWMProxy)) for c in children)

    @articles.default
    def _articles_default(self) -> Tuple[Union[ArticleWM, ArticleWMProxy], ...]:
        return tuple(c for c in self.children if isinstance(c, (ArticleWM, ArticleWMProxy)))

    @articles_map.default
    def _articles_map_default(self) -> Dict[str, Union[ArticleWM, ArticleWMProxy]]:
        return {c.identifier: c for c in self.articles}

    def map_articles(
        self,
        modifier: Callable[[Reference, ArticleWM], ArticleWM],
        filter_for_reference: Optional[Reference] = None,
    ) -> 'ActWM':
        new_children = []
        children_changed = False
        for child in self.children:
            if isinstance(child, (ArticleWM, ArticleWMProxy)):
                article_reference = Reference(self.identifier, child.identifier)
                if filter_for_reference is None or filter_for_reference.contains(article_reference):
                    if isinstance(child, ArticleWM):
                        child_to_modify = child
                    else:
                        child_to_modify = child.article
                    new_child = modifier(article_reference, child_to_modify)
                    if new_child is not child_to_modify:
                        child = new_child
                        children_changed = True
            new_children.append(child)
        if not children_changed:
            return self
        return attr.evolve(self, children=tuple(new_children))

    def map_saes(
        self,
        modifier: Callable[[Reference, SaeWMType], SaeWMType],
        filter_for_reference: Optional[Reference] = None,
        children_first: bool = False,
    ) -> 'ActWM':
        def article_modifier(_reference: Reference, article: ArticleWM) -> ArticleWM:
            return article.map_recursive_wm(Reference(self.identifier), modifier, filter_for_reference, children_first)
        return self.map_articles(article_modifier)

    def to_simple_act(self) -> Act:
        new_children: Tuple[Union[StructuralElement, Article], ...] = tuple(
            c.to_simple_article() if isinstance(c, (ArticleWM, ArticleWMProxy)) else c for c in self.children
        )
        return evolve_into(  # type: ignore
            self,
            Act,
            children=new_children
        )

    def save_all_articles(self) -> "ActWM":
        if not any(isinstance(c, (ArticleWM)) for c in self.children):
            return self
        new_children: Tuple[Union[StructuralElement, ArticleWMProxy], ...] = tuple(
            ArticleWMProxy.save_article(c) if isinstance(c, (ArticleWM)) else c for c in self.children
        )
        return attr.evolve(self, children=new_children)

    def article(self, article_id: str) -> ArticleWM:
        result = self.articles_map[str(article_id)]
        if isinstance(result, ArticleWMProxy):
            return result.article
        return result

    def at_reference(self, reference: Reference) -> Tuple[Union[ArticleWM, SaeWMType], ...]:
        assert reference.act is None or reference.act == self.identifier
        assert reference.article is not None
        if reference.paragraph is None and reference.point is None and reference.subpoint is None:
            if isinstance(reference.article, str):
                return (self.article(reference.article),)
            return tuple(
                element.article if isinstance(element, ArticleWMProxy) else element
                for element in cut_by_identifier(self.articles, reference.article[0], reference.article[1])
            )
        assert isinstance(reference.article, str)
        return self.article(reference.article).at_reference(reference)


# Needed for attr.s(slots=True), and __subclasses__ to work correctly.
# it is used in the converter of CachedTypedObjectStorage(ActWM)
gc.collect()


@attr.s(slots=True, frozen=True, auto_attribs=True)
class ActWMProxy:
    OBJECT_STORAGE: ClassVar[CachedTypedObjectStorage[ActWM]] = \
        CachedTypedObjectStorage(ActWM, 'acts', 1000)

    key: str
    identifier: str
    subject: str
    interesting_dates: Tuple[Date, ...]

    @classmethod
    def save_act(cls, act: ActWM) -> 'ActWMProxy':
        act = act.save_all_articles()
        key = cls.OBJECT_STORAGE.save(act)
        return ActWMProxy(key, act.identifier, act.subject, act.interesting_dates)

    @property
    def act(self) -> ActWM:
        return self.OBJECT_STORAGE.load(self.key)

    def to_simple_act(self) -> Act:
        return self.act.to_simple_act()


@attr.s(slots=True, frozen=True, auto_attribs=True)
class ReferencePair:
    from_ref: Reference
    to_ref: Reference


@attr.s(slots=True, frozen=True, auto_attribs=True)
class ReferencePairList:
    references: Tuple[ReferencePair, ...]


# Needed for attr.s(slots=True), and __subclasses__ to work correctly.
gc.collect()


@attr.s(slots=True, frozen=True, auto_attribs=True)
class ReferencePairListProxy:
    OBJECT_STORAGE: ClassVar[CachedTypedObjectStorage[ReferencePairList]] = \
        CachedTypedObjectStorage(ReferencePairList, 'ref_lists', 1000)
    key: str

    @classmethod
    def save_reference_list(cls, data: ReferencePairList) -> 'ReferencePairListProxy':
        key = cls.OBJECT_STORAGE.save(data)
        return ReferencePairListProxy(key)

    @property
    def reference_list(self) -> ReferencePairList:
        return self.OBJECT_STORAGE.load(self.key)


@attr.s(slots=True, frozen=True, auto_attribs=True, kw_only=True)
class ActSet:
    acts: Tuple[Union[ActWMProxy, ActWM], ...] = attr.ib(default=())
    reference_index: Tuple[Tuple[str, ReferencePairListProxy], ...] = attr.ib(default=())
    acts_map: Dict[str, Union[ActWMProxy, ActWM]] = attr.ib(init=False)
    reference_index_map: Dict[str, ReferencePairListProxy] = attr.ib(init=False)

    @acts.validator
    def _acts_validator(self, _attribute: Any, acts: Tuple[Union[ActWMProxy, ActWM], ...]) -> None:
        # Attrs validators as decorators are what they are, it cannot be a function.
        # pylint: disable=no-self-use
        # Delete me when attr.evolve does proper type checking with mypy
        assert all(isinstance(a, (ActWM, ActWMProxy)) for a in acts)

    @acts_map.default
    def _acts_map_default(self) -> Dict[str, Union[ActWMProxy, ActWM]]:
        return {act.identifier: act for act in self.acts}

    @reference_index_map.default
    def _reference_index_map_default(self) -> Dict[str, ReferencePairListProxy]:
        return dict(self.reference_index)

    def interesting_acts_at_date(self, date: Date) -> Iterable[ActWM]:
        for act in self.acts:
            if date in act.interesting_dates:
                if isinstance(act, ActWM):
                    yield act
                else:
                    yield act.act

    def act(self, act_id: str) -> ActWM:
        result = self.acts_map[act_id]
        if isinstance(result, ActWM):
            return result
        return result.act

    def has_act(self, act_id: str) -> bool:
        return act_id in self.acts_map

    def replace_acts(self, acts: Sequence[ActWM]) -> 'ActSet':
        acts_to_replace_as_dict = {act.identifier: act for act in acts}
        new_acts: List[Union[ActWMProxy, ActWM]] = []
        for act in self.acts:
            if act.identifier in acts_to_replace_as_dict:
                new_acts.append(acts_to_replace_as_dict.pop(act.identifier))
            else:
                new_acts.append(act)
        assert len(acts_to_replace_as_dict) == 0, "Not all acts to replace existed in the first place"
        # TODO: Record changes ? Mainly amender and amended acts.
        return ActSet(acts=tuple(new_acts))

    def add_acts(self, acts: Sequence[ActWM]) -> 'ActSet':
        assert not any(act.identifier in self.acts_map for act in acts)
        # TODO: Record changes
        return ActSet(acts=self.acts + tuple(acts))

    def save_all_acts(self) -> "ActSet":
        if not any(isinstance(c, (ActWM)) for c in self.acts):
            return self
        new_acts: Tuple[Union[StructuralElement, ActWMProxy], ...] = tuple(
            ActWMProxy.save_act(c) if isinstance(c, (ActWM)) else c for c in self.acts
        )
        return attr.evolve(self, acts=new_acts)

    def has_unsaved(self) -> bool:
        return any(isinstance(act, ActWM) for act in self.acts)

    def get_incoming_references(self, act_id: str) -> Dict[Reference, Tuple[Reference, ...]]:
        if act_id not in self.reference_index_map:
            return {}
        ref_list = self.reference_index_map[act_id].reference_list
        result = defaultdict(list)
        for ref in ref_list.references:
            result[ref.to_ref].append(ref.from_ref)
        return {k: tuple(v) for k, v in result.items()}


def __do_post_processing() -> None:
    for _, cls in inspect.getmembers(sys.modules[__name__], inspect.isclass):
        if attr.has(cls):
            attr.resolve_types(cls)

    # Needed for attr.s(slots=True), and __subclasses__ to work correctly.
    gc.collect()


__do_post_processing()
