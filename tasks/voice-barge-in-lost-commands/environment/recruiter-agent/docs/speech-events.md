# Speech client messages

Deepgram sends `Results` messages through the transcript callback. The best
alternative is in `channel.alternatives[0].transcript`. Interim text can change
as the caller continues speaking.

`is_final` means that a segment is stable. `speech_final` marks the endpoint of
the spoken request. A caller's question can contain several stable segments
before that endpoint. The recruiting agent receives the completed request,
including the words from each stable segment in spoken order.

The availability and platform-screen recordings in `tests/fixtures/` came
from the speech client's local integration sessions. They include interim
revisions and final segments. Run `python -m pytest tests/test_speech_integration.py`
to replay them through the page's voice connection.
