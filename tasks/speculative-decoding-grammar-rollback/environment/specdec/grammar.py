"""Finite-state grammar for status records.

Callers may supply any object implementing initial_state, allowed_tokens,
advance, is_accepting and eos_id. initial_state starts an independent traversal.
State is an opaque cursor: implementations may keep its position in a value
record or in matcher-owned storage behind a handle. Use the state returned by
advance. allowed_tokens returns a length-256 Boolean tensor, which may be a
borrowed workspace valid until the next mask request on that matcher.
Call advance only with an allowed token. Transitions consume complete vocabulary
pieces, including quoted values and keys. EOS is allowed only in an accepting
state. JsonGrammar leaves its complete-object state unchanged after EOS.
"""

from dataclasses import dataclass

import torch

from tokenizer import EOS_ID, TOKEN_IDS, VOCAB_SIZE

TRANSITIONS = {
    "start": {TOKEN_IDS["{"]: "status_key"},
    "status_key": {TOKEN_IDS['"status":']: "status_value"},
    "status_value": {TOKEN_IDS[piece]: "separator" for piece in ('"ok"', '"retry"', '"failed"')},
    "separator": {TOKEN_IDS[","]: "count_key"},
    "count_key": {TOKEN_IDS['"count":']: "count_first"},
    "count_first": {TOKEN_IDS[str(digit)]: "count_tail" for digit in range(10)},
    "count_tail": {**{TOKEN_IDS[str(digit)]: "count_tail" for digit in range(10)}, TOKEN_IDS["}"]: "complete"},
    "complete": {EOS_ID: "complete"},
}


@dataclass
class State:
    phase: str = "start"


class JsonGrammar:
    eos_id = EOS_ID

    def initial_state(self):
        """Return a fresh mutable record at the start of an object."""
        return State()

    def allowed_tokens(self, state):
        """Return a Boolean mask of shape [256] for the whole next piece."""
        mask = torch.zeros(VOCAB_SIZE, dtype=torch.bool)
        mask[list(TRANSITIONS[state.phase])] = True
        return mask

    def advance(self, state, token_id):
        """Consume an allowed token in place and return the same record."""
        state.phase = TRANSITIONS[state.phase].get(int(token_id), state.phase)
        return state

    def is_accepting(self, state):
        """Whether an object is complete and EOS is legal."""
        return state.phase == "complete"
