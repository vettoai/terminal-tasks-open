
def events(operations, frontier, retained):
    result = dict(retained)
    for operation in operations:
        for shipment in operation.get('shipments', []):
            event_id = operation['id'] + ':' + shipment
            result[event_id] = {'event_id': event_id, 'operation_id': operation['id'], 'shipment': shipment,
                                'kind': operation['kind'], 'location': operation['location'],
                                'vehicle': operation['vehicle'], 'start': operation['start'], 'end': operation['end'],
                                'executed': operation['end'] <= frontier,
                                'protected': operation.get('protected', False)}
    return result
