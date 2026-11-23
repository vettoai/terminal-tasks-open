import multiprocessing
import uuid

from src.data import connect, next_observations, read_state
from src.planner.commit import publish
from src.planner.merge import combine
from src.planner.model import PlanningError
from src.planner.subproblem import calculate


def run(fixture, workers, schedule):
    with connect() as connection:
        state = next_observations(fixture, read_state(connection))
        vehicle_ids = sorted(fixture['vehicles'], reverse=True)
        hub_sites = set(fixture['hubs']['sites'])
        vehicle_ids.sort(key=lambda vehicle_id: not (fixture['vehicles'][vehicle_id]['stops'][0]['site'] in hub_sites and fixture['vehicles'][vehicle_id]['stops'][-1]['site'] in hub_sites))
        partitions = [vehicle_ids[index::workers] for index in range(workers)]
        context = multiprocessing.get_context('fork')
        barrier = context.Barrier(workers)
        results = context.Queue()
        processes = [context.Process(target=calculate, args=(index, fixture, state, vehicles, barrier, results),
                                     name=f'routeweave-worker-{index}') for index, vehicles in enumerate(partitions)]
        for process in processes:
            process.start()
        candidates = [results.get() for process in processes]
        for process in processes:
            process.join()
        errors = [candidate['error'] for candidate in candidates if 'error' in candidate]
        if errors:
            raise PlanningError('; '.join(errors))
        candidates.sort(key=lambda item: item['worker_id'], reverse=schedule == 'schedule_b')
        operations = combine(candidates, fixture, state)
        version = publish(connection, fixture, state, operations, candidates, uuid.uuid4().hex)
    return version, operations
