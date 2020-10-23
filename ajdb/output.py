# Copyright 2020, Alex Badics, All Rights Reserved
from pathlib import Path

from ajdb.amender import ActSet
from hun_law.output.html import generate_html_for_act


def generate_html_for_act_set_states(act_set: ActSet, dest_path: Path) -> None:

    dest_path.mkdir(exist_ok=True)
    for date in act_set.interesting_dates():
        date_str = "{}.{:02}.{:02}".format(date.year, date.month, date.day)
        print("Processing date", date_str)
        date_dir = dest_path / date_str
        date_dir.mkdir(exist_ok=True)
        style_symlink = (date_dir / "style.css")
        if not style_symlink.exists():
            style_symlink.symlink_to('../style.css')
        for act in act_set.acts.values():
            act_html_path = date_dir / (act.identifier + '.html')
            with act_html_path.open('w') as f:
                generate_html_for_act(act, f)
