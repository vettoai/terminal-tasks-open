#!/bin/bash
set -euo pipefail
solution_directory="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cp -- "$solution_directory/ocrUtils.ts" /app/src/ocr/ocrUtils.ts
