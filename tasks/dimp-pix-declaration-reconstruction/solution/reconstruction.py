import calendar
import ast
import csv
import io
import subprocess
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from cassandra.cluster import Cluster
from cassandra.query import SimpleStatement
from ortools.sat.python import cp_model


def next_month(month):
    year, number = map(int, month.split('-'))
    return f'{year + (number == 12):04d}-{number % 12 + 1:02d}'


def parse_files(directory, month, external, period):
    totals = defaultdict(lambda: [0, 0])
    for uf in ('SP', 'MG', 'PR'):
        path = Path(directory) / f'DIMP_{uf}_{month.replace("-", "")}.txt'
        for line in path.read_bytes().decode('latin-1').splitlines():
            fields = line.split('|')[1:-1]
            if fields[0] == '1500' and int(fields[4]) == external and fields[5] == period:
                whole, fractional = fields[6].split(',')
                key = (uf, fields[2], 'CNPJ' if fields[10] == '1' else 'CPF',
                       'STATIC' if fields[11] == '1' else 'DYNAMIC')
                pair = totals[key]
                pair[0] += int(whole) * 100 + int(fractional)
                pair[1] += int(fields[7])
    return dict(totals)


def read_ledger(keyspace, month, bucket_count=4):
    cluster = Cluster(['127.0.0.1'], port=9042)
    session = cluster.connect(keyspace)
    accounts = {row.account: row._asdict() for row in session.execute('SELECT * FROM account')}
    year, number = map(int, month.split('-'))
    query = SimpleStatement('SELECT day,bucket,event_ts,pix_id,account,payer_doc_type,'
                            'pix_type,amount_cents,WRITETIME(amount_cents) AS arrival_us '
                            'FROM pix_credit WHERE day=%s AND bucket=%s '
                            'ORDER BY event_ts ASC,pix_id ASC', fetch_size=250)
    rows = []
    for day_number in range(1, calendar.monthrange(year, number)[1] + 1):
        day = date(year, number, day_number)
        for bucket in range(bucket_count):
            for credit in session.execute(query, (day, bucket)):
                row = credit._asdict()
                row['day'] = str(credit.day)
                delta = credit.event_ts - datetime(1970, 1, 1)
                row['event_us'] = (delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds
                del row['event_ts']
                rows.append(row)
    cluster.shutdown()
    return accounts, rows


def row_key(row, accounts):
    return (accounts[row['account']]['uf'], row['account'],
            row['payer_doc_type'], row['pix_type'])


def new_solver():
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 2
    solver.parameters.random_seed = 46173
    return solver


def catch_model(rows, accounts, extra):
    model = cp_model.CpModel()
    by_day = defaultdict(list)
    by_key = defaultdict(list)
    for index, row in enumerate(rows):
        by_day[row['day']].append(index)
        by_key[row_key(row, accounts)].append(index)
    flags = {}
    for day, indices in by_day.items():
        absent = [rows[index]['arrival_us'] for index in indices
                  if extra.get(row_key(rows[index], accounts), [0, 0])[1] == 0]
        lower = max(absent, default=-1)
        previous = None
        current_time = None
        current = None
        for index in sorted(indices, key=lambda item: rows[item]['arrival_us']):
            arrival = rows[index]['arrival_us']
            if arrival <= lower:
                flags[index] = 0
                continue
            if arrival != current_time:
                current = model.NewBoolVar(f'late_{day}_{arrival}')
                if previous is not None:
                    model.Add(previous <= current)
                previous = current
                current_time = arrival
            flags[index] = current
    for key, indices in by_key.items():
        amount, count = extra.get(key, (0, 0))
        model.Add(sum(flags[index] for index in indices) == count)
        model.Add(sum(flags[index] * rows[index]['amount_cents'] for index in indices) == amount)
    return model, flags


def different(model, variables, expected, prefix):
    differences = []
    for index, variable in variables.items():
        if isinstance(variable, int):
            if variable != expected[index]:
                return
            continue
        unequal = model.NewBoolVar(f'{prefix}_{index}')
        model.Add(variable != expected[index]).OnlyEnforceIf(unequal)
        model.Add(variable == expected[index]).OnlyEnforceIf(unequal.Not())
        differences.append(unequal)
    model.AddBoolOr(differences)


def solve_catch(rows, accounts, extra, certify=False):
    model, flags = catch_model(rows, accounts, extra)
    solver = new_solver()
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError(f'No catch-up attribution: {solver.StatusName(status)}')
    result = [flags[index] if isinstance(flags[index], int) else solver.Value(flags[index])
              for index in range(len(rows))]
    if certify:
        different(model, flags, result, 'late_difference')
        second = solver.Solve(model)
        if second != cp_model.INFEASIBLE:
            raise RuntimeError(f'Catch-up vector not certified: {solver.StatusName(second)}')
    return result


def page_candidates(indices, rows, size, ranks):
    pending = [-1]
    visited = set()
    edges = []
    last_gap = max(ranks.values(), default=0)
    while pending:
        cursor = pending.pop()
        if cursor in visited:
            continue
        visited.add(cursor)
        alternatives = {}
        for gap in range(last_gap + 1):
            page = tuple(index for index in indices[cursor + 1:] if ranks[index] <= gap)[:size]
            if page in alternatives:
                alternatives[page][1] = gap
            else:
                alternatives[page] = [gap, gap]
        for page, (first, last) in alternatives.items():
            successor = indices.index(page[-1]) if len(page) == size else None
            edges.append((cursor, successor, page, first, last))
            if successor is not None:
                pending.append(successor)
    return edges


def live_constraints(model, rows, staged, positive, catch_up, changed, sizes,
                     batch_size, uniform):
    by_day = defaultdict(list)
    for index, row in enumerate(rows):
        by_day[row['day']].append(index)
    containing = defaultdict(list)
    nonincreasing, equal = defaultdict(list), defaultdict(list)
    for day, day_indices in sorted(by_day.items()):
        lower = max((rows[index]['arrival_us'] for index in day_indices if not catch_up[index]), default=-1)
        timestamps = sorted({rows[index]['arrival_us'] for index in day_indices if rows[index]['arrival_us'] > lower})
        gap_for = {stamp: position + 1 for position, stamp in enumerate(timestamps)}
        ranks = {index: gap_for.get(rows[index]['arrival_us'], 0) for index in day_indices}
        partitions = {bucket: sorted([index for index in day_indices if rows[index]['bucket'] == bucket],
                                     key=lambda index: (rows[index]['event_us'], rows[index]['pix_id']))
                      for bucket in range(4)}
        for size in sizes:
            active = changed[day] if size == sizes[1] else changed[day].Not()
            incoming, outgoing = defaultdict(list), defaultdict(list)
            times = {}

            def state_time(state):
                if state not in times:
                    times[state] = model.NewIntVar(0, len(timestamps), f'time_{day}_{size}_{state}')
                return times[state]

            for bucket, indices in partitions.items():
                for number, (cursor, successor, page, first, last) in enumerate(page_candidates(indices, rows, size, ranks)):
                    source = (bucket, cursor)
                    target = (bucket + 1, -1) if successor is None else (bucket, successor)
                    chosen = model.NewBoolVar(f'page_{day}_{size}_{bucket}_{number}')
                    outgoing[source].append(chosen)
                    incoming[target].append(chosen)
                    model.Add(state_time(target) >= state_time(source)).OnlyEnforceIf(chosen)
                    model.Add(state_time(target) >= first).OnlyEnforceIf(chosen)
                    model.Add(state_time(target) <= last).OnlyEnforceIf(chosen)
                    for index in page:
                        containing[index].append(chosen)
                    for position in range(1, len(page)):
                        earlier, later = page[position - 1], page[position]
                        nonincreasing[earlier, later].append(chosen)
                        if uniform or position % batch_size:
                            equal[earlier, later].append(chosen)
            for state in incoming.keys() | outgoing.keys():
                balance = (active if state == (0, -1) else
                           -active if state == (4, -1) else 0)
                model.Add(sum(outgoing[state]) - sum(incoming[state]) == balance)
            model.Add(state_time((0, -1)) == 0)
    triggers = {}

    def trigger(choices):
        key = tuple(sorted({choice.Index() for choice in choices}))
        if key not in triggers:
            flag = model.NewBoolVar(f'active_pattern_{len(triggers)}')
            model.AddMaxEquality(flag, choices) if choices else model.Add(flag == 0)
            triggers[key] = flag
        return triggers[key]

    for index, variable in staged.items():
        model.Add(variable == 0).OnlyEnforceIf(trigger(containing[index]).Not())
    for (earlier, later), choices in nonincreasing.items():
        model.Add(staged[earlier] >= staged[later]).OnlyEnforceIf(trigger(choices))
    for (earlier, later), choices in equal.items():
        model.Add(staged[earlier] == staged[later]).OnlyEnforceIf([trigger(choices), positive[later]])


def static_constraints(model, rows, staged, positive, changed, sizes, batch_size):
    partitions = defaultdict(list)
    for index, row in enumerate(rows):
        partitions[row['day'], row['bucket']].append(index)
    for (day, bucket), indices in sorted(partitions.items()):
        indices.sort(key=lambda index: (rows[index]['event_us'], rows[index]['pix_id']))
        timestamps = sorted({rows[index]['arrival_us'] for index in indices})
        ranks = {stamp: position + 1 for position, stamp in enumerate(timestamps)}
        cutoff = model.NewIntVar(0, len(timestamps), f'static_cut_{day}_{bucket}')
        count = model.NewConstant(0)
        previous = model.NewConstant(0)
        for index in indices:
            present = model.NewBoolVar(f'static_present_{index}')
            model.Add(cutoff >= ranks[rows[index]['arrival_us']]).OnlyEnforceIf(present)
            model.Add(cutoff < ranks[rows[index]['arrival_us']]).OnlyEnforceIf(present.Not())
            model.Add(staged[index] == 0).OnlyEnforceIf(present.Not())
            for size in sizes:
                active = changed[day] if size == sizes[1] else changed[day].Not()
                page_first = model.NewBoolVar(f'static_page_{index}_{size}')
                batch_first = model.NewBoolVar(f'static_batch_{index}_{size}')
                page_offset = model.NewIntVar(0, size - 1, f'static_offset_{index}_{size}')
                batch_offset = model.NewIntVar(0, batch_size - 1, f'static_batch_offset_{index}_{size}')
                model.AddModuloEquality(page_offset, count, size)
                model.AddModuloEquality(batch_offset, page_offset, batch_size)
                model.Add(page_offset == 0).OnlyEnforceIf(page_first)
                model.Add(page_offset != 0).OnlyEnforceIf(page_first.Not())
                model.Add(batch_offset == 0).OnlyEnforceIf(batch_first)
                model.Add(batch_offset != 0).OnlyEnforceIf(batch_first.Not())
                model.Add(previous >= staged[index]).OnlyEnforceIf([active, present, page_first.Not()])
                model.Add(previous == staged[index]).OnlyEnforceIf([active, positive[index], batch_first.Not()])
            after = model.NewIntVar(0, len(indices), f'static_count_{index}')
            model.Add(after == count + present)
            last = model.NewIntVar(0, 5, f'static_last_{index}')
            model.Add(last == staged[index]).OnlyEnforceIf(present)
            model.Add(last == previous).OnlyEnforceIf(present.Not())
            count, previous = after, last


def ordinary_model(rows, accounts, ordinary, catch_up,
                   sizes=(100, 250), commit='2024-03-08', batch_size=32,
                   max_receives=5, uniform=False, static=False):
    model = cp_model.CpModel()
    staged = {index: model.NewIntVar(0, max_receives, f'stage_{index}')
              for index in range(len(rows))}
    positive = {}
    for index, variable in staged.items():
        positive[index] = model.NewBoolVar(f'positive_{index}')
        model.Add(variable > 0).OnlyEnforceIf(positive[index])
        model.Add(variable == 0).OnlyEnforceIf(positive[index].Not())
    by_key = defaultdict(list)
    by_holder = defaultdict(list)
    for index, row in enumerate(rows):
        by_key[row_key(row, accounts)].append(index)
        account = accounts[row['account']]
        by_holder[(account['uf'], account['holder_doc'])].append(index)
    days = sorted({row['day'] for row in rows})
    changed = {}
    previous = None
    for day in days:
        if day < commit:
            changed[day] = model.NewConstant(0)
        else:
            changed[day] = model.NewBoolVar(f'configuration_{day}')
            if previous is not None:
                model.Add(previous <= changed[day])
        previous = changed[day]
    if static:
        static_constraints(model, rows, staged, positive, changed, sizes, batch_size)
    else:
        live_constraints(model, rows, staged, positive, catch_up, changed, sizes, batch_size, uniform)
    reported_holders = {(key[0], accounts[key[1]]['holder_doc']) for key in ordinary}
    declared = {}
    for index, row in enumerate(rows):
        account = accounts[row['account']]
        visible = (account['uf'], account['holder_doc']) in reported_holders or account['holder_type'] == 'CNPJ'
        declared[index] = staged.get(index, 0) if visible else 0
    for key, indices in by_key.items():
        account = accounts[key[1]]
        holder = (key[0], account['holder_doc'])
        if account['holder_type'] == 'CNPJ' or holder in reported_holders:
            amount, count = ordinary.get(key, (0, 0))
            model.Add(sum(staged[index] for index in indices) == count)
            model.Add(sum(staged[index] * rows[index]['amount_cents'] for index in indices) == amount)
    for holder, indices in by_holder.items():
        if accounts[rows[indices[0]]['account']]['holder_type'] != 'CPF':
            continue
        amount = sum(staged[index] * rows[index]['amount_cents'] for index in indices)
        count = sum(staged[index] for index in indices)
        if holder in reported_holders:
            model.Add(amount >= 337500)
            model.Add(count >= 30)
        else:
            below_value = model.NewBoolVar(f'floor_{holder[0]}_{holder[1]}')
            model.Add(amount < 337500).OnlyEnforceIf(below_value)
            model.Add(count < 30).OnlyEnforceIf(below_value.Not())
    return model, declared


def solve_ordinary(rows, accounts, ordinary, catch_up, certify=False,
                   sizes=(100, 250), commit='2024-03-08', batch_size=32, max_receives=5):
    model, variables = ordinary_model(rows, accounts, ordinary, catch_up, sizes,
                                      commit, batch_size, max_receives)
    solver = new_solver()
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError(f'No ordinary attribution: {solver.StatusName(status)}')
    result = [variable if isinstance(variable, int) else solver.Value(variable)
              for index, variable in sorted(variables.items())]
    if certify:
        different(model, variables, result, 'ordinary_difference')
        second = solver.Solve(model)
        if second != cp_model.INFEASIBLE:
            raise RuntimeError(f'Ordinary vector not certified: {solver.StatusName(second)}')
    return result


def verify_attribution(rows, accounts, ordinary, extra, declared, catch_up):
    if len(declared) != len(rows) or len(catch_up) != len(rows):
        raise RuntimeError('Attribution length differs from the ledger')
    if any(count < 0 or late not in (0, 1)
           for count, late in zip(declared, catch_up)):
        raise RuntimeError('Invalid attribution')
    for label, weights, expected in (('ordinary', declared, ordinary),
                                      ('catch-up', catch_up, extra)):
        actual = defaultdict(lambda: [0, 0])
        for row, weight in zip(rows, weights):
            if weight:
                pair = actual[row_key(row, accounts)]
                pair[0] += weight * row['amount_cents']
                pair[1] += weight
        actual = {key: tuple(pair) for key, pair in actual.items()}
        expected = {key: tuple(pair) for key, pair in expected.items() if any(pair)}
        if actual != expected:
            raise RuntimeError(f'Attribution does not reproduce {label} amounts and counts')


def job_history(project):
    def constants(text):
        result = {}
        for node in ast.parse(text).body:
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
                try:
                    result[node.targets[0].id] = ast.literal_eval(node.value)
                except (ValueError, TypeError):
                    pass
        return result
    current = constants((project / 'config.py').read_text())
    revisions = subprocess.check_output(['git', '-C', str(project), 'log', '--reverse',
                                         '--format=%H %aI', '--', 'config.py'], text=True).splitlines()
    prior = None
    change = None
    for revision in revisions:
        commit_id, stamp = revision.split(' ', 1)
        source = subprocess.check_output(['git', '-C', str(project), 'show',
                                          f'{commit_id}:config.py'], text=True)
        size = constants(source)['FETCH_SIZE']
        if prior is not None and size != prior:
            change = (prior, size, stamp[:10])
        prior = size
    if change is None:
        raise RuntimeError('No export page-size change in source history')
    return current['BUCKET_COUNT'], change, current['STAGING_BATCH_SIZE'], current['QUEUE_MAX_RECEIVES']


def reconstruct(month, keyspace, sent, out):
    bucket_count, (old_size, new_size, commit), batch_size, max_receives = job_history(
        Path(__file__).resolve().parent)
    accounts, rows = read_ledger(keyspace, month, bucket_count)
    period = month.replace('-', '')
    ordinary = parse_files(sent, month, 0, period)
    extra = parse_files(sent, next_month(month), 1, period)
    catch_up = solve_catch(rows, accounts, extra, certify=True)
    declared = solve_ordinary(rows, accounts, ordinary, catch_up, certify=True,
                              sizes=(old_size, new_size), commit=commit,
                              batch_size=batch_size, max_receives=max_receives)
    verify_attribution(rows, accounts, ordinary, extra, declared, catch_up)
    output = Path(out)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['pix_id', 'declared', 'catch_up'])
        writer.writerows((row['pix_id'], count, late)
                         for row, count, late in zip(rows, declared, catch_up))
