# Copyright 2020, Alex Badics, All Rights Reserved
import attr

from hun_law.structure import Act, SubArticleElement, Reference


def semantic_remover(_reference: Reference, sae: SubArticleElement) -> SubArticleElement:
    return attr.evolve(
        sae,
        semantic_data=None,
        outgoing_references=None,
        act_id_abbreviations=None,
    )


def semantic_faker(_reference: Reference, sae: SubArticleElement) -> SubArticleElement:
    return attr.evolve(
        sae,
        semantic_data=sae.semantic_data or (),
        outgoing_references=sae.outgoing_references or (),
        act_id_abbreviations=sae.act_id_abbreviations or (),
    )


def add_fake_semantic_data(act: Act) -> Act:
    return act.map_saes(semantic_faker)


def remove_semantic_data(act: Act) -> Act:
    return act.map_saes(semantic_remover)
