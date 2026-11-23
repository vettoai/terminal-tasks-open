"""Local HTTP intakes for upload and gateway integration cases."""

import base64
import socket
import threading
from contextlib import contextmanager
from email.parser import BytesHeaderParser
from socketserver import BaseRequestHandler, TCPServer, ThreadingMixIn
from unittest.mock import patch


class IntakeHandler(BaseRequestHandler):
    def handle(self):
        connection = self.request
        connection.settimeout(10)
        incoming = bytearray()
        while b'\r\n\r\n' not in incoming:
            piece = connection.recv(8192)
            if not piece:
                return
            incoming.extend(piece)
        header, body = bytes(incoming).split(b'\r\n\r\n', 1)
        request_line, fields = header.split(b'\r\n', 1)
        method, target, version = request_line.decode('latin-1').split(' ', 2)
        headers = BytesHeaderParser().parsebytes(fields + b'\r\n\r\n')
        length = int(headers.get('Content-Length', '0'))
        record = dict(method=method, path=target, host=headers.get('Host'),
                      cookies=headers.get_all('Cookie', []), length=length,
                      address=self.server.server_address[0], port=self.server.server_address[1],
                      sni=None)
        owner = self.server.owner
        with owner.lock:
            owner.records.append(record)
            reply, consume, fragmented = owner.responder(record)
        try:
            if consume:
                if headers.get('Expect', '').lower() == '100-continue':
                    connection.sendall(b'HTTP/1.1 100 Continue\r\n\r\n')
                while len(body) < length:
                    piece = connection.recv(min(65536, length - len(body)))
                    if not piece:
                        break
                    body += piece
            if fragmented:
                for offset in range(0, len(reply), 17):
                    connection.sendall(reply[offset:offset + 17])
            else:
                connection.sendall(reply)
            connection.shutdown(socket.SHUT_WR)
            if not consume:
                owner.released.wait()
                connection.setblocking(False)
                while True:
                    try:
                        piece = connection.recv(65536)
                    except BlockingIOError:
                        break
                    if not piece:
                        break
                    body += piece
        except OSError:
            pass
        finally:
            with owner.lock:
                record['body'] = base64.b64encode(body).decode('ascii')


class IntakeServer(ThreadingMixIn, TCPServer):
    allow_reuse_address = True

    def server_bind(self):
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
        if self.address_family == socket.AF_INET6:
            self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        super().server_bind()


class Intake:
    def __init__(self, *, address='127.0.0.1', port=0):
        self.lock = threading.Lock()
        self.released = threading.Event()
        self.records = []
        self.responder = lambda record: (b'HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n', True, False)
        server_class = IntakeServer
        if ':' in address:
            class IPv6IntakeServer(IntakeServer):
                address_family = socket.AF_INET6
            server_class = IPv6IntakeServer
        self.server = server_class((address, port), IntakeHandler)
        self.server.owner = self
        ready = threading.Event()

        def serve():
            ready.set()
            self.server.serve_forever(poll_interval=0.02)

        self.thread = threading.Thread(target=serve)
        self.thread.start()
        if not ready.wait(30):
            self.close()
            raise RuntimeError('Local intake did not start')

    @property
    def port(self):
        return self.server.server_address[1]

    def close(self):
        self.released.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


@contextmanager
def bounded_upload_buffers(destinations):
    original = socket.socket.connect

    def connect(connection, address):
        if address[:2] in destinations:
            connection.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
        return original(connection, address)

    with patch.object(socket.socket, 'connect', connect):
        yield
