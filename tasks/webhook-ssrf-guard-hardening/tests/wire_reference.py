"""Protected historical URI and response-state model; no submitted imports."""

import http.client
import io
from collections import Counter
from http.cookies import _unquote
from types import SimpleNamespace

from requests import Request, Response, Session
from requests.adapters import HTTPAdapter
from requests.cookies import extract_cookies_to_jar
from urllib3.response import HTTPResponse
from urllib3.util.url import _encode_target, parse_url


def describe(request):
    parts = parse_url(request.url)
    host = parts.host.strip('[]')
    port = parts.port or (443 if parts.scheme == 'https' else 80)
    authority = f'[{host}]' if ':' in host else host
    default_port = 443 if parts.scheme == 'https' else 80
    if port != default_port:
        authority += f':{port}'
    return dict(
        url=request.url, host=host, sni=host.rstrip('.'), port=port,
        authority=authority,
        target=_encode_target(HTTPAdapter().request_url(request, {})),
        scheme=parts.scheme,
    )


def wire_hops(case):
    request = Request('POST', case['url'], data=case['body']).prepare()
    hops = [describe(request)]
    with Session() as session:
        session.trust_env = False
        for status, octets in zip(case['redirects'], case['locations']):
            response = Response()
            response.status_code = status
            response.url = request.url
            response.request = request
            response._content = b''
            response.headers['Location'] = octets.decode('latin-1')
            request = next(session.resolve_redirects(response, request, yield_requests=True))
            hops.append(describe(request))
    return hops


def cookie_values(fields):
    values = []
    for field in fields:
        for pair in field.split(';'):
            if not pair.strip():
                continue
            name, separator, value = pair.strip().partition('=')
            values.append((name.strip(), _unquote(value.strip()) if separator else None))
    return Counter(values)


def stateful_hops(case):
    request = Request('POST', case['url'], data=case['body']).prepare()
    hops = []
    with Session() as session:
        session.trust_env = False
        for index in range(len(case['locations']) + 1):
            hop = describe(request)
            hop['cookies'] = cookie_values([request.headers.get('Cookie', '')])
            hops.append(hop)
            if index == len(case['locations']):
                break
            fields = [(b'Location', case['locations'][index])]
            fields += [(b'Set-Cookie', value.encode('ascii')) for value in case['cookies'][index]]
            header_bytes = b''.join(name + b': ' + value + b'\r\n' for name, value in fields) + b'\r\n'
            message = http.client.parse_headers(io.BytesIO(header_bytes))
            raw = HTTPResponse(body=b'', original_response=SimpleNamespace(msg=message))
            response = Response()
            response.status_code = case['redirects'][index]
            response.url = request.url
            response.request = request
            response._content = b''
            response.raw = raw
            response.headers['Location'] = message['Location']
            extract_cookies_to_jar(session.cookies, request, raw)
            request = next(session.resolve_redirects(response, request, yield_requests=True))
    return hops
