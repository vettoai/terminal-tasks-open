#!/bin/sh
exec /usr/bin/python3 -I /tests/submission_boundary.py exec /usr/bin/python3 -I /opt/public/chromium_exec.py "$@"
