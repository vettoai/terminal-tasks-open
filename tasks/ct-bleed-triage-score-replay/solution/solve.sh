#!/bin/sh
set -eu
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
install -m 0644 "$script_dir/triage.py" /app/triage.py
