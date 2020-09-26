#!/usr/bin/env python3
import sys
from pathlib import Path
import gzip
import json

from hun_law.structure import Act
from hun_law.utils import Date
from hun_law import dict2object
from hun_law.output.html import generate_html_for_act


from ajdb.fixups import apply_fixups
from ajdb.interpreter import EnforcementDateSet

acts = {}
act_converter = dict2object.get_converter(Act)
for file_path in Path(sys.argv[1]).iterdir():
    if not file_path.is_file():
        continue
    with gzip.open(file_path, 'rt') as f:
        print("Loading {}".format(f))
        the_dict = json.load(f)
    the_act = act_converter.to_object(the_dict)
    the_act = apply_fixups(the_act)
    acts[the_act.identifier] = the_act

test_act = acts['2019. évi LXVII. törvény']
enforcement_dates = EnforcementDateSet.from_act(test_act)
print('   ', enforcement_dates.default)
for aed in enforcement_dates.specials:
    print('      ', aed)
filtered_act = enforcement_dates.filter_act(test_act, Date(2019, 7, 17))

with open("test.html", "w") as f:
    generate_html_for_act(filtered_act, f)
