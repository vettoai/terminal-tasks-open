"""Small causal decoder used for CPU inference.

Input IDs have shape [1, T]; forward returns logits [1, T, 256]. Row j
predicts the token following input_ids[0, j]. Prefix calls and a longer
causally masked call have the same conditionals. There is no KV cache.
Inference uses eval mode, with no dropout.
"""

import torch
from torch import nn


class Decoder(nn.Module):
    def __init__(self, layers, width=128, heads=4, feedforward=512, capacity=256, vocab_size=256):
        super().__init__()
        self.config = dict(layers=layers, width=width, heads=heads, feedforward=feedforward, capacity=capacity, vocab_size=vocab_size)
        self.embedding = nn.Embedding(vocab_size, width)
        self.position = nn.Embedding(capacity, width)
        self.blocks = nn.ModuleList([
            nn.TransformerEncoderLayer(width, heads, feedforward, dropout=0.0, batch_first=True, norm_first=True)
            for _ in range(layers)
        ])
        self.norm = nn.LayerNorm(width)
        self.output = nn.Linear(width, vocab_size, bias=False)

    def forward(self, input_ids):
        """Return every causal next-token row, without persisting model state."""
        length = input_ids.shape[1]
        hidden = self.embedding(input_ids) + self.position(torch.arange(length, device=input_ids.device))
        causal_mask = torch.ones(length, length, dtype=torch.bool, device=input_ids.device).triu(1)
        for block in self.blocks:
            hidden = block(hidden, src_mask=causal_mask)
        return self.output(self.norm(hidden))


def load_model(path):
    """Load architecture metadata and float32 inference weights on the CPU."""
    checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    model = Decoder(**checkpoint["config"])
    model.load_state_dict(checkpoint["state_dict"])
    return model.eval()
