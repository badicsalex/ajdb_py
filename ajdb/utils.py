# Copyright 2020, Alex Badics, All Rights Reserved
from typing import Iterable, Sequence, Any, Callable, Optional, Type
import attr

from hun_law.structure import Act, SubArticleElement, BlockAmendmentContainer


def iterate_all_saes_of_sae(sae: SubArticleElement) -> Iterable[SubArticleElement]:
    yield sae
    if sae.children:
        for child in sae.children:
            if isinstance(child, SubArticleElement) and not isinstance(child, BlockAmendmentContainer):
                yield from iterate_all_saes_of_sae(child)


def iterate_all_saes_of_act(act: Act) -> Iterable[SubArticleElement]:
    for article in act.articles:
        for paragraph in article.paragraphs:
            yield from iterate_all_saes_of_sae(paragraph)


def first_matching_index(data: Sequence[Any], filter_fn: Callable[[Any], bool], start: int = 0) -> int:
    for index in range(start, len(data)):
        if filter_fn(data[index]):
            return index
    return len(data)


def last_matching_index(data: Sequence[Any], filter_fn: Callable[[Any], bool], start: Optional[int] = 0) -> int:
    if start is None:
        start = len(data) - 1
    for index in range(start, -1, -1):
        if filter_fn(data[index]):
            return index
    return -1


def evolve_into(inst: Any, cls: Type, **changes: Any) -> Any:
    attrs = attr.fields(cls)
    for a in attrs:
        if not a.init:
            continue
        attr_name = a.name  # To deal with private attributes.
        init_name = attr_name if attr_name[0] != "_" else attr_name[1:]
        if init_name not in changes:
            changes[init_name] = getattr(inst, attr_name)

    return cls(**changes)
