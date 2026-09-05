"""Private Kaggle entrypoint. Refuse non-T4x2; never carries account credentials."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile
import torch


def main():
    names = [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())]
    print(json.dumps({"allocated_gpus": names, "torch": torch.__version__}), flush=True)
    if len(names) != 2 or not all("T4" in name for name in names):
        raise RuntimeError(f"This experiment requires exactly T4 x2, got {names}")
    input_root = Path("/kaggle/input")
    archives = list(input_root.rglob("alpha-lab-bundle.zip"))
    if len(archives) == 1:
        bundle = Path(tempfile.mkdtemp(prefix="alpha-lab-"))
        with zipfile.ZipFile(archives[0]) as archive:
            for entry in archive.infolist():
                target = (bundle / entry.filename).resolve()
                if not target.is_relative_to(bundle.resolve()):
                    raise ValueError("Unsafe ZIP path")
            archive.extractall(bundle)
    else:
        # Kaggle sometimes expands ZIPs while processing a dataset version.
        manifests = list(input_root.rglob("bundle-hashes.json"))
        if len(manifests) != 1:
            raise RuntimeError("Expected exactly one attached Alpha Lab bundle")
        bundle = manifests[0].parent
    hashes = json.loads((bundle / "bundle-hashes.json").read_text())
    for name, digest in hashes.items():
        path = (bundle / name).resolve()
        if not path.is_relative_to(bundle.resolve()):
            raise ValueError("Unsafe manifest path")
        with path.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != digest:
                raise ValueError(f"Bundle hash mismatch: {name}")
    # Keep the Kaggle CUDA/PyTorch and numpy/pandas runtime intact.
    subprocess.run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
                    "einops==0.8.1", "huggingface_hub==0.33.1", "safetensors==0.6.2", "pyarrow>=18,<24"], check=True)
    env = dict(os.environ, PYTHONPATH=str(bundle / "src"), PYTHONUNBUFFERED="1",
               HF_HUB_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1")
    output = Path("/kaggle/working/checkpoint")
    config = json.loads((bundle / "dataset/config.json").read_text())
    if config["schema"] in {"kronos-base-swing-v2", "kronos-base-swing-v5"}:
        driver = "train_swing_v5.py" if config["schema"] == "kronos-base-swing-v5" else "train_swing.py"
        command = [sys.executable, "-m", "torch.distributed.run", "--standalone", "--nproc_per_node=2", str(bundle / "scripts" / driver)]
    else:
        command = [sys.executable, str(bundle / "scripts/train_kronos_trading.py")]
    subprocess.run([*command,
                    "--dataset", str(bundle / "dataset"), "--upstream", str(bundle / "upstream"),
                    "--weights", str(bundle / "weights"), "--output", str(output), "--require-two-t4"],
                   check=True, env=env)
    shutil.copy2(bundle / "bundle-hashes.json", output / "bundle-hashes.json")
    shutil.make_archive("/kaggle/working/kronos-btc-checkpoint", "zip", output)
    print("TRAINING_COMPLETE: /kaggle/working/kronos-btc-checkpoint.zip", flush=True)


if __name__ == "__main__":
    main()
