from __future__ import annotations

import argparse
from pathlib import Path

from huggingface_hub import snapshot_download


REPOSITORIES = {
    "mini": ["Kronos-Tokenizer-2k", "Kronos-mini"],
    "small": ["Kronos-Tokenizer-base", "Kronos-small"],
    "base": ["Kronos-Tokenizer-base", "Kronos-base"],
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Download official Kronos artifacts without Windows cache symlinks")
    parser.add_argument("--variants", nargs="+", choices=sorted(REPOSITORIES), default=sorted(REPOSITORIES))
    parser.add_argument("--output-root", type=Path, default=Path("artifacts/models"))
    args = parser.parse_args()

    names: list[str] = []
    for variant in args.variants:
        names.extend(REPOSITORIES[variant])
    for name in dict.fromkeys(names):
        destination = args.output_root / name
        path = snapshot_download(repo_id=f"NeoQuasar/{name}", local_dir=destination)
        print(path)


if __name__ == "__main__":
    main()

