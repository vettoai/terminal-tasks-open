#!/bin/bash
set -e
if ! pg_isready -h 127.0.0.1 -p 5432 -U contracts -d contracts >/dev/null 2>&1; then
  pg_ctlcluster 16 main start
fi
