import json
import os
import socketserver
import tempfile
import threading
from pathlib import Path

LIMIT = 8 * 1024 * 1024


class EdgeService:
    def __init__(self, handler):
        self.directory = Path(tempfile.mkdtemp(prefix='voice-edge-'))
        self.directory.chmod(0o711)
        self.path = self.directory / 'provider.sock'

        class Request(socketserver.StreamRequestHandler):
            def handle(connection):
                line = connection.rfile.readline(LIMIT + 1)
                try:
                    if len(line) > LIMIT:
                        raise ValueError('Edge request exceeds IPC limit')
                    result = handler(json.loads(line))
                    encoded = json.dumps(result).encode() + b'\n'
                    if len(encoded) > LIMIT:
                        raise ValueError('Edge response exceeds IPC limit')
                except BaseException as error:
                    encoded = json.dumps({'error': str(error)}).encode() + b'\n'
                connection.wfile.write(encoded)

        self.server = socketserver.ThreadingUnixStreamServer(str(self.path), Request)
        self.server.daemon_threads = True
        os.chmod(self.path, 0o666)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.path.unlink()
        self.directory.rmdir()
