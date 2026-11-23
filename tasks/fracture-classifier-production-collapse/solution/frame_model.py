import io

import numpy as np
from PIL import Image
import torch
from torch import nn
from torchvision import models


def make_network():
    network = models.resnet50(weights=None)
    network.fc = nn.Linear(network.fc.in_features, 2)
    return network


def prepare(images):
    tensor = torch.from_numpy(np.ascontiguousarray(images)).permute(0, 3, 1, 2).float() / 255
    mean = torch.tensor([.485, .456, .406]).view(1, 3, 1, 1)
    deviation = torch.tensor([.229, .224, .225]).view(1, 3, 1, 1)
    return (tensor - mean) / deviation


def noise_level(image):
    gray = image.astype(np.float32).mean(2)
    residual = (4 * gray[1:-1, 1:-1] - gray[:-2, 1:-1] - gray[2:, 1:-1]
                - gray[1:-1, :-2] - gray[1:-1, 2:]) / np.sqrt(20)
    return 1.4826 * np.median(np.abs(residual - np.median(residual)))


class CompositePool:
    def __init__(self, images, labels):
        self.images = images
        self.levels = np.asarray([noise_level(image) for image in images])
        brightness = images.reshape(len(images), -1).mean(1)
        self.groups = {}
        for target in [0, 1]:
            indices = np.flatnonzero(labels == target)
            indices = indices[np.argsort(brightness[indices])]
            self.groups[target] = (indices, brightness[indices])

    def pick(self, generator, target, brightness, noise):
        indices, means = self.groups[target]
        location = np.searchsorted(means, brightness)
        lower = max(0, location - 250)
        upper = min(len(indices), max(lower + 1, location + 250))
        candidates = indices[lower:upper]
        acceptable = candidates[self.levels[candidates] <= noise + .1]
        if len(acceptable) < 5:
            acceptable = candidates[np.argsort(self.levels[candidates])[:20]]
        return int(generator.choice(acceptable))

    def frame(self, generator, target, width=512, height=384):
        target_noise = generator.uniform(.6, 2.8)
        correlation = generator.uniform(0, .9)
        factor = np.sqrt(correlation + (1 - correlation) / 3)
        brightness = self.images[generator.choice(self.groups[0][0])].mean()
        rows, columns = height // 128, width // 128
        positive = int(generator.integers(rows * columns)) if target else -1
        frame = np.empty((height, width, 3), np.float32)
        for index in range(rows * columns):
            source = self.pick(generator, int(index == positive), brightness, target_noise)
            tile = self.images[source]
            tile = np.rot90(tile, int(generator.integers(4)))
            if generator.random() < .5:
                tile = tile[:, ::-1]
            amplitude = np.sqrt(max(target_noise ** 2 - self.levels[source] ** 2, 0)) / factor
            tile = tile.astype(np.float32) + amplitude * (
                np.sqrt(correlation) * generator.normal(size=(128, 128, 1))
                + np.sqrt(1 - correlation) * generator.normal(size=(128, 128, 3)))
            row, column = divmod(index, columns)
            frame[row * 128:(row + 1) * 128, column * 128:(column + 1) * 128] = tile
        frame = np.roll(frame, (int(generator.integers(128)), int(generator.integers(128))), axis=(0, 1))
        frame = frame * generator.uniform(.9, 1.1) + generator.uniform(-10, 10)
        stream = io.BytesIO()
        Image.fromarray(np.clip(frame, 0, 255).round().astype(np.uint8)).save(
            stream, 'JPEG', quality=97, subsampling=0)
        stream.seek(0)
        return np.asarray(Image.open(stream).convert('RGB'))



def image_score(network, image):
    with torch.inference_mode():
        features = prepare(image[None])
        features = network.maxpool(network.relu(network.bn1(network.conv1(features))))
        features = network.layer4(network.layer3(network.layer2(network.layer1(features))))
        height = min(12, features.shape[2])
        width = min(16, features.shape[3])
        pooled = torch.nn.functional.avg_pool2d(features, (height, width),
                                               stride=(max(1, height // 2), max(1, width // 2)))
        logits = network.fc(pooled.permute(0, 2, 3, 1).reshape(-1, 2048))
    return float((logits[:, 1] - logits[:, 0]).max())
