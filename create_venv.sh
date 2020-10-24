#!/bin/sh
# Copyright 2020 Alex Badics <admin@stickman.hu>, All Rights reserved

function create_venv(){
    PYTHON_INTERPRETER="$1"
    VENV_PATH="$2"
    "${PYTHON_INTERPRETER}" -m venv "${VENV_PATH}"
    "${VENV_PATH}/bin/pip" install --upgrade pip
    "${VENV_PATH}/bin/pip" install -r requirements.txt
}

create_venv python3 .venv
if ! command -v pypy3 &> /dev/null; then
    echo "WARN: Pypy3 venv not installed. Consider installing pypy3 for 10x faster execution."
else
    create_venv pypy3 .venv-pypy
fi

