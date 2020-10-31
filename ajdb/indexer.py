# Copyright 2020, Alex Badics, All Rights Reserved
from typing import Iterable
from collections import defaultdict

import attr

from ajdb.structure import ActSet, ActWM, ActWMProxy, SaeWMType, Reference, \
    ReferencePair, ReferencePairList, ReferencePairListProxy


class ReferenceReindexer:
    @classmethod
    def reindex_act_set(cls, act_set: ActSet) -> ActSet:
        index = defaultdict(list)
        dropped = 0
        for act in act_set.acts:
            if isinstance(act, ActWMProxy):
                act = act.act
            for ref_pair in cls.get_refs_from_single_act(act):
                assert ref_pair.to_ref.act is not None
                if not act_set.has_act(ref_pair.to_ref.act):
                    dropped += 1
                    continue
                index[ref_pair.to_ref.act].append(ref_pair)
        print(
            "Reindexed {} acts with {} references (dropped {})"
            .format(
                len(index),
                sum(len(v) for v in index.values()),
                dropped,
            )
        )
        new_index = []
        for act_id, refs in index.items():
            reflist_proxy = ReferencePairListProxy.save_reference_list(ReferencePairList(tuple(refs)))
            new_index.append((act_id, reflist_proxy))
        return attr.evolve(act_set, reference_index=new_index)

    @classmethod
    def get_refs_from_single_act(cls, act: ActWM) -> Iterable[ReferencePair]:
        result = []

        def collector(reference: Reference, sae: SaeWMType) -> SaeWMType:
            nonlocal result
            assert sae.outgoing_references is not None
            for ogr in sae.outgoing_references:
                if ogr.reference.act is not None or ogr.reference.article is not None:
                    to_ref = ogr.reference.relative_to(reference)
                    result.append(ReferencePair(from_ref=reference, to_ref=to_ref))
            return sae
        act.map_saes(collector)
        return result
