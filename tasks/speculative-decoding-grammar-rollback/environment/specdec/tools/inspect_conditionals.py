"""Inspect CPU model rows and scoring for saved generation request windows.

Capture records contain trace_id, prompt_ids, draft_ids, temperature and top_p.
Each JSON output row reports the complete-window versus prefix logit difference,
allowed entry weights, and the selected nucleus in descending scoring order.
"""

import argparse
import json
from pathlib import Path
import sys

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from generate import prompt_state
from grammar import JsonGrammar
from model import load_model
from sampling import probabilities
from tokenizer import BOS_ID


def inspect_request(model, record):
    prompt = record['prompt_ids']
    drafts = record['draft_ids']
    if not prompt or prompt[0] != BOS_ID or len(drafts) > 4:
        raise ValueError('Expected a BOS prompt and a window of at most four tokens')
    grammar = JsonGrammar()
    state = prompt_state(grammar, prompt)
    context = prompt + drafts
    window = model(torch.tensor([context], dtype=torch.long))[0]
    for position in range(len(prompt) - 1, len(context)):
        prefix = context[:position + 1]
        ordinary = model(torch.tensor([prefix], dtype=torch.long))[0, -1]
        mask = grammar.allowed_tokens(state).clone()
        observations = {}
        for name, logits in (('window', window[position]), ('prefix', ordinary)):
            entries = probabilities(logits, mask, record['temperature'], 1.0)
            selected = probabilities(logits, mask, record['temperature'], record['top_p'])
            order = torch.argsort(entries, descending=True, stable=True).tolist()
            running = 0.0
            nucleus = []
            for token in order:
                if selected[token] > 0:
                    running += float(entries[token])
                    nucleus.append({'token_id': token, 'entry_weight': float(entries[token]),
                                    'cumulative_weight': running, 'selected_weight': float(selected[token])})
            observations[name] = {
                'allowed_logits': {str(token): float(logits[token]) for token in torch.where(mask)[0].tolist()},
                'allowed_weights': {str(token): float(entries[token]) for token in torch.where(mask)[0].tolist()},
                'nucleus': nucleus,
            }
        print(json.dumps({'trace_id': record['trace_id'], 'position': position, 'prefix_ids': prefix,
                          'raw_logit_differences': (window[position] - ordinary).tolist(),
                          'maximum_logit_difference': float((window[position] - ordinary).abs().max()),
                          'scoring': observations}, allow_nan=False))
        if position + 1 < len(context):
            token = context[position + 1]
            if not mask[token]:
                raise ValueError('Request continuation is outside the record grammar')
            state = grammar.advance(state, token)
            if token == grammar.eos_id:
                break


def main():
    parser = argparse.ArgumentParser(description='Replay saved CPU request windows and print row/scoring observations.')
    parser.add_argument('--checkpoint', type=Path, required=True, help='Compatible evaluation snapshot')
    parser.add_argument('--capture', type=Path, required=True, help='JSONL request capture')
    arguments = parser.parse_args()
    torch.set_num_threads(1)
    model = load_model(arguments.checkpoint).eval()
    with torch.inference_mode(), arguments.capture.open() as capture:
        for line in capture:
            if line.strip():
                inspect_request(model, json.loads(line))


if __name__ == '__main__':
    main()
