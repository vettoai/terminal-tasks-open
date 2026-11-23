import datetime as dt
import json


def construct_links(rng, profile, tax, identifier, history, documents, logs, partners, listed, labels):
    components = []
    families = ('release_chain','release_cycle','blocked_chain','document_cycle','competing_claims','multiple_holders')
    ordinal = 0
    for family in families:
        for variant in range(3):
            size = rng.randint(3,7) if family in ('release_chain','blocked_chain') else rng.randint(2,6)
            accounts = [tax() for _ in range(size)]
            if rng.choice((False,True)): accounts.reverse()
            candidates = accounts[1:]+[tax()]
            modes = ['moving']*size
            safe = set(range(size))
            claims = set()
            blocker = None
            if family in ('release_cycle','document_cycle'):
                candidates[-1] = accounts[0]
            if family == 'blocked_chain':
                accounts.append(candidates[-1]); candidates.append(None)
                modes.append(('kept','uncertain','excluded')[variant]); safe = set()
            if family == 'document_cycle':
                blocker = rng.randrange(size); safe = set()
            if family == 'competing_claims':
                count = rng.randint(2,3)
                accounts = [tax() for _ in range(count+2)]
                shared = tax()
                candidates = [shared]*count+[accounts[0],accounts[-3]]
                modes = ['moving']*len(accounts)
                claims = set(range(count)); safe = set()
            if family == 'multiple_holders':
                shared = tax()
                accounts = [tax(),shared,shared]
                candidates = [shared,tax(),tax() if variant == 0 else None]
                modes = ['moving','moving','moving' if variant == 0 else 'closed' if variant == 1 else 'excluded']
                safe = {0,1,2} if variant == 0 else {0,1} if variant == 1 else {1}
            order = list(range(len(accounts)))
            rng.shuffle(order)
            accounts,candidates,modes = ([values[index] for index in order] for values in (accounts,candidates,modes))
            safe = {index for index,previous in enumerate(order) if previous in safe}
            claims = {index for index,previous in enumerate(order) if previous in claims}
            blocker = order.index(blocker) if blocker is not None else None
            members = []
            for index,(account,candidate,mode) in enumerate(zip(accounts,candidates,modes)):
                ordinal += 1
                contact = candidate if candidate is not None else tax()
                partner = next(value[0] for value in partners if (value[0] in listed) == (mode == 'kept'))
                person = 'J' if mode == 'excluded' else 'F'
                if mode == 'closed': contact = account
                row = profile(person=person,account=account,contact=contact,partner=partner,flag=mode == 'kept',status=1 if mode == 'closed' else 0)
                created = dt.datetime(2019,6,1)+dt.timedelta(days=ordinal,seconds=rng.randrange(86400))
                row[7:9] = [created.isoformat(timespec='milliseconds'),'2025-09-24T16:37:42.000']
                history[-1][7:9] = [row[7],row[7]]
                older = tax()
                if mode == 'moving':
                    initial = row.copy(); initial[3:5] = [older,older]
                    initial[8] = (created+dt.timedelta(milliseconds=3)).isoformat(timespec='milliseconds'); history.append(initial)
                    authoritative = row.copy(); authoritative[3:5] = [candidate,candidate]
                    authoritative[8] = (dt.datetime(2021,1,1)+dt.timedelta(days=ordinal*3)).isoformat(timespec='milliseconds'); history.append(authoritative)
                    released = row.copy(); released[3:5] = [tax(),candidate]
                    released_at = dt.datetime(2021,1,1)+dt.timedelta(days=ordinal*3+1) if family == 'competing_claims' else dt.datetime(2023,1,1)+dt.timedelta(days=ordinal)
                    released[8] = released_at.isoformat(timespec='milliseconds'); history.append(released)
                else:
                    initial = row.copy(); initial[3:5] = [tax(),tax()]
                    initial[8] = (created+dt.timedelta(milliseconds=3)).isoformat(timespec='milliseconds'); history.append(initial)
                if family == 'multiple_holders' and index == order.index(2) and mode != 'closed':
                    closed = row.copy(); closed[6] = 1; history.append(closed)
                    row[8] = '2025-09-26T09:18:31.000'
                if mode in ('moving','kept','uncertain'):
                    cause = 'conflicting_claims' if index in claims else 'history' if index in safe else 'in_use'
                    outcome = 'repaired' if index in safe else 'manual_review'
                    if mode == 'kept': cause,outcome = 'second_contact','kept'
                    if mode == 'uncertain': cause = 'ambiguous'
                    labels[row[0]] = dict(kind=family,cause=cause,outcome=outcome,final=[candidate,candidate] if outcome == 'repaired' else row[3:5].copy())
                if index == blocker:
                    documents.append([identifier('DOC-'),row[0],rng.choice(('label','service_invoice')),'2025-09-25T13:21:00.000',account])
                elif mode == 'moving' and index == 0:
                    printed = candidate if variant % 2 else older
                    issued = (dt.datetime(2021,1,1)+dt.timedelta(days=ordinal*3,hours=12)).isoformat(timespec='milliseconds') if printed == candidate else '2020-04-14T11:42:00.000'
                    documents.append([identifier('DOC-'),row[0],rng.choice(('label','service_invoice')),issued,printed])
                logs.append([row[0],'2025-09-24T16:37:42.000',rng.choice(('marketplace-sync','warehouse-bridge','partner-import')),json.dumps({'accountTaxId':account})])
                members.append(row[0])
            rng.shuffle(members)
            components.append(dict(family=family,variant=variant,members=members))
    return components
