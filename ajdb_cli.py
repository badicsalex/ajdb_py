#!/usr/bin/env python3
import sys
from pathlib import Path
import gzip
import json

from hun_law.structure import Act, EnforcementDate, SubArticleElement
from hun_law import dict2object

from ajdb.fixups import apply_fixups


class ActWithMetadata:
    act: Act

    def apply_enforcements(self):
        pass

    def apply_block_amendments(self):
        pass

    def repeal(self):
        pass

    def apply_text_amendment(self):
        pass


def get_semantic_recursive(sae: SubArticleElement):
    if sae.semantic_data is None or not sae.CAN_BE_SEMANTIC_PARSED:
        return
    yield from sae.semantic_data
    if sae.children:
        for child in sae.children:
            if isinstance(child, SubArticleElement):
                yield from get_semantic_recursive(child)


acts = []
act_converter = dict2object.get_converter(Act)
for file_path in Path(sys.argv[1]).iterdir():
    if not file_path.is_file():
        continue
    with gzip.open(file_path, 'rt') as f:
        print("Loading {}".format(f))
        the_dict = json.load(f)
    the_act = act_converter.to_object(the_dict)
    the_act = apply_fixups(the_act)
    acts.append(the_act)

for act in acts:
    had_enf_date = False
    for article in act.articles:
        for paragraph in article.paragraphs:
            for sd in get_semantic_recursive(paragraph):
                if isinstance(sd, EnforcementDate):
                    if sd.position is None:
                        had_enf_date = True
    if not had_enf_date:
        print(act.identifier)
        for article in act.articles:
            for paragraph in article.paragraphs:
                if paragraph.text and 'lép hatályba' in paragraph.text:
                    print(' -- ', article.identifier, paragraph.identifier, paragraph.text)
