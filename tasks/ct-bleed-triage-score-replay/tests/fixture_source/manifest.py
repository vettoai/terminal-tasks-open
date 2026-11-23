import hashlib
import json
from pathlib import Path


root = Path("/pristine")
files = [root / "model" / "ich_lite.onnx", *sorted((root / "sites").rglob("*.dcm"))]
manifest = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in files}
(root / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
