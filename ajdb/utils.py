# Copyright 2020, Alex Badics, All Rights Reserved
from typing import Iterable, Any, Callable

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


def first_matching_index(data: Iterable[Any], filter_fn: Callable[[Any], bool]) -> int:
    index = 0
    for d in data:
        if filter_fn(d):
            return index
        index += 1
    return index
