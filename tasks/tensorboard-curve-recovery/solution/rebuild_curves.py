import csv
from itertools import chain
from math import gcd
from pathlib import Path
import struct
import sys

import crc32c
from google.protobuf.message import DecodeError
from tensorboard.compat.proto import event_pb2


TAGS = {"train/loss", "train/lr", "train/grad_norm", "eval/accuracy"}


def masked_crc(data):
    checksum = crc32c.crc32c(data)
    return (((checksum >> 15) | (checksum << 17)) + 0xA282EAD8) & 0xFFFFFFFF


def read_frames(path):
    data = path.read_bytes()
    position = 0
    frames = []
    while position + 16 <= len(data):
        length_bytes = data[position:position + 8]
        length = struct.unpack("<Q", length_bytes)[0]
        if length > len(data) - position - 16:
            position += 1
            continue
        expected_length_crc = struct.unpack_from("<I", data, position + 8)[0]
        if masked_crc(length_bytes) != expected_length_crc:
            position += 1
            continue
        payload_end = position + 12 + length
        payload = data[position + 12:payload_end]
        expected_payload_crc = struct.unpack_from("<I", data, payload_end)[0]
        if masked_crc(payload) != expected_payload_crc:
            position += 1
            continue
        end = payload_end + 4
        try:
            event = event_pb2.Event.FromString(payload)
        except DecodeError:
            event = None
        frames.append((position, end, event))
        position = end
    return frames


def replay_interval(frames):
    gaps = [(left[1], right[0]) for left, right in zip(frames, frames[1:]) if left[1] < right[0]]
    if len(gaps) != 2 or frames[0][0] != 0:
        return None
    left, right = gaps
    candidates = []
    for start in range(((left[0] + 4095) // 4096) * 4096, left[1] + 1, 4096):
        if right[0] <= start + 4096 <= right[1]:
            candidates.append((start, start + 4096))
    return candidates[0] if len(candidates) == 1 else None


def read_events(path):
    frames = read_frames(path)
    replay = replay_interval(frames)
    for start, end, event in frames:
        if event is None:
            continue
        if replay is not None and replay[0] <= start and end <= replay[1]:
            continue
        yield event


def logical_attempts(paths):
    events = []
    fragments = []
    restored_step = None
    for path in paths:
        fragments.append(path)
        for event in read_events(path):
            if event.HasField("session_log") and event.session_log.status == event_pb2.SessionLog.START:
                if events:
                    yield fragments, events, restored_step
                events = []
                fragments = [path]
                restored_step = event.step
            events.append(event)
    if events:
        yield fragments, events, restored_step


def read_attempt(paths, events=None):
    last_step = 0
    rows = {}
    event_stream = events if events is not None else chain.from_iterable(read_events(path) for path in paths)
    for event in event_stream:
        if not event.HasField("summary"):
            continue
        accepted = False
        for scalar in event.summary.value:
            if scalar.tag not in TAGS:
                continue
            if scalar.tag != "eval/accuracy" and event.step < last_step:
                continue
            if scalar.HasField("simple_value"):
                value = scalar.simple_value
            elif scalar.HasField("tensor") and scalar.tensor.dtype == 1 and len(scalar.tensor.tensor_content) == 4:
                value = struct.unpack("<f", scalar.tensor.tensor_content)[0]
            else:
                continue
            rows[scalar.tag, event.step] = value
            accepted = accepted or scalar.tag != "eval/accuracy"
        if accepted:
            last_step = event.step
    if not rows or not any(tag != "train/loss" for tag, step in rows):
        return None
    steps = [step for tag, step in rows]
    return min(steps), max(steps), rows


def attempt_start(paths, rows, checkpoint):
    training = [step for tag, step in rows if tag.startswith("train/")]
    first = min(training)
    frames = read_frames(paths[0])
    if frames[0][0] == 0:
        return first
    first_loss = min(step for tag, step in rows if tag == "train/loss")
    candidates = [step for step in range(1, first + 1, checkpoint) if (first_loss - step) * 16 <= frames[0][0]]
    if len(candidates) != 1:
        raise ValueError("Cannot identify the checkpoint preceding the missing prefix")
    return candidates[0]


def checkpoint_steps(paths, events=None):
    return {
        event.step
        for event in (events if events is not None else chain.from_iterable(read_events(path) for path in paths))
        if event.HasField("session_log") and event.session_log.status == event_pb2.SessionLog.CHECKPOINT
    }


def select_lineage(attempts):
    if not any(saved for first, last, rows, saved in attempts):
        return sorted(((first, last, rows) for first, last, rows, saved in attempts), key=lambda attempt: (attempt[0], attempt[1]))
    current = max(attempts, key=lambda attempt: attempt[1])
    lineage = [current]
    while current[0] > 1:
        loaded = current[0] - 1
        parents = [attempt for attempt in attempts if attempt[0] <= loaded <= attempt[1] and loaded in attempt[3]]
        if len(parents) != 1:
            raise ValueError("Cannot identify the producer of the loaded checkpoint")
        current = parents[0]
        lineage.append(current)
    return [(first, last, rows) for first, last, rows, saved in reversed(lineage)]


def process_lifetimes(fragments):
    lifetime = []
    counters = set()
    for fragment in sorted(fragments):
        counter = fragment[1]
        if counter in counters:
            yield [path for timestamp, counter, path in sorted(lifetime, key=lambda item: item[1])]
            lifetime = []
            counters = set()
        lifetime.append(fragment)
        counters.add(counter)
    if lifetime:
        yield [path for timestamp, counter, path in sorted(lifetime, key=lambda item: item[1])]


def rebuild(project, output):
    output.mkdir(parents=True, exist_ok=True)
    for directory in sorted((project / "runs").iterdir()):
        if not directory.is_dir():
            continue
        attempts = []
        processes = {}
        for path in sorted(directory.iterdir()):
            timestamp, host, pid, counter = path.name.removeprefix("events.out.tfevents.").removesuffix(".v2").rsplit(".", 3)
            processes.setdefault((host, pid), []).append((int(timestamp), int(counter), path))
        for fragments in processes.values():
            for paths in process_lifetimes(fragments):
                for fragments, events, restored_step in logical_attempts(paths):
                    attempt = read_attempt(fragments, events)
                    if attempt is not None:
                        attempts.append((fragments, events, restored_step, attempt))
        final_step = max(attempt[1] for paths, events, restored, attempt in attempts)
        checkpoint = gcd(*(step for paths, events, restored, attempt in attempts for tag, step in attempt[2] if tag == "eval/accuracy" and step < final_step))
        attempts = [(restored if restored is not None else attempt_start(paths, rows, checkpoint), last, rows, checkpoint_steps(paths, events)) for paths, events, restored, (first, last, rows) in attempts]
        attempts = select_lineage(attempts)
        history = {}
        for index, (first, last, rows) in enumerate(attempts):
            next_first = attempts[index + 1][0] if index + 1 < len(attempts) else last + 1
            for (tag, step), value in rows.items():
                if first <= step < next_first:
                    history[tag, step] = value
        with (output / (directory.name + ".csv")).open("w", newline="") as stream:
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(("tag", "step", "value"))
            for (tag, step), value in sorted(history.items()):
                writer.writerow((tag, step, format(value, ".9g")))


if __name__ == "__main__":
    rebuild(Path(sys.argv[1]), Path(sys.argv[2]))
