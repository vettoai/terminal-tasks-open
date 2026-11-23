from __future__ import annotations

import hashlib
import math
import struct
import subprocess
import threading
import time
from types import SimpleNamespace


class SpeechConnection:
    def __init__(self):
        self.handlers = {}
        self.voiced = False
        self.turn = 0

    def on(self, event, callback):
        self.handlers[event] = callback

    async def start(self, options):
        return True

    async def send(self, data):
        from deepgram import LiveTranscriptionEvents

        samples = struct.unpack('<' + 'h' * (len(data) // 2), data)
        loud = any(abs(sample) > 900 for sample in samples)
        if self.voiced and not loud:
            self.turn += 1
            transcript = [
                'Tell me about backend engineering experience',
                'What projects use machine learning',
                'Tell me about availability for an interview',
            ][(self.turn - 1) % 3]
            result = SimpleNamespace(
                channel=SimpleNamespace(alternatives=[SimpleNamespace(transcript=transcript)]),
                is_final=True, speech_final=True,
            )
            await self.handlers[LiveTranscriptionEvents.Transcript](self, result=result)
        self.voiced = loud

    async def finish(self):
        return True


class SpeechClient:
    def __init__(self, *args, **kwargs):
        self.listen = SimpleNamespace(asyncwebsocket=SimpleNamespace(v=lambda version: SpeechConnection()))


class SynthesisClient:
    def __init__(self):
        self.lock = threading.Lock()
        self.next_release = 0

    def synthesize_speech(self, *, input, **kwargs):
        digest = hashlib.sha256(input.text.encode()).digest()
        frequency = 330 + int.from_bytes(digest[:2], 'little') % 440
        pcm = b''.join(struct.pack('<h', int(3000 * math.sin(2 * math.pi * frequency * sample / 16000)))
                       for sample in range(640))
        audio = subprocess.run(
            ['ffmpeg', '-loglevel', 'error', '-f', 's16le', '-ar', '16000', '-ac', '1',
             '-i', 'pipe:0', '-metadata', 'comment=' + digest.hex(), '-f', 'mp3', 'pipe:1'],
            input=pcm, capture_output=True, check=True,
        ).stdout
        with self.lock:
            release = max(time.monotonic(), self.next_release) + 0.02
            self.next_release = release
        time.sleep(max(0, release - time.monotonic()))
        return SimpleNamespace(audio_content=audio)


def install():
    import os
    import deepgram
    from google.cloud import texttospeech

    os.environ.setdefault('DEEPGRAM_API_KEY', 'local-development')
    deepgram.DeepgramClient = SpeechClient
    texttospeech.TextToSpeechClient = SynthesisClient
