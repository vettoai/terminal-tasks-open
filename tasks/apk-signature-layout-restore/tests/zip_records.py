from dataclasses import dataclass
from pathlib import Path
import struct


@dataclass(frozen=True)
class Entry:
    name: bytes
    method: int
    crc: int
    compressed_size: int
    size: int
    local_offset: int
    data_offset: int
    timestamp: int
    date: int
    extra_offset: int
    extra_length: int


class Archive:
    def __init__(self, path):
        self.path = Path(path)
        self.length = self.path.stat().st_size
        self.entries = {}
        with self.path.open('rb') as stream:
            tail_length = min(self.length, 65557)
            stream.seek(self.length - tail_length)
            tail = stream.read(tail_length)
            marker = tail.rfind(b'PK\x05\x06')
            if marker < 0 or marker + 22 > len(tail):
                raise ValueError('Missing ZIP end record')
            signature, disk, central_disk, disk_count, count, central_length, central_offset, comment_length = struct.unpack_from('<IHHHHIIH', tail, marker)
            if disk or central_disk or disk_count != count:
                raise ValueError('Unsupported multipart ZIP')
            end_offset = self.length - tail_length + marker
            if marker + 22 + comment_length != len(tail) or central_offset + central_length > end_offset:
                raise ValueError('Invalid ZIP directory bounds')
            if count > central_length // 46:
                raise ValueError('Entry count exceeds possible directory records')
            cursor = central_offset
            central_end = central_offset + central_length
            for index in range(count):
                header = self._read(stream, cursor, 46, central_end)
                fields = struct.unpack('<IHHHHHHIIIHHHHHII', header)
                if fields[0] != 0x02014B50:
                    raise ValueError('Invalid central record signature')
                method, crc, compressed_size, size = fields[4], fields[7], fields[8], fields[9]
                name_length, extra_length, note_length = fields[10:13]
                local_offset = fields[16]
                record_length = 46 + name_length + extra_length + note_length
                self._bounds(cursor, record_length, central_end)
                name = self._read(stream, cursor + 46, name_length, central_end)
                if name in self.entries:
                    raise ValueError('Duplicate entry name')
                local = struct.unpack('<IHHHHHIIIHH', self._read(stream, local_offset, 30, central_offset))
                if local[0] != 0x04034B50:
                    raise ValueError('Invalid local record signature')
                local_name_length, local_extra_length = local[-2:]
                local_name = self._read(stream, local_offset + 30, local_name_length, central_offset)
                if name != local_name:
                    raise ValueError('Local and central names differ')
                extra_offset = local_offset + 30 + local_name_length
                self._bounds(extra_offset, local_extra_length, central_offset)
                data_offset = local_offset + 30 + local_name_length + local_extra_length
                self._bounds(data_offset, compressed_size, central_offset)
                self.entries[name] = Entry(name, method, crc, compressed_size, size, local_offset,
                                           data_offset, local[4], local[5], extra_offset, local_extra_length)
                cursor += record_length
            if cursor != central_end:
                raise ValueError('Central directory length mismatch')

    def read_extra(self, entry):
        with self.path.open('rb') as stream:
            return self._read(stream, entry.extra_offset, entry.extra_length, self.length)

    @staticmethod
    def _bounds(offset, length, limit):
        if offset < 0 or length < 0 or offset > limit or length > limit - offset:
            raise ValueError('ZIP record exceeds file bounds')

    @classmethod
    def _read(cls, stream, offset, length, limit):
        cls._bounds(offset, length, limit)
        stream.seek(offset)
        data = stream.read(length)
        if len(data) != length:
            raise ValueError('Truncated ZIP record')
        return data


def same_payload(first_path, first, second_path, second):
    if first.compressed_size != second.compressed_size:
        return False
    remaining = first.compressed_size
    with Path(first_path).open('rb') as left, Path(second_path).open('rb') as right:
        left.seek(first.data_offset)
        right.seek(second.data_offset)
        while remaining:
            length = min(remaining, 1024 * 1024)
            left_bytes, right_bytes = left.read(length), right.read(length)
            if len(left_bytes) != length or left_bytes != right_bytes:
                return False
            remaining -= length
    return True
