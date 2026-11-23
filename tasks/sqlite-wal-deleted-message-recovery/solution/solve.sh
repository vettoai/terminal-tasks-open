#!/bin/sh
set -eu
mkdir -p /opt/recover /cases
install -m 755 /solution/recovery.py /opt/recover/recover
/opt/recover/recover /evidence/chat.db /evidence/chat.db-wal /cases/report.jsonl
