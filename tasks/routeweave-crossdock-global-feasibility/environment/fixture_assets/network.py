import json
import math
import random
import sys
from pathlib import Path

import pyarrow as arrow
import pyarrow.parquet as parquet


def materialize(manifest_path, destination):
    manifest = json.loads(Path(manifest_path).read_text())
    rng = random.Random(420014)
    rows = []
    for lane in manifest['lanes']:
        for band in manifest['bands']:
            rows.append({'edge_id': lane['id'], 'origin': lane['origin'], 'destination': lane['destination'],
                         'distance_km': lane['distance_km'], 'band_start': band['start'], 'band_end': band['end'],
                         'minutes': lane['minutes'] + band['delay']})
    points = manifest.get('regional_points', [])
    for origin in points:
        for destination_point in points:
            if origin['id'] == destination_point['id']:
                continue
            distance = round(math.hypot(origin['x'] - destination_point['x'], origin['y'] - destination_point['y']) * 1.17, 3)
            base = max(1, math.ceil(distance * 1.6))
            for band in manifest['bands']:
                rows.append({'edge_id': origin['id'] + ':' + destination_point['id'], 'origin': origin['id'],
                             'destination': destination_point['id'], 'distance_km': distance,
                             'band_start': band['start'], 'band_end': band['end'],
                             'minutes': base + band['delay'] + rng.randrange(4)})
    output = Path(destination)
    output.parent.mkdir(parents=True, exist_ok=True)
    parquet.write_table(arrow.Table.from_pylist(rows), output, compression='NONE', use_dictionary=False)


if __name__ == '__main__':
    materialize(sys.argv[1], sys.argv[2])
