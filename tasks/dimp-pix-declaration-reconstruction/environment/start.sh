#!/bin/sh
set -eu
export MAX_HEAP_SIZE=1G HEAP_NEWSIZE=200M
mkdir -p /var/lib/cassandra/logs /var/lib/cassandra/commitlog /var/lib/cassandra/data /var/lib/cassandra/hints /var/lib/cassandra/saved_caches
chown -R cassandra:cassandra /var/lib/cassandra
gosu cassandra /opt/cassandra/bin/cassandra -f > /var/lib/cassandra/logs/server.log 2>&1 &
python3 /usr/local/lib/dimp-ready.py
if [ "$#" -eq 0 ]; then
    set -- sleep infinity
fi
exec "$@"
