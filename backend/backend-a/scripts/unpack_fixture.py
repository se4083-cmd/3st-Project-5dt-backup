"""Safely extract the supplied archive locally; do not run its scripts or SQL."""

import argparse
import hashlib
import zipfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("zip_path", type=Path)
    parser.add_argument("--dest", type=Path, default=Path("reference/fixture"))
    args = parser.parse_args()
    root = args.dest.resolve()
    with zipfile.ZipFile(args.zip_path) as archive:
        members = []
        for info in archive.infolist():
            path = (root / info.filename).resolve()
            if not path.is_relative_to(root) or info.file_size > 100_000_000:
                raise ValueError("Unsafe archive member")
            if not info.is_dir() and path.exists():
                raise FileExistsError("Destination contains files; use a fresh directory")
            members.append((info, path))
        if sum(i.file_size for i, _ in members) > 200_000_000:
            raise ValueError("Archive exceeds the fixture size limit")
        for info, path in members:
            if info.is_dir():
                path.mkdir(parents=True, exist_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(archive.read(info))
    print("Extracted source SHA256:", hashlib.sha256(args.zip_path.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
