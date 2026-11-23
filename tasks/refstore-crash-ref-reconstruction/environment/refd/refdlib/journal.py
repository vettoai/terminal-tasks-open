import json


def entries(path):
    if path.exists():
        for line in path.read_bytes().split(b"\n")[:-1]:
            yield json.loads(line)


def sends(root):
    for client in ("gate", "merge", "deploy"):
        for entry in entries(root / "journal" / (client + ".jsonl")):
            if entry["line"] == "send":
                yield entry
