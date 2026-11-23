"""Shared piece vocabulary for the status-record models."""

import json
from pathlib import Path

VOCAB = json.loads(Path(__file__).with_name("vocab.json").read_text())
TOKEN_IDS = {piece: token_id for token_id, piece in enumerate(VOCAB)}
BOS_ID = 0
EOS_ID = 1
VOCAB_SIZE = 256


def encode(text, *, add_bos=True):
    """Encode using longest matching pieces; prepend the context marker by default."""
    pieces = sorted(enumerate(VOCAB[2:], 2), key=lambda item: (-len(item[1]), item[0]))
    result = [BOS_ID] if add_bos else []
    position = 0
    while position < len(text):
        for token_id, piece in pieces:
            if text.startswith(piece, position):
                result.append(token_id)
                position += len(piece)
                break
        else:
            raise ValueError(f"No vocabulary piece at character {position}")
    return result


def decode(token_ids):
    """Join ordinary pieces, omitting the BOS and EOS markers."""
    return "".join(VOCAB[int(token_id)] for token_id in token_ids if int(token_id) > 1)
