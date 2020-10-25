# Copyright 2020, Alex Badics, All Rights Reserved

import sys
import inspect
import gc
from typing import Tuple, Union, Optional, Callable, Dict, Iterable, Any, Sequence, List
import functools

import attr

from hun_law import dict2object
from hun_law.utils import Date
from hun_law.structure import Act, Article, \
    SubArticleElement, Paragraph, NumericPoint, AlphabeticPoint, NumericSubpoint, AlphabeticSubpoint, \
    QuotedBlock, BlockAmendmentContainer, \
    Reference, \
    StructuralElement, \
    EnforcementDate, EnforcementDateTypes, DaysAfterPublication, DayInMonthAfterPublication

from ajdb.utils import evolve_into
from ajdb.object_storage import ObjectStorage


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


@attr.s(slots=True, frozen=True, auto_attribs=True)
class ArticleWMProxy:
    key: str
    identifier: str

    @classmethod
    def save_article(cls, article: ArticleWM) -> 'ArticleWMProxy':
        article_as_dict = ARTICLE_WM_CONVERTER.to_dict(article)
        key = ObjectStorage('articles').save(article_as_dict)
        return ArticleWMProxy(key, article.identifier)

    @property
    def article(self) -> ArticleWM:
        return self._get_article(self.key)

    @classmethod
    @functools.lru_cache(maxsize=10000)
    def _get_article(cls, key: str) -> ArticleWM:
        result: ArticleWM = ARTICLE_WM_CONVERTER.to_object(ObjectStorage('articles').load(key))
        return result

    def to_simple_article(self) -> Article:
        return self.article.to_simple_article()


@attr.s(slots=True, frozen=True, auto_attribs=True, kw_only=True)
class ActWM:
    identifier: str
    publication_date: Date
    subject: str
    preamble: str
    children: Tuple[Union[StructuralElement, ArticleWM, ArticleWMProxy], ...] = attr.ib()
    interesting_dates: Tuple[Date, ...]

    @children.validator
    def _children_validator(self, _attribute: Any, children: Tuple[Paragraph, ...]) -> None:
        # Attrs validators as decorators are what they are, it cannot be a function.
        # pylint: disable=no-self-use
        # Delete me when attr.evolve does proper type checking with mypy
        assert all(isinstance(c, (StructuralElement, ArticleWM, ArticleWMProxy)) for c in children)

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


@attr.s(slots=True, frozen=True, auto_attribs=True)
class ActWMProxy:
    key: str
    identifier: str
    interesting_dates: Tuple[Date, ...]

    @classmethod
    def save_act(cls, act: ActWM) -> 'ActWMProxy':
        act = act.save_all_articles()
        act_as_dict = ACT_WM_CONVERTER.to_dict(act)
        key = ObjectStorage('acts').save(act_as_dict)
        return ActWMProxy(key, act.identifier, act.interesting_dates)

    @property
    def act(self) -> ActWM:
        return self._get_act(self.key)

    @classmethod
    @functools.lru_cache(maxsize=1000)
    def _get_act(cls, key: str) -> ActWM:
        act_as_dict = ObjectStorage('acts').load(key)
        result: ActWM = ACT_WM_CONVERTER.to_object(act_as_dict)
        return result

    def to_simple_act(self) -> Act:
        return self.act.to_simple_act()


@attr.s(slots=True, frozen=True, auto_attribs=True, kw_only=True)
class ActSet:
    acts: Tuple[Union[ActWMProxy, ActWM], ...] = attr.ib()
    acts_map: Dict[str, Union[ActWMProxy, ActWM]] = attr.ib(init=False)

    @acts.validator
    def _acts_validator(self, _attribute: Any, acts: Tuple[Union[ActWMProxy, ActWM], ...]) -> None:
        # Attrs validators as decorators are what they are, it cannot be a function.
        # pylint: disable=no-self-use
        # Delete me when attr.evolve does proper type checking with mypy
        assert all(isinstance(a, (ActWM, ActWMProxy)) for a in acts)

    @acts_map.default
    def _acts_map_default(self) -> Dict[str, Union[ActWMProxy, ActWM]]:
        return {act.identifier: act for act in self.acts}

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
        return ActSet(acts=tuple(new_acts))


def __do_post_processing() -> None:
    for _, cls in inspect.getmembers(sys.modules[__name__], inspect.isclass):
        if attr.has(cls):
            attr.resolve_types(cls)

    # Needed for attr.s(slots=True), and __subclasses__ to work correctly.
    gc.collect()


__do_post_processing()

# Converters can only be made after post processing due to the magic subclasses thing.
ARTICLE_WM_CONVERTER = dict2object.get_converter(ArticleWM)
ACT_WM_CONVERTER = dict2object.get_converter(ActWM)
