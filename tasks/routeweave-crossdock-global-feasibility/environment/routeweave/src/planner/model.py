from collections import defaultdict

from ortools.sat.python import cp_model

from src.planner.routes import construct, requirements
from src.planner.travel_time import Network


class PlanningError(RuntimeError):
    pass


def solve(fixture, state, vehicle_ids, anchors=None, protect=False, lifetime=False):
    routes, transfers = construct(fixture)
    network = Network(fixture['edges'])
    selected = set(vehicle_ids)
    specs = [operation for vehicle in sorted(selected) for operation in routes[vehicle]]
    owners = {operation['id']: vehicle for vehicle, items in routes.items() for operation in items}
    relevant = [transfer for transfer in transfers if owners[transfer['inbound']] in selected]
    for transfer in relevant:
        specs.append(transfer['handling'])
    specs = {operation['id']: dict(operation) for operation in specs}
    fixed = {item['id']: item for item in state['operations'] if item.get('frozen') or item['start'] < state['frontier']}
    forecast = {item['id']: item for item in fixture['initial'].get('forecast', [])}
    forecast.update(anchors or {})
    horizon = max(vehicle['shift_close'] for vehicle in fixture['vehicles'].values())
    floor = min(vehicle['shift_open'] for vehicle in fixture['vehicles'].values())
    model = cp_model.CpModel()
    starts, ends, intervals, movements = {}, {}, {}, {}
    resource_intervals = defaultdict(list)
    resource_demands = defaultdict(list)
    for operation_id, operation in specs.items():
        starts[operation_id] = model.NewIntVar(floor, horizon, operation_id + ':start')
        ends[operation_id] = model.NewIntVar(floor, horizon, operation_id + ':end')
        start, end = starts[operation_id], ends[operation_id]
        model.Add(start >= max(operation.get('earliest', floor), state['ready'].get(operation_id, floor)))
        if 'latest' in operation:
            model.Add(end <= operation['latest'])
        if operation['kind'] != 'drive':
            model.Add(end == start + operation['duration'])
            intervals[operation_id] = model.NewIntervalVar(start, operation['duration'], end, operation_id)
        else:
            edge_vars = []
            departure = start
            for edge_index, edge_id in enumerate(operation['edges']):
                arrival = model.NewIntVar(floor, horizon, operation_id + f':arrival:{edge_index}')
                selectors = []
                for band_index, band in enumerate(network.edges[edge_id]):
                    choice = model.NewBoolVar(operation_id + f':band:{edge_index}:{band_index}')
                    selectors.append(choice)
                    model.Add(departure >= band['band_start']).OnlyEnforceIf(choice)
                    model.Add(departure < band['band_end']).OnlyEnforceIf(choice)
                    model.Add(arrival == departure + band['minutes']).OnlyEnforceIf(choice)
                model.AddExactlyOne(selectors)
                edge_vars.append((edge_id, departure, arrival))
                departure = arrival
            model.Add(end == departure)
            movements[operation_id] = edge_vars
        if operation_id in fixed:
            model.Add(start == fixed[operation_id]['start'])
            model.Add(end == fixed[operation_id]['end'])
        else:
            model.Add(start >= state['frontier'])
        for resource_id, demand in requirements(fixture, operation):
            resource_intervals[resource_id].append(intervals[operation_id])
            resource_demands[resource_id].append(demand)
    objective = []
    for vehicle_id in sorted(selected):
        route = routes[vehicle_id]
        vehicle = fixture['vehicles'][vehicle_id]
        for before, after in zip(route, route[1:]):
            model.Add(starts[after['id']] >= ends[before['id']])
        model.Add(starts[route[0]['id']] >= vehicle['shift_open'])
        model.Add(ends[route[-1]['id']] <= vehicle['shift_close'])
        span = ends[route[-1]['id']] - starts[route[0]['id']]
        model.Add(span <= vehicle['max_duty'])
        objective.append(span)
        onboard, quantities = [], []
        for shipment in fixture['shipments'].values():
            for leg in shipment['legs']:
                if leg['vehicle'] == vehicle_id:
                    load, unload = leg['load_id'], leg['unload_id']
                    length = model.NewIntVar(0, horizon - floor, load + ':onboard')
                    model.Add(length == ends[unload] - starts[load])
                    onboard.append(model.NewIntervalVar(starts[load], length, ends[unload], load + ':capacity'))
                    quantities.append(shipment['quantity'])
        model.AddCumulative(onboard, quantities, vehicle['capacity'])
    stages = []
    for transfer in relevant:
        inbound, handling, outbound = transfer['inbound'], transfer['handling']['id'], transfer['outbound']
        model.Add(starts[handling] >= ends[inbound])
        if outbound in starts:
            model.Add(starts[outbound] >= ends[handling])
            outbound_start = starts[outbound]
        else:
            outbound_start = max(forecast.get(outbound, {}).get('start', floor), floor)
        shipment = fixture['shipments'][transfer['shipment']]
        for stage_id, begin, finish in ((transfer['before_stage'], ends[inbound], starts[handling]),
                                         (transfer['after_stage'], ends[handling], outbound_start)):
            if not lifetime and stage_id == transfer['after_stage'] and outbound not in starts:
                continue
            length = model.NewIntVar(0, horizon - floor, stage_id + ':length')
            model.Add(length == finish - begin)
            interval = model.NewIntervalVar(begin, length, finish, stage_id)
            stage = {'id': stage_id, 'kind': 'stage', 'vehicle': None, 'location': transfer['handling']['location'],
                     'shipments': [shipment['id']], 'protected': bool(protect and shipment['chilled'])}
            if stage_id in fixed:
                model.Add(begin == fixed[stage_id]['start'])
                model.Add(finish == fixed[stage_id]['end'])
                stage['protected'] = fixed[stage_id].get('protected', False)
            stages.append((stage, begin, finish))
            for resource_id, demand in requirements(fixture, stage):
                resource_intervals[resource_id].append(interval)
                resource_demands[resource_id].append(demand)
            objective.append(length * shipment['quantity'])
    if lifetime:
        for shipment in fixture['shipments'].values():
            if not shipment['chilled']:
                continue
            exposure = [ends[item['id']] - starts[item['id']] for item in specs.values()
                        if shipment['id'] in item.get('shipments', []) and item['kind'] != 'drive']
            exposure.extend(finish - begin for stage, begin, finish in stages
                            if shipment['id'] in stage['shipments'] and not stage['protected'])
            for leg in shipment['legs']:
                if not fixture['vehicles'][leg['vehicle']]['refrigerated']:
                    exposure.append(starts[leg['unload_id']] - ends[leg['load_id']])
            model.Add(sum(exposure) <= shipment['budget'])
    else:
        for shipment in fixture['shipments'].values():
            if shipment['chilled']:
                for leg in shipment['legs']:
                    if leg['vehicle'] in selected:
                        model.Add(ends[leg['unload_id']] - starts[leg['unload_id']] +
                                  ends[leg['load_id']] - starts[leg['load_id']] <= shipment['budget'])
        for shipment in fixture['shipments'].values():
            for leg_index, leg in enumerate(shipment['legs'][1:], 1):
                if leg['load_id'] in starts and shipment['legs'][leg_index - 1]['unload_id'] not in ends:
                    upstream = forecast.get(shipment['legs'][leg_index - 1]['unload_id'], {})
                    model.Add(starts[leg['load_id']] >= upstream.get('end', leg['not_before']))
    for resource_id, occupied in resource_intervals.items():
        model.AddCumulative(occupied, resource_demands[resource_id], fixture['hubs']['resources'][resource_id]['capacity'])
    model.Minimize(sum(objective) + sum(starts[identity] * max(operation.get('duration', 1), 1) ** 2 for identity, operation in specs.items()))
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 19
    solver.parameters.max_time_in_seconds = 5 if len(fixture['shipments']) < 100 else 45
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise PlanningError('No complete dispatch schedule: ' + solver.StatusName(status))
    result = []
    for operation_id, operation in specs.items():
        record = dict(operation, start=solver.Value(starts[operation_id]), end=solver.Value(ends[operation_id]))
        if operation_id in fixed:
            record['frozen'] = fixed[operation_id].get('frozen', False)
        record['resources'] = [{'resource': resource, 'demand': demand} for resource, demand in requirements(fixture, record)]
        if operation_id in movements:
            record['movements'] = []
            for edge_id, departure, arrival in movements[operation_id]:
                band = network.at(edge_id, solver.Value(departure))
                record['movements'].append({'edge_id': edge_id, 'from': band['origin'], 'to': band['destination'],
                                            'start': solver.Value(departure), 'end': solver.Value(arrival),
                                            'distance_km': band['distance_km']})
        result.append(record)
    for stage, begin, finish in stages:
        record = dict(stage, start=solver.Value(begin), end=solver.Value(finish))
        record['resources'] = [{'resource': resource, 'demand': demand} for resource, demand in requirements(fixture, record)]
        result.append(record)
    return result
