from collections import defaultdict

from src.planner.model import PlanningError
from src.planner.travel_time import Network


def combine(candidates, fixture, state):
    operations = {}
    published = {}
    network = Network(fixture['edges'])
    frozen = {operation['id']: operation for operation in state['operations'] if operation.get('frozen') or operation['start'] < state['frontier']}
    for candidate in candidates:
        routes = defaultdict(list)
        for operation in candidate['operations']:
            if operation['vehicle']:
                routes[operation['vehicle']].append(operation)
        for vehicle_id, route in routes.items():
            route.sort(key=lambda operation: (operation['start'], operation['end'], operation['id']))
            available = fixture['vehicles'][vehicle_id]['shift_open']
            for operation in route:
                ready = max([operation['start'], available] +
                            [published.get((shipment, operation['location']), operation['start'])
                             for shipment in operation['shipments'] if operation['kind'] == 'load'])
                if operation['id'] in frozen and ready != operation['start']:
                    raise PlanningError('A published handoff conflicts with a fixed service')
                duration = operation['end'] - operation['start']
                operation['start'], operation['end'] = ready, ready + duration
                if operation['kind'] == 'drive':
                    operation['movements'] = network.trip(operation['edges'], ready)
                    operation['end'] = operation['movements'][-1]['end']
                available = operation['end']
            vehicle = fixture['vehicles'][vehicle_id]
            if route[-1]['end'] > vehicle['shift_close'] or route[-1]['end'] - route[0]['start'] > vehicle['max_duty']:
                raise PlanningError('Route duty exceeds vehicle availability')
        for operation in candidate['operations']:
            operations[operation['id']] = operation
            if operation['kind'] == 'handle':
                for shipment in operation['shipments']:
                    published[(shipment, operation['location'])] = operation['end']
    return sorted(operations.values(), key=lambda item: (item['start'], item['id']))
