#!/usr/bin/bash
set -euo pipefail

echo "Checking types with mypy"
mypy .

echo "Checking other bugs with pylint"
pylint ajdb tests *.py
