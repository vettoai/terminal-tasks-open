from collections import defaultdict

from psycopg.types.json import Jsonb

from src.planner.routes import requirements
from src.planner.route_checks import check
from src.state.custody import events


def publish(connection, fixture, state, operations, candidates, invocation):
    diagnostics = check(fixture, operations)
    print('Route checks: ' + str(diagnostics), flush=True)
    routes = defaultdict(list)
    for operation in operations:
        routes[operation['vehicle'] or '@hub'].append(operation)
    with connection.cursor() as cursor:
        parent = state['version']
        for candidate in candidates:
            ids = [operation['id'] for operation in candidate['operations']]
            cursor.execute('INSERT INTO plan_versions(parent_version, invocation, worker_id, operation_ids) VALUES (%s,%s,%s,%s) RETURNING version',
                           (parent, invocation, candidate['worker_id'], Jsonb(ids)))
            revision = cursor.fetchone()[0]
            print(f"worker={candidate['worker_id']} version={revision} operations={len(ids)}", flush=True)
            parent = revision
        cursor.execute('UPDATE plan_versions SET is_current=false WHERE is_current')
        cursor.execute('INSERT INTO plan_versions(parent_version, invocation, is_current, operation_ids) VALUES (%s,%s,true,%s) RETURNING version',
                       (parent, invocation, Jsonb([operation['id'] for operation in operations])))
        version = cursor.fetchone()[0]
        for table in ('committed_routes', 'resource_reservations', 'shipment_assignments'):
            cursor.execute('DELETE FROM ' + table)
        cursor.executemany('INSERT INTO committed_routes VALUES (%s,%s,%s)',
                           [(vehicle, version, Jsonb(items)) for vehicle, items in routes.items()])
        allocations = []
        for operation in operations:
            if operation['end'] == operation['start']:
                continue
            for resource_id, demand in requirements(fixture, operation):
                allocations.append((operation['id'] + ':' + resource_id, version, operation['id'], resource_id,
                                    operation['start'], operation['end'], demand, 'committed'))
        cursor.executemany('INSERT INTO resource_reservations VALUES (%s,%s,%s,%s,%s,%s,%s,%s)', allocations)
        assignments = [(shipment, version, Jsonb([operation['id'] for operation in operations if shipment in operation['shipments']]))
                       for shipment in fixture['shipments']]
        cursor.executemany('INSERT INTO shipment_assignments VALUES (%s,%s,%s)', assignments)
        retained = events(operations, state['frontier'], state['history'])
        cursor.execute('DELETE FROM shipment_events WHERE NOT executed')
        for event_id, event in retained.items():
            cursor.execute('INSERT INTO shipment_events VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT(event_id) DO UPDATE SET version=EXCLUDED.version, executed=EXCLUDED.executed, payload=EXCLUDED.payload',
                           (event_id, event['shipment'], event['operation_id'], version, event['executed'], Jsonb(event)))
        cursor.execute('UPDATE planning_state SET observation_cursor=%s, execution_frontier=%s, observations=%s, ready_times=%s',
                       (state['cursor'], state['frontier'], Jsonb(state['observations']), Jsonb(state['ready'])))
    return version
