#!/bin/bash
set -euo pipefail
source_directory="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
install -m 755 "$source_directory/estimator.py" /workspace/estimate
