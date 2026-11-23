import copy


def performed_state(fixture, state):
    result = dict(state)
    operations = copy.deepcopy(state['operations'])
    by_id = {operation['id']: operation for operation in operations}
    receipts = {item['operation_id']: item['time'] for item in state['observations'] if item['kind'] == 'completed'}
    prior_frontier = fixture['initial']['frontier'] if state['cursor'] <= 1 else fixture['batches'][state['cursor'] - 2]['frontier']
    for identity, finish in receipts.items():
        operation = by_id[identity]
        if operation['kind'] == 'stage':
            operation['end'] = finish
        elif operation['kind'] in ('load', 'unload', 'handle'):
            duration = operation['duration']
            operation.update(start=finish - duration, end=finish)
    for shipment in fixture['shipments'].values():
        for previous, leg in zip(shipment['legs'], shipment['legs'][1:]):
            for root_id, incoming, outgoing in (
                    (leg['before_stage_id'], previous['unload_id'], leg['handling_id']),
                    (leg['after_stage_id'], leg['handling_id'], leg['load_id'])):
                family = []
                for operation in operations:
                    if operation['kind'] != 'stage':
                        continue
                    ancestor = operation
                    visited = set()
                    while ancestor.get('parent_id') and ancestor['id'] not in visited:
                        visited.add(ancestor['id'])
                        ancestor = by_id[ancestor['parent_id']]
                    if ancestor['id'] == root_id:
                        family.append(operation)
                family.sort(key=lambda item: (item['start'], item['end'], item['id']))
                if family and incoming in receipts:
                    family[0]['start'] = by_id[incoming]['end']
                if family and outgoing in receipts:
                    family[-1]['end'] = by_id[outgoing]['start']
    original = {operation['id']: operation for operation in state['operations']}
    for operation in operations:
        previous = original[operation['id']]
        if previous.get('frozen') or (previous['kind'] != 'stage' and previous['start'] < prior_frontier) or previous['end'] <= prior_frontier:
            if (operation['start'], operation['end']) != (previous['start'], previous['end']):
                raise ValueError('Completion conflicts with performed history')
        elif previous['kind'] == 'stage' and previous['start'] < prior_frontier:
            if operation['start'] != previous['start'] or operation['end'] < prior_frontier:
                raise ValueError('Completion removes occupied storage')
    result['operations'] = operations
    return result
