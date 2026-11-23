"""Local HTTPS receivers for integration tests and customer snapshot replay."""

import base64
import ipaddress
import json
import os
import socket
import ssl
import threading
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'local_ca'
LOCAL_NETWORKS = (ipaddress.ip_network('127.0.0.1/32'),)
SHARED_HOSTS = ('events.edgeharbor.net', 'hooks.deliverymesh.net', 'cdn-a.test', 'cdn-b.test')


def client_context(assets=ASSETS, ca='ca.pem'):
    return ssl.create_default_context(cafile=str(Path(assets) / ca))


def resolver_for(mapping):
    def resolve(host, port, family=0, type=0, proto=0, flags=0):
        hostname = host.decode() if isinstance(host, bytes) else host
        hostname = hostname.rstrip('.').lower()
        addresses = mapping.get(hostname)
        if addresses is None:
            try:
                addresses = [str(ipaddress.ip_address(hostname))]
            except ValueError:
                raise socket.gaierror(socket.EAI_NONAME, hostname)
        answers = []
        for address in addresses:
            version = ipaddress.ip_address(address).version
            address_family = socket.AF_INET6 if version == 6 else socket.AF_INET
            if family not in (0, socket.AF_UNSPEC, address_family):
                continue
            kind = type or socket.SOCK_STREAM
            protocol = proto or (socket.IPPROTO_UDP if kind == socket.SOCK_DGRAM else socket.IPPROTO_TCP)
            sockaddr = (address, int(port), 0, 0) if version == 6 else (address, int(port))
            answers.append((address_family, kind, protocol, '', sockaddr))
        return answers
    return resolve


class ReceiverHandler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.0'

    def log_message(self, *args):
        return None

    def receive(self):
        body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
        record = {
            'method': self.command, 'path': self.path,
            'host': self.headers.get('Host'),
            'sni': getattr(self.connection, 'receiver_sni', None),
            'body': base64.b64encode(body).decode(),
            'address': self.server.server_address[0],
            'port': self.server.server_address[1],
            'cookies': self.headers.get_all('Cookie', []),
        }
        with self.server.pool.lock:
            self.server.pool.records.append(record)
            response = self.server.routes.get(self.path, (200, None, (), None))
            if self.server.pool.responder is not None:
                response = self.server.pool.responder(record)
        if isinstance(response, bytes):
            self.close_connection = True
            try:
                self.connection.sendall(response)
            except OSError:
                pass
            return
        status, location, headers, required = response
        if required is not None:
            supplied = SimpleCookie()
            for field in record['cookies']:
                supplied.load(field)
            if any(name not in supplied or supplied[name].value != value for name, value in required.items()):
                status, location, headers = 403, None, ()
        self.send_response(status)
        if location is not None:
            self.send_header('Location', location.decode('latin-1') if isinstance(location, bytes) else location)
        for name, value in headers:
            self.send_header(name, value.decode('latin-1') if isinstance(value, bytes) else value)
        self.send_header('Content-Length', '0')
        self.end_headers()

    do_POST = receive
    do_GET = receive
    do_PUT = receive


class ReceiverServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def get_request(self):
        connection, address = super().get_request()
        with self.pool.lock:
            self.pool.connections.append(address)
        connection.settimeout(10)
        if self.tls:
            try:
                connection = self.context.wrap_socket(connection, server_side=True)
            except BaseException:
                connection.close()
                raise
        return connection, address


class ReceiverPool:
    def __init__(self, ports=(0,), *, assets=ASSETS, address='127.0.0.1', tls=True):
        self.assets = Path(assets)
        self.manifest = json.loads((self.assets / 'manifest.json').read_text())
        self.lock = threading.Lock()
        self.records = []
        self.connections = []
        self.responder = None
        self.servers = []
        self.threads = []
        self.contexts = {}
        for host, stem in self.manifest.items():
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(str(self.assets / (stem + '.pem')), str(self.assets / (stem + '.key')))
            self.contexts[host] = context
        try:
            for port in ports:
                server_class = ReceiverServer
                if ':' in address:
                    class IPv6ReceiverServer(ReceiverServer):
                        address_family = socket.AF_INET6
                    server_class = IPv6ReceiverServer
                server = server_class((address, port), ReceiverHandler)
                server.pool = self
                server.tls = tls
                server.routes = {}
                server.context = self.contexts['wrong.test']
                server.default_host = 'wrong.test'
                server.shared = False
                server.context = self.make_context(server)
                self.servers.append(server)
                ready = threading.Event()

                def serve(listener=server, started=ready):
                    started.set()
                    listener.serve_forever(poll_interval=0.02)

                thread = threading.Thread(target=serve, daemon=True)
                thread.start()
                self.threads.append(thread)
                if not ready.wait(30):
                    raise RuntimeError('Local receiver did not start')
        except BaseException:
            self.close()
            raise

    def make_context(self, server):
        stem = self.manifest['wrong.test']
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(self.assets / (stem + '.pem')), str(self.assets / (stem + '.key')))

        def select(connection, name, initial_context):
            connection.receiver_sni = name
            if server.shared:
                chosen = name if name in self.contexts else 'wrong.test'
            else:
                chosen = server.default_host
            connection.context = self.contexts[chosen]

        context.set_servername_callback(select)
        return context

    @property
    def port(self):
        return self.servers[0].server_address[1]

    def configure(self, host, *, shared=None):
        name = host.rstrip('.')
        with self.lock:
            for server in self.servers:
                server.default_host = name
                server.shared = name in SHARED_HOSTS if shared is None else shared

    def route(self, path, status=200, location=None, *, headers=(), cookies=None):
        with self.lock:
            for server in self.servers:
                server.routes[path] = (status, location, tuple(headers), cookies)

    def drain(self):
        with self.lock:
            result = list(self.records)
            self.records.clear()
        return result

    def close(self):
        for server in self.servers:
            server.shutdown()
            server.server_close()
        for thread in self.threads:
            thread.join(timeout=10)
        self.servers.clear()
        self.threads.clear()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class ControlHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        return None

    def do_POST(self):
        message = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if message['action'] == 'configure':
            self.server.pool.configure(message['host'])
            result = None
        elif message['action'] == 'drain':
            result = self.server.pool.drain()
        else:
            self.send_error(400)
            return
        data = json.dumps(result).encode()
        self.send_response(200)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class ReceiverControl:
    def __init__(self, pool):
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), ControlHandler)
        self.server.pool = pool
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': 0.02}, daemon=True)

    def __enter__(self):
        self.thread.start()
        return f'http://127.0.0.1:{self.server.server_port}/'

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=10)


class RemotePool:
    def __init__(self, endpoint):
        self.endpoint = endpoint
        self.opener = build_opener(ProxyHandler({}))

    def request(self, action, **fields):
        data = json.dumps(dict(action=action, **fields)).encode()
        with self.opener.open(Request(self.endpoint, data=data), timeout=30) as response:
            return json.load(response)

    def configure(self, host):
        self.request('configure', host=host)

    def drain(self):
        return self.request('drain')

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


def replay_pool(ports):
    endpoint = os.environ.get('WEBHOOK_REPLAY_RECEIVERS')
    return RemotePool(endpoint) if endpoint else ReceiverPool(ports)
