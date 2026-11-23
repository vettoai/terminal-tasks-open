import hashlib
import io
import tempfile
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path

import numpy as np
import pydicom


BASE_URL = "https://s3.ap-south-1.amazonaws.com/qure.headct.study/"


def download(url, destination, expected_hash=None):
    for attempt in range(3):
        hasher = hashlib.sha256()
        try:
            with urllib.request.urlopen(url, timeout=120) as response, Path(destination).open("wb") as output:
                while block := response.read(1024 * 1024):
                    hasher.update(block)
                    output.write(block)
            break
        except (OSError, TimeoutError):
            if attempt == 2:
                raise
    actual = hasher.hexdigest()
    if expected_hash is not None and actual != expected_hash:
        raise ValueError(f"Source fingerprint differs: {url}")
    return actual


def validate_volume(datasets):
    first = datasets[0]
    orientation = np.array(first.ImageOrientationPatient, dtype=float)
    normal = np.cross(orientation[:3], orientation[3:])
    positions = np.array([np.dot(np.array(dataset.ImagePositionPatient, dtype=float), normal) for dataset in datasets])
    if len(np.unique(np.round(positions, 4))) != len(datasets):
        raise ValueError("Repeated axial positions")
    if not 70 <= positions[-1] - positions[0] <= 250:
        raise ValueError("Unsuitable axial coverage")
    if np.max(np.diff(positions)) > float(first.SliceThickness) * 1.25:
        raise ValueError("Axial volume has missing planes")
    if any(str(dataset.SeriesInstanceUID) != str(first.SeriesInstanceUID)
           or dataset.Rows != first.Rows or dataset.Columns != first.Columns
           or not np.allclose(np.array(dataset.PixelSpacing, dtype=float), np.array(first.PixelSpacing, dtype=float))
           for dataset in datasets):
        raise ValueError("Inconsistent native axial grid")


def read_archive(path, series_uid=None):
    with zipfile.ZipFile(path) as archive:
        directories = defaultdict(list)
        for name in archive.namelist():
            if name.lower().endswith(".dcm"):
                directories[name.rsplit("/", 1)[0]].append(name)
        candidates = []
        for directory, names in sorted(directories.items()):
            first = pydicom.dcmread(io.BytesIO(archive.read(sorted(names)[0])), stop_before_pixels=True)
            if series_uid is not None:
                if str(first.SeriesInstanceUID) == series_uid:
                    candidates = [(0, directory, names, first)]
                    break
                continue
            description = str(first.get("SeriesDescription", "")).upper()
            kernel = str(first.get("ConvolutionKernel", "")).upper()
            thickness = float(first.get("SliceThickness", 0))
            orientation = np.array(first.get("ImageOrientationPatient", [0] * 6), dtype=float)
            normal = np.cross(orientation[:3], orientation[3:])
            if not 25 <= len(names) <= 60 or not 2.5 <= thickness <= 5.5:
                continue
            if abs(normal[2]) < 0.95 or first.Rows != 512 or first.Columns != 512:
                continue
            if any(word in description + " " + kernel for word in ("BONE", "THIN", "POST", "ANGIO")):
                continue
            rank = int(not any(word in kernel for word in ("STANDARD", "SOFT", "H30", "H31", "J40")))
            candidates.append((rank, directory, names, first))
        if not candidates:
            raise ValueError("No complete routine axial volume")
        _, directory, names, first = min(candidates, key=lambda item: (item[0], item[1]))
        datasets = [pydicom.dcmread(io.BytesIO(archive.read(name))) for name in names]
    orientation = np.array(first.ImageOrientationPatient, dtype=float)
    normal = np.cross(orientation[:3], orientation[3:])
    datasets.sort(key=lambda dataset: float(np.dot(np.array(dataset.ImagePositionPatient, dtype=float), normal)))
    validate_volume(datasets)
    arrays = [dataset.pixel_array for dataset in datasets]
    return datasets, np.stack(arrays), directory


def load_source(entry, cache=None):
    if cache is not None:
        cached = Path(cache) / f"case-{entry['case']}.npz"
        if cached.exists():
            import json
            with np.load(cached) as saved:
                datasets = [pydicom.Dataset.from_json(item) for item in json.loads(saved["metadata"].tobytes())]
                validate_volume(datasets)
                return datasets, saved["pixels"].copy()
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "source.zip"
        download(entry["url"], path, entry["sha256"])
        datasets, arrays, _ = read_archive(path, entry["series_uid"])
        return datasets, arrays
