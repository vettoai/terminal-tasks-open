import zlib

CASSANDRA_HOSTS = ['127.0.0.1']
CASSANDRA_PORT = 9042
BUCKET_COUNT = 4
FETCH_SIZE = 250
STAGING_BATCH_SIZE = 32
CPF_MIN_CENTS = 337500
CPF_MIN_COUNT = 30
QUEUE_MAX_RECEIVES = 5
QUEUE_DEAD_LETTER = 'dimp-parts-dlq'
CSV_FIELDS = ('day', 'bucket', 'event_ts', 'pix_id', 'account',
              'payer_doc_type', 'pix_type', 'amount_cents')

# Credits are append-only. The amount cell write timestamp is receipt time.
def bucket_for(pix_id):
    return zlib.crc32(pix_id.encode('ascii')) % BUCKET_COUNT
