#!/bin/sh
set -eu
source_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cp "$source_dir/guard.py" /srv/webhooks/webhooks/guard.py
cp "$source_dir/deliver.py" /srv/webhooks/webhooks/deliver.py
