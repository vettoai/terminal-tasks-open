import argparse
import sys

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, Subset
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from torchvision import models


def fit_readout(network, dataset, direction_c, scale_c, workers):
    network.eval()
    input_features = network.fc.in_features
    network.fc = nn.Identity()
    features, targets = [], []
    with torch.inference_mode():
        for images, labels in DataLoader(dataset, batch_size=32, num_workers=workers):
            features.append(network(images).numpy())
            targets.extend(labels.tolist())
    features = np.concatenate(features)
    scaler = StandardScaler()
    standardized = scaler.fit_transform(features)
    direction = LogisticRegression(C=direction_c, class_weight="balanced", solver="lbfgs",
                                   max_iter=1000, tol=1e-10, random_state=68143)
    direction.fit(standardized, targets)
    scores = direction.decision_function(standardized)
    score_scale = scores.std()
    calibration = LogisticRegression(C=scale_c, fit_intercept=False, class_weight="balanced",
                                     solver="lbfgs", max_iter=1000, tol=1e-10, random_state=68143)
    calibration.fit((scores / score_scale).reshape(-1, 1), targets)
    multiplier = calibration.coef_[0, 0] / score_scale
    coefficients = multiplier * direction.coef_[0] / scaler.scale_
    intercept = multiplier * direction.intercept_[0] - np.dot(coefficients, scaler.mean_)
    network.fc = nn.Linear(input_features, 2)
    with torch.no_grad():
        network.fc.weight.copy_(torch.tensor(np.stack([-coefficients / 2, coefficients / 2]), dtype=torch.float32))
        network.fc.bias.copy_(torch.tensor([-intercept / 2, intercept / 2], dtype=torch.float32))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-samples", type=int, default=8192)
    parser.add_argument("--direction-c", type=float, default=1.0)
    parser.add_argument("--scale-c", type=float, default=0.000001)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--workers", type=int, default=4)
    options = parser.parse_args()
    sys.path.insert(0, "/opt/ml")
    from train import InspectionImages, save_model
    torch.manual_seed(68143)
    torch.set_num_threads(options.threads)
    torch.use_deterministic_algorithms(True)
    network = models.resnet50(weights=None)
    network.fc = nn.Linear(network.fc.in_features, 2)
    network.load_state_dict(torch.load(options.output, map_location="cpu", weights_only=True)["state_dict"])
    dataset = InspectionImages(options.data, "train", False)
    indices = torch.randperm(len(dataset), generator=torch.Generator().manual_seed(72157))[:options.max_samples]
    fit_readout(network, Subset(dataset, indices.tolist()), options.direction_c, options.scale_c, options.workers)
    save_model(network, options.output)


if __name__ == "__main__":
    main()
