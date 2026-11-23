import csv
import hashlib
import itertools
import struct

CHUNK = 1024 * 1024
TIME = 0x0821
DATE = 0x0221


def end_of(entry):
    return struct.unpack_from('<I', entry[5], 42)[0] + 30 + len(entry[0]) + len(entry[3]) + len(entry[4])


def local_record(entry, padding=0):
    name, method, local, extra, raw, central = entry
    crc, compressed, size = struct.unpack_from('<III', central, 16)
    return struct.pack('<IHHHHHIIIHH', 0x04034B50, 0, 0, method, TIME, DATE,
                       crc, compressed, size, len(name), padding) + name + bytes(padding) + raw


def directory_record(entry, offset):
    record = bytearray(entry[5])
    struct.pack_into('<HHHHHH', record, 4, 0, 0, 0, entry[1], TIME, DATE)
    struct.pack_into('<HI', record, 36, 0, 0)
    struct.pack_into('<I', record, 42, offset)
    return bytes(record)


def virtual_records(start, stop):
    while start < stop:
        remaining = stop - start
        length = remaining if remaining <= 65505 else 65475
        yield start, struct.pack('<IHHHHHIIIHH', 0x04034B50, 0, 0, 0, TIME, DATE,
                                 0, 0, 0, 0, length - 30) + bytes(length - 30)
        start += length


class Allocation:
    def __init__(self, previous, current, deleted, alignments):
        self.previous = {entry[0]: entry for entry in previous}
        self.current = current
        self.alignments = alignments
        self.offsets = {}
        self.paddings = {}
        self.free = []
        cursor = 0
        for entry in sorted(previous, key=lambda item: struct.unpack_from('<I', item[5], 42)[0]):
            start = struct.unpack_from('<I', entry[5], 42)[0]
            if cursor < start:
                self.free.append([cursor, start])
            cursor = end_of(entry)
        self.free.append([cursor, 2 ** 63 - 1])
        for name in deleted:
            if name not in current:
                self.evict(name)

    def copy(self):
        result = object.__new__(Allocation)
        result.previous = self.previous
        result.current = self.current
        result.alignments = self.alignments
        result.offsets = self.offsets.copy()
        result.paddings = self.paddings.copy()
        result.free = [zone.copy() for zone in self.free]
        return result

    def evict(self, name):
        entry = self.previous[name]
        start = struct.unpack_from('<I', entry[5], 42)[0]
        self.free.append([start, end_of(entry)])
        merged = []
        for start, stop in sorted(self.free):
            if merged and merged[-1][1] == start:
                merged[-1][1] = stop
            else:
                merged.append([start, stop])
        self.free = merged

    def transfer(self, name):
        if name in self.previous:
            self.evict(name)
        entry = self.current[name]
        header_size = 30 + len(name)
        alignment = self.alignments.get(name, 16384 if name.endswith(b'.so') else 4) if entry[1] == 0 else 0
        for zone in self.free:
            padding = (-(zone[0] + header_size)) % alignment if alignment else 0
            length = header_size + padding + len(entry[4])
            if zone[1] - zone[0] >= length + 30:
                self.offsets[name] = zone[0]
                self.paddings[name] = padding
                zone[0] += length
                return
        raise ValueError('No free range')

    def writes(self):
        for name, offset in self.offsets.items():
            yield offset, local_record(self.current[name], self.paddings[name])
        for start, stop in self.free[:-1]:
            yield from virtual_records(start, stop)

    def directory(self, previous, deleted, order):
        return b''.join(entry[5] for entry in previous if entry[0] not in deleted) + b''.join(
            directory_record(self.current[name], self.offsets[name]) for name in order)


def replay(previous_data, previous, current, deleted, order, alignments):
    state = Allocation(previous, current, deleted, alignments)
    for name in order:
        state.transfer(name)
    before = bytearray(previous_data[:min(state.free[-1][0], len(previous_data))])
    before.extend(bytes(state.free[-1][0] - len(before)))
    for offset, record in state.writes():
        before[offset:offset + len(record)] = record
    directory = state.directory(previous, deleted, order)
    count = len(previous) - len(deleted) + len(order)
    end = struct.pack('<IHHHHIIH', 0x06054B50, 0, 0, count, count, len(directory), len(before), 0)
    return bytes(before), directory, end, state.offsets


def read_events(path, current, transferred):
    with path.open() as stream:
        rows = list(csv.DictReader(line for line in stream if not line.startswith('#')))
    groups = []
    for timestamp, bucket in itertools.groupby(rows, key=lambda row: row['committed_at_utc']):
        names = []
        for row in bucket:
            name = row['archive_path'].encode()
            entry = current[name]
            if int(row['compressed_bytes']) != len(entry[4]) or int(row['compression_method']) != entry[1]:
                raise ValueError('Event metadata disagrees with APK')
            names.append(name)
        groups.append(names)
    if sorted(itertools.chain.from_iterable(groups)) != sorted(transferred):
        raise ValueError('Event paths disagree with the content delta')
    return groups


def chunk_digest(data):
    return hashlib.sha256(b'\xa5' + struct.pack('<I', len(data)) + data).digest()


def chunk_plan(state, start, stop, padding, excluded):
    records = tuple(sorted((offset, name, state.paddings[name])
                           for name, offset in state.offsets.items()
                           if name not in excluded and offset < stop
                           and offset + 30 + len(name) + state.paddings[name] + len(state.current[name][4]) > start))
    holes = tuple((lower, upper) for lower, upper in state.free[:-1] if lower < stop and upper > start)
    tail = state.free[-1][0]
    return (start, stop, records, holes, tail if tail < stop and tail + len(padding) > start else None)


def render_chunk(previous_data, current, padding, plan):
    start, stop, records, holes, tail = plan
    result = bytearray(previous_data[start:min(stop, len(previous_data))])
    result.extend(bytes(stop - start - len(result)))

    def overlay(offset, data):
        lower, upper = max(start, offset), min(stop, offset + len(data))
        if lower < upper:
            result[lower - start:upper - start] = data[lower - offset:upper - offset]

    for offset, name, extra_size in records:
        entry = current[name]
        header = local_record((entry[0], entry[1], entry[2], entry[3], b'', entry[5]), extra_size)
        overlay(offset, header)
        overlay(offset + len(header), entry[4])
    for lower, upper in holes:
        for offset, record in virtual_records(lower, upper):
            overlay(offset, record)
    if tail is not None:
        overlay(tail, padding)
    return bytes(result)


def search(previous_data, previous, current, deleted, groups, padding, target, exhaustive=False):
    from functools import lru_cache

    bursts = [group for group in groups if len(group) > 1]
    if len(bursts) != 2:
        raise ValueError('Expected two ambiguous commit bursts')
    first_index, second_index = [index for index, group in enumerate(groups) if len(group) > 1]
    prefix_order = list(itertools.chain.from_iterable(groups[:first_index]))
    middle_order = list(itertools.chain.from_iterable(groups[first_index + 1:second_index]))
    suffix_order = list(itertools.chain.from_iterable(groups[second_index + 1:]))
    order = list(itertools.chain.from_iterable(groups))
    models = [name for name in prefix_order if name.endswith(b'.tflite')]
    powers = [2 ** exponent for exponent in range(2, 15)]
    retained = b''.join(entry[5] for entry in previous if entry[0] not in deleted)
    variants = []
    seen = set()
    base_prefix = None
    variable_indices = None
    static_chunks = {}
    for pair in itertools.product(powers, repeat=len(models)):
        prefix = Allocation(previous, current, deleted, dict(zip(models, pair)))
        for name in prefix_order:
            prefix.transfer(name)
        identity = (tuple(sorted(prefix.offsets.items())), tuple(sorted(prefix.paddings.items())), tuple(map(tuple, prefix.free)))
        if identity in seen:
            continue
        seen.add(identity)
        if base_prefix is None:
            base_prefix = prefix
            regions = list(prefix.free[:-1])
            for name in deleted:
                if name not in prefix_order and name in prefix.previous:
                    entry = prefix.previous[name]
                    regions.append((struct.unpack_from('<I', entry[5], 42)[0], end_of(entry)))
            variable_indices = sorted({index for lower, upper in regions
                                       for index in range(lower // CHUNK, (upper - 1) // CHUNK + 1)})
        if prefix.free[:-1] != base_prefix.free[:-1]:
            raise ValueError('Alignment changes the finite allocation state')
        for index in variable_indices:
            start, stop = index * CHUNK, (index + 1) * CHUNK
            if chunk_plan(prefix, start, stop, padding, set()) != chunk_plan(base_prefix, start, stop, padding, set()):
                raise ValueError('Alignment changes a history-dependent byte region')
        state = prefix.copy()
        for name in order[len(prefix_order):]:
            state.transfer(name)
        if state.free[-1][0] != prefix.free[-1][0]:
            raise ValueError('History transfers extend the append region')
        total_size = state.free[-1][0] + len(padding)
        hashes = []
        for index, start in enumerate(range(0, total_size, CHUNK)):
            if index in variable_indices:
                hashes.append(None)
            else:
                plan = chunk_plan(state, start, min(total_size, start + CHUNK), padding, set())
                if plan not in static_chunks:
                    static_chunks[plan] = chunk_digest(render_chunk(previous_data, current, padding, plan))
                hashes.append(static_chunks[plan])
        directory_prefix = retained + b''.join(directory_record(current[name], prefix.offsets[name]) for name in prefix_order)
        directory_size = len(retained) + sum(len(current[name][5]) for name in order)
        count = len(previous) - len(deleted) + len(order)
        end = struct.pack('<IHHHHIIH', 0x06054B50, 0, 0, count, count, directory_size, total_size, 0)
        cd_prefix = hashlib.sha256(b'\xa5' + struct.pack('<I', directory_size) + directory_prefix)
        overall_prefix = hashlib.sha256(b'\x5a' + struct.pack('<I', len(hashes) + 2))
        segments = []
        cursor = 0
        for index in variable_indices:
            segments.append(b''.join(hashes[cursor:index]))
            cursor = index + 1
        segments.append(b''.join(hashes[cursor:]))
        variants.append((pair, cd_prefix, overall_prefix, segments, chunk_digest(end)))
    print(f'Alignment search: {len(powers) ** len(models)} pairs, {len(variants)} distinct layouts; '
          f'history-dependent content chunks={variable_indices}', flush=True)

    @lru_cache(maxsize=8192)
    def cached_chunk(plan):
        return chunk_digest(render_chunk(previous_data, current, padding, plan))

    matches = []
    history_count = 0
    for first in itertools.permutations(bursts[0]):
        after_first = base_prefix.copy()
        for name in first + tuple(middle_order):
            after_first.transfer(name)
        for second in itertools.permutations(bursts[1]):
            state = after_first.copy()
            for name in second + tuple(suffix_order):
                state.transfer(name)
            if state.free[-1][0] != base_prefix.free[-1][0]:
                raise ValueError('Candidate history changes append placement')
            hashes = [cached_chunk(chunk_plan(state, index * CHUNK, (index + 1) * CHUNK, padding, set()))
                      for index in variable_indices]
            dynamic_order = list(first) + middle_order + list(second) + suffix_order
            directory_suffix = b''.join(directory_record(current[name], state.offsets[name]) for name in dynamic_order)
            history_count += 1
            for pair, cd_prefix, overall_prefix, segments, end_hash in variants:
                cd = cd_prefix.copy()
                cd.update(directory_suffix)
                overall = overall_prefix.copy()
                for segment, digest in zip(segments, hashes):
                    overall.update(segment)
                    overall.update(digest)
                overall.update(segments[-1])
                overall.update(cd.digest() + end_hash)
                if overall.digest() == target:
                    sequence = prefix_order + dynamic_order
                    matches.append((pair, sequence))
                    print(f'Authenticated layout: models={pair}; order={sequence!r}', flush=True)
                    if not exhaustive:
                        return pair, sequence
        if history_count % 7200 == 0:
            print(f'History search: {history_count}/86400 orders', flush=True)
    print(f'History search: {history_count} orders, {len(variants)} distinct alignment layouts, '
          f'{history_count * len(variants)} distinct layouts, {len(matches)} authenticated layouts', flush=True)
    if len(matches) != 1:
        raise RuntimeError(f'Expected one authenticated layout, found {len(matches)}')
    return matches[0]
