#!/bin/bash
set -euo pipefail
solution_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
python3 "$solution_dir/restore.py"
