import csv
import gzip
import io
import signal
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from cassandra.query import SimpleStatement
import config


class DailyExport:
    def __init__(self, session, objects, queue):
        self.session = session
        self.objects = objects
        self.queue = queue
        self.upload = None
        self.key = None
        signal.signal(signal.SIGTERM, self.terminate)

    def terminate(self, signum, frame):
        if self.upload is not None:
            self.upload.close()
            self.queue.send(self.key)
        raise SystemExit(0)

    def run(self, day=None):
        day = day or (datetime.now(ZoneInfo('America/Sao_Paulo')).date()
                      - timedelta(days=1))
        query = SimpleStatement(
            'SELECT day,bucket,event_ts,pix_id,account,payer_doc_type,pix_type,'
            'amount_cents FROM pix_credit WHERE day=%s AND bucket=%s '
            'ORDER BY event_ts ASC,pix_id ASC', fetch_size=config.FETCH_SIZE)
        for bucket in range(config.BUCKET_COUNT):
            result = self.session.execute(query, (day, bucket))
            page_index = 0
            while True:
                self.key = f'{day}/{bucket}/{page_index}'
                self.upload = self.objects.writer(self.key)
                compressed = gzip.GzipFile(fileobj=self.upload, mode='wb')
                text = io.TextIOWrapper(compressed, encoding='utf-8', newline='')
                writer = csv.writer(text, lineterminator='\n')
                for row in result.current_rows:
                    writer.writerow([getattr(row, field) for field in config.CSV_FIELDS])
                    text.flush()
                    compressed.flush()
                text.flush()
                text.detach()
                compressed.close()
                self.upload.close()
                self.upload = None
                self.queue.send(self.key)
                page_index += 1
                if not result.has_more_pages:
                    break
                result.fetch_next_page()
