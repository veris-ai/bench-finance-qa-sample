"""Fetch a world's blobs from a Hugging Face dataset into its blob store, then check
them against the snapshot's manifest. Run once, by the world image's build (the
Veris Bench Harbor exporter mounts it into that step; it is not in the image).

    python harbor_fetch_blobs.py ORG/NAME <environment_id> [--revision SHA]

Every blob the manifest lists must be at `<root>/<environment_id>/<sha256>` with its
recorded size (sizes, not digests: a corpus is many GB); otherwise the build fails,
naming the first missing ones, so a failed or empty download is never cached as a
good layer.
"""

import argparse
import json
import sys
from pathlib import Path

SHOWN = 5


def missing_blobs(root: Path, environment_id: str, manifest: Path) -> tuple[list[str], int]:
    """The manifest's digests absent from the store or at the wrong size, and its count."""
    listed = (json.loads(manifest.read_text()).get("blobs") or {}).get("blobs") or []
    bad = []
    for blob in listed:
        path = root / environment_id / blob["sha256"]
        if not path.is_file() or path.stat().st_size != int(blob["size"]):
            bad.append(blob["sha256"])
    return bad, len(listed)


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("dataset")
    p.add_argument("environment_id")
    p.add_argument("--revision")
    p.add_argument("--root", type=Path, default=Path("/veris/blobs"))
    p.add_argument("--manifest", type=Path, default=Path("/baseline/revision.json"))
    args = p.parse_args(argv)
    from huggingface_hub import snapshot_download

    snapshot_download(
        args.dataset,
        repo_type="dataset",
        revision=args.revision,
        local_dir=args.root,
        allow_patterns=[f"{args.environment_id}/*"],
    )
    bad, total = missing_blobs(args.root, args.environment_id, args.manifest)
    if bad:
        shown = ", ".join(bad[:SHOWN]) + (", …" if len(bad) > SHOWN else "")
        print(
            f"{len(bad)} of {total} blobs missing or the wrong size under "
            f"{args.root / args.environment_id} after fetching {args.dataset}"
            f"@{args.revision or 'head'}: {shown}",
            file=sys.stderr,
        )
        return 1
    print(f"{total} blobs fetched from {args.dataset} and checked")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
