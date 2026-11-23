import argparse
from datetime import datetime, timezone
import json
import time

import numpy as np
from PIL import Image
import torch

from frame_model import image_score, make_network


def main():
    parser = argparse.ArgumentParser(description='Steel inspection; confidence is fracture probability.')
    parser.add_argument('--target', required=True)
    parser.add_argument('--output-json', action='store_true')
    parser.add_argument('--model', default='/opt/vision/model.pt')
    args = parser.parse_args()
    started = time.perf_counter()
    torch.set_num_threads(1)
    checkpoint = torch.load(args.model, map_location='cpu', weights_only=True)
    network = make_network()
    network.load_state_dict(checkpoint['state_dict'])
    network.eval()
    with Image.open(args.target) as source:
        image = np.asarray(source.convert('RGB'))
    height, width = image.shape[:2]
    calibration = checkpoint['calibration'][f'{width}x{height}']
    score = image_score(network, image)
    probability = float(1 / (1 + np.exp(-np.clip(
        (score - calibration['offset']) / calibration['temperature'], -50, 50))))
    response = {'timestamp': datetime.now(timezone.utc).isoformat(),
                'latency_ms': (time.perf_counter() - started) * 1000,
                'prediction': 'FAIL' if probability > .5 else 'PASS',
                'confidence': probability, 'kicker_signal': int(probability > .90)}
    print(json.dumps(response) if args.output_json else response['prediction'])


if __name__ == '__main__':
    main()
