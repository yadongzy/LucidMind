"""Create and verify recoverable snapshots for the safe-refactor rollout."""

from __future__ import annotations

import argparse
import hashlib
import json
import tarfile
import tempfile
import time
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_snapshot(project: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    snapshot = destination / f"lucidmind-data-{stamp}"
    snapshot.mkdir()
    archive = snapshot / "data.tar.gz"
    with tarfile.open(archive, "w:gz") as bundle:
        bundle.add(project / "data", arcname="data", recursive=True)
    manifest = {
        "format_version": 1,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": str((project / "data").resolve()),
        "archive": archive.name,
        "size_bytes": archive.stat().st_size,
        "sha256": sha256(archive),
    }
    (snapshot / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return snapshot


def verify_snapshot(snapshot: Path) -> dict:
    manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
    archive = snapshot / manifest["archive"]
    actual = sha256(archive)
    if actual != manifest["sha256"]:
        raise ValueError("snapshot checksum mismatch")
    with tempfile.TemporaryDirectory(prefix="lucidmind-restore-") as tmp:
        restore_root = Path(tmp)
        with tarfile.open(archive, "r:gz") as bundle:
            bundle.extractall(restore_root, filter="data")
        restored = restore_root / "data"
        files = [path for path in restored.rglob("*") if path.is_file()]
        if not restored.is_dir() or not files:
            raise ValueError("restored snapshot contains no data files")
        return {
            "verified": True,
            "archive_sha256": actual,
            "restored_files": len(files),
            "restored_bytes": sum(path.stat().st_size for path in files),
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("create", "verify"))
    parser.add_argument("path", type=Path, help="backup destination or snapshot directory")
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    if args.command == "create":
        snapshot = create_snapshot(args.project.resolve(), args.path.resolve())
        result = {"snapshot": str(snapshot), **verify_snapshot(snapshot)}
    else:
        result = verify_snapshot(args.path.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
