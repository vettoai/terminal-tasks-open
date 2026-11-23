"""Private matched replies with complete headers and diagnostic entities."""

import ipaddress
import random
from http import HTTPStatus

from case_inputs import REDIRECTS
from invocation_inputs import public_alias


def result_workloads(plain_port, secure_port):
    rng = random.Random(20261108)
    statuses = (200, 201, 202, 418, 503)
    results = {kind: iter(rng.sample(statuses, len(statuses)) + [rng.choice(statuses) for _ in range(3)])
               for kind in ('terminal', 'redirect')}
    cases = []
    for kind in ('terminal', 'redirect'):
        for scheme in ('http', 'https'):
            for template in range(4):
                host = 'receiver-' + rng.randbytes(7).hex() + '.test'
                port = secure_port if scheme == 'https' else plain_port
                address = public_alias(rng)
                while ipaddress.ip_address(address).version != (4 if template % 2 == 0 else 6):
                    address = public_alias(rng)
                tag = rng.randbytes(6).hex()
                target = f'/events/{tag}%2Freceipt?batch={rng.randbytes(5).hex()}&batch='
                final_target = f'/regional/{rng.randbytes(6).hex()}%2Fack?trace=&trace={tag}'
                diagnostic = ('gateway receipt ' + rng.randbytes(256).hex()).encode('ascii')
                diagnostic = diagnostic[:rng.randrange(32, 513)]
                split = rng.randrange(1, len(diagnostic) - 1)
                cases.append(dict(kind=kind, scheme=scheme, template=template, host=host,
                                  port=port, address=address, url=f'{scheme}://{host}:{port}{target}',
                                  body=rng.randbytes(rng.randrange(1, 4097)), status=next(results[kind]),
                                  redirect=rng.choice(REDIRECTS),
                                  location=f'{scheme}://{host}:{port}{final_target}'.encode('ascii'),
                                  trace=rng.randbytes(12).hex(), diagnostic=diagnostic,
                                  cut=rng.randrange(1, len(diagnostic)),
                                  split=split, chunk_cut=rng.randrange(1, len(diagnostic) - split),
                                  challenges=[rng.randbytes(17).hex(), rng.randbytes(17).hex()],
                                  fragmented=bool(template % 2)))
    return cases


def diagnostic_response(case, challenge, *, short):
    status = case['redirect'] if case['kind'] == 'redirect' else case['status']
    fields = f'HTTP/1.1 {status} {HTTPStatus(status).phrase}\r\nConnection: close\r\n'
    fields += f"X-Request-Trace: {case['trace']}\r\n"
    if case['kind'] == 'redirect':
        fields += 'Location: ' + case['location'].decode('ascii') + '\r\n'
        fields += f'Set-Cookie: affinity={challenge}; Path=/\r\n'
    diagnostic = case['diagnostic']
    if case['template'] < 2:
        fields += f'Content-Length: {len(diagnostic)}\r\n\r\n'
        body = diagnostic[:0 if case['template'] == 0 else case['cut']] if short else diagnostic
    else:
        fields += 'Transfer-Encoding: chunked\r\n\r\n'
        first, second = diagnostic[:case['split']], diagnostic[case['split']:]
        first_chunk = f'{len(first):X}\r\n'.encode() + first + b'\r\n'
        second_head = f'{len(second):X}\r\n'.encode()
        full_chunks = first_chunk + second_head + second + b'\r\n'
        body = full_chunks + b'0\r\n\r\n'
        if short:
            body = (first_chunk + second_head + second[:case['chunk_cut']]
                    if case['template'] == 2 else full_chunks)
    return fields.encode('ascii') + body
