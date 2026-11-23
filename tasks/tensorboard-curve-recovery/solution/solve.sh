#!/bin/bash
set -euo pipefail
install -m 0755 "$(dirname "${BASH_SOURCE[0]}")/rebuild_curves.py" /workspace/rebuild_curves.py
