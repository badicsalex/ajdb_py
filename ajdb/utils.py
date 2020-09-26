# Copyright 2020, Alex Badics, All Rights Reserved
from typing import Iterable

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
