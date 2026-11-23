import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from psycopg.types.json import Jsonb
from src.data import ROOT, connect, load_fixture
from src.planner.commit import publish


def main():
    parser = argparse.ArgumentParser(description='Import a dispatch export into PostgreSQL, including its committed history and observation cursor.')
    parser.add_argument('--fixture', required=True, help='Directory with shipments.csv, vehicles.csv, hubs.yaml, network_edges.parquet, committed_plan.json and events.jsonl')
    parser.add_argument('--reset', action='store_true', help='Replace the imported planning state and start at the export frontier')
    args = parser.parse_args()
    fixture = load_fixture(args.fixture)
    initial = fixture['initial']
    version = initial['version']
    with connect() as connection:
        connection.execute((ROOT / 'sql/schema.sql').read_text())
        if args.reset:
            connection.execute('TRUNCATE plan_versions, committed_routes, resource_reservations, shipment_assignments, shipment_events, planning_state RESTART IDENTITY CASCADE')
        elif connection.execute('SELECT count(*) FROM planning_state').fetchone()[0]:
            parser.error('A fixture is already imported; use --reset to replace it')
        connection.execute('INSERT INTO plan_versions(version, invocation, is_current, operation_ids) VALUES (%s,\'import\',true,%s)',
                           (version, Jsonb([operation['id'] for operation in initial['operations']])))
        connection.execute("SELECT setval(pg_get_serial_sequence('plan_versions','version'),%s)", (version,))
        connection.execute('INSERT INTO planning_state VALUES (true,%s,0,%s,%s,%s)',
                           (str(Path(args.fixture).resolve()), initial['frontier'], Jsonb([]), Jsonb({})))
        by_vehicle = {}
        for operation in initial['operations']:
            by_vehicle.setdefault(operation['vehicle'] or '@hub', []).append(operation)
        for vehicle, operations in by_vehicle.items():
            connection.execute('INSERT INTO committed_routes VALUES (%s,%s,%s)', (vehicle, version, Jsonb(operations)))
        from src.planner.routes import requirements
        from src.state.custody import events
        for operation in initial['operations']:
            for resource_id, demand in requirements(fixture, operation):
                if operation['start'] != operation['end']:
                    connection.execute('INSERT INTO resource_reservations VALUES (%s,%s,%s,%s,%s,%s,%s,\'committed\')',
                                       (operation['id'] + ':' + resource_id, version, operation['id'], resource_id, operation['start'], operation['end'], demand))
        for shipment in fixture['shipments']:
            ids = [operation['id'] for operation in initial['operations'] if shipment in operation['shipments']]
            connection.execute('INSERT INTO shipment_assignments VALUES (%s,%s,%s)', (shipment, version, Jsonb(ids)))
        for event_id, event in events(initial['operations'], initial['frontier'], {}).items():
            connection.execute('INSERT INTO shipment_events VALUES (%s,%s,%s,%s,%s,%s)',
                               (event_id, event['shipment'], event['operation_id'], version, event['executed'], Jsonb(event)))
    print(f'Imported version {version}; cursor=0; fixture=' + str(args.fixture))


if __name__ == '__main__':
    main()
