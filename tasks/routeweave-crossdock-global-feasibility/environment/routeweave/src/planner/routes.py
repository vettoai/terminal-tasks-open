from collections import defaultdict


def construct(fixture):
    routes = defaultdict(list)
    transfers = []
    for shipment in fixture['shipments'].values():
        preceding = None
        for index, leg in enumerate(shipment['legs']):
            vehicle_id = leg['vehicle']
            load_id = leg['load_id']
            unload_id = leg['unload_id']
            load = {'id': load_id, 'kind': 'load', 'vehicle': vehicle_id, 'location': leg['origin'],
                    'shipments': [shipment['id']], 'duration': leg.get('load_minutes', shipment['load_minutes']), 'leg': index,
                    'rank': leg['load_rank'], 'earliest': leg['not_before']}
            unload = {'id': unload_id, 'kind': 'unload', 'vehicle': vehicle_id, 'location': leg['destination'],
                      'shipments': [shipment['id']], 'duration': leg.get('unload_minutes', shipment['unload_minutes']), 'leg': index,
                      'rank': leg['unload_rank'], 'earliest': leg.get('arrival_not_before', 0)}
            if index == 0:
                load['earliest'] = max(load['earliest'], shipment['ready'])
            if index == len(shipment['legs']) - 1:
                unload['earliest'] = max(unload['earliest'], shipment['window_open'])
                unload['latest'] = shipment['window_close']
            routes[vehicle_id].extend([load, unload])
            if preceding:
                handling = {'id': leg['handling_id'], 'kind': 'handle', 'vehicle': None,
                            'location': leg['origin'], 'shipments': [shipment['id']],
                            'duration': leg.get('handle_minutes', shipment['handle_minutes']), 'earliest': leg.get('handling_not_before', 0)}
                transfers.append({'shipment': shipment['id'], 'inbound': preceding, 'handling': handling,
                                  'outbound': load_id, 'before_stage': leg['before_stage_id'],
                                  'after_stage': leg['after_stage_id']})
            preceding = unload_id
    for vehicle_id, vehicle in fixture['vehicles'].items():
        services = routes[vehicle_id]
        ordered = []
        for stop_index, stop in enumerate(vehicle['stops']):
            local = sorted([item for item in services if item['location'] == stop['site']], key=lambda item: item['rank'])
            ordered.extend(local)
            if stop_index < len(vehicle['stops']) - 1:
                ordered.append({'id': stop['drive_id'], 'kind': 'drive', 'vehicle': vehicle_id,
                                'location': stop['site'], 'destination': vehicle['stops'][stop_index + 1]['site'],
                                'edges': stop['edges'], 'shipments': [], 'earliest': stop['departure_not_before']})
        routes[vehicle_id] = ordered
    return dict(routes), transfers


def requirements(fixture, operation):
    hub = fixture['hubs']['sites'].get(operation['location'])
    if hub is None or operation['kind'] == 'drive':
        return []
    if operation['kind'] == 'stage':
        if not operation.get('protected'):
            return []
        quantity = sum(fixture['shipments'][shipment]['quantity'] for shipment in operation['shipments'])
        return [(hub['staging'], quantity)]
    return [(hub[kind], 1) for kind in hub['actions'].get(operation['kind'], [])]
