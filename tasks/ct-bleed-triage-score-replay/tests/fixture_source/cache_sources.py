import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from source import load_source


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('manifest', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--workers', type=int, default=10)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    def cache_source(entry):
        datasets, pixels = load_source(entry)
        metadata = []
        for dataset in datasets:
            if 'PixelData' in dataset:
                del dataset.PixelData
            metadata.append(dataset.to_json())
        np.savez_compressed(args.output / f"case-{entry['case']}.npz", pixels=pixels,
                            metadata=np.frombuffer(json.dumps(metadata).encode(), dtype=np.uint8))
        print('Cached clinical source', entry['case'], flush=True)

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        list(executor.map(cache_source, json.loads(args.manifest.read_text())['sources']))


if __name__ == '__main__':
    main()
