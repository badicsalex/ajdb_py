#!/usr/bin/bash
set -euo pipefail

echo "Checking types with mypy"
mypy .

echo "Checking other bugs with pylint"
pylint -j 0 ajdb ajdb_web tests tests_web *.py
