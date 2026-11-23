#!/bin/sh
set -eu
solution_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd /workspace/project
python3 "$solution_dir/recover.py"
