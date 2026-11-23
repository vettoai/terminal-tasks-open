import struct

from bson import BSON, Int64

MAGIC = struct.pack('<I', 0x8199E26D)
END = b'\xff' * 4
MASK = (1 << 64) - 1


def crc_table():
    table = []
    for value in range(256):
        for unused in range(8):
            value = (value >> 1) ^ (0xC96C5795D7870F42 if value & 1 else 0)
        table.append(value)
    return table


TABLE = crc_table()


def bson_elements(raw):
    if len(raw) < 5 or struct.unpack_from('<i', raw)[0] != len(raw) or raw[-1] != 0:
        raise ValueError('invalid BSON envelope')
    offset = 4
    fixed = {1: 8, 7: 12, 8: 1, 9: 8, 10: 0, 16: 4, 17: 8, 18: 8, 19: 16}
    while offset < len(raw) - 1:
        start = offset
        kind = raw[offset]
        name_end = raw.index(0, offset + 1)
        name = raw[offset + 1:name_end].decode('utf-8')
        value = name_end + 1
        if kind in fixed:
            ending = value + fixed[kind]
        elif kind in (3, 4):
            size = struct.unpack_from('<i', raw, value)[0]
            if size < 5:
                raise ValueError('invalid BSON subdocument length')
            ending = value + size
        elif kind in (2, 5):
            size = struct.unpack_from('<i', raw, value)[0]
            if size < (1 if kind == 2 else 0):
                raise ValueError('invalid BSON value length')
            ending = value + 4 + size + (1 if kind == 5 else 0)
        else:
            raise ValueError('unsupported BSON element type')
        if ending > len(raw) - 1:
            raise ValueError('BSON element exceeds envelope')
        yield name, kind, start, value, ending
        offset = ending
    if offset != len(raw) - 1:
        raise ValueError('invalid BSON element boundary')


def crc64(data, previous=0):
    value = previous ^ MASK
    for byte in data:
        value = TABLE[(value ^ byte) & 255] ^ (value >> 8)
    return value ^ MASK


def header(namespace, eof=False, checksum=0):
    database, collection = namespace.split('.', 1)
    signed = checksum if checksum < 1 << 63 else checksum - (1 << 64)
    return BSON.encode({'db': database, 'collection': collection,
                        'EOF': eof, 'CRC': Int64(signed)})


def records(data, offset=0):
    while offset < len(data):
        size = struct.unpack_from('<i', data, offset)[0]
        if size < 5 or offset + size > len(data):
            raise ValueError(f'incomplete BSON at {offset}')
        raw = data[offset:offset + size]
        BSON(raw).decode()
        yield raw
        offset += size


def read_dump(path):
    data = path.read_bytes()
    if data[:4] != MAGIC:
        raise ValueError('archive magic')
    offset = 4
    prelude = []
    while data[offset:offset + 4] != END:
        size = struct.unpack_from('<i', data, offset)[0]
        prelude.append(BSON(data[offset:offset + size]).decode())
        offset += size
    offset += 4
    documents = {}
    while offset < len(data):
        size = struct.unpack_from('<i', data, offset)[0]
        block_header = BSON(data[offset:offset + size]).decode()
        offset += size
        namespace = block_header['db'] + '.' + block_header['collection']
        collection = documents.setdefault(namespace, [])
        while data[offset:offset + 4] != END:
            size = struct.unpack_from('<i', data, offset)[0]
            collection.append(data[offset:offset + size])
            offset += size
        offset += 4
    return prelude, documents
