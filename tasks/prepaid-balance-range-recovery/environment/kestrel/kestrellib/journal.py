"""Readers for channel journals, shop sales and sent text receipts."""
import json
from pathlib import Path


def read_journal(incident, channel):
    """A channel's journal entries."""
    path = Path(incident, "journal", channel + ".jsonl")
    text = path.read_text(encoding="utf-8")
    pieces = text.split("\n")
    return [json.loads(line) for line in pieces if line]


def read_sales(incident):
    """Requests in the shops' sales export."""
    text = Path(incident, "dealer", "sales.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line]


def read_messages(incident):
    """Receipts recorded by the notifier."""
    text = Path(incident, "notify", "sent.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line]
