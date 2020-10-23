# Copyright 2020, Alex Badics, All Rights Reserved

import sys
import inspect
import gc
from typing import Tuple, Union, Optional, Callable
import attr

from hun_law.structure import Act, Article, \
    SubArticleElement, Paragraph, NumericPoint, AlphabeticPoint, NumericSubpoint, AlphabeticSubpoint, \
    QuotedBlock, BlockAmendmentContainer, \
    Reference, \
    EnforcementDate, EnforcementDateTypes, DaysAfterPublication, DayInMonthAfterPublication

from hun_law.utils import Date

from ajdb.utils import evolve_into


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
    enforcement_date: ConcreteEnforcementDate
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


def add_metadata(sae: Union[Paragraph, NumericPoint, AlphabeticPoint, NumericSubpoint, AlphabeticSubpoint], metadata: SaeMetadata) -> SaeWMType:
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
        return result.map_recursive(Reference(), self.sae_metadata_remover)


@attr.s(slots=True, frozen=True, auto_attribs=True, kw_only=True)
class ActWM(Act):
    interesting_dates: Tuple[Date, ...]

    def __attrs_post_init__(self) -> None:
        for a in self.children:
            if isinstance(a, Article):
                assert isinstance(a, ArticleWM), "All articles shall have metadata (Id:{})".format(a.identifier)

    def map_articles_wm(
        self,
        modifier: Callable[['Reference', ArticleWM], ArticleWM],
        filter_for_reference: Optional['Reference'] = None,
    ) -> 'ActWM':
        def asserting_modifier(r: Reference, a: Article) -> Article:
            assert isinstance(a, ArticleWM)
            return modifier(r, a)
        result = super().map_articles(asserting_modifier, filter_for_reference)
        assert isinstance(result, ActWM)
        return result

    def map_saes_wm(
        self,
        modifier: Callable[['Reference', SaeWMType], SaeWMType],
        filter_for_reference: Optional['Reference'] = None
    ) -> 'ActWM':
        def asserting_modifier(r: Reference, sae: SubArticleElement) -> SubArticleElement:
            assert isinstance(sae, SAE_WM_CLASSES)
            return modifier(r, sae)
        result = super().map_saes(asserting_modifier, filter_for_reference)
        assert isinstance(result, ActWM)
        return result

    def to_simple_act(self) -> Act:
        return evolve_into(  # type: ignore
            self,
            Act,
            children=tuple(
                c.to_simple_article() if isinstance(c, ArticleWM) else c for c in self.children
            )
        )


def __do_post_processing() -> None:
    for _, cls in inspect.getmembers(sys.modules[__name__], inspect.isclass):
        if attr.has(cls):
            attr.resolve_types(cls)

    # Needed for attr.s(slots=True), and __subclasses__ to work correctly.
    gc.collect()


__do_post_processing()
