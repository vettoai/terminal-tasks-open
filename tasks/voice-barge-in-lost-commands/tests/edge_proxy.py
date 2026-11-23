import json
import os
import socket


def call(operation, **fields):
    encoded = json.dumps({'op': operation, **fields}).encode() + b'\n'
    if len(encoded) > 8 * 1024 * 1024:
        raise ValueError('Edge request too large')
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(30)
        connection.connect(os.environ['VOICE_EDGE'])
        connection.sendall(encoded)
        line = connection.makefile('rb').readline(8 * 1024 * 1024 + 1)
    if len(line) > 8 * 1024 * 1024:
        raise ValueError('Edge response too large')
    response = json.loads(line)
    if 'error' in response:
        raise RuntimeError(response['error'])
    return response
