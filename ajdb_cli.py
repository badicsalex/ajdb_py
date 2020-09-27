#!/usr/bin/env python3
import sys
from pathlib import Path

from ajdb.database import ActSet
from ajdb.output import generate_html_for_act

act_set = ActSet()
for file_path in Path(sys.argv[1]).iterdir():
    if not file_path.is_file():
        continue
    act_set.load_from_file(file_path)

dest_path = Path(sys.argv[2])
dest_path.mkdir(exist_ok=True)
for date in act_set.interesting_dates():
    date_str = "{}.{:02}.{:02}".format(date.year, date.month, date.day)
    print("Processing date", date_str)

    for act in act_set.acts_at_date(date):
        act_set.apply_modifications(act)

    date_dir = dest_path / date_str
    date_dir.mkdir(exist_ok=True)
    style_symlink = (date_dir / "style.css")
    if not style_symlink.exists():
        style_symlink.symlink_to('../style.css')
    for act in act_set.acts_at_date(date):
        act_html_path = date_dir / (act.identifier + '.html')
        with act_html_path.open('w') as f:
            generate_html_for_act(act, f)
