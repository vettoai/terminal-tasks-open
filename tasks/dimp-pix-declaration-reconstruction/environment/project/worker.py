import csv
import io
import zlib
from itertools import islice

import config


def complete_records(chunks):
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    pending = b''
    for chunk in chunks:
        pending += decoder.decompress(chunk)
        lines = pending.split(b'\n')
        pending = lines.pop()
        for line in lines:
            yield next(csv.reader(io.StringIO(line.decode('utf-8'))))


def record_batches(records):
    records = iter(records)
    while batch := list(islice(records, config.STAGING_BATCH_SIZE)):
        yield batch


def consume(queue, objects, staging):
    queue.configure(max_receives=config.QUEUE_MAX_RECEIVES,
                    dead_letter=config.QUEUE_DEAD_LETTER)
    for message in queue.receive():
        try:
            records = complete_records(objects.chunks(message.body))
            for batch in record_batches(records):
                with staging.transaction():
                    for fields in batch:
                        row = dict(zip(config.CSV_FIELDS, fields))
                        row['bucket'] = int(row['bucket'])
                        row['amount_cents'] = int(row['amount_cents'])
                        staging.append(row)
            queue.ack(message)
        except Exception:
            queue.retry(message)
