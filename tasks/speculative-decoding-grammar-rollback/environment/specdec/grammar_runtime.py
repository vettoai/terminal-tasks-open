"""Table-backed finite-state matcher for token-piece grammars."""

import torch

from tokenizer import EOS_ID, VOCAB_SIZE


class CursorGrammar:
    """Traverse transition rows using matcher-owned cursors.

    Each row maps token IDs to destination row indices. State handles identify
    traversals rather than graph nodes; their positions belong to this matcher.
    The Boolean mask workspace is borrowed until the next allowed_tokens call.
    """

    def __init__(self, transitions, accepting, eos_id=EOS_ID):
        self.transitions = [dict(row) for row in transitions]
        self.accepting = set(accepting)
        self.eos_id = eos_id
        self.positions = {}
        self.next_handle = 1
        self.workspace = torch.zeros(VOCAB_SIZE, dtype=torch.bool)

    def initial_state(self):
        """Allocate a fresh independent traversal at the initial row."""
        handle = self.next_handle
        self.next_handle += 1
        self.positions[handle] = 0
        return handle

    def allowed_tokens(self, state):
        """Fill and lend the matcher workspace for this cursor's next piece."""
        self.workspace.zero_()
        self.workspace[list(self.transitions[self.positions[state]])] = True
        return self.workspace

    def advance(self, state, token_id):
        """Consume an allowed whole piece and return the updated cursor handle."""
        self.positions[state] = self.transitions[self.positions[state]][int(token_id)]
        return state

    def is_accepting(self, state):
        """Whether this cursor's row permits record completion."""
        return self.positions[state] in self.accepting
