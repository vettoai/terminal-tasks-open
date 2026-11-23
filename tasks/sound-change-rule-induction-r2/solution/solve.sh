#!/bin/bash
set -euo pipefail
python3 -I -S "$(dirname "$0")/induce.py"
