from src.planner.model import solve


def combine(candidates, fixture, state):
    anchors = {operation['id']: operation for candidate in candidates for operation in candidate['operations']}
    operations = solve(fixture, state, sorted(fixture['vehicles']), anchors=anchors, protect=True, lifetime=True)
    accepted = {operation['id'] for operation in operations}
    for candidate in candidates:
        candidate['operations'] = [operation for operation in candidate['operations'] if operation['id'] in accepted]
    return sorted(operations, key=lambda operation: (operation['start'], operation['id']))
