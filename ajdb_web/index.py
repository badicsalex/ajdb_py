# Copyright 2020, Alex Badics, All Rights Reserved
from flask import Blueprint, render_template
from ajdb.database import Database
from hun_law.utils import Date

_blueprint = Blueprint('index', __name__)


@_blueprint.route('/')
def index() -> str:
    act_set = Database.load_act_set(Date.today())
    return render_template('index.html', act_set=act_set)


INDEX_BLUEPRINT = _blueprint
