"""Prefix-keyed fixed logits for small inference experiments.

TableModel accepts complete input prefixes, including BOS. Each table row
predicts the next token, with negative infinity denoting zero mass. Forward
returns all causal rows [1, T, 256], using the row for each prefix in turn.
Each reachable sampling context must have positive allowed mass. A default
row can represent contexts outside the supplied table.
"""

import torch


class TableModel:
    def __init__(self, tables, default_logits=None):
        self.tables = {tuple(prefix): torch.as_tensor(row, dtype=torch.float64) for prefix, row in tables.items()}
        self.default_logits = torch.zeros(256, dtype=torch.float64) if default_logits is None else torch.as_tensor(default_logits, dtype=torch.float64)

    def __call__(self, input_ids):
        prefix = input_ids[0].tolist()
        return torch.stack([self.tables.get(tuple(prefix[:position]), self.default_logits) for position in range(1, len(prefix) + 1)]).unsqueeze(0)
