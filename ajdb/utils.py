# Copyright 2020, Alex Badics, All Rights Reserved
from typing import Iterable, Sequence, Any, Callable, Optional, Type, TypeVar, MutableMapping
from collections import OrderedDict

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


_KT = TypeVar('_KT')
_VT = TypeVar('_VT')


class LruDict(OrderedDict, MutableMapping[_KT, _VT]):
    def __init__(self, max_elements: int):
        super().__init__()
        self.max_elements = max_elements

    def __getitem__(self, key: _KT) -> _VT:
        result: _VT = super().__getitem__(key)
        try:
            self.move_to_end(key)
        except KeyError:
            # We are in the middle of a pop: which first removes the element
            # from the internal map, then gets it with getitem one last time
            pass
        return result

    def __setitem__(self, key: _KT, value: _VT) -> None:
        super().__setitem__(key, value)
        self.move_to_end(key)
        if len(self) > self.max_elements:
            self.popitem(last=False)

    def get(self, k: _KT, default: Any = None) -> Any:
        try:
            return self[k]
        except KeyError:
            return default
