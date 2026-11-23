import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.data import connect


def main():
    parser = argparse.ArgumentParser(description='Inspect the materialized allocation ledger in PostgreSQL. Emits allocation, operation, resource, interval, demand, status and version fields as JSON.')
    parser.add_argument('--resource', help='Restrict to one resource identity')
    parser.add_argument('--version', type=int, help='Restrict to one plan version')
    args = parser.parse_args()
    with connect() as connection:
        rows = connection.execute('SELECT allocation_id, operation_id, resource_id, start_min, end_min, demand, status, version FROM resource_reservations WHERE (%s::text IS NULL OR resource_id=%s) AND (%s::bigint IS NULL OR version=%s) ORDER BY start_min, allocation_id',
                                  (args.resource, args.resource, args.version, args.version)).fetchall()
    print(json.dumps([dict(zip(('allocation_id', 'operation_id', 'resource_id', 'start', 'end', 'demand', 'status', 'version'), row)) for row in rows], indent=2))


if __name__ == '__main__':
    main()
