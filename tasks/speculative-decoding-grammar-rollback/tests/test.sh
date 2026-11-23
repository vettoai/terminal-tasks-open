#!/bin/sh
set -eu
mkdir -p /logs/verifier
exec python -I /tests/run_verifier.py
