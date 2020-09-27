#!/usr/bin/env python3
import sys
from pathlib import Path

from ajdb.database import ActSet
from ajdb.output import generate_html_for_act_set_states

act_set = ActSet()
for file_path in Path(sys.argv[1]).iterdir():
    if not file_path.is_file():
        continue
    act_set.load_from_file(file_path)

generate_html_for_act_set_states(act_set, Path(sys.argv[2]))
