import argparse
import csv
from pathlib import Path
import tempfile

import numpy as np
from PIL import Image
import torch
from torch import nn

from frame_model import CompositePool, image_score, make_network, prepare


def load_split(root, split):
    with (root / 'annotations.csv').open() as handle:
        labels = {row['image_id']: int(row['label']) for row in csv.DictReader(handle)}
    paths = sorted((root / split).glob('*.jpg'))
    images = np.stack([np.asarray(Image.open(path).convert('RGB')) for path in paths])
    return images, np.asarray([labels[path.stem] for path in paths])


def feature_cache(stem, pool, count, seed, destination):
    generator = np.random.default_rng(seed)
    targets = np.arange(count) % 2
    generator.shuffle(targets)
    features = np.memmap(destination, mode='w+', dtype=np.float16, shape=(count, 1024, 24, 32))
    for start in range(0, count, 8):
        stop = min(start + 8, count)
        images = np.stack([pool.frame(generator, int(target)) for target in targets[start:stop]])
        with torch.inference_mode():
            features[start:stop] = stem(prepare(images)).numpy().astype(np.float16)
        if start % 200 == 0:
            print('Training features', start, '/', count, flush=True)
    features.flush()
    return features, torch.from_numpy(targets).long()


def calibrate(scores, targets):
    candidates = []
    for temperature in [.15, .25, .4, .6, .8, 1.0, 1.5]:
        for offset in np.arange(-6, 10.01, .25):
            probabilities = 1 / (1 + np.exp(-np.clip((scores - offset) / temperature, -50, 50)))
            accuracy = np.mean((probabilities > .5) == targets)
            decisive = np.mean((probabilities < .1) | (probabilities > .9))
            false_kicks = np.mean(probabilities[targets == 0] > .9)
            cracked_kicks = np.mean(probabilities[targets == 1] > .9)
            margin = min(accuracy / .96, decisive / .90, cracked_kicks / .85,
                         .03 / max(false_kicks, .001))
            candidates.append((margin, accuracy, decisive, -false_kicks, cracked_kicks,
                               temperature, float(offset)))
    return max(candidates)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=Path, default=Path('/opt/ml/data'))
    parser.add_argument('--initialize', default='/opt/ml/resnet50_init.pt')
    parser.add_argument('--output', default='/opt/vision/model.pt')
    parser.add_argument('--work', type=Path)
    parser.add_argument('--frames', type=int, default=3600)
    parser.add_argument('--epochs', type=int, default=6)
    parser.add_argument('--calibration', type=int, default=160)
    parser.add_argument('--threads', type=int, default=8)
    parser.add_argument('--calibrate-only', action='store_true')
    args = parser.parse_args()
    torch.manual_seed(21)
    torch.set_num_threads(args.threads)
    torch.use_deterministic_algorithms(True)
    network = make_network()
    initial = torch.load(args.initialize, map_location='cpu', weights_only=True)
    network.load_state_dict({name: value for name, value in initial.get('state_dict', initial).items()
                             if not name.startswith('fc.')}, strict=False)
    network.eval()
    stem = nn.Sequential(network.conv1, network.bn1, network.relu, network.maxpool,
                         network.layer1, network.layer2, network.layer3)
    for parameter in stem.parameters():
        parameter.requires_grad = False
    if args.calibrate_only:
        network.load_state_dict(torch.load(args.output, map_location='cpu', weights_only=True)['state_dict'])
    else:
        images, labels = load_split(args.data, 'train')
        pool = CompositePool(images, labels)
        with tempfile.TemporaryDirectory(dir=args.work) as directory:
            features, targets = feature_cache(stem, pool, args.frames, 72141, Path(directory) / 'features.bin')
            head = nn.Sequential(network.layer4, network.avgpool, nn.Flatten(), network.fc)
            optimizer = torch.optim.AdamW([
                {'params': network.layer4.parameters(), 'lr': 2e-4},
                {'params': network.fc.parameters(), 'lr': 1e-3}], weight_decay=1e-4)
            steps = args.epochs * ((args.frames + 15) // 16)
            scheduler = torch.optim.lr_scheduler.OneCycleLR(optimizer, max_lr=[2e-4, 1e-3],
                                                           total_steps=steps, pct_start=.1)
            for epoch in range(args.epochs):
                head.eval()
                permutation = torch.randperm(args.frames)
                total_loss = 0.0
                for start in range(0, args.frames, 16):
                    indices = permutation[start:start + 16]
                    batch = torch.from_numpy(np.array(features[indices.numpy()], dtype=np.float32))
                    if torch.rand(1).item() < .5:
                        batch = torch.flip(batch, [3])
                    if torch.rand(1).item() < .5:
                        batch = torch.flip(batch, [2])
                    loss = nn.functional.cross_entropy(head(batch), targets[indices])
                    optimizer.zero_grad()
                    loss.backward()
                    optimizer.step()
                    scheduler.step()
                    total_loss += loss.item() * len(indices)
                print('Epoch', epoch + 1, 'loss', total_loss / args.frames, flush=True)
                torch.save({'state_dict': network.state_dict(), 'calibration': {}}, args.output)
        del features, images, pool
    network.eval()
    images, labels = load_split(args.data, 'holdout')
    calibration_pool = CompositePool(images[::2], labels[::2])
    validation_pool = CompositePool(images[1::2], labels[1::2])
    calibration = {}
    for width, height in [(512, 384), (1024, 768)]:
        generator = np.random.default_rng(38971 + width)
        targets = np.arange(args.calibration) % 2
        scores = np.asarray([image_score(network, calibration_pool.frame(generator, int(target), width, height))
                             for target in targets])
        chosen = calibrate(scores, targets)
        calibration[f'{width}x{height}'] = {'temperature': chosen[-2], 'offset': chosen[-1]}
        print('Public frame calibration', width, height, chosen, flush=True)
        validation_scores = np.asarray([image_score(network, validation_pool.frame(generator, int(target), width, height))
                                        for target in targets])
        probabilities = 1 / (1 + np.exp(-np.clip((validation_scores - chosen[-1]) / chosen[-2], -50, 50)))
        print('Disjoint public validation', width, height,
              'correct', int(np.sum((probabilities > .5) == targets)), '/', len(targets),
              'decisive', int(np.sum((probabilities < .1) | (probabilities > .9))),
              'good kicks', int(np.sum(probabilities[targets == 0] > .9)),
              'cracked kicks', int(np.sum(probabilities[targets == 1] > .9)), flush=True)
        torch.save({'state_dict': network.state_dict(), 'calibration': calibration}, args.output)


if __name__ == '__main__':
    main()
