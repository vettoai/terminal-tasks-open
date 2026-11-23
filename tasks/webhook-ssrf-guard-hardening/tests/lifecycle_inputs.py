"""Private fixed-seed producer, retry and DNS-outage workloads."""

import random

from invocation_inputs import public_alias


def lifecycle_workflows(port):
    rng = random.Random(20261101)
    workflows = []
    for kind in ('provision', 'outage', 'retry_private', 'saved_private', 'snapshot'):
        endpoints = []
        events = []
        topic = rng.choice(('shipment.received', 'invoice.paid', 'inventory.adjusted'))
        for index in range(2 if kind == 'snapshot' else 1):
            host = 'intake-' + rng.randbytes(7).hex() + '.test'
            target = '/events/' + rng.randbytes(6).hex() + '?region=&region=' + rng.randbytes(4).hex()
            endpoints.append(dict(host=host, target=target, url=f'https://{host}:{port}{target}',
                                  address=public_alias(rng), status=rng.choice((201, 202, 204))))
            events.append(dict(event_id='evt_' + rng.randbytes(12).hex(), topic=topic,
                               data=dict(reference=rng.randbytes(8).hex(), quantity=rng.randrange(1, 97),
                                         region=rng.choice(('west', 'central', 'north')), note='received')))
        workflows.append(dict(kind=kind, customer_id='cust_' + rng.randbytes(9).hex(),
                              topic=topic, endpoints=endpoints, events=events))
    return workflows


def resolution_groups(plain_port, secure_port):
    rng = random.Random(20261102)
    groups = []
    for redirect in (False, True):
        for scheme in ('http', 'https'):
            for default in (False, True):
                port = secure_port if scheme == 'https' else plain_port
                host = 'receiver-' + rng.randbytes(7).hex() + '.test'
                target = '/receipts/' + rng.randbytes(6).hex() + '?event=&event=' + rng.randbytes(4).hex()
                destination = f'{scheme}://{host}:{port}{target}'
                addresses = [public_alias(rng)]
                while len(addresses) < 2:
                    candidate = public_alias(rng)
                    if (':' in candidate) != (':' in addresses[0]):
                        addresses.append(candidate)
                aliases = {host: addresses}
                url = destination
                if redirect:
                    first = 'gateway-' + rng.randbytes(7).hex() + '.test'
                    url = f'{scheme}://{first}:{port}/handoff/{rng.randbytes(6).hex()}?region=&region=west'
                    first_address = public_alias(rng)
                    while first_address in addresses:
                        first_address = public_alias(rng)
                    aliases[first] = [first_address]
                groups.append(dict(url=url, host=host, mapping=aliases, default=default,
                                   body=rng.randbytes(rng.randrange(1, 4097)),
                                   redirects=[307] if redirect else [],
                                   locations=[destination.encode()] if redirect else [],
                                   status=rng.choice((201, 202, 204, 418))))
    return groups
