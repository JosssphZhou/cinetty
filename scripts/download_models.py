"""Download the two models into ./models (never into ~/.cache/huggingface).

  RT-DETR  PekingU/rtdetr_r50vd        Apache-2.0   object detection
  SAM 2.1  facebook/sam2.1-hiera-tiny  Apache-2.0   box-prompted segmentation
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"
os.environ["HF_HOME"] = str(MODELS / ".hf")          # keep downloads inside the repository
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

from huggingface_hub import snapshot_download  # noqa: E402

REPOS = {"rtdetr_r50vd": "PekingU/rtdetr_r50vd", "sam2.1-hiera-tiny": "facebook/sam2.1-hiera-tiny"}
PATTERNS = ["*.json", "*.safetensors", "*.txt", "*.md"]

for name, repo in REPOS.items():
    dest = MODELS / name
    if (dest / "config.json").exists() and any(dest.glob("*.safetensors")):
        print(f"[setup] {repo}: already in models/{name}")
        continue
    print(f"[setup] downloading {repo} -> models/{name}")
    snapshot_download(repo, local_dir=dest, allow_patterns=PATTERNS)
print("[setup] models ready")
