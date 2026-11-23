"""Packed CPU sampling of a status-record continuation."""

import torch

from generate import target_generate
from grammar import JsonGrammar
from sampling import QuantileSampler
from table_model import TableModel
from tokenizer import EOS_ID, TOKEN_IDS, encode


def test_packed_status_prefill():
    prompt = encode('{"status":')
    tokens = TOKEN_IDS

    def logits(masses):
        row = torch.full((256,), -torch.inf, dtype=torch.float64)
        for token, mass in masses.items():
            row[token] = torch.log(torch.tensor(mass, dtype=torch.float64))
        return row

    head = logits({tokens['"ok"']: 0.46, tokens['"retry"']: 0.35, tokens['"failed"']: 0.19})
    table = {tuple(prompt): head}
    for status in ('"ok"', '"retry"', '"failed"'):
        prefix = prompt + [tokens[status]]
        for token in (tokens[','], tokens['"count":'], tokens['3'], tokens['}'], EOS_ID):
            table[tuple(prefix)] = logits({token: 1.0})
            prefix.append(token)
    output = target_generate(TableModel(table, default_logits=head), JsonGrammar(), prompt,
                             temperature=1.0, top_p=1.0, max_new_tokens=6,
                             sampler=QuantileSampler(6827))
    grammar = JsonGrammar()
    state = grammar.initial_state()
    for token in prompt[1:] + output:
        assert grammar.allowed_tokens(state)[token]
        state = grammar.advance(state, token)
    assert len(output) == 6 and output[-1] == EOS_ID
    assert grammar.is_accepting(state)
