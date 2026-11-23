import csv
import json
import sys
from pathlib import Path

import numpy as np


def logs(path):
    with path.open() as handle:
        return [(float(row["time_s"]), row["event"], int(row["people_in_flat"]))
                for row in csv.DictReader(handle)]


def observations(path):
    series = {}
    last = {}
    with path.open() as handle:
        for line in handle:
            row = json.loads(line)
            for entry in row["bss"]:
                address = entry["bssid"]
                if last.get(address) != entry["host_timestamp"]:
                    series.setdefault(address, []).append((row["t"], entry["rssi_dbm"]))
                    last[address] = entry["host_timestamp"]
    return {address: np.asarray(values) for address, values in series.items()}


def main():
    source = Path("/data/train")
    addresses = None
    effects = {}
    increments = {}
    for path in sorted(source.glob("*.jsonl")):
        events = logs(path.with_suffix(".log.csv"))
        series = observations(path)
        persistent = {address for address, values in series.items() if len(values) > 300}
        addresses = persistent if addresses is None else addresses & persistent
        for address in sorted(persistent):
            values = series[address]
            for when, event, count in events:
                if event != "enter" or count != 1:
                    continue
                before = values[(values[:, 0] >= when - 120) & (values[:, 0] < when), 1]
                after = values[(values[:, 0] >= when + 20) & (values[:, 0] < when + 140), 1]
                if len(before) and len(after):
                    effects.setdefault(address, []).append(float(after.mean() - before.mean()))
            event_index = 0
            count = 0
            sitting = False
            occupied = np.zeros(len(values), dtype=bool)
            for index, when in enumerate(values[:, 0]):
                while event_index < len(events) and events[event_index][0] <= when:
                    event_time, event, count = events[event_index]
                    if event == "sit_start":
                        sitting = True
                    elif event == "sit_end":
                        sitting = False
                    event_index += 1
                occupied[index] = count > 0 and not sitting
            differences = np.abs(np.diff(values[:, 1]))
            walking = occupied[1:] & occupied[:-1]
            empty = ~occupied[1:] & ~occupied[:-1]
            moving_hist = np.bincount(differences[walking].astype(int), minlength=20)[:20]
            empty_hist = np.bincount(differences[empty].astype(int), minlength=20)[:20]
            noise = float(np.mean(np.minimum(differences[empty], 5) ** 2)) if empty.any() else np.inf
            increments.setdefault(address, []).append((noise, moving_hist, empty_hist))
    estimates = {address: float(np.median(effects[address])) for address in sorted(addresses)}
    selected = sorted(addresses, key=lambda address: (-abs(estimates[address]), address))[:26]
    separations = []
    for address in selected:
        noise, moving, empty = min(increments[address], key=lambda item: item[0])
        excess = np.maximum(moving / max(moving.sum(), 1) - empty / max(empty.sum(), 1), 0)[2:5]
        separation = float(np.dot(excess, np.arange(2, 5)) / excess.sum()) if excess.sum() else 3.0
        separations.append(float(np.clip(separation, 2.0, 3.5)))
    model = {"warmup_seconds": 240, "addresses": selected, "separations": separations,
             "signs": [1 if estimates[address] >= 0 else -1 for address in selected],
             "entry_hits": 3, "entry_channels": 2,
             "hold_hits": 3, "hold_channels": 2,
             "hold_seconds": 40}
    Path(sys.argv[1]).write_text(json.dumps(model))


if __name__ == "__main__":
    main()
