# Copyright 2020, Alex Badics, All Rights Reserved
from typing import Dict, List, Optional, Type
from types import TracebackType


class HtmlTag:
    def __init__(self, writer: 'HtmlWriter', name: str, attributes: Dict[str, str]) -> None:
        self.writer = writer
        self.name = name
        self.attributes = attributes

    def __enter__(self) -> 'HtmlTag':
        attributes_list = []
        for k, v in self.attributes.items():
            if not v:
                continue
            if k[0] == '_':
                k = k[1:]
            k = k.replace('_', '-')
            attributes_list.append('{}="{}"'.format(k, v))
        attributes_str = " ".join(attributes_list)
        if attributes_str:
            attributes_str = " " + attributes_str
        tag_str = "<{}{}>".format(self.name, attributes_str)
        self.writer.write(tag_str)
        return self

    def __exit__(
        self,
        t: Optional[Type[BaseException]],
        value: Optional[BaseException],
        traceback: Optional[TracebackType]
    ) -> None:
        self.writer.write("</{}>".format(self.name))


class HtmlWriter:
    def __init__(self) -> None:
        self.output: List[str] = []

    def br(self) -> None:
        self.write('<br>')

    def tag(self, name: str, **attributes: str) -> HtmlTag:
        return HtmlTag(self, name, attributes)

    def div(self, _class: str, **attributes: str) -> HtmlTag:
        attributes['_class'] = _class
        return HtmlTag(self, 'div', attributes)

    def write(self, s: str) -> None:
        self.output.append(s)

    def get_str(self) -> str:
        return "".join(self.output)
