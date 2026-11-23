#!/bin/sh
set -eu
/usr/local/bin/start-mongod
exec "$@"
