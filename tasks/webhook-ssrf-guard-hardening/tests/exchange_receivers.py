"""Trusted real HTTP/TLS peers that emit complete or truncated response streams."""

import base64
import ssl
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler

from support.receivers import ReceiverPool


def response_bytes(*, interims, status, location=None, cookies=(), trace='', incomplete=False):
    blocks = []
    for code in interims:
        headers = f'X-Request-Trace: {trace}\r\n'
        if code == 103:
            headers += 'Link: </assets/receiver.css>; rel=preload; as=style\r\n'
        blocks.append(f'HTTP/1.1 {code} {HTTPStatus(code).phrase}\r\n{headers}\r\n'.encode('ascii'))
    if not incomplete:
        body = b'' if status == 204 else b'receiver acknowledgement\n'
        fields = [('Connection', 'close'), ('X-Request-Trace', trace)]
        if status != 204:
            fields.append(('Content-Length', str(len(body))))
        if location is not None:
            fields.append(('Location', location.decode('latin-1')))
        fields.extend(('Set-Cookie', value) for value in cookies)
        headers = ''.join(f'{name}: {value}\r\n' for name, value in fields)
        blocks.append(f'HTTP/1.1 {status} {HTTPStatus(status).phrase}\r\n{headers}\r\n'.encode('latin-1') + body)
    return b''.join(blocks)


class ExchangeHandler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *args):
        return None

    def receive(self):
        body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
        record = dict(method=self.command, path=self.path, host=self.headers.get('Host'),
                      sni=getattr(self.connection, 'receiver_sni', None),
                      body=base64.b64encode(body).decode(), cookies=self.headers.get_all('Cookie', []),
                      address=self.server.server_address[0], port=self.server.server_address[1])
        with self.server.pool.lock:
            self.server.pool.records.append(record)
            data, fragmented = self.server.pool.responder(record)
        self.close_connection = True
        try:
            if fragmented:
                # Deliberately split CRLFCRLF, without assuming a TCP packet boundary.
                offset = 0
                while offset < len(data):
                    delimiter = data.find(b'\r\n\r\n', offset)
                    end = min(offset + 11, len(data))
                    if offset <= delimiter < end:
                        end = delimiter + 1
                    self.connection.sendall(data[offset:end])
                    offset = end
            else:
                self.connection.sendall(data)
        except OSError:
            # A client may close without reading the final response body.
            pass
        finally:
            if self.server.pool.orderly_tls and isinstance(self.connection, ssl.SSLSocket):
                try:
                    self.connection.unwrap().close()
                except OSError:
                    # unwrap sends close_notify before waiting for the peer's shutdown.
                    pass

    do_POST = receive
    do_GET = receive
    do_PUT = receive


class ExchangePool(ReceiverPool):
    def __init__(self, *args, orderly_tls=False, **kwargs):
        self.orderly_tls = orderly_tls
        super().__init__(*args, **kwargs)
        for server in self.servers:
            server.RequestHandlerClass = ExchangeHandler
